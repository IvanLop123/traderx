import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.selection.research import run_policy_research
if __name__=='__main__':
 r=run_policy_research(Database());Path('data/selection_phase/policy_results.json').write_text(json.dumps(r,indent=2));print('Completed',len(r['results']),'fixed policy comparisons')
