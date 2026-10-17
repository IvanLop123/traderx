from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import pytest
from test_platform import db
from backend.schemas.contracts import now
from backend.product.paper import ManualPaper,Ticket,Confirm,Reset,Watch
from backend.research.strategies import fit_model,predict

class Market:
    def lookup(self,symbol):return {'symbol':symbol,'asset_class':'crypto' if symbol.endswith('-USD') else 'stock','liquidity_bucket':'deep','market_cap_bucket':'unknown','eligibility':{'eligible':True,'reasons':[],'mean_dollar_volume':1e9},'score':50,'regime':'range'}
def quote(at=None,symbol='BTC-USD',size=1000,bid=100,ask=100.01):
    t=at or now();return {'symbol':symbol,'bid':bid,'ask':ask,'bid_size':size,'ask_size':size,'timestamp':t.isoformat(),'observed_at':t.isoformat(),'depth_units':'base_units'}
def placed(service,**kwargs):
    p=service.preview(Ticket(symbol='BTC-USD',side='buy',quantity=1,**kwargs),quote());return service.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'))
def after(order,seconds=6):return pd.Timestamp(order['created_at']).to_pydatetime()+timedelta(seconds=seconds)

def test_no_creation_on_read_and_original_books_untouched(db):
    db.set_setting('paper',{'cash':123});db.set_setting('forward_state_test',{'id':'test'});service=ManualPaper(db,Market());assert service.view()['cash']==10000;assert service.state() is None
    o=placed(service);assert o['source']=='manual_paper';assert db.setting('paper')['cash']==123;assert db.setting('forward_state_test')=={'id':'test'};assert not db.records('forward_decision')
def test_confirmation_idempotent_concurrent(db):
    s=ManualPaper(db,Market());p=s.preview(Ticket(symbol='BTC-USD',side='buy',quantity=1),quote());req=Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER')
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:s.place(req),range(3)))
    assert len({r['id'] for r in results})==1;assert len(s.view()['orders'])==1

def test_latency_partial_repeat_and_roundtrip(db):
    s=ManualPaper(db,Market());o=placed(s);early=after(o,1);s.process('BTC-USD',quote(early),early);assert not s.view()['fills']
    t=after(o);q=quote(t,size=10);s.process('BTC-USD',q,t);v=s.view();assert v['orders'][0]['status']=='PARTIALLY_FILLED';assert v['positions'][0]['quantity']==.5;assert v['fills'][0]['price']>q['ask'];cash=v['cash']
    s.process('BTC-USD',q,t+timedelta(seconds=1));assert s.view()['cash']==cash
    t+=timedelta(seconds=2);s.process('BTC-USD',quote(t,size=10),t);assert s.view()['orders'][0]['status']=='FILLED'
    p=s.preview(Ticket(symbol='BTC-USD',side='sell',quantity=1),quote());sell=s.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'));t=after(sell,30);s.process('BTC-USD',quote(t,bid=110,ask=110.01),t);v=s.view();assert not v['positions'];assert v['realized_pnl']>0;assert v['total_pnl']==pytest.approx(v['realized_pnl']);assert len(v['fills'])==3

def test_no_short_no_overallocation_and_adversarial_values(db):
    s=ManualPaper(db,Market())
    with pytest.raises(ValueError,match='holdings'):s.preview(Ticket(symbol='BTC-USD',side='sell',quantity=1),quote())
    with pytest.raises(ValueError,match='cash'):s.preview(Ticket(symbol='BTC-USD',side='buy',quantity=101),quote())
    for n in [float('nan'),float('inf'),-1,0]:
        with pytest.raises(ValueError):Ticket(symbol='BTC-USD',side='buy',quantity=n)
    o=placed(s);assert s.view()['reserved_cash']>100
    with pytest.raises(ValueError,match='cash'):s.preview(Ticket(symbol='BTC-USD',side='buy',quantity=99),quote())

def test_limit_respects_adverse_slippage_cancel_and_expiry(db):
    s=ManualPaper(db,Market());o=placed(s,order_type='limit',limit_price=100.01);t=after(o);s.process('BTC-USD',quote(t),t);assert not s.view()['fills'];assert 'limit' in s.view()['orders'][0]['last_status'];s.cancel(o['id']);assert s.view()['reserved_cash']==0
    with pytest.raises(ValueError):s.cancel(o['id'])
    o=placed(s);t=after(o,61);s.process('BTC-USD',quote(t),t);assert s.view()['orders'][0]['status']=='NO_FILL'

