import asyncio,copy
from datetime import timedelta
import numpy as np
import pandas as pd
import pytest
from test_platform import db
from test_personal_paper import Market,quote
from backend.schemas.contracts import now
from backend.ensemble.engine import decide,forecasts,reliability
from backend.ensemble.portfolio import ShadowPortfolio,ManualExits,Consent,ExitPolicy,trigger
from backend.product.paper import ManualPaper,Ticket,Confirm
from backend.research.advanced.models import allocation,by_adjust,deep_fit

def evidence(at=None,symbol='BTC-USD',edge=.04):
    votes=[{'family':f,'model_id':'test_'+f,'prediction_after_cost':edge,'probability':.8 if edge>0 else .2,'uncertainty':.03,'health':[],'features':{'known_return':.1},'weight':0,'eligible':False,'horizon':5} for f in ['momentum','trend_following','macro_regime']]
    return {'symbol':symbol,'asset_class':'crypto','feature_available_at':(at or now()).isoformat(),'votes':votes,'health':[],'daily_volatility':.02,'estimated_roundtrip_cost':.0022,'score':25,'regime':'uptrend'}

def test_variants_cannot_multiply_influence_or_override_group():
    r=evidence();a=Market().lookup('BTC-USD');x=decide(r,a);r['votes'] += [{**r['votes'][0],'model_id':str(i)} for i in range(1000)];y=decide(r,a)
    assert x['edge']==y['edge'] and x['family_weights']==y['family_weights'];assert x['action']=='BUY';assert max(g['weight'] for g in x['groups'])<=.5
    r['votes']=[v for v in r['votes'] if v['family']!='macro_regime'];assert decide(r,a)['action']=='INSUFFICIENT EVIDENCE'

def test_abstention_horizon_uncertainty_health_and_no_short():
    r=evidence();a=Market().lookup('BTC-USD');r['votes'][2]['horizon']=20;assert decide(r,a)['action']=='INSUFFICIENT EVIDENCE'
    r=evidence(edge=.001);assert decide(r,a)['action']=='NO TRADE'
    r=evidence(edge=-.02);assert decide(r,a)['action']=='NO TRADE';assert decide(r,a,held=True)['action']=='SELL'
    r=evidence();r['health']=['stale provider'];assert decide(r,a)['action']=='NO TRADE'
    r=evidence();r['feature_available_at']=(now()+timedelta(days=1)).isoformat();assert decide(r,a)['action']=='INSUFFICIENT EVIDENCE'
    r=evidence();assert decide(r,a,qualified_only=True)['action']=='INSUFFICIENT EVIDENCE'

def test_recent_results_cannot_win_weights_and_minimum_dates():
    v={'historical_reliability':{'mse':.5,'zero_mse':1,'nonoverlapping_date_clusters':100}}
    p=reliability(v,'dynamic');assert reliability({**v,'forward_reliability':{'date_clusters':100,'mean_net_return':100}},'dynamic')==p
    assert reliability({**v,'forward_reliability':{'date_clusters':29,'mean_net_return':-1}},'dynamic')==p
    assert reliability({**v,'forward_reliability':{'date_clusters':100,'mean_net_return':-1}},'dynamic')<p

def pipeline(db,monkeypatch):
    import backend.ensemble.portfolio as ep
    import backend.product.paper as pp
    t=[now()];monkeypatch.setattr(ep,'now',lambda:t[0]);monkeypatch.setattr(pp,'now',lambda:t[0])
    class Provider:
        price=100
        async def forward_quote(self,symbol):return quote(t[0],symbol=symbol,bid=self.price,ask=self.price+.01)
    provider=Provider();svc=ShadowPortfolio(db,provider,Market());a=Market().lookup('BTC-USD');r=evidence(t[0]);db.set_setting('model_opportunities',{'as_of':t[0].isoformat(),'rows':[r],'assets':{'BTC-USD':a},'correlation':{}});return svc,provider,t,r

