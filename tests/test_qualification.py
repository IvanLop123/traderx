"""Only isolated synthetic data exercises positive qualification. Never patches live history."""
from datetime import timedelta
import pytest
import pandas as pd
from test_platform import db
from test_selection import approved_fixture
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.qualification.policy import QualificationCriteria
from backend.qualification.statistics import nonoverlapping,interval
from backend.qualification.integrity import implementation_hash
from backend.qualification.evaluation import evaluate,comparison,mature
from backend.qualification.books import ComparisonBook
from backend.qualification.engine import QualificationEngine
from backend.qualification.replay import replay
from backend.qualification.routes import release,TrainingRelease
from backend.selection.policy import PortfolioPolicy
from backend.selection.registry import SelectionRegistry

def definition(db):
    m={'id':'fixture_model','family':'momentum','asset_class':'crypto','prior':.5};db.put('strategy_model',m,record_id=m['id']);c=QualificationCriteria().model_dump();t=now()-timedelta(days=1500)
    d={'id':'qualification_'+stable_hash(m['id']),'model_id':m['id'],'model_hash':stable_hash(m),'family':'momentum','asset_class':'crypto','criteria':c,'criteria_hash':stable_hash(c),'registered_at':t.isoformat(),'family_count':27,'sentinels':['BTC-USD'],'implementation_hash':implementation_hash(),'risk_policy':PortfolioPolicy().model_dump()}
    db.put('qualification_definition',d,record_id=d['id']);db.put('qualification_enrollment',{'study_ids':['fixture_study']},record_id=d['id']+'_enrollment');db.set_setting('forward_state_fixture_study',{'state':'collecting','evidence_policy':'quarantined_evaluation','symbol':'BTC-USD'})
    plan={'registered_at':(t-timedelta(days=1)).isoformat()};db.put('qualification_research_plan',plan,record_id='fixture_plan')
    folds=[{'interval':{'lower':.01},'mse':.1,'zero_mse':.2,'brier':.01,'base_rate_brier':.25}]*3
    db.put('qualification_development',{'model_hash':d['model_hash'],'plan_id':'fixture_plan','folds':folds},record_id='qdevelopment_'+stable_hash(m['id']))
    return d

def observations(db,d,count=100,negative=False):
    start=pd.Timestamp(d['registered_at']).to_pydatetime()+timedelta(days=1)
    for i in range(count):
        at=start+timedelta(days=i*8);end=at+timedelta(days=5);did='fixture_decision_'+str(i);o={'model_id':d['model_id'],'study_id':'fixture_study','decision_id':did,'symbol':'BTC-USD','status':'COMPLETED','completed_at':end.isoformat(),'entry_cost':100.,'realized_pnl':-2. if negative else 2.,'regime':'uptrend' if i%2 else 'range'}
        db.put('forward_decision',{'model_id':d['model_id'],'study_id':'fixture_study','model_hash':d['model_hash'],'decided_at':at.isoformat(),'feature_available_at':at.isoformat(),'probability':.98,'probability_target':'positive_after_cost'},record_id=did)
        db.put('forward_outcome',o,'BTC-USD',record_id='fixture_outcome_'+str(i))

def portfolio(db,d):
    pid='fixture_portfolio';db.put('qualification_portfolio',{'id':pid,'risk_policy':d['risk_policy'],'criteria':d['criteria'],'qualification_ids':[d['id']]},record_id=pid);start=now()-timedelta(days=600)
    for arm in ['candidate',*d['criteria']['benchmark_arms']]:
        equity=10000.
        for i in range(300):
            equity*=1.001 if arm=='candidate' else 1.0001 if arm not in ('cash','incumbent') else 1
            v={'definition_id':pid,'scope':'forward','arm':arm,'date':(start+timedelta(days=i)).date().isoformat(),'equity':equity,'fresh':True,'fees':2.,'turnover':.5,'exposure':.2,'concentration':.04,'regime':'range' if i%2 else 'uptrend'};db.set_setting('qmark_'+stable_hash([arm,i])[:32],v)
    for i in range(40):
        at=start+timedelta(days=i*6);db.put('qualification_outcome',{'definition_id':pid,'scope':'forward','arm':'candidate','decided_at':at.isoformat(),'completed_at':(at+timedelta(days=5)).isoformat(),'probability':.98,'realized_pnl':2.,'net_return':.02},record_id='fixture_book_outcome_'+str(i))
    return comparison(db,pid,d['criteria'],.05/270)

def test_full_source_qualification_and_registry_path(db):
    d=definition(db);observations(db,d);p=portfolio(db,d);r=evaluate(db,d,p)
    assert p['independent_blocks']==60 and r['state']=='QUALIFIED_FOR_MODEL_PAPER',r
    assert all(r['gates'].values()) and not r['real_money_authorized']
    # Actual engine monitoring must grant paper eligibility from the derived receipt.
    db.set_setting('model_opportunities',{'rows':[{'votes':[{'model_id':d['model_id'],'health':[]}]}]})
    status=QualificationEngine(db).review();assert status['rows'][0]['execution_allowed']
    assert SelectionRegistry(db).refresh()['eligible']==1
    assert not db.setting('manual_paper') and not db.setting('model_paper_account')
    changed={**d,'model_hash':'changed'};assert evaluate(db,changed,p)['state']=='RESEARCH_ONLY'

