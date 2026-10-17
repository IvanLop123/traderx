import asyncio,copy,json
from datetime import datetime,timedelta,timezone
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_platform import db
from test_ensemble import evidence,pipeline
from test_personal_paper import Market,quote
from backend.research.structure.intraday import Bars,derive,microstructure
from backend.research.structure.options import surface
from backend.research.structure.experiments import capacity,return_correlations,compare
from backend.ensemble.lifecycle import changes,Recommendations
from backend.ensemble.engine import decide
from backend.ensemble.portfolio import trigger,ExitPolicy,ManualExits,Consent
from backend.product.paper import ManualPaper,Ticket,Confirm
from backend.schemas.contracts import now

def ts(s):return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)











def ibars(rows,interval=60,asset='stock'):
    return Bars(symbol='AAPL' if asset=='stock' else 'BTC-USD',asset_class=asset,provider='fixture',feed='fixture',interval_seconds=interval,rows=[{'timestamp':t,'available_at':t+timedelta(seconds=interval+1),'open':v,'high':v+1,'low':v-1,'close':v,'volume':10,'vwap':v} for t,v in rows])

def test_intraday_session_overnight_weekend_and_crypto():
    sessions=[{'open':ts('2024-03-08T14:30:00'),'close':ts('2024-03-08T21:00:00'),'label':'Friday'},{'open':ts('2024-03-11T13:30:00'),'close':ts('2024-03-11T20:00:00'),'label':'Monday'}]
    # Labels must be sortable dates as exchange calendars supply, including DST change.
    sessions[0]['label']='2024-03-08';sessions[1]['label']='2024-03-11'
    r=derive(ibars([(ts('2024-03-08T20:59:00'),100),(ts('2024-03-09T14:30:00'),999),(ts('2024-03-11T13:30:00'),110)]),sessions);assert r['out_of_session_bars']==1;assert r['sessions'][1]['previous_close_to_open']==pytest.approx(.1)
    r=derive(ibars([(ts('2024-03-09T14:30:00'),100)],asset='crypto'),[]);assert r['out_of_session_bars']==0;assert r['sessions'][0]['segment']=='24/7'

def test_intraday_no_future_volume_expectation_or_partial_open_range():
    rows=[(ts('2024-01-01')+timedelta(days=i),100+i) for i in range(7)];r=derive(ibars(rows,asset='crypto'),[]);assert r['sessions'][0]['relative_time_of_day_volume'] is None;assert r['sessions'][5]['relative_time_of_day_volume']==1;assert r['sessions'][0]['opening_range_high'] is None

def test_microstructure_real_depth_and_no_history_claim():
    t=ts('2024-01-01');q={'timestamp':t.isoformat(),'bid':99,'ask':101};b={'timestamp':t.isoformat(),'bids':[[99,10]],'asks':[[101,20]]};r=microstructure([q],[b],at=t+timedelta(seconds=5));assert r['spread_bps']==200;assert r['notional_imbalance']<0;assert r['quote_staleness_seconds']==5;assert 'FORWARD COLLECTED ONLY' in r['scope'];assert r['buy_1000_depth_impact_proxy']==0

def chain(day='2024-01-01',iv=.2):
    d=datetime.fromisoformat(day);return {'data':[{'symbol':'AAPL','date':day,'expiration':(d+timedelta(days=30)).date().isoformat(),'type':kind,'strike':100,'bid':2,'ask':2.1,'delta':.5 if kind=='call' else -.5,'implied_volatility':iv,'volume':10,'open_interest':100} for kind in ['call','put']]}

def test_option_history_gate_surface_and_expected_move():
    r=surface(chain(),'AAPL');assert r['iv_rank'] is None;assert r['expirations'][0]['expected_move_fraction']==pytest.approx(.2*np.sqrt(30/365));assert r['totals']['put_call_volume_ratio']==1;assert len(r['surface'])==2
    history=[surface(chain((ts('2024-01-01')+timedelta(days=i)).date().isoformat(),.1+i/1000),'AAPL') for i in range(65)];r=surface(chain('2024-04-01',.2),'AAPL',history);assert r['iv_history_days']==65;assert r['iv_percentile']==1;assert r['iv_rank']>1 # rank can exceed past range; never silently clamp.

def test_options_greeks_and_parity_require_synchronized_underlying():
    u={'observation_date':'2024-01-01','spot':100,'rate':.03,'bid':99.99,'ask':100.01,'costs_per_share':.1};r=surface(chain(),'AAPL',underlying=u);assert len(r['local_greeks'])==2;assert not r['parity'];u['synchronized_quotes']=True;r=surface(chain(),'AAPL',underlying=u);assert r['parity'];assert 'American' in r['parity'][0]['warning']

def test_material_recommendations_idempotent_and_cumulative_change(db):
    svc,provider,t,r=None,None,None,evidence();db.set_setting('model_opportunities',{'rows':[r],'assets':{'BTC-USD':Market().lookup('BTC-USD')}});s=Recommendations(db);assert len(s.cycle())==1;assert s.cycle()==[];r['regime']='downtrend';db.set_setting('model_opportunities',{'rows':[r],'assets':{'BTC-USD':Market().lookup('BTC-USD')}});assert len(s.cycle())==1;assert 'regime' in s.recent()[0]['changes'];assert len(db.records('recommendation_change'))==2
    a={'edge':.04,'uncertainty':.03};assert not changes(a,{**a,'edge':.041});assert 'edge' in changes(a,{**a,'edge':.06})

