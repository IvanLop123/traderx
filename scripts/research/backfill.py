"""Explicit, bounded read-only backfill. Resume cached completed tasks with --resume."""
import sys,asyncio,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.providers.market import MarketProviders,ProviderError
from backend.providers.history import HistoricalBackfill
from backend.research.universe import load_universe
from backend.research.features import MACRO
from backend.schemas.contracts import now

async def main():
    args=argparse.ArgumentParser();args.add_argument('--resume',action='store_true');args.add_argument('--sec-limit',type=int,default=250);a=args.parse_args()
    db=Database();h=HistoricalBackfill(MarketProviders(db));u=load_universe(db);stocks=[i.symbol for i in u.instruments if i.asset_class in ('stock','etf')];tasks=[]
    tasks.extend([('calendar',h.calendar),('instruments',h.instruments)])
    for s in ['BTC-USD','ETH-USD','SOL-USD']:tasks.append(('price_'+s,lambda s=s:h.coinbase(s)))
    for i in range(0,len(stocks),u.backfill_batch_size):
        batch=stocks[i:i+u.backfill_batch_size];tasks.append(('equities_'+str(i),lambda batch=batch:h.alpaca(batch)))
    tasks.append(('corporate_actions',lambda:h.corporate_actions(stocks)))
    for s in MACRO:tasks.append(('macro_'+s,lambda s=s:h.macro(s)))
    for s in ['BTC','ETH','SOL']:tasks.append(('funding_'+s,lambda s=s:h.funding(s)))
    for s,c in [('AAPL','320193'),('MSFT','789019'),('NVDA','1045810')]:tasks.append(('sec_'+s,lambda s=s,c=c:h.sec_form4(s,c,a.sec_limit)))
    path=Path('data/universe_phase/backfill.json');result=json.loads(path.read_text()) if a.resume and path.exists() else {}
    for name,fn in tasks:
        if a.resume and result.get(name,{}).get('status')=='COMPLETE':continue
        print(name+' started',flush=True)
        try:
            value=await fn();result[name]={'status':'COMPLETE','result':value,'at':now().isoformat()}
        except Exception as e:result[name]={'status':e.status if isinstance(e,ProviderError) else type(e).__name__,'detail':e.detail if isinstance(e,ProviderError) else 'Historical response failed validation; no replacement data','at':now().isoformat()}
        path.parent.mkdir(exist_ok=True,parents=True);path.write_text(json.dumps(result,indent=2));db.set_setting('historical_backfill_status',result);print(name+' '+result[name]['status'],flush=True)
if __name__=='__main__':asyncio.run(main())
