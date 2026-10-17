import asyncio,json,os
from datetime import timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_platform import db
from backend.schemas.contracts import Bar,now
from backend.research.autonomous.schema import ExperimentSpec,Feature,Budget,ReviewProposal,ReviewDecision
from backend.research.autonomous.service import AutonomousResearch,novelty,implementation_hash
from backend.research.autonomous.numerics import frames,run,classify
from backend.research.autonomous.isolation import execute,clean_environment,clean_abandoned
from backend.research.features import stable_hash

@pytest.fixture
def spec():return ExperimentSpec(hypothesis='Momentum may persist when volatility is stable and the after-cost signal is positive.',economic_mechanism='Information diffusion may produce persistence after correcting for common risk and turnover costs.',lineage='momentum-regime',universe=['BTC-USD'],asset_class='crypto',features=[Feature(name='return_20'),Feature(name='regime_vol_ratio')],training_window=1000)

@pytest.fixture
def snapshot():
    rng=np.random.default_rng(184);n=1000;start=now()-timedelta(days=n+2);closes=100*np.exp(np.cumsum(rng.normal(.0003,.01,n)));rows=[]
    for i,c in enumerate(closes):
        o=float(closes[max(0,i-1)]);t=start+timedelta(days=i)
        rows.append(Bar(symbol='BTC-USD',provider='fixture',timestamp=t,available_at=t+timedelta(days=1),observed_at=t+timedelta(days=1),open=o,high=max(o,c)*1.01,low=min(o,c)*.99,close=float(c),volume=100000).model_dump(mode='json'))
    return {'assets':{'BTC-USD':{'bars':rows,'features':[]}},'news':[],'holdout_start':rows[800]['timestamp']}

@pytest.fixture
def service(db,tmp_path,snapshot):
    for b in snapshot['assets']['BTC-USD']['bars']:db.put('bar',b,'BTC-USD')
    return AutonomousResearch(db,root=tmp_path/'autonomous')

@pytest.mark.parametrize('extra',[{'code':'import os; os.remove("production")'},{'risk_limit':0},{'broker':'live'},{'version':'v2'},{'model_family':'transformer'},{'trials':[1,2,3]},{'maximum_participation':1}])
def test_spec_rejects_unsupported_or_malicious(spec,extra):
    with pytest.raises(ValueError):ExperimentSpec.model_validate({**spec.model_dump(),**extra})

def test_invalid_feature_and_path(spec):
    with pytest.raises(ValueError):Feature(name='__import__("os")')
    with pytest.raises(ValueError):ExperimentSpec.model_validate({**spec.model_dump(),'universe':['../../secrets']})

def test_preregistration_immutable_and_frozen_snapshot(service,spec):
    reg=service.register(spec);assert reg['immutable'];assert reg['alpha_threshold']==.00625
    service.db.put('auto_registration',{'spec':'tampered'},record_id=reg['id'])
    assert service.db.get(reg['id'])['payload']==reg
    restored=service.restore(reg);assert stable_hash(restored)==reg['dataset']['dataset_hash']
    assert service.db.records('experiment_definition')[0]['payload']['autonomous_registration']==reg['id']
    with pytest.raises(ValueError,match='Daily'):service.register(spec)

def test_novelty_renamed_parameter_variants(spec):
    old={'id':'x','spec':spec.model_dump(),'lineage':'original'}
    candidate=spec.model_copy(update={'lineage':'renamed','horizon':10,'features':[Feature(name='return_5'),Feature(name='regime_vol_ratio')]})
    assert novelty(candidate,[old])['redundant'];assert novelty(candidate,[old])['nearest']['lineage']=='original'

def test_snapshot_changes_rejected(service,spec):
    reg=service.register(spec);rid=reg['dataset']['assets']['BTC-USD']['bar_ids'][0]
    from backend.storage.database import Record
    with service.db.transaction() as s:
        row=s.get(Record,rid);row.payload={**row.payload,'close':7.}
    with pytest.raises(ValueError,match='changed'):service.restore(reg)