def test_insufficient_and_failure_are_not_overridden(db):
    d=definition(db);assert evaluate(db,d,{})['state']=='FORWARD_TESTING'
    observations(db,d,negative=True);p=portfolio(db,d);r=evaluate(db,d,p);assert r['state']=='FAILED'
    # Adding favorable rows cannot retrospectively turn the fixed terminal trial into a pass.
    observations(db,d,110);assert evaluate(db,d,p)['state']=='FAILED'

def test_preregistration_future_and_release_exclusions(db):
    d=definition(db);observations(db,d,3);assert len(mature(db,d))==3
    assert not mature(db,{**d,'registered_at':now().isoformat()})
    db.set_setting('forward_state_fixture_study',{'evidence_policy':'released_for_future_training_only'});assert not mature(db,d)

def test_independence_purges_overlaps_and_same_date_assets():
    t=now();rows=[{'decided_at':(t+timedelta(days=i)).isoformat(),'completed_at':(t+timedelta(days=i+5)).isoformat(),'net_return':.01} for i in range(12) for _ in range(100)]
    assert len(nonoverlapping(rows))==2;assert interval([.01]*5)['lower'] is None

def test_quote_book_full_cycle_and_isolation(db):
    t=now();a,snapshot=approved_fixture(db,t);p=PortfolioPolicy(horizon_sessions=1);d={'id':'fixture_book','registered_at':(t-timedelta(days=1)).isoformat(),'risk_policy':p.model_dump(),'criteria':QualificationCriteria().model_dump(),'universe':['BTC-USD'],'incumbent_ids':[]};b=ComparisonBook(db,d,'candidate');c=snapshot['rows'][0]
    def step(at,price=100,depth=1000):
        q={'symbol':a['symbol'],'bid':price,'ask':price+.01,'bid_size':depth,'ask_size':depth,'timestamp':at.isoformat(),'observed_at':at.isoformat(),'depth_units':'base_units'};return b.step(at,{a['symbol']:q},{a['symbol']:c},{a['symbol']:a},{})
    assert len(step(t)['orders'])==1
    assert step(t+timedelta(seconds=6))['positions']
    assert any(o['side']=='sell' for o in step(t+timedelta(days=1,seconds=6),105)['orders'])
    assert not step(t+timedelta(days=1,seconds=12),105)['positions']
    out=db.records('qualification_outcome');assert len(out)==1 and out[0]['payload']['realized_pnl']>0
    assert not db.records('auto_fill') and not db.records('manual_fill') and not db.records('forward_fill')
    assert not db.setting('model_paper_account') and not db.setting('manual_paper')

def test_historical_replay_without_quotes_never_manufactures_fills(db):
    t=now();a,s=approved_fixture(db,t);db.put('auto_snapshot',s,record_id='fixture_snapshot',available_at=t.isoformat());r=replay(db)
    assert r['trace_count']==1 and r['fills']==0 and r['orders']==0 and r['scope']=='historical_debug_only'
    assert not db.records('qualification_sample') and not db.records('manual_fill') and not db.records('auto_fill')

def test_controlled_release_requires_retirement_and_age(db):
    d=definition(db);observations(db,d,3);req=TrainingRelease(definition_id=d['id'],reason='Explicit test-only mature cohort release',confirmation='RETIRE EVALUATION AND RELEASE AGED SAMPLES')
    with pytest.raises(ValueError,match='Retire'):release(db,req)
    db.set_setting('forward_state_fixture_study',{'state':'retired','evidence_policy':'quarantined_evaluation','symbol':'BTC-USD'})
    result=release(db,req);assert not result['automatic_training'] and not result['evaluation_eligible'];assert not mature(db,d)

def test_no_external_or_llm_imports():
    import ast
    from pathlib import Path
    for path in Path('backend/qualification').glob('*.py'):
        imports=[n.module for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.ImportFrom)]
        assert not any(v and (v.startswith('backend.execution') or v.startswith('backend.llm')) for v in imports)


def test_frozen_implementation_and_forged_approval_fail_closed(db):
    d=definition(db);observations(db,d);p=portfolio(db,d)
    result=evaluate(db,{**d,'implementation_hash':'changed'},p)
    assert result['state']=='RESEARCH_ONLY'
    db.set_setting('qstatus_'+stable_hash(d['model_id'])[:32],{'definition_id':d['id'],'state':'QUALIFIED_FOR_MODEL_PAPER','execution_allowed':True,'criteria_hash':d['criteria_hash'],'at':now().isoformat()})
    assert SelectionRegistry(db).refresh()['eligible']==0

