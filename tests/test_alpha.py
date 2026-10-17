import copy
from datetime import timedelta
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_platform import db
from test_ensemble import evidence
from test_personal_paper import Market,quote
from backend.schemas.contracts import now
from backend.research.alpha.math import METHODS,optimize,adaptive,neutralize,shrink_covariance,attribution
from backend.research.alpha.registry import AlphaRegistry,POLICY,context,independent,lane,forward_dependence
from backend.research.alpha.research import pair_path,volatility_path
from backend.research.alpha.forward import AlphaForward

def snapshot(at):
    r=evidence(at);return {'as_of':at.isoformat(),'rows':[r],'assets':{'BTC-USD':Market().lookup('BTC-USD')}}

def test_alpha_versioning_preserves_old_definition_and_excludes_variants(db):
    t=now();service=AlphaRegistry(db);s=snapshot(t);a=service.register(s,t);again=service.register(s,t);assert a==again and len(a)==12
    original=copy.deepcopy(db.get(a['momentum']));s['rows'][0]['votes'][0]['artifact_hash']='changed';b=service.register(s,t+timedelta(days=1));assert a['momentum']!=b['momentum'];assert db.get(a['momentum'])==original;assert service.state(a['momentum'])['state']=='RETIRED'
    assert len(service.status()['alphas'])==12

def test_alpha_threshold_change_creates_new_epoch(db,monkeypatch):
    t=now();r=AlphaRegistry(db);a=r.register(snapshot(t),t);monkeypatch.setitem(POLICY,'minimum_dates',61);b=r.register(snapshot(t),t);assert a['momentum']!=b['momentum'];assert r.state(b['momentum'])['phase_started_at']==t.isoformat()

def test_alpha_no_unproven_promotion(db):
    t=now();r=AlphaRegistry(db);a=r.register(snapshot(t),t)['momentum']
    with pytest.raises(ValueError):r.transition(a,'FORWARD_TESTING','wishful thinking')
    with pytest.raises(ValueError):r.transition(a,'QUALIFIED_SIMULATION','skip phases')
    assert r.state(a)['state']=='HOLDOUT'

def test_suspension_reactivation_requires_new_healthy_epochs(db):
    t=now();s=snapshot(t);r=AlphaRegistry(db);g=r.cycle(s,t);aid=g['families']['momentum']['id'];s['rows'][0]['votes'][0]['health']=['provider missing'];g=r.cycle(s,t);assert g['families']['momentum']['state']=='SUSPENDED';s['rows'][0]['votes'][0]['health']=[]
    for _ in range(5):r.cycle(s,t)
    assert r.state(aid)['state']=='SUSPENDED'
    for i in range(1,4):s['rows'][0]['feature_available_at']=(t+timedelta(days=i)).isoformat();r.cycle(s,t+timedelta(days=i))
    assert r.state(aid)['state']=='HOLDOUT';assert db.get(aid)

def test_adaptive_limits_shrinkage_minimum_and_polling_idempotence(db):
    prior={'a':1,'b':1,'c':1};w,diag=adaptive(prior,{'a':[1]*59,'b':[-1]*59,'c':[0]*59});assert w==dict.fromkeys(prior,1/3)
    previous=w
    for _ in range(20):
        w,d=adaptive(prior,{'a':[1]*80,'b':[-1]*80,'c':[0]*80},previous);assert sum(w.values())==pytest.approx(1);assert max(abs(w[k]-previous[k]) for k in w)<=.020000001;assert min(w.values())>=.8/3;previous=w
    t=now();r=AlphaRegistry(db);a=r.cycle(snapshot(t),t);b=r.cycle(snapshot(t),t+timedelta(seconds=60));assert a['weights']==b['weights'];assert a['weight_epoch']==b['weight_epoch'];assert len(db.records('alpha_weights'))==1

