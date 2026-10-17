"""Venue boundary. Only paper Alpaca has a network submission implementation."""
from abc import ABC,abstractmethod
import httpx
from backend.schemas.contracts import ApprovedOrder

class ExecutionProvider(ABC):
    @abstractmethod
    async def submit(self,order:ApprovedOrder,client_order_id:str):...

class DisabledExecutionProvider(ExecutionProvider):
    def __init__(self,venue):self.venue=venue
    async def submit(self,order,client_order_id):
        if type(order) is not ApprovedOrder:raise TypeError('ApprovedOrder required')
        raise ValueError(self.venue+' external execution is disabled; use the internal simulator')

class AlpacaPaperProvider(ExecutionProvider):
    BASE='https://paper-api.alpaca.markets'
    def __init__(self,credentials,transport=None):self.cfg=credentials;self.transport=transport
    def configured(self):return bool(self.cfg.get('ALPACA_API_KEY') and self.cfg.get('ALPACA_API_SECRET'))
    def guard(self,mutation=False):
        if self.cfg.get('ALPACA_TRADING_MODE','paper')!='paper' or self.cfg.get('ALPACA_TRADING_BASE_URL',self.BASE).rstrip('/')!=self.BASE:
            raise ValueError('Only the fixed Alpaca paper endpoint is supported')
        if not self.configured():raise ValueError('Alpaca paper credentials are not configured')
        if mutation and self.cfg.get('ALPACA_PAPER_EXECUTION_ENABLED')!='true':raise ValueError('Alpaca paper submission is disabled in configuration')
    async def request(self,path,*,method='GET',params=None,body=None,allow_missing=False):
        self.guard(method!='GET')
        headers={'APCA-API-KEY-ID':self.cfg['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':self.cfg['ALPACA_API_SECRET']}
        try:
            async with httpx.AsyncClient(timeout=15,trust_env=False,follow_redirects=False,transport=self.transport) as client:
                response=await client.request(method,self.BASE+path,headers=headers,params=params,json=body)
            if response.status_code==404 and allow_missing:return None
            if response.status_code==204:return {}
            if response.status_code>=300:raise ValueError('Alpaca paper request returned HTTP '+str(response.status_code))
            return response.json()
        except httpx.HTTPError:raise ValueError('Alpaca paper connection outcome is uncertain; reconcile before further submission') from None
    async def snapshot(self):
        account=await self.request('/v2/account');positions=await self.request('/v2/positions')
        orders=await self.request('/v2/orders',params={'status':'open','limit':500,'nested':'false'})
        if not isinstance(orders,list) or len(orders)>=500:raise ValueError('Open-order list is incomplete; submission blocked')
        if not isinstance(positions,list):raise ValueError('Invalid position response')
        return account,positions,orders
    async def lookup(self,client_order_id):
        return await self.request('/v2/orders:by_client_order_id',params={'client_order_id':client_order_id},allow_missing=True)
    async def submit(self,order,client_order_id):
        if type(order) is not ApprovedOrder or order.venue!='alpaca_paper':raise TypeError('Alpaca paper ApprovedOrder required')
        if order.asset.asset_class not in ('stock','etf') or not float(order.quantity).is_integer():raise ValueError('Paper adapter supports whole-share stocks/ETFs only')
        from decimal import Decimal,ROUND_DOWN,ROUND_UP
        price=Decimal(str(order.limit_price));tick=Decimal('.01') if price>=1 else Decimal('.0001')
        price=price.quantize(tick,rounding=ROUND_DOWN if order.side=='buy' else ROUND_UP)
        if price<=0:raise ValueError('Limit price is below the supported price increment')
        return await self.request('/v2/orders',method='POST',body={'symbol':order.asset.symbol,'qty':str(int(order.quantity)),'side':order.side,
                     'type':'limit','time_in_force':'day','limit_price':str(price),'client_order_id':client_order_id,'extended_hours':False})
    async def cancel(self,broker_order_id):
        from uuid import UUID
        identifier=str(UUID(broker_order_id))
        return await self.request('/v2/orders/'+identifier,method='DELETE')

class InternalPaperProvider(ExecutionProvider):
    """The same strict order boundary used by network paper venues."""
    def __init__(self,engine,quote_reader):self.engine=engine;self.quote_reader=quote_reader
    async def submit(self,order,client_order_id):
        if type(order) is not ApprovedOrder or order.venue!='internal_paper':raise TypeError('Internal paper ApprovedOrder required')
        # Engine verifies persisted approval and protects its own idempotent ledger.
        quote,healthy=self.quote_reader(order.asset.symbol)
        return self.engine.execute(order,quote,healthy)

class CoinbaseReadOnlyProvider(DisabledExecutionProvider):
    def __init__(self,market):super().__init__('coinbase');self.market=market
    async def snapshot(self):return await self.market.coinbase_quote('BTC-USD')

class HyperliquidReadOnlyProvider(DisabledExecutionProvider):
    def __init__(self,market):super().__init__('hyperliquid');self.market=market
    async def snapshot(self):return await self.market.hyperliquid()
