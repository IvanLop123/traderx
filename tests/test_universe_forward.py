from datetime import timedelta
import json
import pandas as pd
import numpy as np
import pytest
from test_platform import db
from backend.schemas.contracts import now,Bar
from backend.research.universe import Instrument,Eligibility,Universe,eligible_at
from backend.research.history import HistoryStore,total_return
from backend.research.forward import ForwardStudies,ForwardPolicy,EnrollRequest,ReleaseRequest,quote_check
from backend.research.features import stable_hash

@pytest.fixture
def series():
    start=now()-timedelta(days=301)
    return [Bar(symbol='AAPL',provider='fixture',timestamp=start+timedelta(days=i),available_at=start+timedelta(days=i+1),open=100,high=101,low=99,close=100,volume=100000).model_dump(mode='json') for i in range(300)]

def test_adjusted_series_are_isolated_idempotent_and_checked(db,tmp_path,series):
    store=HistoryStore(db,tmp_path);raw=store.save('AAPL','fixture',series);adjusted=[{**r,'open':50,'close':50,'high':50.5,'low':49.5,'volume':200000} for r in series]
    adj=store.save('AAPL','fixture',adjusted,adjustment='all')
    assert raw['id']!=adj['id'] and store.read('AAPL','raw')[0]['close']==100 and store.read('AAPL')[0]['close']==50
    assert store.save('AAPL','fixture',series)['id']==raw['id']
    path=tmp_path/(raw['hash']+'.parquet');path.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):store.read('AAPL','raw')

def test_conflicting_duplicate_and_incomplete_bars_rejected(db,tmp_path,series):
    store=HistoryStore(db,tmp_path)
    with pytest.raises(ValueError,match='duplicate'):store.save('AAPL','fixture',[series[0],{**series[0],'volume':123}])
    with pytest.raises(ValueError,match='Incomplete'):store.save('AAPL','fixture',[{**series[0],'available_at':series[0]['timestamp']}])
    assert store.save('AAPL','fixture',[series[0],series[0]])['count']==1

def test_split_dividend_return_and_no_action_equivalence():
    assert total_return(100,50,split_ratio=2)==0
    assert total_return(100,49,split_ratio=2,cash_dividend=1)==0
    assert total_return(100,110)==pytest.approx(.1)
    with pytest.raises(ValueError):total_return(100,50,split_ratio=0)

def test_universe_is_trailing_only_and_unknown_spread_is_not_executable(series):
    inst=Instrument(symbol='AAPL',asset_class='stock');days=[r['timestamp'] for r in series];at=pd.Timestamp(series[270]['available_at'])
    result=eligible_at(inst,series,at,Eligibility(),expected_sessions=days)
    assert result['eligible'] and not result['executable'] and 'Spread unavailable' in result['execution_reasons']
    altered=[dict(r) for r in series]
    for r in altered[271:]:r['close']=.001;r['volume']=0
    assert result==eligible_at(inst,altered,at,Eligibility(),expected_sessions=days)
    strict=eligible_at(inst,series,at,Eligibility(),expected_sessions=days,strict_membership=True)
    assert not strict['eligible'] and 'Historical membership' in strict['reasons'][0]

def test_universe_rejects_duplicate_and_false_archived_membership():
    with pytest.raises(ValueError):Universe(instruments=[Instrument(symbol='A',asset_class='stock')]*2)
    with pytest.raises(ValueError):Universe(instruments=[Instrument(symbol='A',asset_class='stock')],policy='archived_membership')

def enrolled(db,symbol='BTC-USD'):
    model={'symbol':symbol,'feature_families':['price'],'selected':{'horizon':1},'version':'test'};db.put('ml_study',model,symbol,record_id='test-model')
    service=ForwardStudies(db);state=service.enroll(EnrollRequest(model_id='test-model',policy=ForwardPolicy(entry_expiry_seconds=30)))
    at=now()+timedelta(seconds=1);prediction={'model_id':'test-model','model_hash':stable_hash(model),'symbol':symbol,'features':{'return_1':.01},'feature_available_at':at.isoformat(),'feature_families':['price'],'prediction':.05,'probability':.8,'probability_target':'positive','uncertainty':.01,'horizon':1,'regime':'uptrend','imputed_features':[]}
    service.decide(state['id'],prediction,at,{'eligible':True,'reasons':[]})
    return service,state,at,prediction

def q(at,bid=100,ask=101,size=20,symbol='BTC-USD'):
    return {'symbol':symbol,'timestamp':at.isoformat(),'observed_at':at.isoformat(),'bid':bid,'ask':ask,'bid_size':size,'ask_size':size,'depth_units':'base_units'}

