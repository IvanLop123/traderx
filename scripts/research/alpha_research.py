"""Explicit deterministic research; no new providers, inference or external orders."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.research.alpha.research import run
from backend.research.alpha.registry import AlphaRegistry
if __name__=='__main__':
    db=Database();result=run(db);AlphaRegistry(db).cycle(db.setting('model_opportunities',{}));Path('data/alpha_phase/results.json').write_text(json.dumps(result,indent=2));print('Saved',result['id'],flush=True)
