from datetime import timedelta
import math
import pytest
from backend.storage.database import Database,Base
from backend.risk.engine import PaperEngine
from backend.risk.analytics import portfolio_risk
from backend.risk.sizing import SizingRequest,position_size
from backend.schemas.contracts import now

@pytest.fixture
def context(tmp_path):
    db=Database('sqlite:///'+str(tmp_path/'risk.db'));Base.metadata.create_all(db.engine)
    return db,PaperEngine(db)

def test_missing_history_is_unavailable_not_zero(context):
    db,p=context;s=p.initial();s['positions']={'AAPL':{'quantity':10,'market_price':100,'average_cost':100,'asset_class':'stock'}}
    r=portfolio_risk(db,s,p.limits)
    assert r['annualized_volatility'] is None and not r['covariance_available']
    assert r['sector_fractions']['Technology']==.01
    assert r['stress_scenarios'][0]['estimated_pnl']==-200

def test_synchronized_covariance_correlated_groups_and_tail_loss(context):
    db,p=context;s=p.initial();s['positions']={v:{'quantity':50,'market_price':100,'average_cost':100,'asset_class':'stock'} for v in ['AAPL','MSFT']}
    for symbol in s['positions']:
        price=100
        for i in range(90):
            t=now()-timedelta(days=100-i);price*=1+math.sin(i)*.02
            db.put('bar',{'timestamp':t.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),'available_at':t.isoformat(),'close':price,'interval_seconds':86400},symbol)
    r=portfolio_risk(db,s,p.limits)
    assert r['covariance_available'] and r['annualized_volatility']>0
    assert r['historical_daily_expected_shortfall_95_usd']>=r['historical_daily_var_95_usd']>0
    assert r['correlated_groups']==[{'symbols':['AAPL','MSFT'],'gross_fraction':.1}]

def test_sizing_caps_cash_and_never_negative_kelly(context):
    _,p=context
    r=position_size(SizingRequest(method='volatility_target',equity=100000,price=100,available_cash=500,annual_volatility=.01),p.limits)
    assert r['capped_fraction']==.1 and 0<r['notional']<500
    r=position_size(SizingRequest(method='fractional_kelly',equity=100000,price=100,available_cash=100000,probability_win=.2,win_loss_ratio=1),p.limits)
    assert r['quantity']==0
    with pytest.raises(ValueError):position_size(SizingRequest(method='risk_budget',equity=1000,price=10,available_cash=1000),p.limits)

def test_invalid_mark_halts_without_poisoning_account(context):
    db,p=context;s=p.initial();s['kill_switch']=False;s['positions']={'AAPL':{'quantity':1,'market_price':100,'average_cost':100,'asset_class':'stock'}};db.set_setting('portfolio',s)
    for bad in [float('nan'),0,'invalid']:
        r=p.mark({'AAPL':{'price':bad}})
        assert r['kill_switch'] and r['positions']['AAPL']['market_price']==100 and math.isfinite(r['equity'])
