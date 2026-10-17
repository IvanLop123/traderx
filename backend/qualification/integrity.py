"""Freeze the implementation as well as the numerical criteria."""
import hashlib
from pathlib import Path

FILES=('backend/intelligence/news.py','backend/ensemble/engine.py','backend/ensemble/portfolio.py','backend/qualification/studies.py','backend/qualification/integrity.py','backend/qualification/policy.py','backend/selection/portfolio.py','backend/selection/registry.py','backend/qualification/engine.py','backend/qualification/books.py','backend/qualification/evaluation.py','backend/qualification/statistics.py','backend/selection/opportunities.py','backend/selection/risk.py','backend/product/paper.py','backend/research/forward.py','backend/research/strategies.py')
def implementation_hash():
    root=Path(__file__).resolve().parents[2]
    files=sorted(set(FILES)|{str(p.relative_to(root)) for p in (root/'backend/research/alpha').glob('*.py')})
    return hashlib.sha256(b''.join(name.encode()+ (root/name).read_bytes() for name in files)).hexdigest()

def paper_authorized(db,model_id,artifact_hash):
    """Recheck a registered model at decision AND fill, including release and monitoring."""
    import pandas as pd
    from backend.schemas.contracts import now
    from backend.research.features import stable_hash
    d=db.get(db.setting('qcurrent_'+stable_hash(model_id)[:32],'qualification_'+stable_hash(model_id)))
    if not d:return None # Older adapters retain their own source checks.
    status=db.setting('qstatus_'+stable_hash(model_id)[:32],{});terminal=db.get(status.get('terminal_receipt_id',''))
    return bool(quarantined(db,d['payload']) and terminal and terminal['kind']=='qualification_terminal' and terminal['payload'].get('state')=='QUALIFIED_FOR_MODEL_PAPER' and terminal['payload'].get('model_hash')==artifact_hash and status.get('state')=='QUALIFIED_FOR_MODEL_PAPER' and status.get('execution_allowed') and status.get('criteria_hash')==d['payload']['criteria_hash'] and d['payload'].get('implementation_hash')==implementation_hash() and not db.setting('qreleased_'+stable_hash(d['payload']['id'])[:32]) and status.get('at') and 0<=(pd.Timestamp(now())-pd.Timestamp(status['at'])).total_seconds()<=7200)


def quarantined(db,definition):
    enrollment=db.get(definition['id']+'_enrollment')
    ids=enrollment['payload'].get('study_ids',[]) if enrollment else []
    return bool(ids) and all(db.setting('forward_state_'+sid,{}).get('evidence_policy')=='quarantined_evaluation' for sid in ids)
