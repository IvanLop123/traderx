"""Paper execution contract tests. All brokerage responses are isolated fixtures."""
from datetime import timedelta
import httpx
import pytest
from backend.storage.database import Database,Base
from backend.risk.engine import PaperEngine
from backend.execution.paper_broker import PaperBroker
from backend.schemas.contracts import TradeCandidate,AssetIdentifier,ApprovedOrder,now

@pytest.fixture
def context(tmp_path):
    db=Database('sqlite:///'+str(tmp_path/'broker.db'));Base.metadata.create_all(db.engine)
    paper=PaperEngine(db);paper.halt(False)
    return db,paper

class BrokerFixture:
    def __init__(self):self.posts=0;self.remote={};self.fail=False;self.pending=[];self.account_id='fixture-account'
    def __call__(self,request):
        assert request.url.host=='paper-api.alpaca.markets'
        assert request.headers['APCA-API-KEY-ID']=='fixture'
        path=request.url.path
        if path=='/v2/account':return httpx.Response(200,json={'id':self.account_id,'equity':'100000','cash':'100000','last_equity':'100000','buying_power':'100000','status':'ACTIVE'})
        if path=='/v2/positions':return httpx.Response(200,json=[])
        if path=='/v2/orders' and request.method=='GET':return httpx.Response(200,json=self.pending)
        if path=='/v2/orders:by_client_order_id':
            o=self.remote.get(request.url.params['client_order_id']);return httpx.Response(200 if o else 404,json=o or {})
        if path=='/v2/orders' and request.method=='POST':
            import json
            self.posts+=1;p=json.loads(request.content)
            o={**p,'id':'11111111-1111-1111-1111-111111111111','status':'new','filled_qty':'0','filled_avg_price':None}
            self.remote[p['client_order_id']]=o
            if self.fail:raise httpx.ReadTimeout('fixture timeout after remote acceptance')
            return httpx.Response(200,json=o)
        if request.method=='DELETE':
            for o in self.remote.values():o['status']='canceled'
            return httpx.Response(204)
        raise AssertionError(path)

def setup(context,enabled=True):
    db,paper=context;remote=BrokerFixture();cfg={'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture-secret','ALPACA_PAPER_EXECUTION_ENABLED':'true' if enabled else 'false'}
    broker=PaperBroker(db,paper,cfg,httpx.MockTransport(remote))
    quote={'price':100,'bid':99.99,'ask':100.01,'volume':100000,'timestamp':now().isoformat()}
    c=TradeCandidate(asset=AssetIdentifier(symbol='TEST',asset_class='stock'),prediction_id='fixture',direction='buy',horizon='1d',entry_price=100,quantity=5,
                     expected_edge=.03,expected_costs=.001,expected_downside=-.1,confidence=.6,evidence_ids=['fixture'],expires_at=now()+timedelta(minutes=3),liquidity={})
    db.put('candidate',c,'TEST');return db,paper,broker,remote,quote,c

async def test_only_durable_approval_can_submit_and_venue_is_pinned(context):
    db,paper,b,r,q,c=setup(context)
    with pytest.raises(TypeError):await b.execute(c,q)
    order=await b.assess(c,q)
    assert order.venue=='alpaca_paper'
    with pytest.raises(ValueError,match='venue'):paper.execute(order,q)
    result=await b.execute(order,q);assert r.posts==1 and result['status']=='new'
    again=await b.execute(order,q);assert r.posts==1 and again['client_order_id']==result['client_order_id']
    r.remote[result['client_order_id']].update(status='partially_filled',filled_qty='2',filled_avg_price='100')
    await b.sync();assert b.orders()[0]['filled_quantity']==2
    r.remote[result['client_order_id']].update(status='filled',filled_qty='5')
    await b.sync();assert b.orders()[0]['status']=='filled'
    assert paper.snapshot()['positions']=={}  # Broker accounting never contaminates the internal simulator.

async def test_uncertain_post_reconciles_without_duplicate(context):
    db,paper,b,r,q,c=setup(context);o=await b.assess(c,q);r.fail=True
    result=await b.execute(o,q)
    assert result['status']=='uncertain' and paper.snapshot()['kill_switch'] and r.posts==1
    result=await b.execute(o,q)
    assert result['status']=='new' and r.posts==1