def test_stale_missing_crossed_wrong_units_and_market_closed(db):
    s=ManualPaper(db,Market());o=placed(s);t=after(o)
    for q in [{},quote(t-timedelta(seconds=90)),{**quote(t),'depth_units':'lots'},quote(t,bid=102,ask=100),quote(t,symbol='ETH-USD')]:s.process('BTC-USD',q,t);assert not s.view()['fills']
    p=s.preview(Ticket(symbol='AAPL',side='buy',quantity=1),quote(symbol='AAPL'));o=s.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'));t=after(o);s.process('AAPL',quote(t,symbol='AAPL'),t);assert not s.view()['fills'];assert any('closed' in v['last_status'] for v in s.view()['orders'])

def test_two_orders_cannot_reuse_same_displayed_quote(db):
    s=ManualPaper(db,Market());a=placed(s);b=placed(s);t=after(b);s.process('BTC-USD',quote(t,size=20),t);assert len(s.view()['fills'])==1

def test_reset_confirm_archive_and_preview_invalidation(db):
    s=ManualPaper(db,Market());o=placed(s);p=s.preview(Ticket(symbol='BTC-USD',side='buy',quantity=1),quote());old=s.view()['id']
    with pytest.raises(ValueError):Reset(starting_balance=5000,confirmation='yes',account_id=old)
    v=s.reset(Reset(starting_balance=5000,confirmation='RESET MY PAPER ACCOUNT',account_id=old));assert v['cash']==5000 and not v['orders'];assert len(db.records('manual_account_archive'))==1;assert len(db.records('manual_order'))==1
    with pytest.raises(ValueError,match='changed'):s.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'))

def test_stock_whole_shares_conservative_unknown_cap(db):
    s=ManualPaper(db,Market());p=s.preview(Ticket(symbol='AAPL',side='buy',amount=150),quote(symbol='AAPL'));assert p['quantity']==1;assert p['policy']['slippage_bps']==25;assert p['policy']['participation']==.02
    with pytest.raises(ValueError,match='Whole'):s.preview(Ticket(symbol='AAPL',side='buy',quantity=1.2),quote(symbol='AAPL'))

def test_strategy_coefficients_are_portable_and_calibration_temporal():
    import numpy as np
    rng=np.random.default_rng(41);x=rng.normal(size=500);frame=pd.DataFrame({'x':x,'net_return':x*.01+rng.normal(0,.02,500)});m=fit_model(frame.iloc[:300],frame.iloc[300:400],['x']);a,p=predict(m,frame.iloc[400:]);assert len(a)==100 and all((p>=0)&(p<=1));assert m['columns']==['x'];assert m['uncertainty']>0
    altered=frame.copy();altered.loc[400:,'net_return']=999;assert fit_model(altered.iloc[:300],altered.iloc[300:400],['x'])==m
    with pytest.raises(ValueError):fit_model(frame.iloc[:20],frame.iloc[300:400],['x'])

def test_zero_depth_and_halted_quote_do_not_crash_or_fill(db):
    s=ManualPaper(db,Market());o=placed(s);t=after(o)
    for changes in [{'bid':0,'ask':0},{'halted':True},{'bid_size':0},{'ask_size':0}]:
        s.process('BTC-USD',{**quote(t),**changes},t)
        assert not s.view()['fills']

def test_halt_changed_after_preview_blocks_fills(db):
    from backend.research.universe import Universe,Instrument
    s=ManualPaper(db,Market());o=placed(s);db.set_setting('research_universe',Universe(instruments=[Instrument(symbol='BTC-USD',asset_class='crypto',halted=True)]).model_dump(mode='json'));t=after(o);s.process('BTC-USD',quote(t),t);assert not s.view()['fills'];assert 'halted' in s.view()['orders'][0]['last_status']

def test_removing_instrument_after_order_blocks_fills(db):
    from backend.research.universe import Universe,Instrument
    s=ManualPaper(db,Market());o=placed(s)
    db.set_setting('research_universe',Universe(instruments=[Instrument(symbol='ETH-USD',asset_class='crypto')]).model_dump(mode='json'))
    t=after(o);s.process('BTC-USD',quote(t),t)
    assert not s.view()['fills'];assert 'no longer' in s.view()['orders'][0]['last_status']

