"""Material recommendation transitions; polling is not independent evidence."""
from sqlalchemy import select
from backend.storage.database import Record,Setting
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.ensemble.engine import decide,finite

VERSION='recommendation-events-v1'
def changes(previous,current,edge_absolute=.0025,relative=.25):
    if not previous:return ['initial_observation']
    reasons=[]
    for field,label in [('action','direction'),('supporting_families','supporting_families'),('regime','regime'),('eligible','liquidity_eligibility'),('reasons','health_or_cost_gate'),('horizon_sessions','horizon'),('held','position_status'),('news_revision_ids','news_evidence')]:
        if previous.get(field)!=current.get(field):reasons.append(label)
    for field in ('edge','uncertainty'):
        a,b=previous.get(field),current.get(field)
        if a!=b and (not finite(a) or not finite(b) or abs(a-b)>=max(edge_absolute,relative*abs(a))):reasons.append(field)
    a,b=previous.get('cost'),current.get('cost')
    if finite(a) and finite(b) and abs(a-b)>=edge_absolute:reasons.append('execution_cost')
    return reasons

class Recommendations:
    def __init__(self,db):self.db=db
    def cycle(self,at=None,symbols=None):
        at=at or now();snap=self.db.setting('model_opportunities',{});assets=snap.get('assets',{});held=set()
        for key in ('manual_paper','ensemble_shadow_account','model_paper_account'):
            p=self.db.setting(key,{}) or {}
            held.update(s for s,v in p.get('positions',{}).items() if isinstance(v,dict) and v.get('quantity',0)>0)
        from backend.intelligence.news import live_governance
        governance=live_governance(self.db)
        values=[]
        for r in snap.get('rows',[]):
            if symbols is not None and r['symbol'] not in symbols:continue
            from backend.research.alpha.registry import context
            r=context(r,governance,at);asset=assets.get(r['symbol'],{});e=decide(r,asset,held=r['symbol'] in held,at=at)
            values.append({**e,'held':r['symbol'] in held,'regime':r.get('regime'),'eligible':bool(asset.get('eligibility',{}).get('eligible')),'cost':r.get('current_roundtrip_cost',r.get('estimated_roundtrip_cost')),'supporting_families':sorted(f['family'] for f in e['families'] if f['applicable'] and (f['edge'] or 0)>0),'observed_at':at.isoformat(),'snapshot_at':snap.get('as_of')})
        emitted=[]
        with self.db.transaction() as s:
            stored=s.get(Setting,'recommendation_lifecycle');state=stored.value if stored else {};updated=dict(state)
            for value in values:
                symbol=value['symbol'];prior=state.get(symbol)
                if prior and prior.get('observed_at','')>value['observed_at']:continue
                why=changes(prior,value)
                if why:
                    event={'version':VERSION,'symbol':symbol,'at':at.isoformat(),'before':prior,'after':value,'changes':why,'feature_snapshot':next((r.get('votes',[]) for r in snap.get('rows',[]) if r['symbol']==symbol),[]),'thresholds':{'absolute_edge_or_uncertainty':.0025,'relative_change':.25},'evidence_policy':'Recommendation history only; not a new independent training sample'}
                    rid='recommendation_'+stable_hash([symbol,prior.get('event_id') if prior else None,value,why]);event['id']=rid
                    s.add(Record(id=rid,kind='recommendation_change',symbol=symbol,available_at=at.isoformat(),payload=event));updated[symbol]={**value,'event_id':rid};emitted.append(rid)
            # Keep a material baseline: many tiny changes eventually cross its threshold.
            s.merge(Setting(key='recommendation_lifecycle',value=updated));s.merge(Setting(key='recommendation_worker',value={'at':at.isoformat(),'assets':len(values),'changes':len(emitted),'status':'RUNNING'}))
        return emitted
    def recent(self,limit=30,symbol=None):return [r['payload'] for r in self.db.records('recommendation_change',symbol,limit=limit)]