def test_point_in_time_news_and_future_features(spec,snapshot):
    spec=spec.model_copy(update={'features':[Feature(name='return_20'),Feature(name='news_negative')]})
    before=frames(spec,snapshot)['BTC-USD'][1]
    s=json.loads(json.dumps(snapshot));at=s['assets']['BTC-USD']['bars'][900]['available_at']
    s['news']=[{'available_at':at,'symbols':['BTC-USD'],'cluster_id':'a','direction':'negative','materiality':'high'}]
    after=frames(spec,s)['BTC-USD'][1]
    pd.testing.assert_frame_equal(before.iloc[:900],after.iloc[:900]);assert after.news_negative.iloc[900]==1
    assert after.news_negative.iloc[899]!=after.news_negative.iloc[899]

def test_frozen_holdout_never_selects_hyperparameter(spec,snapshot):
    a=run(spec.model_dump(),snapshot);b=json.loads(json.dumps(snapshot))
    for bar in b['assets']['BTC-USD']['bars'][850:]:
        for k in ('open','high','low','close'):bar[k]*=3
    changed=run(spec.model_dump(),b)
    assert a['selected_strength']==changed['selected_strength'];assert a['trials']==changed['trials']
    assert a['point_in_time']['purge_bars']==7
    assert classify(a,spec,.00625)

def test_pause_budgets_and_worker_cleanup(service,spec):
    reg=service.register(spec);assert service.run_next()['status']=='PAUSED'
    service.configure(Budget(paused=False,wall_seconds=60))
    result=service.run_next();assert result['status']=='REJECTED';assert result['metrics']
    assert not list(service.temporary.glob('run-*'));assert service.db.get(reg['id']+'-result')
    assert service.run_next()['status']=='IDLE'
    assert service.status()['experiments'][0]['adjusted_p_value_by']>=0

def test_worker_environment_and_runtime_restrictions(spec,snapshot,tmp_path):
    env=clean_environment(tmp_path);assert not any(k in env for k in ('OPENAI_API_KEY','ALPACA_API_KEY','DATABASE_URL','PYTHONPATH'))
    result=execute(spec.model_dump(),snapshot,Budget().model_dump(),tmp_path,lambda:True)
    assert result['reason']=='paused_by_owner';assert not list(tmp_path.glob('run-*'))

def test_resource_budget_schema():
    for kwargs in ({'maximum_concurrent':2},{'memory_mb':10000},{'maximum_trials':30},{'experiments_per_day':500}):
        with pytest.raises(ValueError):Budget(**kwargs)

def test_challenger_gate_does_not_promote(service,spec):
    reg=service.register(spec);result={'status':'EVALUATED','result':run(spec.model_dump(),service.restore(reg))}
    before={r['id'] for r in service.db.records('order')};out=service._finish(reg,result)
    assert out['status']=='REJECTED';assert not service.db.records('auto_model');assert not service.db.records('candidate');assert before=={r['id'] for r in service.db.records('order')}
    with pytest.raises(ValueError):service.enroll(reg['id'])

def test_invalid_api_does_not_write_state(db,spec):
    from backend.api.main import create_app
    with TestClient(create_app(db,start_workers=False)) as client:
        before=len(db.records('auto_registration'))
        assert client.post('/api/v1/research/autonomous/register',headers={'X-TraderX-Client':'local-ui'},json={**spec.model_dump(),'code':'import os'}).status_code==422
        assert len(db.records('auto_registration'))==before
        assert client.get('/api/v1/research/autonomous').json()['budget']['paused']

def test_abandoned_temporary_retention(tmp_path):
    import time
    directory=tmp_path/'run-old';directory.mkdir();(directory/'matrix.tmp').write_text('temporary')
    os.utime(directory,(time.time()-1000,time.time()-1000));assert clean_abandoned(tmp_path)==1;assert not directory.exists()