def test_forward_delayed_partial_fill_no_repeated_depth_and_exit(db):
    service,state,at,pred=enrolled(db);sid=state['id'];policy=ForwardPolicy(maximum_spread_bps=200)
    # Keep the live policy tight; first wide spread is rejected.
    service.process_quote(sid,q(at+timedelta(seconds=6)),at+timedelta(seconds=6));assert not db.records('forward_fill')
    quote=q(at+timedelta(seconds=6),bid=100,ask=100.1)
    service.process_quote(sid,quote,at+timedelta(seconds=6));fills=db.records('forward_fill');assert len(fills)==1 and fills[0]['payload']['partial']
    assert fills[0]['payload']['quantity']==1 and fills[0]['payload']['price']>quote['ask']
    service.process_quote(sid,quote,at+timedelta(seconds=7));assert len(db.records('forward_fill'))==1
    exit_time=at+timedelta(days=1,seconds=7);service.process_quote(sid,q(exit_time,bid=102,ask=102.1),exit_time)
    outcomes=db.records('forward_outcome');assert len(outcomes)==1 and outcomes[0]['payload']['status']=='COMPLETED'
    assert outcomes[0]['payload']['realized_pnl']>0 and not db.records('order')
    assert db.setting('forward_state_'+sid)['cash']==pytest.approx(100000+outcomes[0]['payload']['realized_pnl'])

def test_missing_quote_expiry_gives_unfilled_not_fake_close(db):
    service,state,at,_=enrolled(db);service.process_quote(state['id'],{},at+timedelta(seconds=31))
    o=db.records('forward_outcome')[0]['payload'];assert o['status']=='UNFILLED' and o['realized_pnl']==0 and not db.records('forward_fill')

def test_cash_reasons_and_exact_features_are_saved(db):
    service,state,at,pred=enrolled(db)
    # Independent second book policy; do not mutate original decision.
    state2=service.enroll(EnrollRequest(model_id='test-model',policy=ForwardPolicy(initial_cash=20000)))
    later=now()+timedelta(seconds=3);pred.update(prediction=-.01,probability=.51,feature_available_at=later.isoformat())
    out=service.decide(state2['id'],pred,later,{'eligible':True,'reasons':[]})
    assert out['decision']=='CASH' and len(out['reasons'])==2 and out['features']=={'return_1':.01}
    assert service.decide(state2['id'],pred,later,{'eligible':True}) is None

def test_forward_rejects_future_features_and_changed_version(db):
    service,state,at,pred=enrolled(db);other=service.enroll(EnrollRequest(model_id='test-model',policy=ForwardPolicy(initial_cash=30000)))
    pred['feature_available_at']=(at+timedelta(days=1)).isoformat();assert service.decide(other['id'],pred,at,{'eligible':True}) is None
    pred['model_hash']='tampered'
    with pytest.raises(ValueError,match='identity'):service.decide(other['id'],pred,at,{'eligible':True})

def test_sessions_delay_timezone_and_depth_are_mandatory():
    at=pd.Timestamp('2026-11-27T18:01:00Z').to_pydatetime();decision={'symbol':'AAPL','decided_at':(at-timedelta(seconds=10)).isoformat()};sessions=[{'open':'2026-11-27T14:30:00Z','close':'2026-11-27T18:00:00Z'}]
    assert 'Market closed or calendar unavailable' in quote_check(q(at,symbol='AAPL',ask=100.1),decision,ForwardPolicy(),at,sessions,'stock')
    assert not quote_check(q(at,symbol='AAPL',ask=100.1),decision,ForwardPolicy(),at,[],'crypto')
    bad=q(at,symbol='AAPL');bad.pop('ask_size');assert quote_check(bad,decision,ForwardPolicy(),at,sessions,'stock')
    future=q(at+timedelta(seconds=1),symbol='AAPL',ask=100.1);assert 'Stale or future quote' in quote_check(future,decision,ForwardPolicy(),at,sessions,'stock')

def test_forward_quarantine_requires_retirement_age_and_completed_trade(db):
    service,state,at,_=enrolled(db);sid=state['id'];request=ReleaseRequest(study_id=sid,reason='Retired cohort reviewed for controlled future training')
    with pytest.raises(ValueError,match='Retire'):service.release(request)
    service.process_quote(sid,{},at+timedelta(seconds=31));service.retire(sid)
    with pytest.raises(ValueError,match='90-day'):service.release(request)
    with pytest.raises(ValueError):ReleaseRequest(study_id=sid,minimum_age_days=1,reason=request.reason)

