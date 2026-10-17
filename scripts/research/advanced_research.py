"""Explicit bounded local research. Does not run on ticks or schedule itself."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.research.advanced.lab import run
if __name__=='__main__':
    result=run(Database());out=Path('data/ensemble_phase/advanced_results.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2));print('Saved',result['id'],len(result['folds']),'folds')