def test_multiple_testing_includes_failed_attempts_and_lineage(service,spec):
    service.configure(Budget(experiments_per_day=4))
    first=service.register(spec)
    service._finish(first,{'status':'REJECTED','reason':'insufficient_data'})
    other=spec.model_copy(update={'lineage':'other-mechanism','features':[Feature(name='bollinger_z'),Feature(name='volume_zscore')],'economic_mechanism':'Temporary inventory imbalances can create reversion when available liquidity supports trading at low participation.'})
    second=service.register(other)
    assert second['attempt']==2 and second['alpha_threshold']<first['alpha_threshold']
    states=service.status();assert states['registered_total']==2
    assert all(x['adjusted_p_value_by']==1 for x in states['experiments'])
    assert service.db.records('experiment_holdout')[0]['payload']['holdout']['p_value'] is None

def test_concurrent_execution_claim_is_exclusive(service,spec,monkeypatch):
    import threading
    import backend.research.autonomous.service as module
    reg=service.register(spec);service.configure(Budget(paused=False));entered=threading.Event();release=threading.Event()
    def worker(*args,**kwargs):entered.set();release.wait(5);return {'status':'REJECTED','reason':'test_rejection'}
    monkeypatch.setattr(module,'execute',worker)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(service.run_next);assert entered.wait(5)
        assert service.run_next()['status']=='BUSY';release.set();assert a.result()['status']=='REJECTED'
    assert len(service.db.records('auto_result'))==1

def test_generated_code_is_quarantined_and_approval_never_executes(db,tmp_path,monkeypatch):
    import backend.research.autonomous.service as module
    monkeypatch.setattr(module,'ROOT',tmp_path)
    service=AutonomousResearch(db,root=tmp_path/'data');target=tmp_path/'must-not-exist'
    proposal=ReviewProposal(rationale='A new architecture requires independent implementation and a review of its scientific assumptions.',proposed_patch=f'from pathlib import Path; Path({str(target)!r}).write_text("bad")',tests='Check future perturbations and training-only fit.',required_data='Real observed historical input coverage.',experiment_design='Freeze a chronological holdout and costs before any architecture or parameter selection.')
    result=service.code_proposal(proposal);folder=tmp_path/'research/proposals'/result['id']
    assert (folder/'proposed.patch.txt').read_text().startswith('REQUIRES REVIEW')
    approved=service.review_code(result['id'],ReviewDecision(decision='approved_for_human_review',reason='Review the proposal manually before implementing anything.'))
    assert not approved['executed'];assert not target.exists();assert all(p.suffix!='.py' for p in folder.iterdir())
    assert service.disk_usage()['quarantine_bytes']>0

def test_challenger_creation_and_forward_enrollment_are_research_only(service,spec,monkeypatch):
    # Exercise the registration handoff with an explicit gate fixture; not a measured performance claim.
    reg=service.register(spec);metrics=run(spec.model_dump(),service.restore(reg))
    import backend.research.autonomous.service as module
    monkeypatch.setattr(module,'classify',lambda *args:[])
    before=service.db.setting('alpha_governance');service.db.set_setting('research_universe',{'instruments':[{'symbol':'BTC-USD','asset_class':'crypto'}]})
    result=service._finish(reg,{'status':'EVALUATED','result':metrics});assert result['status']=='CHALLENGER'
    model=result['model_ids'][0];study=service.enroll(model)
    assert study['evidence_policy']=='quarantined_evaluation';assert service.enroll(model)['id']==study['id']
    assert service.db.setting('alpha_governance')==before
    assert not service.db.records('candidate') and not service.db.records('order')
    from backend.research.forward import study_prediction
    prediction=study_prediction(service.db,model);assert prediction['model_id']==model
    assert service.status()['qualified_discoveries']==[]

def test_storage_and_trial_limits(service,spec):
    service.configure(Budget(maximum_trials=1))
    with pytest.raises(ValueError,match='Hyperparameter'):service.register(spec)
    service.configure(Budget(storage_mb=4))
    service.root.mkdir(parents=True);(service.root/'review-artifact.txt').write_bytes(b'x'*(3*1024**2))
    with pytest.raises(ValueError,match='storage'):service.register(spec)