def test_form4_only_after_publication_excludes_private_exercise_and_unresolved_amendment(db):
    from backend.research.filings import historical_features
    begin=now()-timedelta(days=200);public=begin+timedelta(days=100)
    db.set_setting('form4_coverage_AAPL',{'complete_window':True,'start':begin.isoformat(),'end':now().isoformat()})
    txn={'code':'P','derivative':False,'acquired_disposed':'A','value':1000,'planned_10b5_1':False,'owners':[{'cik':'1','officer':True,'director':False}],'footnotes':['Purchased on the open market']}
    db.put('historical_form4',{'form':'4','accession':'1','published_at':public.isoformat(),'transactions':[txn,{**txn,'code':'M'},{**txn,'footnotes':['Private placement']}]},'AAPL')
    times=[public-timedelta(seconds=1),public,public+timedelta(days=1)];x=historical_features(db,'AAPL',times)
    assert x.insider_purchase_count_30d.tolist()==[0,1,1] and x.insider_open_market_confirmed_count_30d.tolist()==[0,1,1]
    db.put('historical_form4',{'form':'4/A','accession':'2','published_at':times[2].isoformat(),'transactions':[]},'AAPL')
    assert historical_features(db,'AAPL',times).iloc[-1].isna().all()
    db.set_setting('form4_coverage_AAPL',{'complete_window':False});assert historical_features(db,'AAPL',times).isna().all().all()

def test_cash_forward_observations_are_not_recycled(db):
    service,state,at,pred=enrolled(db);other=service.enroll(EnrollRequest(model_id='test-model',policy=ForwardPolicy(initial_cash=40000)))
    at=now()+timedelta(seconds=2);pred.update(prediction=-.01,probability=.4,feature_available_at=at.isoformat());service.decide(other['id'],pred,at,{'eligible':True})
    start=at+timedelta(seconds=6);service.process_quote(other['id'],q(start,ask=100.1),start)
    end=start+timedelta(days=1);service.process_quote(other['id'],q(end,bid=101,ask=101.1),end)
    result=[r['payload'] for r in db.records('forward_outcome') if r['payload']['study_id']==other['id']][0]
    assert result['status']=='CASH_EVALUATED' and result['realized_pnl']==0 and result['cash_price_change']==pytest.approx(.01)
    assert not db.records('forward_training_release') and not db.records('forward_fill')

def test_forward_split_and_dividend_idempotence_with_payable_cash(db):
    service,state,at,pred=enrolled(db,'AAPL');sid=state['id']
    db.set_setting('research_calendar',{'sessions':[{'open':(at-timedelta(hours=1)).isoformat(),'close':(at+timedelta(hours=1)).isoformat()},{'open':(at+timedelta(days=1)).isoformat(),'close':(at+timedelta(days=1,hours=6)).isoformat()}]})
    t=at+timedelta(seconds=6);service.process_quote(sid,q(t,ask=100.1,size=200,symbol='AAPL'),t)
    ex=(t+timedelta(days=1)).date().isoformat();pay=(t+timedelta(days=3)).date().isoformat()
    for rid,kind,data in [('split','forward_splits',{'ex_date':ex,'new_rate':2,'old_rate':1}),('div','cash_dividends',{'ex_date':ex,'rate':1,'payable_date':pay})]:db.put('corporate_action',{'action_type':kind,'data':data,'observed_at':t.isoformat()},'AAPL',record_id=rid)
    effective=t+timedelta(days=1,hours=6);cash=db.setting('forward_state_'+sid)['cash'];service.apply_corporate_actions(sid,effective)
    out=db.setting('forward_state_'+sid);assert out['pending']['quantity']==8 and out['cash']==cash
    service.apply_corporate_actions(sid,effective);assert len(db.records('forward_action'))==2
    service.apply_corporate_actions(sid,t+timedelta(days=4));assert db.setting('forward_state_'+sid)['cash']==cash+8

