import ast,asyncio,json
from datetime import timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from test_platform import db
from backend.schemas.contracts import now
from backend.selection.policy import PortfolioPolicy,policy,policy_hash,GROUPS
from backend.selection.registry import SelectionRegistry,clustered_evidence
from backend.selection.risk import size,correlation_context,exit_reason
from backend.selection.opportunities import OpportunityEngine,score_opportunity
from backend.selection.portfolio import ModelPortfolio,ModelPaper,portfolio_metrics
from backend.product.paper import ManualPaper,Ticket,Confirm
from backend.research.features import stable_hash


def inputs():
 a={'symbol':'BTC-USD','name':'Acceptance Bitcoin','asset_class':'crypto','sector':'digital','regime':'uptrend','liquidity_bucket':'deep','market_cap_bucket':'unknown','eligibility':{'eligible':True,'reasons':[],'mean_dollar_volume':1e9},'price':100,'price_at':now().isoformat()}
 c={'symbol':'BTC-USD','trade_eligible':True,'score':90,'groups':['price_trend','macro'],'expected_edge':.08,'uncertainty':.03,'probability':.85,'daily_volatility':.02}
 v={'equity':10000.,'initial_cash':10000.,'total_pnl':0.,'cash':10000.,'available_cash':10000.,'positions':[],'orders':[],'fills':[],'fees':0.}
 return a,c,v

def approved_fixture(db,at):
 """Synthetic eligibility only in the test module; production has no override switch."""
 a,c,v=inputs();rows=[]
 for family in ['momentum','macro_regime']:
  mid='fixture_'+family;m={'id':mid,'columns':['return_20'],'mean':[0.],'scale':[1.],'medians':{'return_20':0.},'return_coef':[0.],'return_intercept':.08,'logit_coef':[0.],'logit_intercept':2.,'calibration_coef':1.,'calibration_intercept':0.,'uncertainty':.03,'prior':.6}
  db.put('strategy_model',m,record_id=mid)
  rows.append({'id':mid,'source_kind':'strategy_model','family':family,'asset_class':'crypto','artifact_hash':stable_hash(m),'validation':{'mse':1.,'zero_mse':2.,'brier':.1,'base_rate_brier':.2,'mean_net_strategy_return':.02},'conditional_validation':{},'eligibility':'eligible','forward':{'date_clusters':0,'mean_net_return':None},'reasons':[]})
 panel=pd.DataFrame([{'symbol':'BTC-USD','date':at-timedelta(days=90-i),'return_1':.001+np.sin(i)*.01,'return_20':.1,'realized_volatility':.02,'cost':.0022} for i in range(91)])
 result=OpportunityEngine(db).build([a],{'rows':rows},policy(db),v,prepared=panel);result.update(id='fixture_snapshot',policy_hash=policy_hash(policy(db)),assets={'BTC-USD':a});return a,result


def test_related_variants_share_dependence_group():
 assert GROUPS['momentum']==GROUPS['trend_following']==GROUPS['cross_sectional_ranking'];assert GROUPS['macro_regime']!=GROUPS['momentum']

def test_policy_hard_ceiling_and_finite_validation():
 with pytest.raises(ValueError):PortfolioPolicy(maximum_position=1)
 with pytest.raises(ValueError):PortfolioPolicy(maximum_drawdown=float('nan'))

def test_date_clusters_not_number_of_assets():
 observations=[{'net_return':.01,'completed_at':(now()-timedelta(days=i)).isoformat()} for i in range(10) for _ in range(100)]
 e=clustered_evidence(observations);assert e['observations']==1000 and e['date_clusters']==10 and not e['positive_evidence']

def test_bootstrap_requires_positive_independent_evidence():
 e=clustered_evidence([{'net_return':.01,'completed_at':(now()-timedelta(days=i)).isoformat()} for i in range(80)]);assert e['positive_evidence'] and e['lower_bound']>0

def test_legacy_registered_but_never_auto_approved(db):
 db.put('model',{'model':'test','features':['x'],'research_candidate_eligible':True},'AAPL');r=SelectionRegistry(db).refresh();assert r['count']==1 and r['eligible']==0;assert r['rows'][0]['meta_weight']==0;assert len(db.records('selection_challenger'))==1;SelectionRegistry(db).refresh();assert len(db.records('selection_challenger'))==1