@pytest.mark.parametrize('method',METHODS)
def test_optimizer_all_constraints(method):
    a=[{'edge':.04,'confidence':.8,'cost':.001,'adv':1e9,'sector':'tech' if i<5 else 'energy','asset_class':'stock' if i%2 else 'etf'} for i in range(10)];a[0]['adv']=100
    cov=np.eye(10)*.0004;cov[:3,:3]=.00032;np.fill_diagonal(cov,.0004)
    r=optimize(method,a,cov);w=np.array(r['weights']);assert r['status']=='FEASIBLE';assert np.min(w)>=0;assert max(w)<=.10000001;assert w[0]<=.0000011;assert sum(w)<=.8000001;assert sum(w[:5])<=.3000001;assert sum(w[::2])<=.6000001;assert sum(w[:3])<=.2500001;assert r['turnover']<=.4000001;assert r['estimated_cost_drag']<=.0030001;assert r['annual_volatility']<=.1000001

def test_optimizer_never_bypasses_infeasible_turnover_or_missing_inputs():
    a=[{'edge':.1,'confidence':.9,'cost':.001,'adv':1e9,'sector':'tech','asset_class':'stock'}];r=optimize('mean_variance',a,np.array([[.01]]),previous=[.9],limits={'turnover':.01});assert r['status']=='NO ALLOCATION';assert r['weights']==[0]
    a[0]['edge']=float('nan');assert optimize('equal',a,np.eye(1))['status']=='NO ALLOCATION'

def test_missing_returns_not_zero_filled_and_covariance_is_prior_only():
    rng=np.random.default_rng(5);idx=pd.date_range('2020-01-01',periods=150,tz='UTC');x=pd.DataFrame(rng.normal(size=(150,3)),index=idx);a,p=shrink_covariance(x,idx[100]);y=x.copy();y.loc[idx[100]:]=1e9;b,_=shrink_covariance(y,idx[100]);np.testing.assert_allclose(a,b);x.iloc[:100,0]=np.nan
    with pytest.raises(ValueError):shrink_covariance(x,idx[100])

def test_factor_neutralization_removes_exposures():
    rng=np.random.default_rng(8);x=rng.normal(size=(100,3));y=2+3*x[:,0]-x[:,1]+rng.normal(size=100);res=neutralize(y,x);np.testing.assert_allclose(x.T@res,0,atol=1e-10);assert abs(res.mean())<1e-10;assert np.isnan(neutralize([1,2],[[1],[2]])).all()

def test_pair_selection_and_kalman_never_see_future_prices():
    rng=np.random.default_rng(41);b=np.exp(4+np.cumsum(rng.normal(0,.01,500)));a=b*np.exp(rng.normal(0,.005,500));p=pd.DataFrame({'a':a,'b':b},index=pd.date_range('2020',periods=500,tz='UTC'));tr=p.iloc[:350];te=p.iloc[350:];x=pair_path(tr,te);changed=te.copy();changed.iloc[50:]*=3;y=pair_path(tr,changed);assert x['cointegration_p']==y['cointegration_p'];assert x['path'][:50]==y['path'][:50]

def test_volatility_and_regime_forward_filter_chronology():
    rng=np.random.default_rng(41);tr=rng.normal(0,.01,700);te=rng.normal(0,.02,100);x=volatility_path(tr,te);changed=te.copy();changed[50:]=1;y=volatility_path(tr,changed);np.testing.assert_allclose(pd.DataFrame(x[:51]).astype(float),pd.DataFrame(y[:51]).astype(float),rtol=1e-10,atol=1e-12);assert all(v[k]>0 for v in x for k in ('realized','ewma','garch','hmm'))

def test_nonoverlap_clusters_do_not_count_assets_as_dates():
    t=pd.Timestamp('2025-01-01',tz='UTC');rows=[{'decision_at':(t+pd.Timedelta(days=i)).isoformat(),'completed_at':(t+pd.Timedelta(days=i+5)).isoformat(),'net_return':.01,'probability':.7} for i in range(60) for _ in range(10)];assert len(independent(rows))==10

