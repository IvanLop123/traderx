"""Bounded forward comparison collection and source-derived qualification.

Read-only market data is shared across isolated study books. There is no broker or LLM.
"""
import asyncio,math
from collections import Counter,defaultdict
from datetime import timedelta
import numpy as np
import pandas as pd
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.research.strategies import predict
from backend.selection.policy import PortfolioPolicy,GROUPS
from backend.selection.opportunities import score_opportunity
from backend.qualification.books import ComparisonBook
from backend.qualification.diagnostics import refresh_diagnostics
from backend.qualification.evaluation import evaluate,comparison
from backend.qualification.studies import register,audit
from backend.qualification.integrity import implementation_hash,quarantined

class QualificationEngine:
    def __init__(self,db,providers=None):self.db=db;self.providers=providers;self.lock=asyncio.Lock();self.books={}
    def activate(self):
        registry=self.db.setting('selection_registry');snapshot=self.db.setting('model_opportunities',{})
        if not registry or not snapshot.get('rows'):raise ValueError('Saved registry and research snapshot required')
        from backend.product.market import ProductMarket
        assets=ProductMarket(self.db).forecasts();
        if not self.db.setting('qualification_audit'):audit(self.db,registry)
        definitions=register(self.db,registry,assets);by=defaultdict(list)
        for d in definitions:by[d['asset_class']].append(d)
        active=[]
        for asset_class,items in by.items():
            rid='qportfolio_'+stable_hash(sorted(d['id'] for d in items))
            d=items[0];definition={'id':rid,'asset_class':asset_class,'registered_at':now().isoformat(),'implementation_hash':implementation_hash(),'model_ids':[i['model_id'] for i in items],'model_hashes':{i['model_id']:i['model_hash'] for i in items},'qualification_ids':[i['id'] for i in items],'criteria':d['criteria'],'criteria_hash':d['criteria_hash'],'risk_policy':d['risk_policy'],'risk_hash':d['risk_hash'],'universe':d['universe'],'buy_hold_symbol':d['sentinels'][0] if d['sentinels'] else None,'incumbent_ids':d['incumbent_ids'],'incumbent_hashes':{mid:stable_hash(self.db.get(mid)['payload']) for mid in d['incumbent_ids']},'benchmark_rule':'Separate real-quote books; buy-and-hold uses the frozen most-liquid sentinel, equal weight attempts every eligible member; failed/unavailable executions retain cash. No unconstrained frictionless index substitution.','meta_rule':'ensemble-v1 canonical family grouping, dynamic shrinkage, two groups minimum and 50% group cap. The implementation hash freezes this algorithm. Provisional study votes do not confer Model Paper eligibility.'}
            self.db.put('qualification_portfolio',definition,record_id=rid);active.append(rid)
        self.db.set_setting('qualification_active_portfolios',active);self.db.set_setting('qualification_active',True);refresh_diagnostics(self.db);return {'definitions':len(definitions),'portfolio_comparisons':len(by)}
    def contexts(self,definition,snapshot,at,incumbent=False):
        models={mid:self.db.get(mid)['payload'] for mid in (definition.get('incumbent_ids',[]) if incumbent else definition['model_ids']) if self.db.get(mid)};assets=snapshot.get('assets',{});result={};p=PortfolioPolicy(**definition['risk_policy'])
        current_implementation=implementation_hash()
        for original in snapshot.get('rows',[]):
            symbol=original['symbol']
            if symbol not in definition['universe']:continue
            a=assets.get(symbol,{});raw={k:v for vote in original.get('votes',[]) for k,v in vote.get('features',{}).items()};votes=[];health=list(original.get('health',[]));date=original.get('feature_available_at')
            if not date or not 0<=(pd.Timestamp(at)-pd.Timestamp(date)).total_seconds()<=p.maximum_data_age_days*86400:health.append('Stale required feature data')
            if definition.get('implementation_hash')!=current_implementation:health.append('Frozen qualification implementation changed')
            for mid,m in models.items():
                issues=[]
                for vote in original.get('votes',[]):
                    if vote.get('model_id')==mid:issues.extend(vote.get('health',[]))
                values=np.asarray([raw.get(c,np.nan) if raw.get(c) is not None else np.nan for c in m['columns']],dtype=float)
                if not np.isfinite(values).all():issues.append('Required feature missing/schema invalid')
                z=(values-np.asarray(m['mean']))/np.maximum(m['scale'],1e-12)
                if np.nanmax(abs(z),initial=0)>p.maximum_feature_z:issues.append('Extreme frozen-model features')
                if (definition.get('incumbent_hashes',{}) if incumbent else definition['model_hashes']).get(mid)!=stable_hash(m):issues.append('Frozen model changed')
                expected,prob=predict(m,pd.DataFrame([raw],dtype=float));edge=float(expected[0]);prob=float(prob[0]);unc=float(m['uncertainty'])
                if not all(math.isfinite(v) for v in [edge,prob,unc]) or abs(edge)>1 or unc<=0:issues.append('Invalid prediction');edge=0.;prob=.5;unc=1.
                prior=next((v for v in original.get('votes',[]) if v.get('model_id')==mid),{})
                votes.append({**{k:prior.get(k) for k in ['historical_reliability','forward_reliability','forward_calibration_error','conditional'] if prior.get(k) is not None},'horizon':m.get('horizon',5),'model_id':mid,'artifact_hash':stable_hash(m),'family':m['family'],'group':GROUPS.get(m['family'],'mixed_price_research'),'prediction_after_cost':edge,'probability':prob,'uncertainty':unc,'weight':0. if issues else 1.,'health':issues,'features':{k:raw.get(k) for k in m['columns']},'study_weight_only':True})
            row=pd.Series({'date':date or at,'cost':original.get('estimated_roundtrip_cost') or .011,'realized_volatility':original.get('daily_volatility') or np.nan});asset={**a,**{k:original.get(k) for k in ['symbol','asset_class','sector','regime','liquidity_bucket','market_cap_bucket']}}
            c=score_opportunity(asset,row,votes,health,p,snapshot.get('correlation',{}));from backend.ensemble.engine import candidate
            c=candidate(c,asset,at=at)
            c.update(return_20=raw.get('return_20',0) or 0,rsi=raw.get('rsi',100) if raw.get('rsi') is not None else 100,qualification_study_only=True);result[symbol]=c
        return result
    async def cycle(self):
        if not self.db.setting('qualification_active',False):return
        async with self.lock:
            at=now();snapshot=self.db.setting('model_opportunities',{});definitions=[r['payload'] for r in self.db.records('qualification_portfolio',limit=None) if r['id'] in self.db.setting('qualification_active_portfolios',[r['id']])]
            if not snapshot.get('rows'):return
            symbols=sorted({s for d in definitions for s in d['universe']});urgent=[]
            for d in definitions:
                for arm in ['candidate',*d['criteria']['benchmark_arms']]:
                    book=self.book(d,arm)
                    view=book.paper.view();urgent.extend(o['symbol'] for o in view['orders'] if o['status'] in ('OPEN','PARTIALLY_FILLED'))
                    if arm in ('candidate','incumbent'):urgent.extend(p['symbol'] for p in view['positions'])
            cursor=self.db.setting('qualification_quote_cursor',0);rotated=symbols[cursor:]+symbols[:cursor];chosen=list(dict.fromkeys(urgent+rotated))[:12];quotes={}
            for s in chosen:
                try:q=await self.providers.forward_quote(s)
                except Exception:q={}
                if q:
                    quotes[s]=q;self.db.put('qualification_quote',{'quote':q,'observed_at':at.isoformat(),'scope':'forward','source':'read_only_provider'},s,record_id='qquote_'+stable_hash([s,q.get('timestamp'),q]))
            if symbols:self.db.set_setting('qualification_quote_cursor',(cursor+max(1,12-len(set(urgent))))%len(symbols))
            for d in definitions:
                contexts=await asyncio.to_thread(self.contexts,d,snapshot,at);incumbent=await asyncio.to_thread(self.contexts,d,snapshot,at,True) if d['incumbent_ids'] else contexts
                for arm in ['candidate',*d['criteria']['benchmark_arms']]:await asyncio.to_thread(self.book(d,arm).step,at,quotes,incumbent if arm=='incumbent' else contexts,snapshot['assets'],snapshot.get('correlation',{}))
            last=self.db.setting('qualification_evaluated_at','')
            if not last or (pd.Timestamp(at)-pd.Timestamp(last)).total_seconds()>=3600:await asyncio.to_thread(self.review);self.db.set_setting('qualification_evaluated_at',at.isoformat())
            self.db.set_setting('qualification_worker',{'status':'RUNNING','last_cycle':at.isoformat(),'quote_requests':len(chosen),'external_execution':False})
    def book(self,d,arm):
        key=(d['id'],arm)
        if key not in self.books:self.books[key]=ComparisonBook(self.db,d,arm)
        return self.books[key]
    def review(self):
        result=[];portfolios=[r['payload'] for r in self.db.records('qualification_portfolio',limit=None) if r['id'] in self.db.setting('qualification_active_portfolios',[r['id']])];definitions={r['id']:r['payload'] for r in self.db.records('qualification_definition',limit=None)}
        for p in portfolios:
            alpha=p['criteria']['familywise_alpha']/max(1,sum(len(x['qualification_ids']) for x in portfolios)*(len(p['criteria']['benchmark_arms'])+4));comp=comparison(self.db,p['id'],p['criteria'],alpha)
            self.db.set_setting('qcomparison_'+stable_hash(p['id'])[:32],comp)
            for did in p['qualification_ids']:
                d=definitions[did];status=evaluate(self.db,d,comp);enroll=self.db.get(did+'_enrollment');ids=set(enroll['payload']['study_ids'] if enroll else []);decisions=[r['payload'] for r in self.db.records('forward_decision',limit=None) if r['payload'].get('study_id') in ids and r['payload'].get('decided_at','')>=d['registered_at']];outcomes=[r['payload'] for r in self.db.records('qualification_sample',limit=None) if r['payload'].get('definition_id')==did];fills=[r for r in self.db.records('forward_fill',limit=None) if r['payload'].get('study_id') in ids and r['payload'].get('at','')>=d['registered_at']]
                votes=[vote for row in self.db.setting('model_opportunities',{}).get('rows',[]) for vote in row.get('votes',[]) if vote['model_id']==d['model_id']]
                health=['No healthy applicable feature snapshots'] if not votes or all(v.get('health') for v in votes) else []
                if not quarantined(self.db,d):health.append('Source cohort no longer quarantined for evaluation')
                if status.get('monitoring',{}).get('suspended'):health.append('Recent independent return or calibration degradation')
                if status.get('suspended_reason'):health.append(status['suspended_reason'])
                if self.db.setting('qreleased_'+stable_hash(did)[:32]):health.append('Evaluation cohort released for future training; qualification revoked')
                status.update(days_observed=len({r['decided_at'][:10] for r in decisions}),elapsed_calendar_days=max(0,(pd.Timestamp(now())-pd.Timestamp(d['registered_at'])).days),decisions=len(decisions),no_trades=sum(r.get('decision')=='CASH' for r in decisions),fills=len(fills),no_fills=sum(r.get('status')=='UNFILLED' for r in outcomes),completed_trades=sum(r.get('status')=='COMPLETED' for r in outcomes),completed_outcomes=len(outcomes),suspension_reasons=sorted(set(health)),execution_allowed=status['state']=='QUALIFIED_FOR_MODEL_PAPER' and not health,remaining_time='No reliable ETA; depends on nonoverlapping completed outcomes, market regimes and successful quote coverage. Minimum 100 holdout/forward clusters plus 60 five-date portfolio blocks.');self.db.set_setting('qstatus_'+stable_hash(d['model_id'])[:32],status);result.append(status)
        summary={'at':now().isoformat(),'rows':result,'counts':dict(Counter(r['state'] for r in result)),'worker':self.db.setting('qualification_worker',{}),'real_money_authorized':False,'evidence_policy':'quarantined_evaluation'};self.db.set_setting('qualification_status',summary);refresh_diagnostics(self.db);return summary
