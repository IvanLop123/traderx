"""Read-only evidence screens and explicit bounded local research actions."""
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import Field
from backend.schemas.contracts import Contract,now
from backend.research.features import stable_hash
from backend.research.forward import ForwardStudies,ReleaseRequest
from backend.qualification.replay import replay

class ReplayRequest(Contract):
    snapshots:int=Field(default=50,ge=1,le=100)
class TrainingRelease(Contract):
    definition_id:str
    reason:str=Field(min_length=20,max_length=1000)
    confirmation:Literal['RETIRE EVALUATION AND RELEASE AGED SAMPLES']

def release(db,request):
    definition=db.get(request.definition_id);enrollment=db.get(request.definition_id+'_enrollment')
    if not definition or definition['kind']!='qualification_definition' or not enrollment:raise ValueError('Registered qualification cohort required')
    import pandas as pd
    d=definition['payload'];ids=enrollment['payload']['study_ids'];states=[db.setting('forward_state_'+sid,{}) for sid in ids]
    if any(s.get('state')!='retired' or s.get('pending') for s in states):raise ValueError('Retire all source scientific cohorts and complete their pending observations first')
    outcomes=[r for r in db.records('forward_outcome',limit=None) if r['payload'].get('study_id') in ids and r['payload'].get('status') in ('COMPLETED','CASH_EVALUATED')]
    cutoff=pd.Timestamp(now())-pd.Timedelta(days=d['criteria']['minimum_training_release_days'])
    if not outcomes or any(pd.Timestamp(o['payload']['completed_at'])>cutoff for o in outcomes):raise ValueError('Every source outcome must complete the frozen minimum 90-day quarantine')
    service=ForwardStudies(db);receipts=[service.release(ReleaseRequest(study_id=sid,reason=request.reason,minimum_age_days=d['criteria']['minimum_training_release_days'])) for sid in ids if any(o['payload']['study_id']==sid for o in outcomes)]
    payload={'definition_id':d['id'],'source_releases':[r['id'] for r in receipts],'released_at':now().isoformat(),'reason':request.reason,'automatic_training':False,'evaluation_eligible':False};db.put('qualification_training_release',payload);db.set_setting('qreleased_'+stable_hash(d['id'])[:32],payload)
    status=db.setting('qstatus_'+stable_hash(d['model_id'])[:32],{});db.set_setting('qstatus_'+stable_hash(d['model_id'])[:32],{**status,'execution_allowed':False,'suspension_reasons':['Evaluation cohort released for future training']});return payload

def qualification_routes(service):
    db=service.db;r=APIRouter(prefix='/api/v1/qualification')
    @r.get('/diagnostics')
    def diagnostics():return db.setting('qualification_diagnostics',{})
    @r.get('/evidence')
    def evidence():return {**db.setting('qualification_status',{}),'worker':db.setting('qualification_worker',{})}
    @r.get('/research')
    def research():
        current=db.setting('qualification_research',{});return {**current,'chronology_status':'CURRENT — fold-specific uncertainty','superseded_experiments':[{'id':r['id'],'state':'SUPERSEDED','reason':'Threshold diagnostic used final-fold uncertainty; excluded from current evidence'} for r in db.records('qualification_research',limit=None) if r['payload'].get('definition',{}).get('version')=='qualification-research-v1']}
    @r.get('/audit')
    def audit():return db.setting('qualification_audit',{})
    @r.get('/replay')
    def replay_status():
        value=db.setting('qualification_replay',{});return {**value,'traces':value.get('traces',[])[:100]}
    @r.post('/replay')
    def replay_run(req:ReplayRequest):
        try:
            value=replay(db,req.snapshots);return {**value,'traces':value['traces'][:100]}
        except ValueError as exc:raise HTTPException(400,str(exc))
    @r.post('/release')
    def training_release(req:TrainingRelease):
        try:return release(db,req)
        except ValueError as exc:raise HTTPException(400,str(exc))
    return r