def test_forward_correlation_requires_exact_models_and_mature_adaptation():
    t=pd.Timestamp('2024-01-01',tz='UTC');rows=[]
    for i in range(45):
        for m in ['a','b']:
            rows.append({'decision_at':(t+pd.Timedelta(days=i*7)).isoformat(),'completed_at':(t+pd.Timedelta(days=i*7+5)).isoformat(),'net_return':float(np.sin(i))*.01,'probability':.6,'model_ids':[m],'lane':'adaptation'})
    p=forward_dependence(rows,t+pd.Timedelta(days=400));assert len(p['pairs'])==1;assert p['pairs'][0]['return_correlation']==pytest.approx(1)
    assert not forward_dependence([{**r,'lane':'evaluation'} for r in rows],t+pd.Timedelta(days=400));assert not forward_dependence(rows[:20],t+pd.Timedelta(days=400))

def test_attribution_each_dimension_reconciles_and_fees_not_double_counted():
    a=attribution(120,8,{'momentum':.25,'trend':.75},{'momentum':'alpha_m','trend':'alpha_t'},'AAPL','up','tech','plan1')
    for dimension in ('alpha','family','asset','regime','sector','sizing_decision'):assert sum(a[dimension].values())==pytest.approx(120)
    assert a['costs']['gross_before_fees']-a['costs']['fees']==a['costs']['net']

def test_governance_cannot_be_bypassed_by_stale_vote_context(db):
    t=now();r=AlphaRegistry(db);s=snapshot(t);g=r.cycle(s,t);v=context(s['rows'][0],g);assert v['votes'][0]['alpha_id'];g['families']['momentum']['state']='SUSPENDED';bad=context(v,g);assert 'Alpha suspended' in bad['votes'][0]['health'];g['families']['momentum']['state']='HOLDOUT';healthy=context(bad,g);assert not healthy['votes'][0]['health']

def test_alpha_forward_freezes_features_weights_and_waits_for_real_quotes(db):
    t=now();r=AlphaRegistry(db);s=snapshot(t);g=r.cycle(s,t);service=AlphaForward(db,None);row=s['rows'][0];asset=s['assets']['BTC-USD'];service.record(row,asset,g,t);assert db.records('alpha_forecast');d=db.records('alpha_forecast')[0]['payload'];assert d['lane']==lane('BTC-USD');from backend.research.features import stable_hash
    key='af_'+stable_hash(['BTC-USD',5])[:32];service.process(key,quote(t),t);assert db.setting(key)['entry'] is None
    t2=t+timedelta(seconds=6);service.process(key,quote(t2),t2);assert db.setting(key)['entry'];assert not db.records('alpha_outcome');end=t2+timedelta(days=5,seconds=1);service.process(key,quote(end,bid=110,ask=110.1),end);assert db.records('alpha_outcome');assert db.records('alpha_benchmark');assert db.get(d['id'])['payload']==d;assert not db.records('manual_fill');assert not db.records('forward_outcome')

def test_alpha_status_api_read_only(db):
    from backend.api.main import create_app
    r=AlphaRegistry(db);r.cycle(snapshot(now()));client=TestClient(create_app(db,start_workers=False));v=client.get('/api/v1/alpha/status');assert v.status_code==200;assert v.json()['distinct_families']==12;assert v.json()['benchmark']['independent_dates']==0;assert v.json()['external_execution'] is False


def test_entry_only_optimizer_never_credits_unexecuted_sales():
    a=[{'edge':.04,'confidence':.8,'cost':.001,'adv':1e9,'sector':str(i),'asset_class':'stock'} for i in range(3)]
    cov=np.eye(3)*.0001;old=np.array([.1,0,0]);r=optimize('mean_variance',a,cov,previous=old,entry_only=True)
    assert r['status']=='FEASIBLE';assert np.all(np.array(r['weights'])>=old-1e-8)
    a[0]['edge']=-.01
    assert optimize('mean_variance',a,cov,previous=old,entry_only=True)['status']=='NO ALLOCATION'


def test_governance_staleness_blocks_new_votes(db):
    t=now();s=snapshot(t);g=AlphaRegistry(db).cycle(s,t)
    stale=context(s['rows'][0],g,t+timedelta(minutes=6))
    assert all('Alpha governance unavailable or stale' in v['health'] for v in stale['votes'])


