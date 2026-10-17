from datetime import timedelta
import numpy as np
import pandas as pd
import pytest
from test_platform import db
from backend.schemas.contracts import Bar,now
from backend.research.features import market_frame,build_frame,select_features
from backend.research.studies import Studies,StudyRequest,folds,targets

@pytest.fixture
def history(db):
    rng=np.random.default_rng(81);n=600;close=100*np.exp(np.cumsum(rng.normal(0,.015,n)));start=now()-timedelta(days=n+1)
    rows=[]
    for i,c in enumerate(close):
        opening=float(close[max(0,i-1)]);bar=Bar(symbol='BTC-USD',provider='fixture',timestamp=start+timedelta(days=i),available_at=start+timedelta(days=i+1),observed_at=now(),open=opening,high=max(opening,c)*1.01,low=min(opening,c)*.99,close=float(c),volume=float(rng.uniform(1000,3000))).model_dump(mode='json')
        db.put('bar',bar,'BTC-USD');rows.append(bar)
    return rows

def test_features_do_not_change_when_future_is_perturbed(history):
    before=market_frame(history)[1]
    after=[dict(r) for r in history]
    for r in after[-30:]:
        for k in ('open','high','low','close'):r[k]*=4
        r['volume']*=20
    pd.testing.assert_frame_equal(before.iloc[:-30],market_frame(after)[1].iloc[:-30])

def test_fold_purging_and_nonoverlap():
    for h in [1,5,10]:
        for fit,cal,val in folds(900,h):
            assert fit[-1]+h+1<cal[0] and cal[-1]+h+1<val[0]
            assert np.all(np.diff(val)>h)

def test_training_only_feature_filters():
    x=pd.DataFrame({'a':np.arange(100.),'redundant':np.arange(100.)*2,'late':[np.nan]*80+[1.]*20,'flat':[2.]*100})
    included,medians,excluded=select_features(x,{n:'price' for n in x},range(70),['price'])
    assert included==['a'] and medians['a']==34.5
    assert 'coverage' in excluded['late'] and 'correlated' in excluded['redundant']

def test_macro_release_and_cross_asset_alignment(db,history):
    release=pd.Timestamp(history[300]['timestamp']).date().isoformat()
    db.put('macro_initial',{'observations':[{'date':release,'realtime_start':release,'value':'5'}]},'UNRATE')
    df,x,g,_=build_frame(db,'BTC-USD')
    first=(pd.Timestamp(release)+pd.Timedelta(days=1)).tz_localize('America/New_York').tz_convert('UTC')
    assert x.loc[pd.to_datetime(df.available_at,utc=True)<first,'macro_UNRATE'].isna().all()
    assert x.loc[(pd.to_datetime(df.available_at,utc=True)>=first)&(pd.to_datetime(df.available_at,utc=True)<first+pd.Timedelta(days=99)),'macro_UNRATE'].eq(5).all()
    # Newly observed funding does not become invented historical history.
    db.put('crypto',{'provider':'hyperliquid','observed_at':now().isoformat(),'funding':.01,'open_interest':123,'mark_price':100,'oracle_price':99},'BTC')
    assert build_frame(db,'BTC-USD')[1].crypto_funding.isna().all()

def test_study_is_reproducible_holdout_locked_and_release_idempotent(db,history,monkeypatch):
    import backend.research.studies as module
    monkeypatch.setattr(module,'CONFIGS',[module.CONFIGS[0]])
    service=Studies(db);request=StudyRequest(horizons=[5]);r=service.run(request)
    assert r['holdout']=={'status':'LOCKED'} and r['promotion_eligible'] is False
    assert len(db.records('ml_trial'))==3
    assert service.run(request)['id']==r['id'] and len(db.records('ml_trial'))==3
    out=service.release(r['id']);assert out['holdout']['status']=='RELEASED_ONCE'
    assert service.release(r['id'])['holdout']==out['holdout']
    assert out['holdout']['gates']['future_validation_required'] is False
    assert out['holdout']['metrics']['samples']<200
    assert not db.records('candidate') and not db.records('order')

def test_target_next_open_delay_and_horizon(history):
    df=pd.DataFrame(history);y,labels,vol=targets(df,5,.0022)
    assert y.iloc[100]==pytest.approx(df.open.iloc[107]/df.open.iloc[102]-1)
    assert labels['after_cost'].iloc[100]==int(y.iloc[100]>.0022)
    assert vol.iloc[100]>=0

def test_future_holdout_changes_cannot_change_development_selection(db,history,monkeypatch):
    import backend.research.studies as module
    monkeypatch.setattr(module,'CONFIGS',[module.CONFIGS[0]])
    service=Studies(db);request=StudyRequest(horizons=[5]);before=service.run(request)
    for i,row in enumerate(history[500:]):
        changed={**row,'observed_at':now().isoformat()}
        for key in ['open','high','low','close']:changed[key]*=3
        db.put('bar',changed,'BTC-USD')
    after=service.run(request)
    assert before['selected']==after['selected']
    assert before['features']==after['features']
    assert before['ablations']==after['ablations']

def test_study_lease_blocks_duplicate_concurrent_work(db,history):
    from backend.research.features import stable_hash
    db.set_setting('study_lease_'+stable_hash('BTC-USD')[:32],{'token':'other','until':(now()+timedelta(minutes=1)).isoformat()})
    with pytest.raises(ValueError,match='already running'):Studies(db).run(StudyRequest())


def test_peer_alignment_never_uses_later_available_bar(db,history):
    for row in history:
        peer={**row,'symbol':'ETH-USD','available_at':(pd.Timestamp(row['available_at'])+pd.Timedelta(hours=1)).isoformat()}
        db.put('bar',peer,'ETH-USD')
    df,x,_,_=build_frame(db,'BTC-USD')
    # The otherwise identical peer releases an hour later, so only yesterday's momentum is known.
    expected=x.return_20-x.return_20.shift(1)
    np.testing.assert_allclose(x.cross_ETH_USD_relative_momentum.iloc[65:],expected.iloc[65:],rtol=1e-12,atol=1e-12)


def test_simulation_charges_both_sides_and_respects_unavailable_signal(history):
    from backend.research.studies import simulate
    df=pd.DataFrame(history);cost=.0011
    out=simulate(df,[100],[True],5,cost)
    assert out['trades']==1 and out['turnover']==2
    assert out['total_return']==pytest.approx(df.open.iloc[107]/df.open.iloc[102]*(1-cost)/(1+cost)-1)
    df.loc[100,'available_at']=df.iloc[108].timestamp
    assert simulate(df,[100],[True],5,cost)['trades']==0


def test_internal_holdout_input_not_available_through_generic_routes(db):
    from fastapi.testclient import TestClient
    from backend.api.main import create_app
    db.put('ml_study_input',{'matrix':[[123]]},record_id='private-study-input')
    with TestClient(create_app(db,start_workers=False)) as client:
        assert client.get('/api/v1/records/ml_study_input').status_code==403
        assert client.get('/api/v1/evidence/private-study-input').status_code==403


def test_historical_close_remains_distinct_from_an_executable_quote(db,history):
    from fastapi.testclient import TestClient
    from backend.api.main import create_app
    with TestClient(create_app(db,start_workers=False)) as client:
        result=client.get('/api/v1/assets/BTC-USD').json()
        assert result['quote'] is None
        assert result['bars'][-1]['close']==history[-1]['close']
        assert not db.records('quote','BTC-USD')
