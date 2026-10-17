from backend.intelligence.news import live_governance
"""Local feature monitoring, dependence-aware votes and decomposed opportunity ranking."""
from collections import defaultdict
import math
import numpy as np
import pandas as pd
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.research.strategies import make_panel,available_panel,predict
from backend.research.history import HistoryStore
from backend.selection.policy import GROUPS
from backend.selection.risk import correlation_context

class OpportunityEngine:
    def __init__(self,db):self.db=db;self.signature=None;self.panel=None;self.manifests={}
    def prepare(self,assets):
        store=HistoryStore(self.db);signature=stable_hash([(a['symbol'],(store.manifest(a['symbol']) or {}).get('id')) for a in assets])
        if self.signature!=signature:
            self.panel,self.manifests=make_panel(self.db);self.signature=signature
        return available_panel(self.panel)
    def build(self,assets,registry,p,view=None,prepared=None):
        panel=prepared if prepared is not None else self.prepare(assets);latest=panel.sort_values('date').groupby('symbol').tail(1).set_index('symbol');returns=panel.pivot_table(index='date',columns='symbol',values='return_1').tail(90);correlation=correlation_context(returns,p.minimum_correlation_observations);result=[]
        candidates=[r for r in registry['rows'] if r['source_kind']=='strategy_model' and (r.get('development_plan_current',True) or r.get('eligibility')=='eligible')];selected={}
        # One version per family/class selected ONLY by development metrics; duplicated variants gain no votes.
        for r in candidates:
            v=r.get('validation') or {};score=(v.get('mse') or 1e9)/max(v.get('zero_mse') or 1e-9,1e-9)+(v.get('brier') or 1e9)/max(v.get('base_rate_brier') or 1e-9,1e-9)
            key=(r['family'],r['asset_class'])
            if key not in selected or score<selected[key][0]:selected[key]=(score,r)
        models={r['id']:self.db.get(r['id'])['payload'] for _,r in selected.values()}
        for a in assets:
            symbol=a['symbol'];votes=[];health=[];row=latest.loc[symbol] if symbol in latest.index else None
            if row is None:health.append('No current feature row')
            elif (pd.Timestamp(now())-pd.Timestamp(row.date)).total_seconds()>p.maximum_data_age_days*86400:health.append('Stale feature data')
            if not a.get('eligibility',{}).get('eligible'):health.append('Universe eligibility failed')
            for _,r in selected.values():
                if r['asset_class']!=a.get('asset_class') or row is None:continue
                m=models[r['id']];x=row.reindex(m['columns']).astype(float);missing=x.isna();z=(x.to_numpy()-np.array(m['mean']))/np.maximum(m['scale'],1e-12);issues=[]
                if missing.any():issues.append('Required feature missing')
                if not np.isfinite(z).all():issues.append('Nonfinite feature/schema mismatch')
                if np.nanmax(np.abs(z),initial=0)>p.maximum_feature_z:issues.append('Extreme or shifted features')
                expected,prob=predict(m,row.reindex(m['columns']).astype(float).to_frame().T);edge=float(expected[0]);prob=float(prob[0]);uncertainty=float(m['uncertainty'])
                if not math.isfinite(edge) or abs(edge)>1 or not math.isfinite(uncertainty) or uncertainty<=0:
                    issues.append('Invalid prediction distribution');edge=0.;prob=.5;uncertainty=1.
                history=panel[panel.symbol==symbol].tail(80).reindex(columns=m['columns']).astype(float)
                if len(history)>=60:
                    baseline=history.iloc[:-20];recent=history.iloc[-20:];shift=((recent.mean()-baseline.mean()).abs()/baseline.std().replace(0,np.nan)).max()
                    if pd.notna(shift) and shift>4:issues.append('Feature distribution shift')
                    if (recent.isna().mean()-baseline.isna().mean()).max()>.2:issues.append('Sudden feature missingness')
                if r.get('forward_calibration_error') is not None and r['forward_calibration_error']>p.maximum_calibration_error:issues.append('Calibration drift')
                context={};factors=[]
                for dimension,value in [('regime',a.get('regime')),('liquidity_bucket',a.get('liquidity_bucket')),('market_cap_bucket',a.get('market_cap_bucket'))]:
                    conditional=r.get('conditional_validation',{}).get(dimension,{}).get(value,{});n=conditional.get('nonoverlapping_date_clusters',0);base=(r.get('validation') or {}).get('mean_net_strategy_return') or 0.;sample=conditional.get('mean_net_strategy_return',base);mix=n/(n+p.shrinkage_prior_dates) if n>=p.minimum_conditional_dates else 0.;shrunk=mix*sample+(1-mix)*base
                    context[dimension]={'value':value,'date_clusters':n,'shrinkage':mix,'shrunk_net_return':shrunk,'usable':n>=p.minimum_conditional_dates};factors.append(1 if shrunk>0 else .25)
                forward=r.get('recent_forward',r['forward']);n=forward['date_clusters'];recent_weight=n/(n+p.shrinkage_prior_dates) if n>=p.minimum_conditional_dates else 0.;recent_factor=1-recent_weight if (forward.get('mean_net_return') or 0)<0 else 1
                eligible=r['eligibility']=='eligible' and not issues and not health;weight=float(np.prod(factors)*recent_factor) if eligible else 0.
                votes.append({'model_id':r['id'],'artifact_hash':r['artifact_hash'],'family':r['family'],'group':GROUPS.get(r['family'],'mixed_price_research'),'prediction_after_cost':edge,'probability':prob,'uncertainty':uncertainty,'weight':weight,'eligible':eligible,'health':issues,'eligibility_reasons':r['reasons'],'conditional':context,'forward_shrinkage':recent_weight,'features':{k:None if pd.isna(v) else float(v) for k,v in x.items()},'maximum_feature_z':float(np.nanmax(np.abs(z),initial=0)) if np.isfinite(z).any() else None,'horizon':m.get('horizon',5),'historical_reliability':r.get('validation',{}),'forward_reliability':r.get('recent_forward',r.get('forward',{})),'forward_calibration_error':r.get('forward_calibration_error'),'training_prior':m['prior']})
            from backend.ensemble.engine import candidate
            scored=score_opportunity(a,row,votes,health,p,correlation,view)
            scored['strategy_return_dependence']=self.db.setting('strategy_return_dependence',{})
            from backend.research.alpha.registry import context
            scored=context(scored,live_governance(self.db))
            result.append(candidate(scored,a,qualified_only=True))
        result.sort(key=lambda r:(r['score'],r['research_score']),reverse=True)
        return {'as_of':now().isoformat(),'rows':result,'correlation':correlation,'history_ids':self.manifests,'definition':'Scores decompose research utility; they are not win probabilities. Unapproved evidence is capped at 25 and cannot create orders.','model_selection':'Development-only family/class winner; dependence groups capped to one vote. No holdout-based reselection.'}

