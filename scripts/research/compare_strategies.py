import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.research.strategies import run,prepare,publish_current_forecasts
if __name__=='__main__':
 db=Database();snapshot=prepare(db);print('Freezing development comparisons',flush=True);run(db,prepared=snapshot);print('Releasing fixed holdout once',flush=True);result=run(db,release=True,prepared=snapshot);Path('data/product_phase/strategy_results.json').write_text(json.dumps(result,indent=2));print('Saved '+str(len(result['family_results']))+' family/class comparisons',flush=True)
