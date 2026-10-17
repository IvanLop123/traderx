from datetime import datetime,timedelta,timezone
import pytest
from backend.research.replay import ReplayInstrument,ReplayEvent,ReplayIntent,ReplayRequest,EventReplay
T=datetime(2025,1,1,tzinfo=timezone.utc)

def instrument(symbol='TEST',**kwargs):return ReplayInstrument(symbol=symbol,asset_class=kwargs.pop('asset_class','stock'),eligible_from=T,**kwargs)
def quote(n,symbol='TEST',price=100,volume=100):return ReplayEvent(id=f'q-{symbol}-{n}',symbol=symbol,kind='quote',event_at=T+timedelta(seconds=n),available_at=T+timedelta(seconds=n),bid=price,ask=price,volume=volume,source_reference='fixture')
def intent(n=0,symbol='TEST',qty=3,**kwargs):return ReplayIntent(id='o-'+symbol,symbol=symbol,side=kwargs.pop('side','buy'),quantity=qty,limit_price=kwargs.pop('limit_price',101),decided_at=T+timedelta(seconds=n),evidence_available_at=T,expires_at=T+timedelta(days=2),**kwargs)
def action(kind,n,value,symbol='TEST'):return ReplayEvent(id=f'{kind}-{symbol}-{n}',symbol=symbol,kind=kind,event_at=T+timedelta(seconds=n),available_at=T+timedelta(seconds=n),source_reference='fixture',value=value)
def run(instruments,events,intents):return EventReplay(ReplayRequest(instruments=instruments,events=events,intents=intents,fee_bps=0,slippage_bps=0)).run()

def test_latency_partial_fills_and_no_same_tick_execution():
    result=run([instrument()],[quote(0),quote(1),quote(2),quote(3)],[intent()])
    assert [f['quantity'] for f in result['fills']]==[1,1,1]
    assert result['fills'][0]['timestamp']==(T+timedelta(seconds=1)).isoformat()
    assert result['cash']==99700 and result['orders'][0]['status']=='filled'

def test_future_evidence_and_late_liquidity_rejected():
    with pytest.raises(ValueError,match='future evidence'):intent().model_copy() and ReplayIntent(**{**intent().model_dump(),'evidence_available_at':T+timedelta(seconds=1)})
    q=quote(1);q.available_at=T+timedelta(days=1)
    result=run([instrument()],[quote(0),q],[intent()])
    assert result['fills']==[]

def test_split_and_dividend_conserve_equity():
    result=run([instrument()],[quote(0),quote(1,volume=300),action('split',2,2),quote(3,price=50),action('dividend',4,1)],[intent()])
    assert result['positions']['TEST']['quantity']==6
    assert result['cash']==99706 and result['curve'][-1]['equity']==100006

def test_expiry_requires_settlement_and_binary_payout():
    i=instrument(asset_class='prediction',expiry=T+timedelta(seconds=3))
    order=intent(qty=2,limit_price=.6)
    with pytest.raises(ValueError,match='no explicit'):run([i],[quote(0,price=.5),quote(1,price=.5,volume=200),quote(4,price=.5)],[order])
    r=run([i],[quote(0,price=.5),quote(1,price=.5,volume=200),action('settlement',3,1)],[order])
    assert r['cash']==100001 and not r['positions']
    with pytest.raises(ValueError,match='payout'):run([i],[quote(0,price=.5),action('settlement',3,2)],[])

def test_option_cash_and_physical_exercise():
    i=instrument('CALL',asset_class='option',expiry=T+timedelta(seconds=3),strike=100,option_type='call',underlying='TEST',multiplier=100)
    events=[quote(0,'CALL',price=2),quote(1,'CALL',price=2,volume=100),action('exercise',3,110,'CALL')]
    order=intent(symbol='CALL',qty=1,limit_price=2.1)
    r=run([i],events,[order]);assert r['cash']==100800 and not r['positions']
    i.settlement='physical';r=run([instrument(),i],events,[order]);assert r['cash']==89800 and r['positions']['TEST']['quantity']==100

def test_funding_charges_existing_position_without_external_calls():
    i=instrument(asset_class='perpetual');r=run([i],[quote(0),quote(1,volume=300),action('funding',2,.01)],[intent()])
    assert r['cash']==99697 and r['curve'][-1]['equity']==99997

def test_membership_and_sell_limit_are_enforced():
    i=instrument(eligible_until=T+timedelta(seconds=1))
    r=run([i],[quote(0),quote(1)],[intent()]);assert r['fills']==[] and r['orders'][0]['status']=='canceled_universe_or_expiry'
    r=run([instrument()],[quote(0),quote(1)],[intent(side='sell')]);assert r['fills']==[]

def test_duplicate_event_and_late_corporate_action_fail():
    with pytest.raises(ValueError,match='Duplicate event'):run([instrument()],[quote(0),quote(0)],[])
    a=action('split',1,2);a.available_at=T+timedelta(seconds=2)
    with pytest.raises(ValueError,match='effective time'):run([instrument()],[quote(0),a],[])


def test_cash_contract_multipliers_and_unfunded_charges_rejected():
    with pytest.raises(ValueError,match='unit multiplier'):instrument(multiplier=100)
    with pytest.raises(ValueError,match='exceeds free cash'):run([instrument()],[quote(0),quote(1),action('borrow',2,200000)],[intent()])