def test_shadow_end_to_end_delayed_fill_change_exit_attribution(db,monkeypatch):
    svc,p,t,r=pipeline(db,monkeypatch);db.set_setting('manual_paper',{'sentinel':123});db.set_setting('forward_state_sentinel',{'cash':456});db.set_setting('model_paper_account',{'sentinel':789})
    asyncio.run(svc.cycle());assert len(svc.paper.view()['orders'])==1;assert not svc.paper.view()['fills']
    asyncio.run(svc.cycle());assert len(svc.paper.view()['orders'])==1
    t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());assert svc.paper.view()['positions'];assert svc.paper.view()['fills'][0]['price']>100.01
    snap=db.setting('model_opportunities');snap['rows']=[evidence(t[0],edge=-.03)];db.set_setting('model_opportunities',snap);p.price=110;asyncio.run(svc.cycle());assert svc.paper.view()['orders'][0]['side']=='sell';assert svc.paper.view()['positions']
    t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());v=svc.paper.view();assert not v['positions'];assert v['realized_pnl']>0;o=svc.status()['outcomes'];assert len(o)==1;assert sum(o[0]['family_attribution'].values())==pytest.approx(v['realized_pnl']);assert o[0]['exit_reason']=='reversal'
    assert db.setting('manual_paper')=={'sentinel':123};assert db.setting('model_paper_account')=={'sentinel':789};assert db.setting('forward_state_sentinel')=={'cash':456};assert not db.records('forward_fill');assert not db.records('model')

def test_changed_evidence_cancels_pending_entry_and_pause(db,monkeypatch):
    svc,p,t,r=pipeline(db,monkeypatch);asyncio.run(svc.cycle());snap=db.setting('model_opportunities');snap['rows']=[evidence(t[0],edge=-.03)];db.set_setting('model_opportunities',snap);t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());assert not svc.paper.view()['fills'];assert svc.paper.view()['orders'][0]['status']=='CANCELED'
    db.set_setting('ensemble_shadow_paused',True);snap['rows']=[evidence(t[0])];db.set_setting('model_opportunities',snap);asyncio.run(svc.cycle());assert len(svc.paper.view()['orders'])==1

def test_manual_exit_is_opt_in_bound_to_position_and_account(db,monkeypatch):
    svc,provider,t,r=pipeline(db,monkeypatch);manual=ManualPaper(db,Market());p=manual.preview(Ticket(symbol='BTC-USD',side='buy',quantity=1),quote(t[0]));manual.place(Confirm(preview_id=p['id'],confirmation='PLACE PAPER ORDER'));t[0]+=timedelta(seconds=6);manual.process('BTC-USD',quote(t[0]),t[0]);ex=ManualExits(db,manual)
    snap=db.setting('model_opportunities');snap['rows']=[evidence(t[0],edge=-.1)];db.set_setting('model_opportunities',snap);asyncio.run(ex.cycle(provider));assert len(manual.view()['orders'])==1;assert ex.status()['BTC-USD']['enabled'] is False
    v=manual.view();pos=v['positions'][0]
    with pytest.raises(ValueError):ex.consent(Consent(symbol='BTC-USD',account_id='wrong',opened_at=pos['opened_at'],enabled=True))
    ex.consent(Consent(symbol='BTC-USD',account_id=v['id'],opened_at=pos['opened_at'],enabled=True));asyncio.run(ex.cycle(provider));assert len(manual.view()['orders'])==2;asyncio.run(ex.cycle(provider));assert len(manual.view()['orders'])==2
    t[0]+=timedelta(seconds=6);manual.process('BTC-USD',quote(t[0]),t[0]);assert not manual.view()['positions'];assert not db.records('shadow_fill')

@pytest.mark.parametrize('method',['equal','inverse_volatility','volatility_target','capped_edge','risk_parity','covariance_constrained'])
def test_allocations_keep_cash_caps_liquidity_and_no_leverage(method):
    w=allocation(method,np.ones(15)*.02,np.ones(15)*.02,np.eye(15)*.0004,np.r_[1000,np.ones(14)*1e9]);assert np.all(w>=0);assert w.max()<=.10000001;assert w.sum()<=.800001;assert w[0]<=.00001

def test_multiple_test_adjustment_includes_unavailable_trials():
    assert by_adjust([.01,.04],100)[0]>by_adjust([.01,.04],2)[0];assert all(0<=q<=1 for q in by_adjust([.0001,.5,.1]))

@pytest.mark.parametrize('kind',['tcn','gru','transformer'])
def test_deep_implementations_train_bounded_and_return_finite(kind):
    pytest.importorskip('torch');rng=np.random.default_rng(1);x=rng.normal(size=(64,12,8)).astype('float32');y=x[:,-1,0]*.01;a,b,d=deep_fit(kind,x,y,x[:10],x[10:20],epochs=1);assert len(a)==len(b)==10;assert np.isfinite(b).all();assert d['parameters']<10000