def test_failed_frozen_gate_is_not_retried_after_more_winners(db):
    t=now();s=snapshot(t);registry=AlphaRegistry(db);aid=registry.register(s,t)['momentum']
    def save(i,ret):
        at=t+timedelta(days=2*i+1);oid=f'alpha_test_outcome_{i}'
        o={'id':oid,'alpha_id':aid,'phase':'HOLDOUT','lane':'evaluation','decision_at':at.isoformat(),'completed_at':(at+timedelta(days=1)).isoformat(),'net_return':ret,'strategy_return':ret,'probability':.5,'prediction':.01,'asset_class':'crypto','regime':'unknown'}
        db.put('alpha_outcome',o,record_id=oid)
    for i in range(60):save(i,0.)
    registry.cycle(s,t+timedelta(days=122));gate=db.records('alpha_gate')[0]['payload'];assert not gate['passed'];assert registry.state(aid)['state']=='HOLDOUT'
    for i in range(60,200):save(i,.01)
    registry.cycle(s,t+timedelta(days=402));assert len(db.records('alpha_gate'))==1;assert db.records('alpha_gate')[0]['payload']==gate;assert registry.state(aid)['state']=='HOLDOUT'


def test_forged_gate_cannot_promote_without_real_phase_evidence(db):
    t=now();r=AlphaRegistry(db);aid=r.register(snapshot(t),t)['momentum'];d=db.get(aid)['payload']
    db.put('alpha_gate',{'alpha_id':aid,'phase':'HOLDOUT','policy_hash':d['policy_hash'],'passed':True,'at':t.isoformat(),'outcomes':['nonexistent']},record_id='forged')
    with pytest.raises(ValueError):r.transition(aid,'FORWARD_TESTING','fake',t.isoformat(),'forged')


def test_alpha_optimizer_shadow_pipeline_and_isolated_attribution(db,monkeypatch):
    import asyncio
    import backend.research.alpha.registry as registry
    import backend.research.alpha.allocation as allocation
    from test_ensemble import pipeline
    svc,provider,t,row=pipeline(db,monkeypatch)
    monkeypatch.setattr(registry,'now',lambda:t[0]);monkeypatch.setattr(allocation,'now',lambda:t[0])
    monkeypatch.setattr(allocation.HistoryStore,'manifest',lambda self,symbol:{'id':'fixture_prior_history'})
    idx=pd.date_range(end=pd.Timestamp(t[0])-pd.Timedelta(days=1),periods=100)
    svc.allocator.cache['fixture_prior_history']=pd.Series(np.sin(np.arange(100))*.001,index=idx)
    db.set_setting('alpha_required',True);g=AlphaRegistry(db).cycle(db.setting('model_opportunities'),t[0])
    asyncio.run(svc.cycle());v=svc.paper.view();assert len(v['orders'])==1;assert not v['fills']
    decision=db.get(v['orders'][0]['evidence']['id'])['payload'];assert decision['allocation']['status']=='FEASIBLE';assert decision['ensemble']['alpha_sources']
    t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());assert svc.paper.view()['positions']
    snap=db.setting('model_opportunities');snap['rows']=[evidence(t[0],edge=-.03)];db.set_setting('model_opportunities',snap);AlphaRegistry(db).cycle(snap,t[0]);provider.price=110
    asyncio.run(svc.cycle());t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle())
    assert not svc.paper.view()['positions'];out=svc.status()['outcomes'][0]
    for key in ('alpha','family','asset','regime','sector','sizing_decision'):assert sum(out['attribution'][key].values())==pytest.approx(out['realized_pnl'])
    assert not db.records('manual_fill');assert not db.records('forward_fill');assert not db.records('model')


def test_volatility_target_scales_proposal_before_shared_caps():
    assets=[{'edge':.1,'confidence':.8,'cost':.001,'adv':10000 if i==0 else 1e9,'sector':str(i),'asset_class':'stock'} for i in range(10)]
    cov=np.eye(10)*.002;limits={'turnover':1,'asset_class':.9}
    inverse=optimize('inverse_volatility',assets,cov,limits=limits)
    target=optimize('volatility_target',assets,cov,limits=limits)
    assert target['status']==inverse['status']=='FEASIBLE'
    assert target['annual_volatility']<=.100001
    assert target['gross']<inverse['gross']-.01
