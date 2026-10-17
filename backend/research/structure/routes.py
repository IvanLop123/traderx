"""Research-only routes; imports and quote replays cannot reach a broker."""
from fastapi import APIRouter,HTTPException
from backend.schemas.contracts import Contract,now
from backend.research.structure.intraday import microstructure
from backend.research.structure.experiments import compare
from backend.ensemble.lifecycle import Recommendations


def routes(db,collector):
    r=APIRouter(prefix='/api/v1/structure')
    @r.get('/status')
    def status():
        intra={}
        for x in db.records('intraday_research',limit=200):
            p=x['payload'];intra.setdefault((p['symbol'],p['interval_seconds']),p)
        options={}
        for x in db.records('structure_options',limit=30):options.setdefault(x['symbol'],x['payload'])
        ex=db.get(db.setting('structure_experiment_latest',''));symbols=collector.cfg['symbols'];micro={s:microstructure([x['payload'] for x in db.records('quote',s,limit=120)],[x['payload'] for x in db.records('order_book',s,limit=3)],[x['payload'] for x in db.records('trade',s,limit=100)]) for s in symbols}
        return {'at':now().isoformat(),'collection':db.setting('structure_collection',{}),'limits':collector.cfg,'intraday':list(intra.values()),'options':list(options.values()),'microstructure':micro,'experiment':ex['payload'] if ex else None,'experiments':[{'id':x['id'],'at':x['payload']['at'],'version':x['payload']['identity']['version']} for x in db.records('structure_experiment',limit=50)],'recommendation_events':Recommendations(db).recent(),'recommendation_worker':db.setting('recommendation_worker',{}),'external_execution':False}
    @r.post('/collect')
    async def collect():return await collector.cycle() # Cadence enforced even for repeated clicks.
    @r.get('/experiments/compare')
    def comparison(a:str,b:str):
        records=[db.get(k) for k in (a,b)]
        if not all(x and x['kind']=='structure_experiment' for x in records):raise HTTPException(404,'Saved research experiments required')
        return compare(*(x['payload'] for x in records))
    return r
