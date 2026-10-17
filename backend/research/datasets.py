"""Content-addressed, source-attributed historical dataset imports and coverage gates."""
import hashlib
from typing import Literal
from pydantic import Field,AwareDatetime,model_validator
from backend.schemas.contracts import Contract,now
from backend.research.replay import ReplayRequest,EventReplay

class Coverage(Contract):
    symbol:str=Field(min_length=1,max_length=128)
    start:AwareDatetime
    end:AwareDatetime
    action_types:list[Literal['split','dividend']]=Field(min_length=1,max_length=2)
    source_reference:str=Field(min_length=1,max_length=1000)
    complete_for_window:bool=False
    @model_validator(mode='after')
    def valid(self):
        if self.start>=self.end:raise ValueError('Coverage start must precede end')
        return self

class HistoricalDataset(Contract):
    name:str=Field(min_length=1,max_length=200)
    source_reference:str=Field(min_length=1,max_length=1000)
    universe_definition:str=Field(min_length=10,max_length=2000)
    universe_includes_inactive:bool=False
    membership_known_at:dict[str,AwareDatetime]
    corporate_actions:list[Coverage]=Field(default_factory=list,max_length=200)
    request:ReplayRequest
    observation_policy:Literal['point_in_time','retrospective']='retrospective'


def coverage_report(dataset):
    r=dataset.request;issues=[];start=min(e.event_at for e in r.events);end=max(e.event_at for e in r.events)
    symbols={i.symbol for i in r.instruments}
    if not dataset.universe_includes_inactive:issues.append('UNIVERSE_INACTIVE_ASSETS_NOT_CONFIRMED')
    if set(dataset.membership_known_at)!=symbols:issues.append('MEMBERSHIP_KNOWLEDGE_MISSING_OR_EXTRA')
    if any(e.symbol not in symbols for e in r.events):issues.append('UNKNOWN_EVENT_INSTRUMENT')
    if len({e.id for e in r.events})!=len(r.events):issues.append('DUPLICATE_EVENT_ID')
    for i in r.instruments:
        known=dataset.membership_known_at.get(i.symbol)
        if dataset.observation_policy=='point_in_time' and known and known>max(start,i.eligible_from):issues.append('FUTURE_MEMBERSHIP:'+i.symbol)
        if i.asset_class not in ('stock','etf'):continue
        for kind in ('split','dividend'):
            ranges=sorted((c.start,c.end) for c in dataset.corporate_actions if c.symbol==i.symbol and kind in c.action_types and c.complete_for_window)
            cursor=start
            for a,b in ranges:
                if a>cursor:break
                cursor=max(cursor,b)
            if cursor<end:issues.append('ACTION_COVERAGE_GAP:'+i.symbol+':'+kind)
    return {'status':'COVERAGE_DECLARED' if not issues else 'BLOCKED','issues':issues,'start':start.isoformat(),'end':end.isoformat(),
            'scope':dataset.universe_definition,'observation_policy':dataset.observation_policy,
            'warning':'Coverage is a source declaration checked for internal completeness, not independent proof that the source omitted nothing. Current listings alone do not establish historical universe membership.'}


def store_dataset(db,dataset):
    report=coverage_report(dataset);key=hashlib.sha256(dataset.model_dump_json().encode()).hexdigest()
    payload={**dataset.model_dump(mode='json'),'coverage':report,'imported_at':now().isoformat(),'dataset_hash':key}
    db.put('historical_dataset',payload,record_id=key)
    return {'id':key,'name':dataset.name,'coverage':report,'dataset_hash':key}


def replay_dataset(db,rid):
    row=db.get(rid)
    if not row or row['kind']!='historical_dataset':raise ValueError('Stored historical dataset required')
    payload=row['payload'];dataset=HistoricalDataset.model_validate({k:v for k,v in payload.items() if k not in ('coverage','imported_at','dataset_hash')})
    report=coverage_report(dataset)
    if report['issues']:raise ValueError('Historical coverage blocked: '+', '.join(report['issues']))
    result=EventReplay(dataset.request).run();result['coverage']=report;result['dataset_record_id']=rid
    result['warnings']+=['This replay uses an explicitly sourced universe and coverage declarations. Statistical validity still requires an untouched holdout and forward validation.']
    return {'id':db.put('replay',result),**result}