def test_no_lookahead_and_nonoverlapping_sampling():
    from backend.research.strategies import sample_intervals
    dates=pd.date_range('2020-01-01',periods=80,tz='UTC');frame=pd.DataFrame({'date':dates,'label_end':dates+pd.Timedelta(days=9)})
    result=sample_intervals(frame,dates,0,len(dates));assert len(result)==8
    assert all(a>b for a,b in zip(result.date.iloc[1:],result.label_end.iloc[:-1]))

def test_relative_rank_is_not_absolute_buy_permission():
    from backend.research.strategies import metrics
    z=pd.DataFrame({'date':pd.date_range('2020-01-01',periods=4,tz='UTC'),'future_rank':[.2,.8,.6,.4],'relative_return':[-.1,.1,.05,-.05],'net_return':[-.2,-.3,-.1,-.1],'gross_return':[-.19,-.29,-.09,-.09],'predicted':[.6,.7,.8,.9],'probability':[.8]*4,'missing_features':[False]*4,'prior':[.5]*4,'return_20':[.1]*4,'rsi':[50]*4,'target_baseline':[.5]*4})
    result=metrics(z,target='future_rank',label_target='relative_return');assert result['trade_observations']==0;assert not result['trade_rule_available']

def test_dividend_entitlement_survives_exit_before_late_source_arrival(db):
    from backend.storage.database import Setting,Record
    s=ManualPaper(db,Market());o=placed(s);state=s.state();t=now();opened=t-timedelta(days=4);effective=(t-timedelta(days=2)).date().isoformat()
    state['positions']['AAPL']={'quantity':0.,'average_cost':100.,'realized_pnl':0.,'opened_at':opened.isoformat()};db.set_setting('manual_paper',state)
    db.put('manual_fill',{'account_id':state['id'],'side':'sell','quantity':2,'at':(t-timedelta(days=1)).isoformat()},'AAPL')
    db.put('corporate_action',{'action_type':'cash_dividends','data':{'ex_date':effective,'payable_date':(t-timedelta(days=1)).date().isoformat(),'rate':1},'observed_at':t.isoformat()},'AAPL')
    before=s.view()['cash'];s.actions();s.actions();assert s.view()['cash']==pytest.approx(before+2);s.actions();assert s.view()['cash']==pytest.approx(before+2)


def test_current_strategy_rows_wait_for_availability_bucket():
    from backend.research.strategies import available_panel
    t=now();frame=pd.DataFrame({'date':[t-timedelta(days=1),t,t+timedelta(seconds=1)],'symbol':['AAPL']*3})
    assert len(available_panel(frame,t))==2

def test_product_does_not_display_future_forecast(db):
    from backend.product.market import ProductMarket
    t=now();market=ProductMarket(db);market.universe=lambda:[{'symbol':'AAPL'}]
    fields={'model_prediction':.01,'probability':.6,'uncertainty':.03,'strategy_family':'momentum','model_id':'known','horizon':5,'status':'experimental'}
    db.put('research_forecast',{**fields,'feature_available_at':(t-timedelta(days=1)).isoformat()},'AAPL')
    db.put('research_forecast',{**fields,'model_id':'future','feature_available_at':(t+timedelta(hours=1)).isoformat()},'AAPL')
    assert market.forecasts()[0]['model_id']=='known'


def test_trim_then_sell_all_coin_precision(db):
    s=ManualPaper(db,Market());t=now();s.clock=lambda:t
    p=s.preview(Ticket(symbol='BTC-USD',side='buy',amount=100),quote(t));o=s.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'));t+=timedelta(seconds=6);s.process('BTC-USD',quote(t),t)
    for quantity in [.49945042,None]:
        qty=quantity if quantity is not None else s.view()['positions'][0]['quantity']
        p=s.preview(Ticket(symbol='BTC-USD',side='sell',quantity=qty),quote(t));assert p['quantity']==qty
        s.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'));t+=timedelta(seconds=6);s.process('BTC-USD',quote(t),t)
    assert not s.view()['positions'];assert s.state()['positions']['BTC-USD']['quantity']==0
