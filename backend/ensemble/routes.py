from backend.intelligence.news import live_governance
from fastapi import APIRouter
from backend.ensemble.portfolio import Consent,Pause,ManualExits
from backend.ensemble.engine import decide,VERSION,FAMILY_GROUPS

def ensemble_routes(service,manual):
    r=APIRouter(prefix='/api/v1/ensemble');db=service.db;exits=ManualExits(db,manual)
    @r.get('/shadow')
    def shadow():return service.status()
    @r.post('/shadow/pause')
    def pause(req:Pause):db.set_setting('ensemble_shadow_paused',req.paused);return {'paused':req.paused,'external_execution':False}
    @r.get('/manual-exits')
    def manual_status():return exits.status()
    @r.put('/manual-exits')
    def consent(req:Consent):return exits.consent(req)
    @r.get('/research')
    def research():
        from backend.research.alpha.registry import context
        snap=db.setting('model_opportunities',{});g=live_governance(db);rows=[decide(context(row,g),snap.get('assets',{}).get(row['symbol'],{})) for row in snap.get('rows',[])]
        return {'version':VERSION,'families':FAMILY_GROUPS,'current':rows,'advanced':db.setting('advanced_research_result',{}),'status':'EXPERIMENTAL — NOT VALIDATED','external_execution':False}
    return r