def test_approval_cannot_accept_unverified_record(db):
 mid=db.put('strategy_model',{'family':'momentum'});reg=SelectionRegistry(db);reg.refresh();ev=db.put('manual_fill',{'eligible':True})
 with pytest.raises(ValueError):reg.evaluate(mid,ev)

def test_risk_limits_and_unknown_correlations_are_conservative():
 a,c,v=inputs();p=PortfolioPolicy();r=size(c,v,{a['symbol']:a},{},p,10000);assert 0<r['notional']<=1000
 v['positions']=[{'symbol':'ETH-USD','market_value':2600,'quantity':26,'average_cost':100}];assets={a['symbol']:a,'ETH-USD':{**a,'symbol':'ETH-USD'}};r=size(c,v,assets,{},p,10000);assert r['notional']==0

def test_cash_drawdown_sector_and_pending_orders_limits():
 a,c,v=inputs();p=PortfolioPolicy();v['available_cash']=5;assert size(c,v,{a['symbol']:a},{},p,10000)['notional']<=5
 v['equity']=8500;assert size(c,v,{a['symbol']:a},{},p,10000)['notional']==0
 a,c,v=inputs();v['orders']=[{'id':'x','side':'buy','status':'OPEN','symbol':'BTC-USD','quantity':1,'filled_quantity':0,'reserve_price':100}];assert size(c,v,{a['symbol']:a},{},p,10000)['notional']==0

def test_correlation_needs_real_overlap():
 c=correlation_context(pd.DataFrame({'a':range(50),'b':range(50)}));assert c['correlations']['a']=={}
 c=correlation_context(pd.DataFrame({'a':range(90),'b':range(90)}));assert c['correlations']['a']['b']==pytest.approx(1.)

@pytest.mark.parametrize('name,ctx,days,expected',[
 ('fixed_horizon',{},5,'fixed_horizon'),('signal_reversal',{'expected_edge':-.1},1,'signal_reversal'),('score_decay',{'score':10},1,'score_decay'),('risk_stop',{'bid':90},1,'risk_stop'),('volatility_stop',{'bid':95,'daily_volatility':.02},1,'volatility_stop'),('profit_target',{'bid':120},1,'profit_target'),('trailing',{'bid':100,'high_bid':120},1,'trailing')])
def test_exit_policies_are_explicit(name,ctx,days,expected):assert exit_reason({'average_cost':100},{'bid':100,**ctx},PortfolioPolicy(exit_policy=name),days)==expected

def test_tiny_sample_metrics_do_not_annualize():
 a,c,v=inputs();m=portfolio_metrics([{'equity':10000,'date':'2026-01-01'},{'equity':10001,'date':'2026-01-02'}],[],v);assert m['sharpe_like'] is None and m['annualized_volatility'] is None and m['completed_trades']==0

def test_pipeline_votes_risk_order_fill_exit_attribution_and_isolation(db,monkeypatch):
 import backend.selection.portfolio as engine
 import backend.product.paper as simulator
 t=[now()];monkeypatch.setattr(engine,'now',lambda:t[0]);monkeypatch.setattr(simulator,'now',lambda:t[0])
 p=PortfolioPolicy(horizon_sessions=1);db.set_setting('model_portfolio_policy',p.model_dump());a,snapshot=approved_fixture(db,t[0]);db.set_setting('model_opportunities',snapshot)
 class Provider:
  async def forward_quote(self,symbol):return {'symbol':symbol,'bid':100,'ask':100.01,'bid_size':1000,'ask_size':1000,'timestamp':t[0].isoformat(),'observed_at':t[0].isoformat(),'depth_units':'base_units'}
 svc=ModelPortfolio(db,Provider());svc.market.lookup=lambda _:a
 assert snapshot['rows'][0]['would_trade'];asyncio.run(svc.cycle());view=svc.paper.view();assert len(view['orders'])==1 and not view['fills'];assert db.setting('manual_paper') is None and not db.records('forward_decision')
 t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());assert svc.paper.view()['positions'];assert svc.paper.view()['orders'][0]['status']=='FILLED'
 t[0]+=timedelta(days=1);snapshot['as_of']=t[0].isoformat();db.set_setting('model_opportunities',snapshot);asyncio.run(svc.cycle());assert any(o['side']=='sell' for o in svc.paper.view()['orders'])
 t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());assert not svc.paper.view()['positions'];out=db.records('auto_outcome');assert len(out)==1;assert out[0]['payload']['realized_pnl']<0;assert sum(out[0]['payload']['family_attribution'].values())==pytest.approx(out[0]['payload']['realized_pnl']);assert not db.records('manual_fill');assert not db.records('forward_fill')

