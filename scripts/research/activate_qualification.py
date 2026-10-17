"""Register fixed prospective criteria after bounded local development. No broker or paid calls."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.selection.portfolio import ModelPortfolio
from backend.qualification.engine import QualificationEngine
from backend.qualification.replay import replay
from backend.qualification.diagnostics import refresh_diagnostics
if __name__=='__main__':
    db=Database();print('Rebuilding current local research snapshot',flush=True)
    if '--register-only' not in sys.argv:ModelPortfolio(db).rebuild()
    engine=QualificationEngine(db);result=engine.activate();print(json.dumps(result),flush=True)
    status=engine.review();print(json.dumps(status['counts']),flush=True)
    replay_result=replay(db);print(json.dumps({k:replay_result[k] for k in ['snapshots','trace_count','recorded_quotes','orders','fills','net_pnl']}),flush=True)
    root=Path('data/qualification_phase');root.mkdir(parents=True,exist_ok=True)
    (root/'diagnostics.json').write_text(json.dumps(refresh_diagnostics(db),indent=2));(root/'activation.json').write_text(json.dumps({'activation':result,'states':status['counts'],'models':[r['model_id'] for r in status['rows']]},indent=2))
