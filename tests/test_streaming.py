import asyncio
import pytest
from backend.storage.database import Database,Base
from backend.providers.market import MarketProviders
from backend.providers.streaming import CoinbaseStream
from backend.schemas.contracts import now

@pytest.fixture
def stream(tmp_path):
    db=Database('sqlite:///'+str(tmp_path/'stream.db'));Base.metadata.create_all(db.engine)
    return CoinbaseStream(db,MarketProviders(db,{}),asyncio.Event(),{'MARKET_SYMBOLS':'BTC-USD','COINBASE_STREAM_BOOKS':'true','COINBASE_STREAM_TRADES':'true'})

def test_ticker_is_deterministic_deduplicated_and_validated(stream):
    message={'type':'ticker','product_id':'BTC-USD','time':now().isoformat(),'price':'100','best_bid':'99','best_ask':'101','volume_24h':'2000'}
    stream.handle(message);stream.handle(message)
    assert len(stream.db.records('quote'))==1
    message.update(time=now().isoformat(),price='nan')
    with pytest.raises(ValueError):stream.handle(message)
    assert stream.db.records('analysis')==[]

def test_book_absolute_size_deletion_and_reconnect_reset(stream):
    stream.handle({'type':'snapshot','product_id':'BTC-USD','bids':[['99','5'],['98','10']],'asks':[['101','4']]})
    stream.handle({'type':'l2update','product_id':'BTC-USD','time':now().isoformat(),'changes':[['buy','99','2'],['buy','98','0']]})
    assert stream.books['BTC-USD']['bids']=={99:2}
    stream.reset()
    with pytest.raises(ValueError,match='before snapshot'):stream.handle({'type':'l2update','product_id':'BTC-USD','time':now().isoformat(),'changes':[]})

def test_trade_gap_is_explicit_and_duplicates_ignored(stream):
    message={'type':'match','product_id':'BTC-USD','time':now().isoformat(),'price':'100','size':'2','side':'buy','trade_id':10}
    stream.handle(message);stream.handle(message)
    stream.handle({**message,'trade_id':12})
    assert len(stream.db.records('trade'))==2 and stream.gaps['BTC-USD']['status']=='GAP_DETECTED'
    assert stream.db.records('trade')[0]['payload']['maker_side']=='buy'
