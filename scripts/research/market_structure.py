"""Explicit bounded, deterministic diagnostics. No broker or language-model calls."""
import sys,json,asyncio
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
if __name__=='__main__':
    db=Database()
    if '--collect' in sys.argv:
        from backend.providers.market import MarketProviders
        from backend.research.structure.collector import Collector
        result=asyncio.run(Collector(db,MarketProviders(db)).cycle(force=True))
    else:
        from backend.research.structure.experiments import run
        result=run(db)
    out=Path('data/market_structure_phase');out.mkdir(exist_ok=True,parents=True);(out/('collection.json' if '--collect' in sys.argv else 'experiment.json')).write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ('id','status','outcomes') if k in result},indent=2))
