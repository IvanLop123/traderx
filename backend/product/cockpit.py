from backend.intelligence.news import live_governance
"""Deterministic decision explanations and personal notes. No execution or model fitting.

All writes use manual_* kinds. Observations are a personal journal, excluded from
scientific evidence and training. Prices are observed references, never promised fills.
"""
from collections import defaultdict
from datetime import timedelta
import math
import pandas as pd
from pydantic import Field
from sqlalchemy import select
from backend.schemas.contracts import Contract,now
from backend.storage.database import Record,Setting
from backend.research.features import stable_hash
from backend.research.universe import load_universe
from backend.selection.policy import GROUPS
from backend.product.paper import Ticket

FAMILIES=['momentum','trend_following','mean_reversion','breakout','volatility','relative_strength','cross_sectional_ranking','insider_event','macro_regime','crypto_funding','pairs_relative_value']
class JournalNote(Contract):
    reason:str=Field(default='',max_length=2000)
    followed_view:str=Field(default='unspecified',pattern='^(followed|disagreed|unspecified)$')
    expected_outcome:str=Field(default='',max_length=2000)
class ResearchTicket(Ticket):
    journal:JournalNote=Field(default_factory=JournalNote)
class Idea(Contract):
    symbol:str=Field(pattern=r'^[A-Z0-9.-]{1,40}$')
    notes:str=Field(default='',max_length=2000)
    target_entry:float|None=Field(default=None,gt=0)
    target_exit:float|None=Field(default=None,gt=0)
    stop:float|None=Field(default=None,gt=0)
    saved:bool=True

def finite(x):return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)
def age_days(value,at):
    try:return (pd.Timestamp(at)-pd.Timestamp(value)).total_seconds()/86400
    except (TypeError,ValueError):return float('inf')