def score_opportunity(asset,row,votes,health,p,correlation,view=None):
    usable=[v for v in votes if not v['health']];approved=[v for v in usable if v['weight']>0];pool=approved or usable;groups=defaultdict(list)
    for v in pool:groups[v['group']].append(v)
    grouped=[]
    for group,items in groups.items():
        weights=np.array([v['weight'] if approved else 1. for v in items]);weights=weights/weights.sum();grouped.append({'group':group,'edge':float(sum(w*v['prediction_after_cost'] for w,v in zip(weights,items))),'probability':float(sum(w*v['probability'] for w,v in zip(weights,items))),'uncertainty':float(sum(w*v['uncertainty'] for w,v in zip(weights,items))),'weight':max(v['weight'] for v in items) if approved else 0.})
    w=np.array([g['weight'] if approved else 1. for g in grouped]);w=w/w.sum() if len(w) and w.sum() else w
    edge=float(sum(v*g['edge'] for v,g in zip(w,grouped))) if grouped else None;prob=float(sum(v*g['probability'] for v,g in zip(w,grouped))) if grouped else None;unc=float(sum(v*g['uncertainty'] for v,g in zip(w,grouped))) if grouped else None
    positive=sum(g['edge']>0 for g in grouped);agreement=max(positive,len(grouped)-positive)/len(grouped) if grouped else 0.;vol=float(row.get('realized_volatility',np.nan)) if row is not None else None;vol=vol if vol and math.isfinite(vol) else None;cost=float(row.get('cost',.011)) if row is not None else None
    held=[v['symbol'] for v in (view or {}).get('positions',[])];corrs=correlation.get('correlations',{}).get(asset['symbol'],{});redundancy=max([abs(corrs.get(s,1.)) for s in held],default=0.)
    adv=asset.get('eligibility',{}).get('mean_dollar_volume') or 0.;age=max(0,(pd.Timestamp(now())-pd.Timestamp(row.date)).total_seconds()/86400) if row is not None else None
    components={'edge':max(0,min(25,(edge or 0)/max(unc or 1,1e-9)*25)),'probability':max(0,min(15,((prob or .5)-.5)*60)),'agreement':10*agreement,'liquidity':10*max(0,min(1,np.log10(max(adv,1)/1e6)/3)),'uncertainty':10*max(0,1-(unc or .2)/.2),'volatility':10*max(0,1-(vol or .1)/.1),'cost':10*max(0,1-(cost or .02)/.02),'diversification':5*(1-redundancy),'freshness':5*max(0,1-(age if age is not None else 4)/4)}
    research=float(sum(components.values()));qualifies=bool(approved and len(groups)>=p.minimum_independent_groups and not health);score=research if qualifies else min(25,research*.25)
    reasons=health+([] if approved else ['No approved strategy evidence'])+([] if len(groups)>=p.minimum_independent_groups else ['Too few independent signal groups'])
    return {'symbol':asset['symbol'],'name':asset.get('name',asset['symbol']),'asset_class':asset.get('asset_class'),'sector':asset.get('sector') or 'unknown','regime':asset.get('regime'),'liquidity_bucket':asset.get('liquidity_bucket'),'market_cap_bucket':asset.get('market_cap_bucket'),'score':round(score,2),'research_score':round(research,2),'components':{k:round(float(v),3) for k,v in components.items()},'direction':'positive research edge' if edge is not None and edge>0 else 'cash / nonpositive' if edge is not None else 'unavailable','expected_edge':edge,'probability':prob,'uncertainty':unc,'daily_volatility':vol,'volatility_basis':'Trailing daily realized volatility proxy; no validated volatility forecast','estimated_roundtrip_cost':cost,'quote_status':'Execution requires a separately checked fresh quote','downside_estimate':(edge-2*unc) if edge is not None and unc is not None else None,'agreement':agreement,'groups':list(groups) if approved else [],'research_groups':list(groups),'group_votes':grouped,'votes':votes,'health':health,'reasons':reasons,'trade_eligible':qualifies,'would_trade':qualifies and score>=p.minimum_score and (edge or 0)>0 and (prob or 0)>=p.minimum_probability,'feature_available_at':str(row.date) if row is not None else None,'max_correlation_to_holdings':redundancy,'context_unavailable':['dated market cap','sector-conditional evidence','validated correlation-regime evidence'],'score_basis':'approved evidence' if qualifies else 'capped research indication; zero execution weight'}
