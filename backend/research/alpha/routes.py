from fastapi import APIRouter
from backend.research.alpha.registry import AlphaRegistry,independent
from backend.research.advanced.models import block_test

def routes(db):
    r=APIRouter(prefix='/api/v1/alpha')
    @r.get('/status')
    def status():
        value=AlphaRegistry(db).status();pairs=[x['payload'] for x in db.records('alpha_benchmark',limit=None) if x['payload']['lane']=='evaluation'];clusters=independent([{**x,'net_return':x['adaptive_return']-x['fixed_return'],'probability':.5} for x in pairs]);diff=block_test([x['net'] for x in clusters]);value.update(worker=db.setting('alpha_worker',{}),allocation=db.setting('alpha_allocation_latest',{}),benchmark={'status':'INSUFFICIENT FORWARD EVIDENCE' if len(clusters)<60 else 'PAIRED EVALUATION — NO AUTOMATIC WINNER DEPLOYMENT','independent_dates':len(clusters),'adaptive_minus_fixed':diff,'observations':len(pairs),'lane':'Reserved evaluation symbols; never used for adaptation'},transitions=[x['payload'] for x in db.records('alpha_transition',limit=50)],deep=db.setting('advanced_research_result',{}).get('folds',[]));return value
    return r
