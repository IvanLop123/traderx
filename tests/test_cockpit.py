"""Deterministic decisions and manual-only notes tested with an isolated ledger."""
import copy
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from test_platform import db
from test_personal_paper import Market,quote
from backend.schemas.contracts import now
from backend.product.paper import ManualPaper,Ticket,Confirm
from backend.product.cockpit import Cockpit,describe,JournalNote,Idea
from backend.research.universe import Universe,Instrument
from backend.api.main import create_app

def evidence(symbol='BTC-USD',at=None):
    at=at or now();v={'family':'momentum','model_id':'fixture_momentum','prediction_after_cost':.02,'health':[],'weight':0,'probability':.65,'uncertainty':.03,'features':{'return_20':.1}}
    return {'symbol':symbol,'score':25,'research_score':70,'expected_edge':.02,'uncertainty':.03,'probability':.65,'agreement':1.,'daily_volatility':.02,'feature_available_at':at.isoformat(),'health':[],'reasons':[],'votes':[v,{**v,'model_id':'variant'},{**v,'family':'macro_regime','model_id':'macro'}],'group_votes':[{'group':'price_trend','edge':.02}],'regime':'uptrend'}
def setup(db):
    db.set_setting('research_universe',Universe(instruments=[Instrument(symbol='BTC-USD',asset_class='crypto'),Instrument(symbol='PLTR',asset_class='stock')]).model_dump(mode='json'))
    assets={s:{**Market().lookup(s),'name':'Isolated fixture '+s,'price':100.,'price_at':now().isoformat()} for s in ['BTC-USD','PLTR']};snap={'as_of':now().isoformat(),'rows':[evidence(s) for s in assets],'assets':assets};db.set_setting('model_opportunities',snap);p=ManualPaper(db,Market());return p,Cockpit(db,p),snap

def test_view_grounded_family_collapse_and_unqualified_manual_allowed(db):
    p,c,s=setup(db);r=c.asset('BTC-USD');assert r['view']=='BUY' and not r['qualified'];assert r['dependence_groups']==2;assert r['families'][0]['used_variants']==2;assert len(r['families'])==11;assert any('10.00%' in x for x in r['likes']);assert r['rank'] is None;assert 'insider' not in ' '.join(r['likes']).lower();assert p.preview(Ticket(symbol='BTC-USD',side='buy',amount=100),quote())
@pytest.mark.parametrize('change,view', [({'expected_edge':-.02},'NO TRADE'),({'probability':.5},'NO TRADE'),({'expected_edge':.0001},'NO TRADE'),({'health':['drift']},'NO TRADE'),({'feature_available_at':(now()-timedelta(days=6)).isoformat()},'INSUFFICIENT EVIDENCE'),({'feature_available_at':(now()+timedelta(days=1)).isoformat()},'INSUFFICIENT EVIDENCE'),({'votes':[]},'INSUFFICIENT EVIDENCE')])
def test_honest_views(db,change,view):
    p,c,s=setup(db);r=copy.deepcopy(s['rows'][0]);r.update(change)
    for v in r['votes']:
        if 'expected_edge' in change:v['prediction_after_cost']=change['expected_edge']
        if 'probability' in change:v['probability']=change['probability']
    assert describe(r,s['assets']['BTC-USD'],now())['view']==view

def test_cross_sectional_rank_requires_same_time_class_and_valid_models(db):
    p,c,s=setup(db);r=s['rows'][0];r['votes'].append({**r['votes'][0],'family':'cross_sectional_ranking'});db.set_setting('model_opportunities',s);assert c.asset('BTC-USD')['rank'] is None
    u=db.setting('research_universe');u['instruments'].append(Instrument(symbol='ETH-USD',asset_class='crypto').model_dump(mode='json'));db.set_setting('research_universe',u);s['assets']['ETH-USD']={**s['assets']['BTC-USD'],'symbol':'ETH-USD'};other=copy.deepcopy(r);other['symbol']='ETH-USD';other['votes'][-1]['prediction_after_cost']=.01;s['rows'].append(other);db.set_setting('model_opportunities',s);assert c.asset('BTC-USD')['rank']['rank']==1;assert c.asset('ETH-USD')['rank']['rank']==2
    other['votes'][-1]['health']=['missing'];db.set_setting('model_opportunities',s);assert c.asset('BTC-USD')['rank'] is None