async def test_disabled_flag_blocks_post_even_with_keys(context):
    db,paper,b,r,q,c=setup(context,False);o=await b.assess(c,q)
    with pytest.raises(ValueError,match='disabled'):await b.execute(o,q)
    assert r.posts==0

async def test_live_endpoint_configuration_rejected(context):
    db,paper,b,r,q,c=setup(context)
    b.provider.cfg['ALPACA_TRADING_BASE_URL']='https://api.alpaca.markets'
    with pytest.raises(ValueError,match='paper endpoint'):await b.sync()
    assert r.posts==0

async def test_halt_and_pending_exposure_block_orders(context):
    db,paper,b,r,q,c=setup(context);o=await b.assess(c,q);paper.halt(True)
    with pytest.raises(ValueError,match='GLOBAL_KILL_SWITCH'):await b.execute(o,q)
    paper.halt(False)
    r.pending=[{'symbol':'TEST','qty':'100','filled_qty':'0','side':'buy','limit_price':'100','client_order_id':'external'}]
    rejected=await b.assess(c,q)
    assert 'POSITION_CONCENTRATION' in rejected.reasons and r.posts==0

async def test_account_change_and_response_tampering_block(context):
    db,paper,b,r,q,c=setup(context);o=await b.assess(c,q);r.account_id='other-account'
    with pytest.raises(ValueError,match='another paper account'):await b.execute(o,q)
    r.account_id='fixture-account';result=await b.execute(o,q)
    r.remote[result['client_order_id']]['qty']='999'
    with pytest.raises(ValueError,match='quantity mismatch'):await b.sync()
    assert paper.snapshot()['kill_switch']

async def test_cancel_requires_broker_confirmation(context):
    db,paper,b,r,q,c=setup(context);o=await b.assess(c,q);result=await b.execute(o,q)
    result=await b.cancel(result['client_order_id'])
    assert result['status']=='canceled' and result['filled_quantity']==0

async def test_pending_sells_do_not_release_risk_exposure(context):
    db,paper,b,r,q,c=setup(context);await b.sync()
    state=db.setting('alpaca_paper_snapshot');state['positions']={'TEST':{'quantity':50,'market_price':100,'average_cost':100,'asset_class':'stock'}}
    state['pending_orders']=[{'symbol':'TEST','qty':'40','filled_qty':'0','side':'sell','client_order_id':'outside'}]
    state,issues=b.risk_state(state)
    assert state['positions']['TEST']['quantity']==50 and state['reserved_sells']['TEST']==40 and not issues

async def test_stale_response_cannot_undo_partial_fill(context):
    db,paper,b,r,q,c=setup(context);order=await b.assess(c,q);ledger=await b.execute(order,q)
    old=dict(r.remote[ledger['client_order_id']]);new={**old,'status':'partially_filled','filled_qty':'3','filled_avg_price':'100'}
    b._record_response(ledger,new)
    result=b._record_response(ledger,old)
    assert result['filled_quantity']==3 and result['status']=='partially_filled'

@pytest.mark.asyncio
async def test_named_readonly_venues_reject_candidates_and_orders():
    from backend.execution.providers import CoinbaseReadOnlyProvider,HyperliquidReadOnlyProvider
    for cls in (CoinbaseReadOnlyProvider,HyperliquidReadOnlyProvider):
        with pytest.raises(TypeError):await cls(None).submit({'direction':'buy'},'never-submit')

def test_execution_capabilities_are_explicit(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.main import create_app
    db=Database('sqlite:///'+str(tmp_path/'venues.db'));Base.metadata.create_all(db.engine)
    client=TestClient(create_app(db,start_workers=False))
    response=client.get('/api/v1/execution/venues');assert response.status_code==200
    rows={r['venue']:r for r in response.json()['venues']}
    assert not response.json()['live_trading'] and rows['internal_paper']['supports_orders']
    assert not rows['internal_paper']['enabled'] and 'kalshi_demo' not in rows
