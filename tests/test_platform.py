from datetime import timedelta
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.schemas.contracts import *
from backend.storage.database import Database, Base
from backend.intelligence.quant import black_scholes, parity
from backend.intelligence.documents import parse_form4, parse_13f, question_answer
from backend.research.engine import backtest, train_fusion, fdr
from backend.risk.engine import PaperEngine
from backend.api.main import create_app

@pytest.fixture
def db(tmp_path):
    d=Database('sqlite:///'+str(tmp_path/'test.db')); Base.metadata.create_all(d.engine); return d

@pytest.fixture
def bars():
    start=now()-timedelta(days=301); rng=np.random.default_rng(8); closes=100*np.exp(np.cumsum(rng.normal(.001,.02,300)))
    return [Bar(symbol='BTC-USD',provider='fixture',timestamp=start+timedelta(days=i),available_at=start+timedelta(days=i+1),
                observed_at=now(),open=float(closes[max(0,i-1)]),high=float(max(closes[i],closes[max(0,i-1)])*1.01),
                low=float(min(closes[i],closes[max(0,i-1)])*.99),close=float(closes[i]),volume=float(rng.uniform(10000,20000))).model_dump(mode='json') for i in range(300)]

def candidate(**changes):
    values=dict(asset=AssetIdentifier(symbol='BTC-USD'),prediction_id='fixture',direction='buy',horizon='1d',entry_price=100,
                quantity=1,expected_edge=.03,expected_costs=.001,expected_downside=-.02,confidence=.7,evidence_ids=['fixture'],expires_at=now()+timedelta(minutes=5),liquidity={})
    return TradeCandidate(**(values|changes))

def quote(**changes): return dict(price=100,bid=99.99,ask=100.01,volume=10000,timestamp=now().isoformat())|changes

def test_pit_contract():
    t=now(); e=Event(source='fixture',provider='fixture',event_type='filing',event_at=t-timedelta(days=30),published_at=t,
                    first_observed_at=t+timedelta(hours=1),ingested_at=t+timedelta(hours=2),processed_at=t+timedelta(hours=3),source_reference='fixture')
    assert e.available_at()==t+timedelta(hours=3)
    with pytest.raises(ValueError): Bar(symbol='X',provider='fixture',timestamp=t,available_at=t,open=100,close=90,low=95,high=101,volume=10)

def test_backtest_costs_determinism_and_latency(bars):
    a=backtest(bars); b=backtest(bars)
    assert a==b and a['total_cost']>0
    zero=backtest(bars,fee_bps=0,slippage_bps=0,spread_bps=0)
    assert a['metrics']['total_return']<zero['metrics']['total_return']
    for fill in a['fills']:
        if 'signal_timestamp' in fill: assert fill['signal_timestamp']<fill['timestamp']
    strict=backtest(bars,strict_observed=True)
    assert len(strict['fills'])==0
    with pytest.raises(ValueError): backtest(bars,latency_bars=0)

def test_future_change_does_not_change_past(bars):
    original=backtest(bars)
    revised=[dict(b) for b in bars]; revised[-1]['close']*=1.3; revised[-1]['high']*=1.3
    result=backtest(revised)
    assert original['curve'][:-1]==result['curve'][:-1]

def test_training_splits_purged(bars):
    result=train_fusion(bars,5); s=result['splits']
    assert s['training']['end']<s['validation']['start']<s['holdout']['start']
    assert 0<=result['holdout_brier']<=1
    assert set(result['prediction']['contributions'])==set(result['features'])
    assert fdr([.001,.03,.8])[0]==pytest.approx(.003)

def test_options_math():
    c=black_scholes(100,100,1,.05,.2); p=black_scholes(100,100,1,.05,.2,'put')
    assert c['price']==pytest.approx(10.45058357)
    assert c['price']-p['price']==pytest.approx(100-100*np.exp(-.05))
    assert c['gamma']>0 and p['delta']<0

def test_risk_halt_and_bypass(db):
    engine=PaperEngine(db); c=candidate(); db.put('candidate',c)
    assert isinstance(engine.assess(c,quote()),RejectedOrder)
    with pytest.raises(TypeError): engine.execute(c,quote())
    fake=ApprovedOrder(candidate_id=c.id,assessment_id='fake',asset=c.asset,side='buy',quantity=1,limit_price=101,expires_at=c.expires_at)
    with pytest.raises(ValueError): engine.execute(fake,quote())