@pytest.mark.asyncio
async def test_historical_adapter_pagination_and_feed_semantics(db,monkeypatch,tmp_path):
    from backend.providers.history import HistoricalBackfill
    class Provider:
        cfg={'ALPACA_DATA_FEED':'iex','ALPACA_API_KEY':'fake','ALPACA_API_SECRET':'fake'}
        def __init__(self):self.db=db;self.requests=[]
        def require(self,*args):pass
        async def request(self,name,url,**kwargs):
            params=dict(kwargs['params']);self.requests.append(params)
            second='page_token' in params
            return {'bars':{'AAPL':[{'t':'2020-01-03T05:00:00Z' if second else '2020-01-02T05:00:00Z','o':100,'h':101,'l':99,'c':100,'v':1000}]},'next_page_token':None if second else 'next'}
    p=Provider();h=HistoricalBackfill(p);h.store=HistoryStore(db,tmp_path);out=await h.alpaca(['AAPL'],feed='sip')
    assert len(out)==2 and all(r['count']==2 and r['feed']=='sip' for r in out)
    assert [r['adjustment'] for r in p.requests]==['raw','raw','all','all']
    assert h.store.read('AAPL','raw')[0]['available_at']=='2020-01-03T05:00:00Z'

@pytest.mark.asyncio
async def test_coinbase_backfill_filters_out_of_window_and_partial_days(db,tmp_path):
    from backend.providers.history import HistoricalBackfill
    class Provider:
        def __init__(self):self.db=db
        async def request(self,*args,**kwargs):
            start=pd.Timestamp(kwargs['params']['start']);end=pd.Timestamp(kwargs['params']['end'])
            return [[int(t.timestamp()),99,101,100,100,1000] for t in [start-pd.Timedelta(days=1),start,end]]
    h=HistoricalBackfill(Provider());h.store=HistoryStore(db,tmp_path);start=(now()-timedelta(days=3)).date().isoformat();m=await h.coinbase('BTC-USD',start)
    assert m['count']==1 and m['start'].startswith(start)


def test_cross_panel_liquidity_and_features_ignore_future(db,series,monkeypatch):
    from backend.research import cross_sectional as mod
    from backend.research.universe import Universe,Instrument
    # Deliberately duplicate one series across four symbols to isolate alignment.
    dates=pd.date_range('2020-01-01',periods=600,tz='UTC');rows=[]
    for t in dates:rows.append({**series[0],'timestamp':t.isoformat(),'available_at':(t+pd.Timedelta(days=1)).isoformat(),'close':100+np.sin(t.dayofyear),'high':102,'low':98})
    class Store:
        def __init__(self,db):pass
        def read(self,symbol,adjustment=None):return [{**r,'symbol':symbol} for r in rows]
        def manifest(self,symbol):return {'id':symbol}
    monkeypatch.setattr(mod,'HistoryStore',Store);monkeypatch.setattr(mod,'load_universe',lambda db:Universe(instruments=[Instrument(symbol=s,asset_class='stock') for s in ['A','B','C','D']]))
    db.set_setting('research_calendar',{'sessions':[{'date':t.date().isoformat()} for t in dates]})
    before,_=mod.panel(db)
    for r in rows[-30:]:r['close']=50;r['open']=50;r['high']=51;r['low']=49;r['volume']=1
    after,_=mod.panel(db);cutoff=dates[-40]
    pd.testing.assert_frame_equal(before[before.date<cutoff].reset_index(drop=True),after[after.date<cutoff].reset_index(drop=True))

def test_training_release_is_explicit_aged_immutable_and_not_automatic(db):
    service,state,at,_=enrolled(db);sid=state['id'];service.process_quote(sid,{},at+timedelta(seconds=31));service.retire(sid)
    old=(now()-timedelta(days=100)).isoformat()
    db.put('forward_outcome',{'study_id':sid,'status':'COMPLETED','completed_at':old},state['symbol'],record_id='aged-completed')
    request=ReleaseRequest(study_id=sid,reason='Completed cohort reviewed and retired from untouched evaluation')
    release=service.release(request);assert release['outcome_ids']==['aged-completed']
    assert release['automatic_training'] is False and release['evaluation_eligible'] is False
    assert service.release(request)==release and len(db.records('forward_training_release'))==1
    assert pd.Timestamp(release['training_available_after'])>pd.Timestamp(old)
    view=service.view();assert all(not r['evaluation_eligible'] for r in view['outcomes'])
    assert all(not groups for groups in view['attribution'].values())


def test_class_specific_volume_limits_do_not_confuse_shares_with_coins(series):
    u=Universe(instruments=[Instrument(symbol='BTC-USD',asset_class='crypto')]);crypto=u.instruments[0]
    bars=[{**r,'symbol':'BTC-USD','close':50000,'volume':500} for r in series]
    result=eligible_at(crypto,bars,now(),u.filters_for(crypto),expected_sessions=[r['timestamp'] for r in bars])
    assert result['eligible'] and not result['executable']
    with pytest.raises(ValueError):Eligibility(minimum_price=float('inf'))
