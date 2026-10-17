"""Free Coinbase streaming; sampled books, optional trades, independent REST fallback."""
import asyncio
import json
import math
import re
import time
from datetime import datetime,timezone
from websockets.asyncio.client import connect
from backend.schemas.contracts import now

URL='wss://ws-feed.exchange.coinbase.com'

def number(value,positive=False):
    n=float(value)
    if not math.isfinite(n) or n<0 or (positive and n==0):raise ValueError('Invalid streaming price/size')
    return n

def stamp(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('Stream time must include timezone')
    if t>now()+__import__('datetime').timedelta(seconds=30):raise ValueError('Stream time is in the future')
    return t.astimezone(timezone.utc)

class CoinbaseStream:
    def __init__(self,db,providers,stop,settings):
        self.db=db;self.providers=providers;self.stop=stop;self.cfg=settings
        self.symbols=[s.strip() for s in (settings.get('MARKET_SYMBOLS') or 'BTC-USD,ETH-USD,SOL-USD').split(',') if re.fullmatch(r'[A-Z0-9-]{2,25}',s.strip())][:5]
        self.books={};self.last_book={};self.last_trade={};self.last_quote={};self.last_repair={};self.messages=0;self.gaps={};self.last_health=0
        self.book_enabled=settings.get('COINBASE_STREAM_BOOKS')=='true';self.trades_enabled=settings.get('COINBASE_STREAM_TRADES')=='true'
    def reset(self):self.books={};self.last_book={};self.last_quote={}
    def status(self,status,**extra):
        self.db.set_setting('stream_coinbase',{'status':status,'updated_at':now().isoformat(),'symbols':self.symbols,'messages':self.messages,
                                             'books_enabled':self.book_enabled,'trades_enabled':self.trades_enabled,'trade_gaps':self.gaps,**extra})
    def trade(self,message):
        symbol=message['product_id'];tid=int(message['trade_id'])
        previous=self.last_trade.get(symbol)
        if previous is not None and tid<=previous:return
        if previous is not None and tid>previous+1:self.gaps[symbol]={'after':previous,'before':tid,'status':'GAP_DETECTED'}
        event_time=stamp(message['time']);side=message['side']
        if side not in ('buy','sell'):raise ValueError('Invalid match side')
        payload={'symbol':symbol,'trade_id':tid,'price':number(message['price'],True),'size':number(message['size'],True),
                 'maker_side':side,'timestamp':event_time.isoformat(),'coverage':'observed_stream','gap_before':tid>previous+1 if previous is not None else None}
        self.providers.persist('coinbase','trade',payload,symbol,event_time,URL)
        self.last_trade[symbol]=tid
    def handle(self,message):
        kind=message.get('type');symbol=message.get('product_id')
        if kind=='error':raise ValueError('Exchange rejected streaming subscription')
        if symbol not in self.symbols:return
        self.messages+=1
        if kind=='ticker':
            t=stamp(message['time'])
            if t<=self.last_quote.get(symbol,datetime.min.replace(tzinfo=timezone.utc)):return
            bid=number(message['best_bid'],True);ask=number(message['best_ask'],True)
            if bid>ask:raise ValueError('Crossed streaming quote')
            q={'symbol':symbol,'price':number(message['price'],True),'bid':bid,'ask':ask,'volume':number(message['volume_24h']),
               'timestamp':t.isoformat(),'asset_class':'crypto','transport':'websocket','provider':'coinbase'}
            self.providers.persist('coinbase','quote',q,symbol,t,URL);self.last_quote[symbol]=t
        elif kind in ('snapshot','l2update') and self.book_enabled:
            if kind=='snapshot':
                if len(message['bids'])+len(message['asks'])>200000:raise ValueError('Book exceeds bounded memory limit')
                self.books[symbol]={'bids':{number(p,True):number(q) for p,q in message['bids']},'asks':{number(p,True):number(q) for p,q in message['asks']}}
                event_time=now()
            else:
                if symbol not in self.books:raise ValueError('Book update arrived before snapshot')
                event_time=stamp(message['time'])
                for side,price,size in message['changes']:
                    if side not in ('buy','sell'):raise ValueError('Invalid book side')
                    book=self.books[symbol]['bids' if side=='buy' else 'asks'];p=number(price,True);q=number(size)
                    if q:book[p]=q
                    else:book.pop(p,None)
            book=self.books[symbol]
            book['bids']={p:q for p,q in book['bids'].items() if q};book['asks']={p:q for p,q in book['asks'].items() if q}
            if len(book['bids'])+len(book['asks'])>200000:raise ValueError('Book exceeds bounded memory limit')
            if not book['bids'] or not book['asks'] or max(book['bids'])>=min(book['asks']):raise ValueError('Invalid reconstructed order book')
            if time.monotonic()-self.last_book.get(symbol,0)>=5:
                bids=sorted(book['bids'].items(),reverse=True)[:20];asks=sorted(book['asks'].items())[:20]
                b=sum(p*q for p,q in bids);a=sum(p*q for p,q in asks)
                payload={'symbol':symbol,'timestamp':event_time.isoformat(),'bids':bids,'asks':asks,'depth':20,
                         'notional_imbalance':(b-a)/(b+a) if b+a else None,'sampling_seconds':5,'coverage':'sampled_top20_not_full_event_history'}
                self.providers.persist('coinbase','order_book',payload,symbol,event_time,URL);self.last_book[symbol]=time.monotonic()
        elif kind=='match' and self.trades_enabled:self.trade(message)
        elif kind=='heartbeat' and self.trades_enabled:
            previous=self.last_trade.get(symbol);latest=int(message['last_trade_id'])
            if previous is not None and latest>previous:self.gaps[symbol]={'after':previous,'before':latest,'status':'HEARTBEAT_GAP'}
        if time.monotonic()-self.last_health>10:self.status('WORKING');self.last_health=time.monotonic()
    async def repair(self):
        for symbol,gap in list(self.gaps.items()):
            if gap['status']=='REPAIRED' or time.monotonic()-self.last_repair.get(symbol,0)<60:continue
            self.last_repair[symbol]=time.monotonic()
            rows=await self.providers.request('coinbase','https://api.exchange.coinbase.com/products/'+symbol+'/trades',params={'limit':100})
            rows=sorted([r for r in rows if int(r['trade_id'])>gap['after']],key=lambda r:int(r['trade_id']))
            ids={int(r['trade_id']) for r in rows};needed=range(gap['after']+1,gap['before']+1)
            # Late repairs retain their actual receive time and never rewrite earlier knowledge.
            for r in rows:
                t=stamp(r['time']);payload={'symbol':symbol,'trade_id':int(r['trade_id']),'price':number(r['price'],True),'size':number(r['size'],True),
                    'maker_side':r['side'],'timestamp':t.isoformat(),'coverage':'late_rest_repair','gap_before':None}
                identity='coinbase-trade-'+symbol+'-'+str(r['trade_id'])
                if not self.db.get(identity):self.db.put('trade_repair',payload,symbol,record_id=identity)
            gap['status']='REPAIRED' if gap['before']-gap['after']<=100 and all(i in ids for i in needed) else 'INCOMPLETE_HISTORY'
    async def run(self):
        delay=1
        channels=['heartbeat','ticker_batch']+(['level2_batch'] if self.book_enabled else [])+(['matches'] if self.trades_enabled else [])
        while not self.stop.is_set():
            self.reset();self.status('CONNECTING')
            try:
                async with connect(URL,open_timeout=15,ping_interval=20,ping_timeout=20,max_size=16*1024*1024,max_queue=1024) as socket:
                    await socket.send(json.dumps({'type':'subscribe','product_ids':self.symbols,'channels':channels}))
                    delay=1
                    while not self.stop.is_set():
                        raw=await asyncio.wait_for(socket.recv(),timeout=30)
                        self.handle(json.loads(raw))
                        if self.trades_enabled and self.gaps:await self.repair()
            except asyncio.CancelledError:raise
            except Exception:self.status('RECONNECTING',fallback='REST polling remains active; incomplete stream intervals are not imputed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=delay)
            except asyncio.TimeoutError:pass
            delay=min(60,delay*2)
        self.status('STOPPED')
