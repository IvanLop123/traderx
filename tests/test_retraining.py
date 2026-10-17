import asyncio
import json
from datetime import timedelta
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.api.main import create_app
from backend.core.config import AISettings
from backend.llm.service import LLMService
from backend.research.retraining import Retrainer, TrainingSchedule
from backend.storage.database import Setting
from backend.schemas.contracts import now
from test_platform import db, bars


def test_scheduled_learning_is_local_and_never_promotes(db,bars):
    for b in bars:db.put('bar',b,'BTC-USD')
    trainer=Retrainer(db)
    assert trainer.cycle()==[]
    trainer.configure(TrainingSchedule(enabled=True,symbols=['BTC-USD']))
    with patch('backend.llm.providers.LocalLLMProvider.complete',side_effect=AssertionError('No LLM')):
        out=trainer.cycle()
    assert out[0]['status']=='RESEARCH_VERSION_SAVED'
    model=db.get(out[0]['model_id'])['payload']
    assert model['activation']=='research_only' and model['artifact']
    assert not db.records('candidate') and not db.records('model_lifecycle')
    assert trainer.cycle()[0]['status']=='WAITING_FOR_SCHEDULE'
    assert len(db.records('model'))==1
    # Due date alone is insufficient: new observations are mandatory.
    key='training_last_'+__import__('hashlib').sha256(b'BTC-USD5').hexdigest()[:32]
    saved=db.setting(key);db.set_setting(key,{**saved,'attempted_at':(now()-timedelta(days=8)).isoformat()})
    assert trainer.cycle()[0]['status']=='WAITING_FOR_NEW_BARS'
    assert len(db.records('model'))==1


def test_training_lease_and_bad_history_do_not_stop_app(db,bars):
    trainer=Retrainer(db);trainer.configure(TrainingSchedule(enabled=True,symbols=['BTC-USD']))
    db.set_setting('training_lease',{'token':'other','until':(now()+timedelta(hours=1)).isoformat()})
    assert trainer.cycle()==[]
    db.set_setting('training_lease',{'token':'old','until':(now()-timedelta(hours=1)).isoformat()})
    assert trainer.cycle()[0]['status']=='INSUFFICIENT_OR_INVALID_DATA'
    assert trainer.status()['worker']['status']=='WORKING'
    with pytest.raises(ValueError):trainer.configure(TrainingSchedule(symbols=['bad']))