def test_observe_propose_register_execute_without_llm(service,monkeypatch):
    service.configure(Budget(paused=False))
    first=asyncio.run(service.propose());assert first['status']=='PREREGISTERED'
    assert first['source']['provider']=='deterministic_template'
    assert asyncio.run(service.propose())['status']=='NO_NEW_OBSERVATIONS'
    result=service.run_next();assert result['status']=='REJECTED';assert result['metrics']
    assert result['resources']['temporary_files_retained'] is False
    assert service.db.setting('alpha_governance') is None

def test_paused_proposals_make_no_llm_calls(service):
    class Forbidden:
        def settings(self):raise AssertionError('No LLM call while paused')
    service.llm=Forbidden();service.configure(Budget(paused=True,director='cloud'))
    assert asyncio.run(service.propose())=={'status':'PAUSED'}

def test_worker_guard_blocks_network_protected_files_and_processes(tmp_path):
    import subprocess,sys
    from backend.research.autonomous.isolation import ROOT
    script='''import sys,pathlib,socket,subprocess
sys.path.insert(0,ROOT)
from backend.research.autonomous.worker import guard
guard(pathlib.Path.cwd())
blocked=0
for operation in (lambda:open("/tmp/.env"),lambda:socket.create_connection(("127.0.0.1",8000)),lambda:subprocess.run(["true"]),lambda:open("/tmp/outside-research.txt","w")):
 try:operation()
 except PermissionError:blocked+=1
assert blocked==4,blocked
'''.replace('ROOT',repr(str(ROOT)),1)
    result=subprocess.run([sys.executable,'-I','-B','-c',script],cwd=tmp_path,env=clean_environment(tmp_path),capture_output=True)
    assert result.returncode==0,result.stderr.decode()

def test_daily_execution_budget_applies_to_old_queue(service,spec,monkeypatch):
    import backend.research.autonomous.service as module
    service.configure(Budget(paused=False,experiments_per_day=2));service.register(spec)
    other=spec.model_copy(update={'features':[Feature(name='bollinger_z'),Feature(name='volume_zscore')]});service.register(other)
    monkeypatch.setattr(module,'execute',lambda *a,**kw:{'status':'REJECTED','reason':'fixture_rejection'})
    assert service.run_next()['status']=='REJECTED'
    service.configure(Budget(paused=False,experiments_per_day=1))
    assert service.run_next()['status']=='DAILY_BUDGET'
    assert len(service.db.records('auto_execution'))==1

def test_optional_local_provider_only_sees_narrative(service,spec):
    from backend.core.config import AISettings
    class Local:
        def settings(self):return AISettings(provider='local',automated=True)
        async def _analyze(self,task,settings):
            assert task.task=='research_hypothesis' and task.automated
            assert 'open' not in task.text.lower() and 'close' not in task.text.lower()
            assert '100000' not in task.text and 'api_key' not in task.text
            assert settings.provider=='local' and not settings.escalation
            return {'status':'COMPLETE','provider':'local','model':'fixture','analysis':{'hypothesis':spec.model_dump()}}
    service.llm=Local();service.configure(Budget(paused=False,director='local'))
    result=asyncio.run(service.propose());assert result['status']=='PREREGISTERED';assert result['source']['model']=='fixture'

def test_global_ai_off_prevents_cloud_calls(service):
    from backend.core.config import AISettings
    class Off:
        def settings(self):return AISettings(provider='off')
        async def _analyze(self,*args):raise AssertionError('Cloud disabled')
    service.llm=Off();service.configure(Budget(paused=False,director='cloud'))
    result=asyncio.run(service.propose());assert result['source']['provider']=='deterministic_template'

def test_supervisor_kills_memory_overrun(spec,snapshot,tmp_path,monkeypatch):
    import backend.research.autonomous.isolation as module
    monkeypatch.setattr(module.subprocess,'check_output',lambda *a,**kw:b'999999999')
    outcome=execute(spec.model_dump(),snapshot,Budget().model_dump(),tmp_path)
    assert outcome['reason']=='memory_budget';assert not list(tmp_path.glob('run-*'))
