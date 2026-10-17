"""New prospective alpha cohorts; never consume scientific or manual account outcomes."""
import asyncio
import copy
import pandas as pd
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.research.forward import ForwardPolicy,quote_check
from backend.ensemble.engine import forecasts
from backend.research.alpha.registry import AlphaRegistry,context,lane,metrics,POLICY

class AlphaForward:
    def __init__(self,db,providers):self.db=db;self.providers=providers
    def record(self,row,asset,g,at=None):
        at=at or now();observational=copy.deepcopy(g)
        for f in observational.get('families',{}).values():
            if f['state']=='SUSPENDED':f['state']='HOLDOUT' # Observe recovery without authorizing allocation.
        r=context(row,observational,at);key='af_'+stable_hash([row['symbol'],row.get('horizon_sessions',5)])[:32];old=self.db.setting(key,{})
        if old.get('pending') or old.get('feature_at')==row.get('feature_available_at'):return
        if row.get('health') or not asset.get('eligibility',{}).get('eligible'):return
        fs=forecasts(r.get('votes',[]),'fixed',False,row.get('horizon_sessions',5));usable=[f for f in fs if f.applicable]
        if not usable:return
        definitions={f.family:self.db.get(g['families'][f.family]['id'])['payload'] for f in usable}
        # No late registration of a feature already observed before the experiment starts.
        usable=[f for f in usable if pd.Timestamp(definitions[f.family]['registered_at'])<=pd.Timestamp(row['feature_available_at'])<=pd.Timestamp(at)]
        if not usable:return
        did='aforecast_'+stable_hash([row['symbol'],row['feature_available_at'],[(f.family,g['families'][f.family]['id']) for f in usable]])
        fixed={f.family:1/len(usable) for f in usable};weights={f.family:g.get('weights',{}).get(f.family,0) for f in usable};total=sum(weights.values());weights={k:v/total for k,v in weights.items()} if total else fixed
        d={'id':did,'decision_at':at.isoformat(),'symbol':row['symbol'],'asset_class':asset.get('asset_class','unknown'),'sector':asset.get('sector') or 'unknown','regime':row.get('regime') or 'unknown','horizon':row.get('horizon_sessions',5),'feature_at':row['feature_available_at'],'features':row.get('votes',[]),'lane':lane(row['symbol']),'fixed_weights':fixed,'adaptive_weights':weights,'weight_epoch':g['weight_epoch'],'alphas':[{'alpha_id':g['families'][f.family]['id'],'family':f.family,'phase':g['families'][f.family]['state'],'prediction':f.edge,'probability':f.probability,'uncertainty':f.uncertainty,'model_ids':f.model_ids} for f in usable],'estimated_cost':row.get('estimated_roundtrip_cost',0),'policy':ForwardPolicy().model_dump(),'evidence_policy':'Prospective alpha cohort; adaptation lane delayed release; evaluation lane never adapted or trained'}
        self.db.put('alpha_forecast',d,row['symbol'],record_id=did);self.db.set_setting(key,{'pending':did,'feature_at':row['feature_available_at'],'entry':None,'last_quote':None})
    def process(self,key,q,at=None):
        at=at or now();state=self.db.setting(key,{})
        if not state.get('pending'):return
        d=self.db.get(state['pending'])['payload'];policy=ForwardPolicy(**d['policy']);sessions=self.db.setting('research_calendar',{}).get('sessions',[])
        if not state.get('entry') and pd.Timestamp(at)>pd.Timestamp(d['decision_at'])+pd.Timedelta(hours=1):
            self.db.put('alpha_unfilled',{'forecast':d['id'],'at':at.isoformat(),'reason':'No timely executable quote'},d['symbol'],record_id=d['id']+'_unfilled');state['pending']=None;self.db.set_setting(key,state);return
        if quote_check(q,{'symbol':d['symbol'],'decided_at':d['decision_at']},policy,at,sessions,d['asset_class']):return
        if state.get('last_quote') and pd.Timestamp(q['timestamp'])<=pd.Timestamp(state['last_quote']):return
        if pd.Timestamp(q['timestamp'])<pd.Timestamp(d['decision_at'])+pd.Timedelta(seconds=policy.latency_seconds):return
        state['last_quote']=q['timestamp'];slip=policy.slippage_bps/1e4;fee=policy.fee_bps/1e4
        if not state.get('entry'):
            # One-hour opportunity window: absent executable observations are recorded as unfilled.
            if pd.Timestamp(at)>pd.Timestamp(d['decision_at'])+pd.Timedelta(hours=1):
                self.db.put('alpha_unfilled',{'forecast':d['id'],'at':at.isoformat(),'reason':'No timely executable quote'},d['symbol'],record_id=d['id']+'_unfilled');state['pending']=None;self.db.set_setting(key,state);return
            price=q['ask']*(1+slip);qty=min(100/price,q['ask_size']*.02)
            if qty<=0:return
            if d['asset_class']=='crypto':end=pd.Timestamp(at)+pd.Timedelta(days=d['horizon'])
            else:
                future=[s for s in sessions if pd.Timestamp(s['open'])>pd.Timestamp(at)]
                if len(future)<d['horizon']:return
                end=pd.Timestamp(future[d['horizon']-1]['open'])
            state['entry']={'at':at.isoformat(),'quote':q,'price':price,'quantity':qty,'cost':qty*price*(1+fee),'exit_not_before':end.isoformat()};self.db.set_setting(key,state);return
        e=state['entry']
        if pd.Timestamp(at)<pd.Timestamp(e['exit_not_before']) or pd.Timestamp(q['timestamp'])<=pd.Timestamp(e['at']):self.db.set_setting(key,state);return
        # If displayed exit size is inadequate, wait; never fill from an observed close.
        if q['bid_size']*.02<e['quantity']:self.db.set_setting(key,state);return
        proceeds=e['quantity']*q['bid']*(1-slip)*(1-fee);net=proceeds/e['cost']-1;actual_cost=(e['quote']['ask']-e['quote']['bid'])/e['quote']['ask']+2*(slip+fee);outcomes=[]
        for a in d['alphas']:
            selected=a['prediction']>max(actual_cost,a['uncertainty']*.25) and a['probability']>=.55
            oid='aout_'+stable_hash([d['id'],a['alpha_id']]);o={**a,'id':oid,'forecast_id':d['id'],'decision_at':d['decision_at'],'completed_at':at.isoformat(),'symbol':d['symbol'],'asset_class':d['asset_class'],'regime':d['regime'],'lane':d['lane'],'horizon':d['horizon'],'net_return':net,'strategy_return':net if selected else 0.,'selected':selected,'cost_ratio':actual_cost/max(d['estimated_cost'],1e-6),'entry':e,'exit_quote':q,'exit_proceeds':proceeds,'evidence_policy':d['evidence_policy']};self.db.put('alpha_outcome',o,d['symbol'],record_id=oid);outcomes.append(o)
        benchmark={'id':d['id']+'_benchmark','decision_at':d['decision_at'],'completed_at':at.isoformat(),'symbol':d['symbol'],'lane':d['lane'],'horizon':d['horizon'],'fixed_return':sum(d['fixed_weights'][o['family']]*o['strategy_return'] for o in outcomes),'adaptive_return':sum(d['adaptive_weights'][o['family']]*o['strategy_return'] for o in outcomes),'fixed_weights':d['fixed_weights'],'adaptive_weights':d['adaptive_weights'],'basis':'Paired equal-hypothesis versus adaptive alpha-sleeve quote markouts; correlated hypotheses are not independent; not realized account P&L; weights frozen before outcomes','weight_epoch':d['weight_epoch']};self.db.put('alpha_benchmark',benchmark,d['symbol'],record_id=benchmark['id']);state['pending']=None;self.db.set_setting(key,state)
    async def cycle(self,at=None):
        at=at or now();snap=self.db.setting('model_opportunities',{});g=await asyncio.to_thread(AlphaRegistry(self.db).cycle,snap,at);rows=sorted([r for r in snap.get('rows',[]) if r['symbol'] in POLICY['forward_symbols']],key=lambda r:r['symbol']);cursor=self.db.setting('alpha_cursor',0);batch=(rows+rows)[cursor:cursor+8] if rows else []
        for r in batch:
            a=snap.get('assets',{}).get(r['symbol'],{});self.record(r,a,g,at)
            key='af_'+stable_hash([r['symbol'],r.get('horizon_sessions',5)])[:32]
            if not self.db.setting(key,{}).get('pending'):continue
            self.process(key,{},at) # Expiry does not depend on provider availability.
            if not self.db.setting(key,{}).get('pending'):continue
            try:q=await self.providers.forward_quote(r['symbol']);self.process(key,q,at)
            except Exception:continue # Missing quote is not an invented observation.
        self.db.set_setting('alpha_cursor',(cursor+8)%len(rows) if rows else 0)
        self.db.set_setting('alpha_worker',{'status':'RUNNING','at':at.isoformat(),'batch':len(batch),'external_execution':False})