def test_namespaces_cannot_confirm_each_others_previews(db):
 a,c,v=inputs()
 class Market:
  def lookup(self,s):return a
 manual=ManualPaper(db,Market());model=ModelPaper(db,Market());t=now();q={'symbol':'BTC-USD','bid':100,'ask':100.01,'bid_size':1000,'ask_size':1000,'timestamp':t.isoformat(),'observed_at':t.isoformat(),'depth_units':'base_units'};preview=manual.preview(Ticket(symbol='BTC-USD',side='buy',quantity=1),q)
 with pytest.raises(ValueError):model.place(Confirm(preview_id=preview['id'],confirmation='PLACE PAPER ORDER'))
 assert model.state() is None

def test_no_external_execution_dependency():
 for path in Path('backend/selection').glob('*.py'):
  tree=ast.parse(path.read_text());imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
  assert not any(v and (v.startswith('backend.execution') or v.startswith('backend.llm')) for v in imports)

def test_poor_liquidity_costs_and_redundancy_reduce_score():
 a,c,v=inputs();p=PortfolioPolicy();row=pd.Series({'date':now(),'realized_volatility':.02,'cost':.0022});votes=[{'group':g,'health':[],'weight':1.,'prediction_after_cost':.05,'probability':.8,'uncertainty':.03} for g in ['price_trend','macro']]
 good=score_opportunity(a,row,votes,[],p,{},v);bad=score_opportunity({**a,'eligibility':{'mean_dollar_volume':1e5}},row.copy().set_axis(row.index),votes,['Missing quote quality'],p,{},v);assert bad['score']<good['score'] and not bad['trade_eligible']

def test_fill_rechecks_artifact_and_hard_risk(db,monkeypatch):
 import backend.selection.portfolio as engine
 import backend.product.paper as simulator
 t=[now()];monkeypatch.setattr(engine,'now',lambda:t[0]);monkeypatch.setattr(simulator,'now',lambda:t[0]);a,s=approved_fixture(db,t[0]);db.set_setting('model_opportunities',s)
 class Provider:
  async def forward_quote(self,symbol):return {'symbol':symbol,'bid':100,'ask':100.01,'bid_size':1000,'ask_size':1000,'timestamp':t[0].isoformat(),'observed_at':t[0].isoformat(),'depth_units':'base_units'}
 svc=ModelPortfolio(db,Provider());svc.market.lookup=lambda _:a;asyncio.run(svc.cycle());assert svc.paper.view()['orders']
 db.set_setting('model_portfolio_control',{'high_water':20000,'entries_blocked':False});t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());assert not svc.paper.view()['fills']

def test_stale_quote_cannot_create_model_order(db):
 a,s=approved_fixture(db,now());db.set_setting('model_opportunities',s)
 class Provider:
  async def forward_quote(self,symbol):return {'symbol':symbol,'bid':100,'ask':100.01,'bid_size':1000,'ask_size':1000,'timestamp':(now()-timedelta(minutes=10)).isoformat(),'observed_at':now().isoformat(),'depth_units':'base_units'}
 svc=ModelPortfolio(db,Provider());svc.market.lookup=lambda _:a;asyncio.run(svc.cycle());assert not svc.paper.view()['orders'];assert 'Stale' in db.records('auto_decision')[0]['payload']['reason']

def test_model_partial_fill_and_expiry(db,monkeypatch):
 import backend.selection.portfolio as engine
 import backend.product.paper as simulator
 t=[now()];monkeypatch.setattr(engine,'now',lambda:t[0]);monkeypatch.setattr(simulator,'now',lambda:t[0]);a,s=approved_fixture(db,t[0]);db.set_setting('model_opportunities',s)
 class Provider:
  async def forward_quote(self,symbol):return {'symbol':symbol,'bid':100,'ask':100.01,'bid_size':1,'ask_size':1,'timestamp':t[0].isoformat(),'observed_at':t[0].isoformat(),'depth_units':'base_units'}
 svc=ModelPortfolio(db,Provider());svc.market.lookup=lambda _:a;asyncio.run(svc.cycle());t[0]+=timedelta(seconds=6);asyncio.run(svc.cycle());o=svc.paper.view()['orders'][0];assert o['status']=='PARTIALLY_FILLED' and o['filled_quantity']==pytest.approx(.05)
 t[0]+=timedelta(seconds=60);asyncio.run(svc.cycle());assert svc.paper.view()['orders'][0]['status']=='EXPIRED'