def describe(row,asset,at,statuses=None):
    """Explanations are exact feature comparisons and healthy model votes; never prose inference."""
    statuses=statuses or {};votes=row.get('votes',[]);features={};families=[]
    for family in FAMILIES:
        all_votes=[v for v in votes if v['family']==family]
        usable=[v for v in all_votes if not v.get('health') and finite(v.get('prediction_after_cost'))]
        edge=sum(v['prediction_after_cost'] for v in usable)/len(usable) if usable else None
        families.append({'family':family,'group':GROUPS.get(family,'unknown'),'view':'No Data' if edge is None else 'Bullish' if edge>0 else 'Bearish' if edge<0 else 'Neutral','edge':edge,'variants':len(all_votes),'used_variants':len(usable),'issues':sorted({e for v in all_votes for e in v.get('health',[])}),'model_ids':[v['model_id'] for v in all_votes]})
        for v in usable:
            for k,value in v.get('features',{}).items():
                if finite(value):features.setdefault(k,value)
    from backend.ensemble.engine import decide
    preliminary=decide(row,asset,at=at);row={**row,'expected_edge':preliminary['edge'],'uncertainty':preliminary['uncertainty'],'probability':preliminary['probability'],'group_votes':preliminary['groups']}
    positive=[];caution=list(row.get('health',[]))+list(asset.get('eligibility',{}).get('reasons',[]));edge=row.get('expected_edge');unc=row.get('uncertainty');prob=row.get('probability');groups=row.get('group_votes',[])
    for key,label in [('return_20','20-session return'),('ma20_to_ma60','20/60-session moving-average gap'),('relative_momentum','Momentum relative to peers')]:
        if key in features:
            value=features[key];(positive if value>0 else caution).append(f'{label}: {value:+.2%} (stored feature)')
    if finite(edge):(positive if edge>0 else caution).append(f'Expected edge after estimated costs: {edge:+.2%}')
    if finite(unc) and finite(edge) and unc>abs(edge):caution.append(f'Residual uncertainty ({unc:.2%}) exceeds the expected edge magnitude')
    if finite(row.get('daily_volatility')) and row['daily_volatility']>=.03:caution.append(f'High daily volatility: {row["daily_volatility"]:.2%}')
    if groups and any(g.get('edge',0)>0 for g in groups) and any(g.get('edge',0)<0 for g in groups):caution.append('Strategy dependence groups disagree on direction')
    if asset.get('liquidity_bucket') in ('limited','unknown'):caution.append('Limited or unknown liquidity; spread and available depth may prevent a fill')
    if asset.get('asset_class')=='stock' and asset.get('market_cap_bucket','unknown')=='unknown':caution.append('Dated market capitalization is unavailable')
    stale=not 0<=age_days(row.get('feature_available_at'),at)<=4
    if stale:caution.append('Research features are stale or unavailable; wait for a current snapshot')
    states=sorted({statuses.get(v['model_id'],{}).get('state','RESEARCH_ONLY') for v in votes}) or ['RESEARCH_ONLY']
    qualified=any(statuses.get(v['model_id'],{}).get('state')=='QUALIFIED_FOR_MODEL_PAPER' and statuses[v['model_id']].get('execution_allowed') and v.get('weight',0)>0 for v in votes)
    if not qualified:caution.append('TraderX has not validated this strategy for automatic Model Paper allocation')
    caution.extend(w for w in asset.get('warnings',[]) if asset.get('asset_class')=='stock' or 'capitalization' not in w.lower())
    no_trade=[]
    if not asset.get('eligibility',{}).get('eligible'):no_trade.append('Asset fails liquidity or data eligibility checks')
    if finite(edge) and edge<=0:no_trade.append('Expected long-side edge is nonpositive after costs; a bearish view is not a short-sale forecast')
    if finite(prob) and prob<.55:no_trade.append('Estimated probability is below the automatic entry threshold')
    if not qualified:no_trade.append('Strategy lacks qualified forward evidence for automatic allocation')
    no_trade+=row.get('reasons',[])
    ensemble=preliminary
    view=ensemble['action'];edge=ensemble['edge'];unc=ensemble['uncertainty'];prob=ensemble['probability']
    no_trade=list(dict.fromkeys(ensemble['reasons']+no_trade));row={**row,'expected_edge':edge,'uncertainty':unc,'probability':prob}
    return {**asset,'ensemble':ensemble,**{k:row.get(k) for k in ['score','research_score','expected_edge','uncertainty','probability','agreement','daily_volatility','estimated_roundtrip_cost','feature_available_at','components']},'view':view,'likes':positive,'cautions':list(dict.fromkeys(caution)),'no_trade_reasons':list(dict.fromkeys(no_trade)),'families':families,'dependence_groups':len(ensemble['groups']),'evidence_strength':f'{len(ensemble["groups"])} usable dependence groups; forward validation '+('passed' if qualified else 'incomplete'),'qualification_states':states,'qualified':qualified,'quality_label':'Qualified for Model Paper' if qualified else 'Experimental research signal','stale':stale,'raw_votes':votes,'rank':None,'rank_scope':'Unavailable unless healthy cross-sectional model predictions share an eligible class and feature timestamp','suggested_side':'sell' if view=='SELL' else 'buy','manual_trade_scope':'Long-only local simulation; sell requires existing holdings','regime':row.get('regime') or asset.get('regime','unknown')}

