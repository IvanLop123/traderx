from fastapi import APIRouter
from pydantic import Field
from backend.schemas.contracts import Contract,now
from backend.selection.policy import policy,policy_hash
from backend.research.features import stable_hash

class PauseRequest(Contract):
    paused:bool

def selection_routes(service):
    db=service.db;r=APIRouter(prefix='/api/v1/selection')
    @r.get('/portfolio')
    def portfolio():return service.status()
    @r.get('/opportunities')
    def opportunities():
        s=db.setting('model_opportunities',{});return {**{k:v for k,v in s.items() if k not in ['correlation','assets','rows']},'rows':[{k:v for k,v in row.items() if k not in ['votes','group_votes']} for row in s.get('rows',[])]}
    @r.get('/opportunities/{symbol}')
    def opportunity(symbol:str):return next((v for v in db.setting('model_opportunities',{}).get('rows',[]) if v['symbol']==symbol),None)
    @r.get('/registry')
    def registry(offset:int=0,limit:int=50):
        s=db.setting('selection_registry',{});return {**{k:v for k,v in s.items() if k!='rows'},'rows':s.get('rows',[])[max(0,offset):max(0,offset)+max(1,min(100,limit))]}
    @r.get('/reviews')
    def reviews():return db.setting('selection_reviews',{})
    @r.get('/families')
    def families():
        s=db.setting('selection_registry',{});return [v for v in s.get('rows',[]) if v['source_kind']=='strategy_model']
    @r.get('/alerts')
    def alerts():return [v['payload'] for v in db.records('auto_alert',limit=100)]
    @r.get('/policy-research')
    def research():return db.setting('portfolio_policy_research',{})
    @r.post('/pause')
    def pause(req:PauseRequest):
        p=policy(db).model_copy(update={'enabled':not req.paused});db.set_setting('model_portfolio_policy',p.model_dump());db.put('auto_control_event',{'paused':req.paused,'at':now().isoformat(),'policy_hash':policy_hash(p)});return {'enabled':p.enabled,'external_execution':False}
    return r