def test_suggested_size_missing_inputs_negative_edge_and_concentration(db):
    p,c,s=setup(db);r=c.asset('BTC-USD');assert 0<r['suggested_size']['amount']<=1000;r['uncertainty']=None;assert c.suggest(r)['amount'] is None;r['uncertainty']=.03;r['expected_edge']=-.01;assert c.suggest(r)['amount']==0

def test_ideas_context_idempotence_journal_and_isolation(db):
    p,c,s=setup(db);db.set_setting('forward_state_sentinel',{'cash':123,'evidence_policy':'quarantined_evaluation'});db.set_setting('model_portfolio_sentinel',{'cash':456})
    t=now();p.clock=lambda:t
    preview=c.save_context(p.preview(Ticket(symbol='BTC-USD',side='buy',quantity=1),quote(t)),JournalNote(reason='Momentum hypothesis',followed_view='followed',expected_outcome='Higher price'))
    req=Confirm(preview_id=preview['id'],confirmation='PLACE PAPER ORDER');o=p.place(req);assert p.place(req)['id']==o['id'];assert not p.view()['fills'];t+=timedelta(seconds=6);p.process('BTC-USD',quote(t),t)
    # Observe with real clock (timestamp is explicitly in its past).
    db.put('manual_observation',{'account_id':p.view()['id'],'symbol':'BTC-USD','at':t.isoformat(),'bid':110.,'average_cost':100.1,'view':'NO TRADE','score':20,'regime':'range'},'BTC-USD')
    s['rows'][0]['agreement']=.5;db.set_setting('model_opportunities',s);t+=timedelta(seconds=1);sell=c.save_context(p.preview(Ticket(symbol='BTC-USD',side='sell',quantity=1),quote(t,bid=110,ask=110.01)),JournalNote());p.place(Confirm(preview_id=sell['id'],confirmation='PLACE PAPER ORDER'));t+=timedelta(seconds=6);p.process('BTC-USD',quote(t,bid=110,ask=110.01),t)
    journal=c.journal();trade=journal['trades'][0];assert trade['closed_at'];assert trade['view_changed'];assert trade['realized_pnl']==pytest.approx(p.view()['realized_pnl']);assert trade['maximum_favorable_excursion']>0;assert trade['entry_evidence']['view']=='BUY';assert trade['entry_evidence']['raw_votes'][0]['features']=={'return_20':.1};assert journal['comparison']['followed']['completed_trades']==1;assert not trade['training_eligible'];assert not trade['evaluation_eligible']
    c.idea(Idea(symbol='PLTR',notes='Niche watch',target_entry=10));assert c.board()['ideas'][0]['notes']=='Niche watch';c.idea(Idea(symbol='PLTR',saved=False));assert not c.board()['ideas'];assert not db.records('forward_decision');assert db.setting('forward_state_sentinel')['cash']==123;assert db.setting('model_portfolio_sentinel')['cash']==456

def test_daily_comparison_uses_previous_asof_not_current_age(db):
    p,c,s=setup(db);old=copy.deepcopy(s);old['as_of']=(now()-timedelta(days=1)).isoformat();old['rows'][0]['feature_available_at']=(now()-timedelta(days=4,hours=1)).isoformat();old['rows'][0]['score']=20;db.put('auto_snapshot',old,available_at=(now()-timedelta(days=1)).isoformat());b=c.board();assert b['changes'][0]['before']=='BUY';assert b['changes'][0]['score_change']==5

def test_api_preview_notes_validation_security_and_no_network(db):
    p,c,s=setup(db);app=create_app(db,start_workers=False);app.state.manual_paper.market.lookup=lambda sym:Market().lookup(sym)
    async def q(sym):return quote(symbol=sym)
    app.state.providers.forward_quote=q
    with TestClient(app) as client:
        h={'X-TraderX-Client':'local-ui'};body={'symbol':'BTC-USD','side':'buy','amount':100,'journal':{'reason':'test','followed_view':'followed'}}
        assert client.post('/api/v1/product/preview',json=body).status_code==403
        assert client.post('/api/v1/product/preview',json={**body,'journal':{'research':{'view':'BUY'}}},headers=h).status_code==422
        r=client.post('/api/v1/product/preview',json=body,headers=h);assert r.status_code==200;r=r.json();assert r['research']['view']=='BUY';assert r['resulting_allocation']>0
        assert client.put('/api/v1/product/ideas',json={'symbol':'UNKNOWN'},headers=h).status_code==422
        assert client.get('/api/v1/product/cockpit').json()['external_execution'] is False
        assert not db.records('manual_order')
