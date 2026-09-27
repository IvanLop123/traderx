import httpx
import pytest
from backend.storage.database import Database,Base
from backend.providers.market import MarketProviders,ProviderError

@pytest.fixture
def db(tmp_path):
    d=Database('sqlite:///'+str(tmp_path/'providers.db'));Base.metadata.create_all(d.engine);return d

async def test_real_shape_quote_normalization(db):
    def handler(request):
        assert request.url.host=='api.exchange.coinbase.com' and request.method=='GET'
        return httpx.Response(200,json={'price':'100','bid':'99.9','ask':'100.1','volume':'2000','time':'2026-09-25T12:00:00Z'})
    p=MarketProviders(db,{},httpx.MockTransport(handler))
    data=await p.coinbase_quote('BTC-USD');assert data['price']==100
    assert len(db.records('event'))==1 and len(db.records('quote'))==1
    p.last.clear();await p.coinbase_quote('BTC-USD')
    assert len(db.records('event'))==1

async def test_missing_optional_credentials_no_network(db):
    def fail(_):pytest.fail('No credential should make no request')
    p=MarketProviders(db,{},httpx.MockTransport(fail))
    with pytest.raises(ProviderError,match='credentials'):await p.fred('FEDFUNDS','2026-01-01')
    with pytest.raises(ProviderError):await p.sec('320193')
    with pytest.raises(ProviderError):await p.social('$AAPL')

@pytest.mark.parametrize('status,expected',[(429,'RATE_LIMITED'),(403,'DEGRADED'),(401,'DEGRADED')])
async def test_provider_failures_isolated(db,status,expected):
    p=MarketProviders(db,{},httpx.MockTransport(lambda r:httpx.Response(status,json={})))
    with pytest.raises(ProviderError):await p.coinbase_quote('BTC-USD')
    assert next(x for x in p.status() if x['provider']=='coinbase')['status']==expected
    assert next(x for x in p.status() if x['provider']=='hyperliquid')['status']=='NOT_CHECKED'

async def test_fred_vintage_explicit(db):
    def handle(req):
        assert req.url.params['realtime_start']=='2025-01-01'
        assert req.url.params['realtime_end']=='2025-01-01'
        return httpx.Response(200,json={'observations':[{'date':'2024-12-01','value':'4.1','realtime_start':'2025-01-01','realtime_end':'2025-01-01'}]})
    p=MarketProviders(db,{'FRED_API_KEY':'fixture'},httpx.MockTransport(handle));await p.fred('UNRATE','2025-01-01')
    assert db.records('macro')[0]['payload']['vintage']=='2025-01-01'

async def test_malformed_provider_data_is_degraded_not_synthetic(db):
    p=MarketProviders(db,{},httpx.MockTransport(lambda req:httpx.Response(200,json={'price':'not-a-number'})))
    with pytest.raises(ProviderError,match='shape'):await p.coinbase_quote('BTC-USD')
    assert next(x for x in p.status() if x['provider']=='coinbase')['status']=='DEGRADED'
    assert db.records('quote')==[]

async def test_alpaca_quote_uses_key_headers_and_no_current_partial_bar(db):
    def handler(req):
        assert req.headers['APCA-API-KEY-ID']=='fixture-id'
        assert 'fixture-id' not in str(req.url)
        return httpx.Response(200,json={'symbol':'AAPL','quote':{'t':'2026-09-25T12:00:00Z','bp':100,'ap':100.1,'bs':10,'as':20}})
    p=MarketProviders(db,{'ALPACA_API_KEY':'fixture-id','ALPACA_API_SECRET':'fixture-secret'},httpx.MockTransport(handler))
    q=await p.alpaca_quote('AAPL')
    assert q['asset_class']=='stock' and q['price_type']=='quote_midpoint'
    assert q['price']==pytest.approx(100.05)

def test_removed_credentials_clear_stale_working_status(db):
    db.set_setting('provider_alpaca',{'status':'WORKING_READ_ONLY','missing_fields':[]})
    p=MarketProviders(db,{})
    row=next(x for x in p.status() if x['provider']=='alpaca')
    assert row['status']=='NOT_CONFIGURED' and row['missing_fields']
