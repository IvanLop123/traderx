"""Read-only provider adapters; production data is never replaced with fixtures."""
import asyncio
import hashlib
import json
import time
from datetime import date, datetime, timezone, timedelta
from urllib.parse import quote
import httpx
from backend.schemas.contracts import Bar, Event, AssetIdentifier, RawRecord, now
from backend.storage.database import Database
from scripts.provider_common import config, validate_sec_contact

class ProviderError(Exception):
    def __init__(self,status,detail): self.status=status; self.detail=detail

def normalized(provider):
    def decorate(fn):
        async def call(self,*args,**kwargs):
            try:return await fn(self,*args,**kwargs)
            except (KeyError,TypeError,ValueError):
                previous=self.db.setting('provider_'+provider,{})
                self.db.set_setting('provider_'+provider,{**previous,'status':'DEGRADED','last_error':'Unexpected provider data shape; no synthetic replacement'})
                raise ProviderError('DEGRADED','Unexpected provider data shape') from None
        return call
    return decorate

class MarketProviders:
    def __init__(self,db:Database,credentials=None,transport=None):
        self.db=db; self.cfg=credentials if credentials is not None else config(); self.transport=transport
        self.locks={}; self.last={}
    def status(self):
        required={'alpaca':['ALPACA_API_KEY','ALPACA_API_SECRET'],'alpha_vantage':['ALPHA_VANTAGE_API_KEY'],
                  'sec':['SEC_USER_AGENT'],'fred':['FRED_API_KEY'],'eia':['EIA_API_KEY'],'x':['X_BEARER_TOKEN']}
        result=[]
        for name in ['coinbase','hyperliquid','kalshi','alpaca','alpha_vantage','sec','fred','eia','x','gs_quant','manual']:
            missing=[k for k in required.get(name,[]) if not self.cfg.get(k)]
            default={'provider':name,'status':'NOT_CONFIGURED' if missing else 'NOT_CHECKED','missing_fields':missing,'last_success':None,'last_error':None,'latency_ms':None}
            if name=='x' and self.cfg.get('X_API_ENABLED')!='true': default['status']='DISABLED'
            if name=='manual': default['status']='READY_FOR_IMPORT'
            saved=self.db.setting('provider_'+name,{})
            if missing or default['status']=='DISABLED':saved={k:v for k,v in saved.items() if k not in ('status','missing_fields')}
            result.append({**default,**saved})
        return result
    async def request(self,name,url,*,method='GET',params=None,headers=None,body=None,raw=False):
        # URLs are constructed only by these adapters, never accepted from user input.
        lock=self.locks.setdefault(name,asyncio.Lock())
        async with lock:
            delay=12 if name=='alpha_vantage' else 1.1
            await asyncio.sleep(max(0,delay-(time.monotonic()-self.last.get(name,0))))
            start=time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=20,trust_env=False,follow_redirects=False,transport=self.transport) as client:
                    for attempt in range(3):
                        self.last[name]=time.monotonic()
                        r=await client.request(method,url,params=params,headers=headers,json=body)
                        if r.status_code==429: raise ProviderError('RATE_LIMITED','Provider rate limit; deferred to next cycle')
                        if r.status_code>=500 and attempt<2:
                            await asyncio.sleep(2**attempt); continue
                        if r.status_code in (401,403): raise ProviderError('DEGRADED','Authentication or entitlement rejected')
                        r.raise_for_status(); break
                data=r.text if raw else r.json()
                if isinstance(data,dict) and any(k in data for k in ('Error Message','Information','Note','error')):
                    raise ProviderError('DEGRADED','Provider returned an error or entitlement notice')
                raw_payload={'text':data} if isinstance(data,str) else data
                raw_id=hashlib.sha256((name+url+json.dumps(raw_payload,sort_keys=True)).encode()).hexdigest()
                self.db.put('raw',RawRecord(id=raw_id,provider=name,source_reference=url,payload=raw_payload),record_id=raw_id)
                self.db.set_setting('provider_'+name,{'status':'WORKING_DEMO' if name=='kalshi' else 'WORKING_READ_ONLY',
                    'last_success':now().isoformat(),'last_error':None,'latency_ms':round((time.monotonic()-start)*1000),'missing_fields':[]})
                return data
            except Exception as e:
                status=e.status if isinstance(e,ProviderError) else 'ERROR'
                detail=e.detail if isinstance(e,ProviderError) else 'Network or response failure; retry scheduled'
                previous=self.db.setting('provider_'+name,{})
                self.db.set_setting('provider_'+name,{**previous,'status':status,'last_error':detail,'last_attempt':now().isoformat()})
                raise ProviderError(status,detail) from None
    def require(self,name,*fields):
        if any(not self.cfg.get(f) for f in fields): raise ProviderError('NOT_CONFIGURED',name+' credentials are missing')
    def persist(self,provider,event_type,payload,symbol='',published_at=None,source=''):
        content=json.dumps(payload,sort_keys=True,separators=(',',':'))
        rid=hashlib.sha256((provider+event_type+symbol+content).encode()).hexdigest()
        existing=self.db.get(rid)
        if existing and self.db.get(rid+'d'): return rid
        timestamp=published_at or now()
        e=Event(id=rid,source=provider,provider=provider,event_type=event_type,
                assets=[AssetIdentifier(symbol=symbol,asset_class='perpetual' if provider=='hyperliquid' else 'prediction' if provider=='kalshi' else 'stock' if provider in ('sec','alpaca','alpha_vantage') else 'crypto')] if symbol else [],event_at=timestamp,published_at=timestamp,
                payload=payload,source_reference=source or provider)
        self.db.put('event',e,symbol,record_id=rid,available_at=e.available_at().isoformat())
        self.db.put(event_type,{**payload,'evidence_id':rid,'provider':provider,'source_reference':source,'observed_at':now().isoformat()},symbol,record_id=rid+'d')
        return rid
    @normalized('coinbase')
    async def coinbase_quote(self,symbol):
        url='https://api.exchange.coinbase.com/products/'+quote(symbol,safe='')+'/ticker'
        data=await self.request('coinbase',url)
        payload={'symbol':symbol,'price':float(data['price']),'bid':float(data['bid']),'ask':float(data['ask']),
                 'volume':float(data['volume']),'timestamp':data['time'],'asset_class':'crypto'}
        self.persist('coinbase','quote',payload,symbol,datetime.fromisoformat(data['time'].replace('Z','+00:00')),url)
        return payload
    @normalized('coinbase')
    async def coinbase_bars(self,symbol,days=1095,granularity=86400):
        url='https://api.exchange.coinbase.com/products/'+quote(symbol,safe='')+'/candles'
        end=now(); boundary=end;remaining=min(days,3650);data=[]
        while remaining>0:
            count=min(remaining,290);start=boundary-timedelta(seconds=granularity*count)
            page=await self.request('coinbase',url,params={'granularity':granularity,'start':start.isoformat(),'end':boundary.isoformat()})
            data.extend(page);remaining-=count;boundary=start
        bars=[]
        for t,low,high,opening,close,volume in sorted(data):
            ts=datetime.fromtimestamp(t,timezone.utc); available=ts+timedelta(seconds=granularity)
            if available>end: continue
            bar=Bar(symbol=symbol,provider='coinbase',timestamp=ts,available_at=available,open=opening,high=high,low=low,close=close,volume=volume,interval_seconds=granularity)
            payload=bar.model_dump(mode='json'); identity={k:v for k,v in payload.items() if k!='observed_at'}
            rid=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            # Historical bars are retrospective. Strict observed-time replay is a separate mode.
            self.db.put('bar',payload,symbol,record_id=rid,available_at=bar.observed_at.isoformat()); bars.append(payload)
        return bars
    @normalized('hyperliquid')
    async def hyperliquid(self):
        url='https://api.hyperliquid.xyz/info'
        meta,contexts=await self.request('hyperliquid',url,method='POST',body={'type':'metaAndAssetCtxs'})
        values=[]
        for asset,ctx in list(zip(meta['universe'],contexts))[:100]:
            payload={'symbol':asset['name'],'asset_class':'perpetual','mark_price':float(ctx['markPx']),
                     'funding':float(ctx['funding']),'open_interest':float(ctx['openInterest']),
                     'day_volume':float(ctx['dayNtlVlm']),'oracle_price':float(ctx['oraclePx'])}
            self.persist('hyperliquid','crypto',payload,asset['name'],source=url); values.append(payload)
        return values
    @normalized('hyperliquid')
    async def wallet(self,address):
        url='https://api.hyperliquid.xyz/info'
        fills=await self.request('hyperliquid',url,method='POST',body={'type':'userFills','user':address})
        portfolio=await self.request('hyperliquid',url,method='POST',body={'type':'portfolio','user':address})
        data={'wallet':address,'fills':fills,'portfolio':portfolio}
        self.persist('hyperliquid','trader',data,source=url); return data
    @normalized('kalshi')
    async def kalshi(self):
        url='https://external-api.demo.kalshi.co/trade-api/v2/markets'
        data=await self.request('kalshi',url,params={'limit':30,'status':'open','mve_filter':'exclude'})
        for m in data['markets']: self.persist('kalshi','prediction_market',m,m['ticker'],source=url)
        return data['markets']
    @normalized('alpaca')
    async def alpaca_quote(self,symbol):
        self.require('Alpaca','ALPACA_API_KEY','ALPACA_API_SECRET')
        url='https://data.alpaca.markets/v2/stocks/'+quote(symbol,safe='')+'/quotes/latest'
        data=await self.request('alpaca',url,params={'feed':self.cfg.get('ALPACA_DATA_FEED','iex')},headers={'APCA-API-KEY-ID':self.cfg['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':self.cfg['ALPACA_API_SECRET']})
        q=data['quote']; bid=float(q['bp']); ask=float(q['ap'])
        if bid<=0 or ask<bid:raise ValueError('Quote is not tradable')
        payload={'symbol':symbol,'price':(bid+ask)/2,'bid':bid,'ask':ask,'timestamp':q['t'],'asset_class':'stock','price_type':'quote_midpoint','bid_size':q.get('bs'),'ask_size':q.get('as')}
        recent=self.db.records('bar',symbol,limit=1000)
        if recent:
            daily=max(recent,key=lambda r:r['payload']['timestamp'])['payload']
            payload.update(volume=daily['volume'],volume_basis='last_completed_daily_bar',volume_timestamp=daily['available_at'])
        self.persist('alpaca','quote',payload,symbol,datetime.fromisoformat(q['t'].replace('Z','+00:00')),url)
        return payload
    @normalized('alpaca')
    async def alpaca_bars(self,symbol,start,end):
        self.require('Alpaca','ALPACA_API_KEY','ALPACA_API_SECRET')
        url='https://data.alpaca.markets/v2/stocks/'+quote(symbol,safe='')+'/bars'
        params={'timeframe':'1Day','start':start,'end':end,'limit':10000,'feed':self.cfg.get('ALPACA_DATA_FEED','iex'),'adjustment':'raw'}
        headers={'APCA-API-KEY-ID':self.cfg['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':self.cfg['ALPACA_API_SECRET']}
        result=[]
        for _ in range(20):
            data=await self.request('alpaca',url,params=params,headers=headers)
            for r in data.get('bars') or []:
                ts=datetime.fromisoformat(r['t'].replace('Z','+00:00'))
                if ts+timedelta(days=1)>now():continue
                b=Bar(symbol=symbol,provider='alpaca',timestamp=ts,available_at=ts+timedelta(days=1),open=r['o'],high=r['h'],low=r['l'],close=r['c'],volume=r['v'])
                p=b.model_dump(mode='json'); rid=hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='observed_at'},sort_keys=True).encode()).hexdigest()
                self.db.put('bar',p,symbol,record_id=rid,available_at=b.observed_at.isoformat()); result.append(p)
            token=data.get('next_page_token')
            if not token: break
            params['page_token']=token
        return result
    @normalized('alpha_vantage')
    async def alpha(self,kind,symbol,quarter='',observation_date=None):
        self.require('Alpha Vantage','ALPHA_VANTAGE_API_KEY')
        function={'news':'NEWS_SENTIMENT','transcript':'EARNINGS_CALL_TRANSCRIPT','options':'HISTORICAL_OPTIONS'}[kind]
        params={'function':function,'apikey':self.cfg['ALPHA_VANTAGE_API_KEY']}
        params['tickers' if kind=='news' else 'symbol']=symbol
        if quarter: params['quarter']=quarter
        if observation_date and kind=='options':params['date']=date.fromisoformat(str(observation_date)).isoformat()
        url='https://www.alphavantage.co/query'
        data=await self.request('alpha_vantage',url,params=params)
        rid=self.persist('alpha_vantage',kind,data,symbol if ',' not in symbol else '',source=url)
        if kind in ('news','transcript'):
            from backend.intelligence.ingest import ingest_alpha_text
            ingest_alpha_text(self.db,kind,data,symbol)
        elif kind=='options':
            from backend.intelligence.options import derive_options
            derive_options(self.db,rid+'d')
        return data
    @normalized('sec')
    async def sec(self,cik):
        self.require('SEC','SEC_USER_AGENT')
        if not validate_sec_contact(self.cfg['SEC_USER_AGENT']): raise ProviderError('NOT_CONFIGURED','SEC requires name and real contact email')
        url=f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'
        data=await self.request('sec',url,headers={'User-Agent':self.cfg['SEC_USER_AGENT']})
        recent=data.get('filings',{}).get('recent',{}); result=[]
        for i,form in enumerate(recent.get('form',[])[:100]):
            p={k:v[i] for k,v in recent.items() if isinstance(v,list) and len(v)>i}
            p['cik']=cik; p['company']=data.get('name'); p['form']=form
            accession=p['accessionNumber'].replace('-','')
            p['document_url']=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{p['primaryDocument']}"
            self.persist('sec','filing',p,str(cik),datetime.fromisoformat(p['filingDate']).replace(tzinfo=timezone.utc),url); result.append(p)
        return result
    async def sec_document(self,cik,accession,filename):
        self.require('SEC','SEC_USER_AGENT')
        if not validate_sec_contact(self.cfg['SEC_USER_AGENT']):raise ProviderError('NOT_CONFIGURED','SEC requires name and real contact email')
        import re
        if not re.fullmatch(r'\d{18}',accession) or not re.fullmatch(r'[A-Za-z0-9_.-]+',filename):raise ValueError('Invalid SEC archive identity')
        url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{filename}'
        text=await self.request('sec',url,headers={'User-Agent':self.cfg['SEC_USER_AGENT']},raw=True)
        self.persist('sec','filing_source',{'text':text,'cik':cik},str(cik),source=url)
        return text
    @normalized('fred')
    async def fred(self,series,vintage):
        self.require('FRED','FRED_API_KEY')
        url='https://api.stlouisfed.org/fred/series/observations'
        data=await self.request('fred',url,params={'api_key':self.cfg['FRED_API_KEY'],'file_type':'json','series_id':series,
            'realtime_start':vintage,'realtime_end':vintage})
        self.persist('fred','macro',{'series':series,'vintage':vintage,'observations':data['observations']},source=url)
        return data
    @normalized('eia')
    async def eia(self):
        self.require('EIA','EIA_API_KEY')
        url='https://api.eia.gov/v2/electricity/retail-sales/data/'
        data=await self.request('eia',url,params={'api_key':self.cfg['EIA_API_KEY'],'frequency':'monthly','data[0]':'price','length':100,'sort[0][column]':'period','sort[0][direction]':'desc'})
        self.persist('eia','energy',data,source=url); return data
    @normalized('x')
    async def social(self,query):
        if self.cfg.get('X_API_ENABLED')!='true': raise ProviderError('DISABLED','X is disabled; paid access requires explicit configuration')
        self.require('X','X_BEARER_TOKEN')
        url='https://api.x.com/2/tweets/search/recent'
        data=await self.request('x',url,params={'query':query,'max_results':10,'tweet.fields':'created_at,author_id,public_metrics'},headers={'Authorization':'Bearer '+self.cfg['X_BEARER_TOKEN']})
        self.persist('x','social',data,source=url); return data