def test_risk_execution_idempotent_and_recheck(db):
    engine=PaperEngine(db); engine.halt(False); c=candidate(); db.put('candidate',c)
    approved=engine.assess(c,quote()); assert isinstance(approved,ApprovedOrder)
    engine.halt(True)
    with pytest.raises(ValueError,match='KILL_SWITCH'): engine.execute(approved,quote())
    engine.halt(False)
    fill=engine.execute(approved,quote()); cash=engine.snapshot()['cash']
    assert engine.execute(approved,quote())==fill
    assert engine.snapshot()['cash']==cash<100000
    assert fill['fee']>0

@pytest.mark.parametrize('changes,reason',[(dict(quantity=200),'POSITION_CONCENTRATION'),(dict(expires_at=now()-timedelta(seconds=1)),'CANDIDATE_EXPIRED')])
def test_risk_limits(db,changes,reason):
    engine=PaperEngine(db); engine.halt(False); c=candidate(**changes); db.put('candidate',c)
    r=engine.assess(c,quote()); assert reason in r.reasons

def test_provider_failure_no_ai_crash(db):
    app=create_app(db,start_workers=False)
    with TestClient(app) as client:
        assert client.get('/api/v1/health').status_code==200
        h={'X-TraderX-Client':'local-ui'}
        assert client.post('/api/v1/chat',json={'message':'Explain earnings'},headers=h).json()['status']=='DISABLED'
        assert client.get('/api/v1/portfolio').json()['cash']==100000
        assert client.post('/api/v1/risk/halt',json={'halted':False}).status_code==403
        assert client.post('/api/v1/risk/halt',json={'halted':False},headers={**h,'Origin':'https://attacker.example'}).status_code==403
        assert client.post('/api/v1/providers/fetch',json={'provider':'fred'},headers=h).status_code==503
        assert client.post('/api/v1/orders/fake/execute',headers=h).status_code==409
        assert client.get('/api/v1/health').json()['live_trading'] is False

def test_form4_and_xml_security():
    xml='<ownershipDocument><nonDerivativeTransaction><transactionCoding><transactionCode>P</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>20</value></transactionShares><transactionPricePerShare><value>10</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction></ownershipDocument>'
    assert parse_form4(xml)[0]['value']==200
    with pytest.raises(Exception): parse_form4('<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><x>&y;</x>')

def test_document_dedup_and_settings(db):
    with TestClient(create_app(db,start_workers=False)) as c:
        headers={'X-TraderX-Client':'local-ui'}; doc={'title':'fixture','text':'Nuclear capacity constraints delay reactor launch.','source_reference':'fixture://doc','kind':'transcript'}
        a=c.post('/api/v1/documents',json=doc,headers=headers).json(); b=c.post('/api/v1/documents',json=doc,headers=headers).json()
        assert a['id']==b['id'] and len(c.get('/api/v1/records/document').json())==1
        assert c.get('/api/v1/records/theme').json()[0]['payload']['edges'][0]['evidence_id']==a['id']
        assert 'OPENAI_API_KEY' not in c.get('/api/v1/settings/ai').text

def test_saved_model_reproducible_without_training(bars):
    from backend.research.engine import infer_registered
    model=train_fusion(bars,3)
    prediction=infer_registered(json.loads(json.dumps(model)),bars)
    for name in ['expected_return','probability_positive','expected_volatility','uncertainty']:
        assert prediction[name]==pytest.approx(model['prediction'][name])

def test_probability_uncertainty_and_costs():
    from backend.intelligence.prediction_markets import probability_from_outcomes,opportunity
    fair=probability_from_outcomes(7,10,['fixture'])
    result=opportunity('TEST',.6,fair,.02,100,now()+timedelta(days=1))
    assert result.estimated_net_edge<result.raw_edge
    assert fair.lower<fair.probability<fair.upper

