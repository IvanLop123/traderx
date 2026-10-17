import sys,asyncio,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.providers.market import MarketProviders,ProviderError
from backend.providers.history import HistoricalBackfill
from backend.storage.database import Database
from backend.research.universe import load_universe
from backend.schemas.contracts import now

async def main():
 db=Database();p=MarketProviders(db);h=HistoricalBackfill(p);symbols=[i.symbol for i in load_universe(db).instruments if i.asset_class in ('stock','etf')]
 result={}
 try:result['sip']=await h.alpaca(symbols,feed='sip');print('SIP historical completed',flush=True)
 except ProviderError as e:result['sip']={'status':e.status};print('SIP '+e.status,flush=True)
 for series in ['T10Y2Y','BAMLC0A0CM']:
  existing=db.records('macro_initial',series,limit=1);rows={r['date']:r for r in existing[0]['payload']['observations'] if r['value']!='.'} if existing else {};missing=[]
  for year in range(2010,now().year+1):
   try:
    data=await p.request('fred','https://api.stlouisfed.org/fred/series/observations',params={'api_key':p.cfg['FRED_API_KEY'],'file_type':'json','series_id':series,'output_type':4,'realtime_start':f'{year}-01-01','realtime_end':min(now().date().isoformat(),f'{year}-12-31'),'observation_start':'2010-01-01','limit':100000})
    if data.get('count',0)>len(data.get('observations',[])):raise ValueError('Truncated')
    for o in data.get('observations',[]):
     if o['value']!='.' and (o['date'] not in rows or o['realtime_start']<rows[o['date']]['realtime_start']):rows[o['date']]=o
   except ProviderError as e:missing.append({'year':year,'status':e.status})
  if rows:p.persist('fred','macro_initial',{'series':series,'observations':[rows[k] for k in sorted(rows)],'policy':'initial_release_only_next_NY_midnight','unavailable_archive_windows':missing},series,source='https://api.stlouisfed.org/fred/series/observations')
  result[series]={'count':len(rows),'unavailable_windows':missing};print(series+' '+str(len(rows)),flush=True)
 db.set_setting('extended_history_status',result);Path('data/universe_phase/extended.json').write_text(json.dumps(result,indent=2));print('Extended history saved',flush=True)
asyncio.run(main())