def test_invalid_data_cannot_become_eligible_by_high_score(db):
 a,s=approved_fixture(db,now());r=s['rows'][0];r['health']=['Required feature missing'];r['trade_eligible']=False;r['score']=100
 assert size(r,inputs()[2],{a['symbol']:a},{},policy(db),10000)['notional']==0

def test_regime_small_samples_shrink_instead_of_chasing():
 p=PortfolioPolicy();assert p.minimum_conditional_dates>=30 and p.shrinkage_prior_dates>=60


def test_selection_api_is_read_only_by_default_and_origin_guarded(db):
 from backend.api.main import create_app
 from fastapi.testclient import TestClient
 with TestClient(create_app(db,start_workers=False)) as client:
  for url in ['portfolio','opportunities','registry','families','alerts','policy-research']:
   assert client.get('/api/v1/selection/'+url).status_code==200
  r=client.post('/api/v1/selection/pause',json={'paused':True},headers={'Origin':'https://evil.example','X-TraderX-Client':'local-ui'});assert r.status_code==403
  assert db.setting('manual_paper') is None and db.setting('model_paper_account') is None

def test_calibration_errors_cannot_cancel_across_bins():
 from backend.selection.registry import calibration_quality
 q=calibration_quality([(.1,1)]*30+[(.9,0)]*30)
 assert q['expected_calibration_error']==pytest.approx(.9)
 assert q['brier']==pytest.approx(.81)
 assert calibration_quality([(.9,1)])['expected_calibration_error'] is None

def test_fill_rechecks_cost_edge(db):
 a,snapshot=approved_fixture(db,now());row=snapshot['rows'][0];row['expected_edge']=.002;db.set_setting('model_opportunities',snapshot)
 svc=ModelPortfolio(db);state=svc.paper.new_account();q={'bid':99,'ask':101,'timestamp':now().isoformat()}
 order={'id':'candidate','symbol':'BTC-USD','policy':{'slippage_bps':5,'fee_bps':5}}
 assert svc.paper.maximum_fill_notional(order,state,q,now())==0

def test_stale_holdings_block_new_entries(db):
 a,snapshot=approved_fixture(db,now());db.set_setting('model_opportunities',snapshot);svc=ModelPortfolio(db);state=svc.paper.new_account()
 state['positions']['BTC-USD']={'quantity':1.,'average_cost':100.,'opened_at':now().isoformat()};state['marks']['BTC-USD']={'bid':100,'timestamp':(now()-timedelta(minutes=10)).isoformat()};db.set_setting(svc.paper.account_key,state)
 assert svc.mark_metrics()[2] is True
 assert db.setting('model_portfolio_control')['stale_marks']==1

def test_automatic_ledger_never_truncates_manual_fill_limit():
 assert ModelPaper.fill_limit is None and ManualPaper.fill_limit==1000

def test_foreign_receipts_cannot_approve_challenger(db):
 mid=db.put('strategy_model',{'family':'momentum'});reg=SelectionRegistry(db);reg.refresh();rid=db.records('selection_challenger')[0]['payload'];fake=db.put('manual_fill',{'model_id':mid})
 e={**{k:fake for k in ['definition_id','walk_forward_id','holdout_id','forward_id','portfolio_id']},'model_id':mid,'artifact_hash':rid['artifact_hash'],'criteria_hash':rid['criteria_hash'],'definition_at':rid['registered_at'],'holdout_start':'2099-01-01','walk_forward_folds':3,'walk_forward_passed':True,'holdout_dates':100,'holdout_lower_bound':1,'forward_dates':100,'forward_lower_bound':1,'portfolio_dates':100,'portfolio_excess_lower_bound':1,'calibration_error':0}
 eid=db.put('selection_evaluation',e);result=reg.evaluate(mid,eid)
 assert not result['eligible'] and not result['gates']['prospective_source_receipts']
 assert len(db.records('selection_eligibility'))==1
 assert reg.refresh()['eligible']==0