def test_point_in_time_join_blocks_late_and_revised_information():
    from backend.research.point_in_time import join_features_asof
    t=now(); times=[t-timedelta(days=2),t-timedelta(days=1),t]
    records=[{'available_at':(t-timedelta(hours=1)).isoformat(),'payload':{'name':'insider','value':10,'available_at':(t-timedelta(hours=1)).isoformat()}},
             {'available_at':(t+timedelta(days=1)).isoformat(),'payload':{'name':'insider','value':999,'available_at':(t+timedelta(days=1)).isoformat()}}]
    joined=join_features_asof(times,records)
    assert joined.insider.iloc[:2].isna().all()
    assert joined.insider.iloc[-1]==10

def test_strategy_comparison_uses_only_past_weights(bars):
    from backend.research.robustness import compare_strategies,weights_for
    import pandas as pd
    result=compare_strategies(bars)
    assert len(result['strategies'])==6 and len(result['walk_forward_folds'])==3
    assert result['deployment_status']=='RESEARCH_ONLY'
    for fold in result['walk_forward_folds']:assert fold['train_end']<fold['test_start']<result['split']['holdout_start']
    for strategy in ['momentum_20','multi_horizon_trend','volatility_target_trend','mean_reversion']:
        first=weights_for(pd.DataFrame(bars),strategy)
        altered=[dict(b) for b in bars];altered[-1]['close']*=10
        second=weights_for(pd.DataFrame(altered),strategy)
        assert np.allclose(first.iloc[:-1],second.iloc[:-1])
    cash=next(r for r in result['strategies'] if r['strategy']=='cash')
    assert cash['holdout']['total_return']==0

def test_paper_round_trip_reconciles_both_entry_and_exit_fees(db):
    engine=PaperEngine(db);engine.halt(False)
    buy=candidate();db.put('candidate',buy,buy.asset.symbol)
    engine.execute(engine.assess(buy,quote()),quote())
    sell=candidate(direction='sell');db.put('candidate',sell,sell.asset.symbol)
    engine.execute(engine.assess(sell,quote()),quote())
    state=engine.snapshot()
    assert state['positions']=={}
    assert state['realized_pnl']==pytest.approx(state['equity']-state['initial_cash'])
    assert state['fees']>0

@pytest.mark.parametrize('change',[{'price':float('nan')},{'bid':float('inf')},{'volume':float('nan')},{'timestamp':'invalid'}])
def test_invalid_quote_fails_closed(db,change):
    engine=PaperEngine(db);engine.halt(False);c=candidate();db.put('candidate',c,c.asset.symbol)
    assert engine.assess(c,quote(**change)).reasons

def test_research_empty_or_intraday_is_explicit(bars):
    with pytest.raises(ValueError,match='No completed'):backtest([])
    for b in bars:b['interval_seconds']=60
    with pytest.raises(ValueError,match='daily'):backtest(bars)

def test_small_sample_cannot_generate_research_candidate(bars):
    result=train_fusion(bars,5)
    assert result['research_candidate_gates']['holdout_at_least_200'] is False
    assert result['research_candidate_eligible'] is False
    assert result['holdout_zero_forecast_mse']>0

def test_ui_exit_path_requires_risk_and_closes_only_internal_paper(db):
    engine=PaperEngine(db);engine.halt(False)
    buy=candidate();db.put('candidate',buy,buy.asset.symbol)
    engine.execute(engine.assess(buy,quote()),quote())
    db.put('quote',quote(),'BTC-USD');db.set_setting('provider_coinbase',{'status':'WORKING_READ_ONLY'})
    with TestClient(create_app(db,start_workers=False)) as client:
        headers={'X-TraderX-Client':'local-ui'}
        request=client.post('/api/v1/portfolio/BTC-USD/close-candidate',json={},headers=headers)
        assert request.status_code==200 and request.json()['status']=='RISK_REVIEW_REQUIRED'
        cid=request.json()['candidate_id']
        approved=client.post('/api/v1/candidates/'+cid+'/assess',json={},headers=headers)
        assert approved.status_code==200 and approved.json()['venue']=='internal_paper'
        order=client.post('/api/v1/orders/'+approved.json()['id']+'/execute',json={},headers=headers)
        assert order.json()['status']=='filled'
        assert client.get('/api/v1/portfolio').json()['positions']=={}
        assert client.get('/api/v1/settings/ai').json()['usage']['calls']==0
