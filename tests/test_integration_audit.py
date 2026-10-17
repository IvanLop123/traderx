"""Cross-module readiness regressions; all execution uses disposable data."""
from pathlib import Path
import copy
from test_platform import db
from test_ensemble import evidence
from test_personal_paper import Market
from backend.ensemble.engine import decide
from backend.qualification.diagnostics import refresh_diagnostics

def test_default_ensemble_does_not_apply_unproven_adaptive_weights():
    row=evidence();asset=Market().lookup('BTC-USD')
    for i,v in enumerate(row['votes']):
        v.update(alpha_id=str(i),adaptive_multiplier=2 if i==0 else .001)
    result=decide(row,asset)
    assert result['mode']=='equal'
    assert result['family_weights']['momentum']==result['family_weights']['trend_following']
    assert max(g['weight'] for g in result['groups'])<=.5
    changed=copy.deepcopy(row);changed['votes'][0]['adaptive_multiplier']=.001
    assert decide(changed,asset)['edge']==result['edge']
    assert decide(row,asset,mode='dynamic')['mode']=='dynamic'

def test_current_diagnostics_bounded_and_original_history_preserved(db,monkeypatch):
    import backend.qualification.diagnostics as module
    monkeypatch.setattr(module,'CURRENT_LIMIT',3)
    for i in range(8):db.put('auto_decision',{'status':'CASH','symbol':'X','candidate':{'health':[],'votes':[]}},record_id='decision-'+str(i),available_at='2026-01-01T00:00:00Z')
    before={r['id'] for r in db.records('auto_decision')}
    result=refresh_diagnostics(db)
    assert result['current']['decisions']==3 and result['original']['decisions']==8
    assert result['total_decisions']==8 and result['current_limit']==3
    assert {r['id'] for r in db.records('auto_decision')}==before
    original=result['original']
    db.put('auto_decision',{'status':'CASH','symbol':'Y','candidate':{'health':[],'votes':[]}},record_id='new')
    next_result=refresh_diagnostics(db)
    assert next_result['original']==original and next_result['total_decisions']==9
    assert next_result['current']['decisions']==3

def test_retired_adapters_not_called_by_history_extension():
    from backend.research import engine
    assert not hasattr(engine,'candidate_from_prediction')
    assert '.kalshi(' not in Path('scripts/research/extend_history.py').read_text()

def test_eia_ingestion_uses_the_same_bounded_geography_as_health_probe(db):
    import asyncio,httpx
    from backend.providers.market import MarketProviders
    def handle(request):
        assert request.url.params['facets[stateid][]']=='US'
        assert request.url.params['facets[sectorid][]']=='ALL'
        assert int(request.url.params['length'])<=100
        return httpx.Response(200,json={'response':{'data':[{'stateid':'US','sectorid':'ALL','price':'12','period':'2026-01'}]}})
    p=MarketProviders(db,credentials={'EIA_API_KEY':'fixture'},transport=httpx.MockTransport(handle))
    asyncio.run(p.eia())
    assert db.setting('provider_eia')['status']=='WORKING_READ_ONLY'
    assert len(db.records('energy'))==1