class Cockpit:
    def __init__(self,db,paper):self.db=db;self.paper=paper
    def rows(self,snapshot=None,at=None,symbols=None):
        historical=snapshot is not None
        snapshot=snapshot if historical else self.db.setting('model_opportunities',{})
        from backend.research.alpha.registry import context
        g={} if historical else live_governance(self.db);raw={v['symbol']:context(v,g,at) for v in snapshot.get('rows',[])};assets={v['symbol']:v for v in self.db.setting('product_summary_cache',{}).get('rows',[])};statuses={r['model_id']:r for r in self.db.setting('qualification_status',{}).get('rows',[])}
        from backend.qualification.integrity import paper_authorized
        for status in statuses.values():
            if status.get('execution_allowed'):status['execution_allowed']=paper_authorized(self.db,status['model_id'],status.get('model_hash')) is True
        universe=load_universe(self.db).instruments
        result=[];at=at or now();held={p['symbol'] for p in self.paper.view()['positions']}
        for i in universe:
            if symbols is not None and i.symbol not in symbols:continue
            a={**{'symbol':i.symbol,'name':i.name or i.symbol,'asset_class':i.asset_class,'sector':i.sector or 'unknown','eligibility':{'eligible':False,'reasons':['Current eligibility unavailable']},'liquidity_bucket':'unknown','market_cap_bucket':'unknown'},**assets.get(i.symbol,{}),**snapshot.get('assets',{}).get(i.symbol,{})}
            r=describe(raw.get(i.symbol,{}),a,at,statuses)
            from backend.ensemble.engine import decide
            if i.symbol in held:
                e=decide(raw.get(i.symbol,{}),a,held=True,at=at);r.update(ensemble=e,view=e['action'],suggested_side='sell' if e['action']=='SELL' else 'buy')
            result.append(r)
        ranks=defaultdict(list);members={}
        # Rank against all eligible peers without rendering their full decision cards.
        for i in universe:
            r=raw.get(i.symbol,{});a={**assets.get(i.symbol,{}),**snapshot.get('assets',{}).get(i.symbol,{})}
            votes=[v for v in r.get('votes',[]) if v['family']=='cross_sectional_ranking' and not v.get('health') and finite(v.get('prediction_after_cost'))]
            if votes and a.get('eligibility',{}).get('eligible') and 0<=age_days(r.get('feature_available_at'),at)<=4:
                key=(a.get('asset_class',i.asset_class),r['feature_available_at']);edge=sum(v['prediction_after_cost'] for v in votes)/len(votes)
                ranks[key].append(edge);members[i.symbol]=(key,edge)
        for r in result:
            if r['symbol'] not in members:continue
            key,edge=members[r['symbol']];group=ranks[key]
            if len(group)>=2:r['rank']={'rank':1+sum(other>edge for other in group),'eligible_assets':len(group),'basis':'After-cost cross-sectional model prediction; same class and feature timestamp'}
        return sorted(result,key=lambda r:(-(r.get('score') if finite(r.get('score')) else -1),-(r.get('research_score') if finite(r.get('research_score')) else -1),r['symbol']))
    def asset(self,symbol):
        r=next((r for r in self.rows(symbols={symbol}) if r['symbol']==symbol),None)
        if not r:raise ValueError('Asset is not in configured research universe')
        r['suggested_size']=self.suggest(r);return r
    def suggest(self,r):
        p=self.paper.view();vol=r.get('daily_volatility');unc=r.get('uncertainty');adv=r.get('eligibility',{}).get('mean_dollar_volume');edge=r.get('expected_edge')
        if r['view'] not in ('BUY','HOLD') or r['stale'] or not r['eligibility'].get('eligible') or not all(finite(x) and x>0 for x in [vol,unc,adv]):return {'amount':None,'reason':'A current volatility, uncertainty and liquidity estimate is required; no size invented'}
        if not finite(edge) or edge<=0:return {'amount':0.,'reason':'No new long position suggested: expected edge after costs is nonpositive'}
        p={**p,'positions':[*p['positions'],*[{'symbol':o['symbol'],'market_value':(o['quantity']-o['filled_quantity'])*o['reserve_price']} for o in p['orders'] if o['side']=='buy' and o['status'] in ('OPEN','PARTIALLY_FILLED')]]}
        snap=self.db.setting('model_opportunities',{});corr=snap.get('correlation',{}).get('correlations',{}).get(r['symbol'],{});held=sum(v['market_value'] for v in p['positions'] if v['symbol']==r['symbol']);sector=sum(v['market_value'] for v in p['positions'] if snap.get('assets',{}).get(v['symbol'],{}).get('sector','unknown')==r.get('sector','unknown'));related=sum(v['market_value'] for v in p['positions'] if abs(corr.get(v['symbol'],1))>=.8)
        limits={'cash':p['available_cash'],'volatility':p['equity']*.0025/vol,'uncertainty':p['equity']*.0025/unc,'position':max(0,p['equity']*.1-held),'sector':max(0,p['equity']*.3-sector),'correlation':max(0,p['equity']*.25-related),'gross_exposure':max(0,p['equity']*.8-sum(v['market_value'] for v in p['positions'])),'liquidity':adv*.0001}
        amount=max(0,min(limits.values()));return {'amount':math.floor(amount*100)/100,'reason':'Research-only cap from '+min(limits,key=limits.get)+'. Assumes full correlation where unknown; you may choose another size. Whole-share rounding and execution checks still apply.','limits':limits}
    def save_context(self,preview,note):
        r=self.asset(preview['symbol']);p=self.paper.view();position=next((v for v in p['positions'] if v['symbol']==preview['symbol']),{});change=preview['quantity']*preview['estimated_price']*(1 if preview['side']=='buy' else -1)
        allocation=max(0,position.get('market_value',0)+change)/max(1,p['equity']-preview['estimated_fee'])
        context={'preview_id':preview['id'],'at':now().isoformat(),'research':r,'note':note.model_dump(),'resulting_allocation':allocation,'source':'manual_journal_only','training_eligible':False,'evaluation_eligible':False}
        self.db.put('manual_context',context,preview['symbol'],record_id='manual_context_'+stable_hash(preview['id']));return {**preview,**{k:context[k] for k in ['research','resulting_allocation']}}
    def idea(self,req):
        self.asset(req.symbol)
        with self.db.transaction() as s:
            row=s.get(Setting,'manual_trade_ideas');items=dict(row.value) if row else {};items[req.symbol]={**req.model_dump(),'updated_at':now().isoformat(),'source':'personal_idea_only','training_eligible':False}
            if sum(v['saved'] for v in items.values())>500:raise ValueError('Trade ideas are limited to 500 active entries')
            if row:row.value=items
            else:s.add(Setting(key='manual_trade_ideas',value=items))
        self.db.put('manual_idea_event',items[req.symbol],req.symbol);return items[req.symbol]
    def observe(self):
        s=self.paper.state()
        if not s or not s['orders']:return
        held={symbol for symbol,p in s['positions'].items() if p['quantity']>0}
        if not held:return
        rows={r['symbol']:r for r in self.rows(symbols=held)};at=now()
        for symbol,p in s['positions'].items():
            if p['quantity']<=0:continue
            q=s['marks'].get(symbol,{});r=rows.get(symbol,{})
            value={'account_id':s['id'],'symbol':symbol,'opened_at':p['opened_at'],'at':at.isoformat(),'quote_at':q.get('timestamp'),'bid':q.get('bid') if 0<=age_days(q.get('timestamp'),at)*86400<=120 else None,'average_cost':p['average_cost'],'view':r.get('view','Insufficient Evidence'),'score':r.get('score'),'regime':r.get('regime'),'source':'manual_journal_only','training_eligible':False}
            rid='manual_observation_'+stable_hash([s['id'],symbol,p['opened_at'],q.get('timestamp'),r.get('feature_available_at'),value['view'],value['score'],value['regime']]);self.db.put('manual_observation',value,symbol,record_id=rid)
    def journal(self,rows=None):
        account=self.paper.view();aid=account['id'];orders={o['id']:o for o in account['orders']}
        with self.db.engine.connect() as c:
            fills=list(c.execute(select(Record.payload).where(Record.kind=='manual_fill',Record.payload['account_id'].as_string()==aid).order_by(Record.created_at,Record.id)).scalars())
            marks=list(c.execute(select(Record.payload).where(Record.kind=='manual_observation',Record.payload['account_id'].as_string()==aid).order_by(Record.created_at)).scalars())
        actions=[]
        for action_id in (self.paper.state() or {}).get('applied_actions',[]):
            rec=self.db.get(action_id)
            if rec and rec['payload'].get('action_type') in ('forward_splits','reverse_splits'):
                d=rec['payload']['data'];actions.append({'symbol':rec['symbol'],'at':pd.Timestamp(d.get('ex_date') or d.get('effective_date')).tz_localize('America/New_York').isoformat(),'split':float(d['new_rate'])/float(d['old_rate'])})
        open_trades={};trades=[];contexts={};current={r['symbol']:r for r in (rows if rows is not None else self.rows())}
        for f in sorted([*fills,*actions],key=lambda f:pd.Timestamp(f['at'])):
            if 'split' in f:
                t=open_trades.get(f['symbol'])
                if t:t['quantity']*=f['split'];t['buy_quantity']*=f['split']
                continue
            symbol=f['symbol'];o=orders.get(f['order_id'],{});pid=o.get('preview_id')
            if pid not in contexts:
                rec=self.db.get('manual_context_'+stable_hash(pid));contexts[pid]=rec['payload'] if rec else {}
            ctx=contexts[pid]
            if f['side']=='buy':
                if symbol not in open_trades:
                    t={'id':f['order_id']+'_'+f['at'],'symbol':symbol,'opened_at':f['at'],'closed_at':None,'quantity':0.,'buy_quantity':0.,'entry_cost':0.,'realized_pnl':0.,'fees':0.,'entry_view':ctx.get('research',{}).get('view','Not recorded'),'entry_score':ctx.get('research',{}).get('score'),'entry_regime':ctx.get('research',{}).get('regime'),'note':ctx.get('note',{}),'entry_evidence':ctx.get('research',{}),'entries':[],'exit_views':[],'fills':[]};open_trades[symbol]=t;trades.append(t)
                t=open_trades[symbol];t['quantity']=round(t['quantity']+f['quantity'],8);t['buy_quantity']+=f['quantity'];t['entry_cost']+=f['quantity']*f['price']+f['fee'];t['entries'].append({'at':f['at'],'context':ctx})
            else:
                if symbol not in open_trades:continue
                t=open_trades[symbol];t['quantity']=max(0,round(t['quantity']-f['quantity'],8));t['realized_pnl']+=f['realized_pnl'];t['exit_views'].append(ctx.get('research',{}).get('view','Not recorded'))
                if t['quantity']<1e-10:t['closed_at']=f['at'];del open_trades[symbol]
            t['fees']+=f['fee'];t['fills'].append(f)
        for t in trades:
            end=t['closed_at'] or now().isoformat();observed=[m for m in marks if m['symbol']==t['symbol'] and pd.Timestamp(t['opened_at'])<=pd.Timestamp(m['at'])<=pd.Timestamp(end)]
            excursions=[m['bid']/m['average_cost']-1 for m in observed if finite(m.get('bid')) and m['average_cost']>0]
            views=[m['view'] for m in observed]+t['exit_views'];r=current.get(t['symbol'],{})
            if not t['closed_at']:views.append(r.get('view','Insufficient Evidence'))
            t.update(holding_seconds=(pd.Timestamp(end)-pd.Timestamp(t['opened_at'])).total_seconds(),average_entry=t['entry_cost']/t['buy_quantity'],maximum_favorable_excursion=max(0.,max(excursions)) if excursions else None,maximum_adverse_excursion=min(0.,min(excursions)) if excursions else None,view_changed=any(v!=t['entry_view'] for v in views),current_view=r.get('view','Insufficient Evidence'),current_score=r.get('score'),current_regime=r.get('regime'),warnings=r.get('cautions',[]),excursion_scope='Observed bid versus contemporaneous average cost; between-poll extremes unavailable',source='manual_journal_only',training_eligible=False,evaluation_eligible=False)
        groups={}
        for choice in ['followed','disagreed','unspecified']:
            rows=[t for t in trades if t['closed_at'] and t['note'].get('followed_view','unspecified')==choice];groups[choice]={'completed_trades':len(rows),'realized_pnl':sum(t['realized_pnl'] for t in rows),'wins':sum(t['realized_pnl']>0 for t in rows)}
        return {'trades':list(reversed(trades)),'comparison':groups,'warning':'Trade P&L sums actual fill P&L; dividends remain in account totals. Personal observational journal; self-selection and small samples do not establish predictive value. Never used as scientific evidence or training.'}
    def board(self):
        rows=self.rows();watch=self.db.setting('personal_watchlist',{'symbols':[]})['symbols'];portfolio=self.paper.view();start=now().replace(hour=0,minute=0,second=0,microsecond=0);prior=None
        with self.db.engine.connect() as c:
            prior=c.execute(select(Record.payload).where(Record.kind=='auto_snapshot',Record.available_at<start.isoformat(),Record.available_at>=(start-timedelta(days=1)).isoformat()).order_by(Record.available_at.desc()).limit(1)).scalar()
        old={r['symbol']:r for r in self.rows(prior,at=prior.get("as_of") or start-timedelta(seconds=1))} if prior else {};changes=[]
        for r in rows:
            before=old.get(r['symbol']);change=None
            if before and finite(before.get('score')) and finite(r.get('score')):change={'symbol':r['symbol'],'before':before['view'],'after':r['view'],'score_change':r['score']-before['score'],'feature_changed':r.get('feature_available_at')!=before.get('feature_available_at')}
            r['change']=change
            if change and (abs(change['score_change'])>=1 or change['before']!=change['after']):changes.append(change)
        changes.sort(key=lambda r:abs(r['score_change']),reverse=True)
        warnings=sorted({c for r in rows for c in r['cautions'] if 'stale' in c.lower() or 'unavailable' in c.lower()});alerts=[r['payload'] for r in self.db.records('auto_alert',limit=20) if r['payload'].get('type')=='data_health']
        unique_alerts={}
        for alert in alerts:
            message=' · '.join(str(alert[k]) for k in ('title','detail','reason') if alert.get(k)) or 'Collector reported a data-health warning; inspect System Health'
            if message not in unique_alerts:unique_alerts[message]={**alert,'message':message,'repeated':0}
            unique_alerts[message]['repeated']+=1
        alerts=list(unique_alerts.values())[:5]
        positions={p['symbol']:p for p in portfolio['positions']}
        for r in rows:r['position']=positions.get(r['symbol'])
        return {'recommendation_events':[{k:r['payload'].get(k) if k not in ('before','after') else {'action':(r['payload'].get(k) or {}).get('action')} for k in ('id','symbol','at','before','after','changes')} for r in self.db.records('recommendation_change',limit=12)],'as_of':self.db.setting('model_opportunities',{}).get('as_of'),'rows':[{**{k:r.get(k) for k in ('symbol','name','asset_class','market_cap_bucket','liquidity_bucket','eligibility','price','price_at','daily_move','regime','score','research_score','expected_edge','uncertainty','probability','agreement','view','likes','cautions','no_trade_reasons','dependence_groups','evidence_strength','qualification_states','qualified','quality_label','stale','suggested_side','change','position')},'families':[{'family':f['family'],'used_variants':f['used_variants']} for f in r['families']]} for r in rows],'top':[r['symbol'] for r in rows if r['eligibility'].get('eligible')][:8],'avoid':[r['symbol'] for r in sorted(rows,key=lambda r:-(r.get('research_score') or 0)) if r['view'] in ('NO TRADE','INSUFFICIENT EVIDENCE','SELL') or r['liquidity_bucket'] in ('limited','unknown')][:8],'changes':changes[:10],'change_basis':'Latest saved snapshot from previous UTC calendar day; same-feature changes may reflect model/policy changes' if prior else 'No previous-day snapshot available; no change invented','watchlist':watch,'ideas':[v for v in self.db.setting('manual_trade_ideas',{}).values() if v['saved']],'portfolio':portfolio,'journal':self.journal(rows),'data_warnings':warnings,'provider_warnings':alerts,'external_execution':False,'training_eligible':False}