@pytest.mark.parametrize('h',[1,2,5,10,20])
def test_multiple_horizon_forecasts_do_not_mix(h):
    r=evidence();r['horizon_sessions']=h
    for v in r['votes']:v['horizon']=h
    e=decide(r,Market().lookup('BTC-USD'));assert e['horizon_sessions']==h;assert e['action']=='BUY';r['votes'][2]['horizon']=3;assert decide(r,Market().lookup('BTC-USD'))['action']=='INSUFFICIENT EVIDENCE'

def test_manual_reversal_only_means_only_reversal_and_never():
    t=now();p={'opened_at':(t-timedelta(days=30)).isoformat(),'average_cost':100};e={'action':'HOLD','edge':.1,'horizon_sessions':20};q={'bid':80};x={'high':100}
    assert trigger(p,e,q,x,ExitPolicy(rule='reversal'),[],'crypto',at=t) is None
    assert trigger(p,e,q,x,ExitPolicy(rule='never'),[],'crypto',at=t) is None
    assert trigger(p,e,q,x,ExitPolicy(),[],'crypto',at=t)=='risk_limit'
    e['regime_compatible']=False;q['bid']=100;p['opened_at']=t.isoformat();assert trigger(p,e,q,x,ExitPolicy(),[],'crypto',at=t)=='regime_incompatibility'

def test_disabling_manual_consent_cancels_only_automatic_exit(db,monkeypatch):
    svc,provider,t,r=pipeline(db,monkeypatch);manual=ManualPaper(db,Market());p=manual.preview(Ticket(symbol='BTC-USD',side='buy',quantity=1),quote(t[0]));manual.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'));t[0]+=timedelta(seconds=6);manual.process('BTC-USD',quote(t[0]),t[0]);ex=ManualExits(db,manual);v=manual.view();pos=v['positions'][0];req=Consent(symbol=pos['symbol'],account_id=v['id'],opened_at=pos['opened_at'],enabled=True);ex.consent(req);snap=db.setting('model_opportunities');snap['rows']=[evidence(t[0],edge=-.1)];db.set_setting('model_opportunities',snap);asyncio.run(ex.cycle(provider));req.enabled=False;ex.consent(req);assert any(o['side']=='sell' and o['status']=='CANCELED' for o in manual.view()['orders'])

def test_capacity_cost_increases_and_labels_stay_uncertified():
    f=pd.DataFrame({'adv':[1e6]*5,'realized_volatility':[.02]*5,'gross_return':[.01]*5,'cost':[.002]*5});a=capacity(f,100);b=capacity(f,1e6);assert b['net_return']<a['net_return'];assert b['classification']=='INSUFFICIENT EVIDENCE'

def test_return_correlations_minimum_dates_and_reproducible_comparison():
    x=np.arange(50);r=return_correlations({'a':pd.Series(x),'b':pd.Series(-x)});assert r['correlations']['a']['b']==pytest.approx(-1);r=return_correlations({'a':pd.Series(x[:10]),'b':pd.Series(-x[:10])});assert r['correlations']['a']['b'] is None
    a={'id':'a','identity':{'seed':41,'data':'same'},'results':[]};b={'id':'b','identity':{'seed':42,'data':'same'},'results':[]};assert list(compare(a,b)['changed'])==['seed'];assert compare(a,a)['changed']=={}


def test_exact_model_return_dependence_reduces_independence_only():
    r=evidence();t=now();r['strategy_return_dependence']={'horizon_sessions':5,'end_at':(t-timedelta(days=1)).isoformat(),'known_at':t.isoformat(),'pairs':[{'model_a':'test_momentum','model_b':'test_macro_regime','return_correlation':.95,'nonoverlapping_dates':60}]};e=decide(r,Market().lookup('BTC-USD'),at=t);assert e['action']=='INSUFFICIENT EVIDENCE';assert e['return_dependence']['status']=='APPLIED'
    r['strategy_return_dependence']['pairs'][0]['model_a']='a_proxy_not_this_model';assert decide(r,Market().lookup('BTC-USD'),at=t)['action']=='BUY'


def test_new_costs_can_invalidate_a_previously_positive_edge():
    r=evidence();a=Market().lookup('BTC-USD');assert decide(r,a)['action']=='BUY';r['current_roundtrip_cost']=.06;e=decide(r,a);assert e['action']=='NO TRADE';assert e['edge']<0;assert e['cost_adjustment']>0

def test_collection_storage_limit_preserves_existing_rows_and_deduplicates(db):
    from backend.research.structure.collector import Collector
    c=Collector(db,None);c.cfg['max_saved_bytes']=100;a=c.save('structure_raw',{'value':'a'},'');assert c.save('structure_raw',{'value':'a'},'')==a
    with pytest.raises(ValueError,match='storage budget'):c.save('structure_raw',{'value':'x'*101},'')
    assert len(db.records('structure_raw'))==1

def test_statistical_shadow_outcomes_never_enter_portfolio_attribution(db):
    from backend.ensemble.portfolio import ShadowPortfolio
    original={'model_id':'old-model','actual_return':.02};rid=db.put('shadow_outcome',original,'BTC-USD');s=ShadowPortfolio(db,None,Market());assert s.status()['outcomes']==[];assert db.get(rid)['payload']==original
