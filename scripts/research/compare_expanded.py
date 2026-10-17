import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.research.studies import Studies,StudyRequest
from backend.research.cross_sectional import compare

db=Database();studies=Studies(db);root=Path('data/universe_phase');result={}
for symbol in ['BTC-USD','ETH-USD','SOL-USD','AAPL','MSFT','NVDA']:
 print('Comparing '+symbol,flush=True)
 try:
  frozen=studies.run(StudyRequest(symbol=symbol));out=studies.release(frozen['id']);result[symbol]=out
  (root/'model_results.json').write_text(json.dumps(result,indent=2));print(symbol+' '+out['selected']['algorithm']+' holdout '+str(out['holdout']['metrics']['samples']),flush=True)
 except Exception as e:print(symbol+' FAILED '+type(e).__name__+' '+str(e),flush=True);raise
print('Cross-sectional development',flush=True);compare(db);print('Cross-sectional frozen holdout',flush=True);cross=compare(db,release=True);(root/'cross_results.json').write_text(json.dumps(cross,indent=2));print('Completed all comparisons',flush=True)