def test_forward_quote_future_and_partial_execution(db):
    t=now();a,s=approved_fixture(db,t);d={'id':'partial_fixture','registered_at':(t-timedelta(days=1)).isoformat(),'risk_policy':PortfolioPolicy().model_dump(),'criteria':QualificationCriteria().model_dump(),'universe':[a['symbol']],'incumbent_ids':[]};b=ComparisonBook(db,d,'candidate')
    def q(at):return {'symbol':a['symbol'],'bid':100.,'ask':100.01,'bid_size':1.,'ask_size':1.,'timestamp':at.isoformat(),'observed_at':at.isoformat(),'depth_units':'base_units'}
    assert not b.step(t,{a['symbol']:q(t+timedelta(seconds=10))},{a['symbol']:s['rows'][0]},{a['symbol']:a},{})['orders']
    b.step(t,{a['symbol']:q(t)},{a['symbol']:s['rows'][0]},{a['symbol']:a},{})
    view=b.step(t+timedelta(seconds=6),{a['symbol']:q(t+timedelta(seconds=6))},{a['symbol']:s['rows'][0]},{a['symbol']:a},{})
    assert view['orders'][0]['status']=='PARTIALLY_FILLED'
    assert view['fills'][0]['quantity']==pytest.approx(.05)

def test_after_registration_feature_timestamps_required(db):
    d=definition(db);observations(db,d,1)
    # Immutable source alteration is simulated by a new preregistration boundary only.
    future={**d,'registered_at':(now()+timedelta(days=1)).isoformat()}
    assert not mature(db,future)

def test_quarantine_blocks_young_completed_source(db):
    d=definition(db);d['registered_at']=(now()-timedelta(days=20)).isoformat();observations(db,d,1)
    db.set_setting('forward_state_fixture_study',{'state':'retired','evidence_policy':'quarantined_evaluation','symbol':'BTC-USD'})
    req=TrainingRelease(definition_id=d['id'],reason='Attempted release of a too-young test cohort',confirmation='RETIRE EVALUATION AND RELEASE AGED SAMPLES')
    with pytest.raises(ValueError,match='90-day'):release(db,req)


def test_missing_feature_context_is_numeric_and_fail_closed(db):
    t=now();a,s=approved_fixture(db,t);mid=s['rows'][0]['votes'][0]['model_id'];artifact=db.get(mid)['payload'];artifact={**artifact,'family':'momentum'}
    # Saved models are immutable; use a separate regression artifact.
    mid='missing_feature_model';artifact['id']=mid;db.put('strategy_model',artifact,record_id=mid)
    d={'model_ids':[mid],'model_hashes':{mid:stable_hash(artifact)},'risk_policy':PortfolioPolicy().model_dump(),'universe':[a['symbol']],'implementation_hash':implementation_hash()}
    for vote in s['rows'][0]['votes']:vote['features']={'return_20':None}
    c=QualificationEngine(db).contexts(d,s,t)[a['symbol']]
    assert not c['trade_eligible'];assert 'Required feature missing/schema invalid' in c['votes'][0]['health']


def test_registration_upgrade_preserves_original_cohort(db,monkeypatch):
    import backend.qualification.studies as studies
    from test_selection import inputs
    d=definition(db);a,_,_=inputs();row={'id':d['model_id'],'source_kind':'strategy_model','family':'momentum','asset_class':'crypto','artifact_hash':d['model_hash'],'dependence_group':'price_trend','eligibility':'challenger_blocked','validation':{}}
    registry={'rows':[row]};first=studies.register(db,registry,[a])[0];saved=db.get(first['id'])['payload']
    monkeypatch.setattr(studies,'implementation_hash',lambda:'new-implementation')
    second=studies.register(db,registry,[a])[0]
    assert second['id']!=first['id'];assert db.get(first['id'])['payload']==saved
    assert db.get(first['id']+'_enrollment')['payload']['study_ids']==db.get(second['id']+'_enrollment')['payload']['study_ids']
    assert db.setting('qcurrent_'+stable_hash(d['model_id'])[:32])==second['id']


def test_replay_keeps_missing_data_in_diagnostic_trace(db):
    t=now();a,s=approved_fixture(db,t);s['rows'][0]['feature_available_at']=None;db.put('auto_snapshot',s,record_id='missing_snapshot',available_at=t.isoformat());r=replay(db)
    assert r['trace_count']==1 and r['statuses']['DATA_UNAVAILABLE']==1 and r['fills']==0


def test_any_source_training_release_revokes_paper_authorization(db):
    from backend.qualification.integrity import paper_authorized
    test_full_source_qualification_and_registry_path(db)
    # Restore a current review after the positive-path test's deliberately changed-artifact check.
    d=db.get('qualification_'+stable_hash('fixture_model'))['payload'];QualificationEngine(db).review()
    assert paper_authorized(db,d['model_id'],d['model_hash']) is True
    db.set_setting('forward_state_fixture_study',{'state':'retired','evidence_policy':'released_for_future_training_only'})
    assert paper_authorized(db,d['model_id'],d['model_hash']) is False
    assert SelectionRegistry(db).refresh()['eligible']==0
    assert not QualificationEngine(db).review()['rows'][0]['execution_allowed']
