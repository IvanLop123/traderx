"""Read-only provider adapters; production data is never replaced with fixtures."""
import asyncio
import hashlib
import json
import time
import math
from datetime import date, datetime, timezone, timedelta
from urllib.parse import quote
import httpx
from backend.schemas.contracts import Bar, Event, AssetIdentifier, RawRecord, now
from backend.storage.database import Database
from scripts.provider_common import config, validate_sec_contact, alpha_notice

class ProviderError(Exception):
    def __init__(self,status,detail): self.status=status; self.detail=detail

def normalized(provider):
    def decorate(fn):
        async def call(self,*args,**kwargs):
            try:return await fn(self,*args,**kwargs)
            except ProviderError as exc:
                previous=self.db.setting('provider_'+provider,{})
                self.db.set_setting('provider_'+provider,{**previous,'status':exc.status,'last_error':exc.detail})
                raise
            except (KeyError,TypeError,ValueError):
                previous=self.db.setting('provider_'+provider,{})
                self.db.set_setting('provider_'+provider,{**previous,'status':'MALFORMED_RESPONSE','last_error':'Unexpected provider data shape; no synthetic replacement'})
                raise ProviderError('MALFORMED_RESPONSE','Unexpected provider data shape') from None
        return call
    return decorate

class MarketProviders:
    def __init__(self,db:Database,credentials=None,transport=None):
        self.db=db; self.cfg=credentials if credentials is not None else config(); self.transport=transport
        self.locks={}; self.last={}
    def status(self):
        purposes={'coinbase':'Public spot crypto quotes and history','hyperliquid':'Read-only crypto funding and market context','alpaca':'US equities/ETF history and quotes; indicative options snapshots','sec':'Dated filings and insider disclosures','fred':'Vintage-aware macroeconomic research','eia':'Energy observations','manual':'Authorized document imports'}
        required={'alpaca':['ALPACA_API_KEY','ALPACA_API_SECRET'],'sec':['SEC_USER_AGENT'],'fred':['FRED_API_KEY'],'eia':['EIA_API_KEY']}
        result=[]
        for name,purpose in purposes.items():
            missing=[k for k in required.get(name,[]) if not self.cfg.get(k)]
            saved=self.db.setting('provider_'+name,{})
            status='NOT_CONFIGURED' if missing else saved.get('status','READY_FOR_IMPORT' if name=='manual' else 'NOT_CHECKED')
            classification='working' if status.startswith('WORKING') else 'unavailable due to entitlement' if status=='ENTITLEMENT_REQUIRED' else 'disabled' if status=='DISABLED' else 'optional'
            result.append({**saved,'provider':name,'status':status,'classification':classification,'scope':purpose,'missing_fields':missing})
        return result
    async def request(self,name,url,*,method='GET',params=None,headers=None,body=None,raw=False,persist_raw=True):
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
                        if r.status_code==401: raise ProviderError('AUTHENTICATION_FAILED','Provider rejected authentication; check configured credentials')
                        if r.status_code==403: raise ProviderError('ENTITLEMENT_REQUIRED','Provider denied this data entitlement')
                        if r.status_code==404: raise ProviderError('UNSUPPORTED_ENDPOINT','Provider endpoint or asset is unavailable')
                        r.raise_for_status(); break
                data=r.text if raw else r.json()
                notice=alpha_notice(data) if name=='alpha_vantage' else None
                if notice: raise ProviderError(*notice)
                if isinstance(data,dict) and any(k in data for k in ('Error Message','Information','Note','error')):
                    raise ProviderError('DEGRADED','Provider returned an error or entitlement notice')
                raw_payload={'text':data} if isinstance(data,str) else data
                raw_id=hashlib.sha256((name+url+json.dumps(raw_payload,sort_keys=True)).encode()).hexdigest()
                if persist_raw:self.db.put('raw',RawRecord(id=raw_id,provider=name,source_reference=url,payload=raw_payload),record_id=raw_id)
                self.db.set_setting('provider_'+name,{'status':'WORKING_READ_ONLY',
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
                assets=[AssetIdentifier(symbol=symbol,asset_class='perpetual' if provider=='hyperliquid' else 'stock' if provider in ('sec','alpaca','alpha_vantage') else 'crypto')] if symbol else [],event_at=timestamp,published_at=timestamp,
                payload=payload,source_reference=source or provider)
        self.db.put('event',e,symbol,record_id=rid,available_at=e.available_at().isoformat())
        self.db.put(event_type,{**payload,'evidence_id':rid,'provider':provider,'source_reference':source,'observed_at':now().isoformat()},symbol,record_id=rid+'d')
        return rid
    async def forward_quote(self,symbol):
        if symbol.endswith('-USD'):
            data=await self.request('coinbase','https://api.exchange.coinbase.com/products/'+quote(symbol,safe='')+'/book',params={'level':1})
            bid,ask=data['bids'][0],data['asks'][0]
            timestamp=data.get('time')
            if not timestamp:raise ProviderError('MISSING_DATA','Book snapshot has no exchange timestamp')
            q={'symbol':symbol,'provider':'coinbase','timestamp':timestamp,'bid':float(bid[0]),'ask':float(ask[0]),'bid_size':float(bid[1]),'ask_size':float(ask[1]),'sequence':data.get('sequence'),'depth_units':'base_units'}
        else:
            q=await self.alpaca_quote(symbol)
            # Current shares convention; older snapshots are not used as live quotes.
            if datetime.fromisoformat(q['timestamp'].replace('Z','+00:00')).date()<date(2025,11,3):raise ProviderError('MISSING_DATA','Quote predates verified share-unit convention')
            q={**q,'provider':'alpaca','depth_units':'base_units'}
        q['observed_at']=now().isoformat()
        self.db.put('forward_quote',q,symbol)
        return q
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
        fills=sorted(fills,key=lambda f:f.get('time',0))
        from backend.intelligence.quant import trader_metrics
        data={'wallet':address,'fills':fills,'portfolio':portfolio,'metrics':trader_metrics(fills)}
        self.persist('hyperliquid','trader',data,source=url); return data
    @normalized('alpaca')
    async def alpaca_quote(self,symbol):
        self.require('Alpaca','ALPACA_API_KEY','ALPACA_API_SECRET')
        url='https://data.alpaca.markets/v2/stocks/'+quote(symbol,safe='')+'/quotes/latest'
        data=await self.request('alpaca',url,params={'feed':self.cfg.get('ALPACA_DATA_FEED','iex')},headers={'APCA-API-KEY-ID':self.cfg['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':self.cfg['ALPACA_API_SECRET']})
        q=data['quote']
        if q is None:raise ProviderError('MISSING_DATA','No IEX quote is currently available for '+symbol)
        bid=float(q['bp']); ask=float(q['ap'])
        if not math.isfinite(bid) or not math.isfinite(ask) or bid<0 or ask<0:raise ValueError('Invalid quote values')
        if bid==0 or ask==0:
            raise ProviderError('MISSING_DATA','IEX has no two-sided quote for '+symbol+' (often outside the session); history remains available')
        if ask<bid:raise ProviderError('DEGRADED','Crossed IEX quote; no tradable midpoint saved')
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
    async def fred_initial(self,series):
        from backend.research.features import MACRO
        if series not in MACRO:raise ValueError('Unsupported research macro series')
        self.require('FRED','FRED_API_KEY')
        url='https://api.stlouisfed.org/fred/series/observations'
        data=await self.request('fred',url,params={'api_key':self.cfg['FRED_API_KEY'],'file_type':'json','series_id':series,
            'realtime_start':'2022-01-01','realtime_end':'9999-12-31','observation_start':'2022-01-01','output_type':4,'limit':100000})
        if data.get('count',0)>len(data.get('observations',[])):raise ValueError('Incomplete macro release history')
        existing=self.db.records('macro_initial',series,limit=1)
        observations={r['date']:r for r in (existing[0]['payload']['observations'] if existing else [])}
        for row in data['observations']:
            if row['date'] not in observations or row['realtime_start']<observations[row['date']]['realtime_start']:observations[row['date']]=row
        data['observations']=[observations[k] for k in sorted(observations)]
        self.persist('fred','macro_initial',{'series':series,'observations':data['observations'],'policy':'initial_release_only_next_NY_midnight'},series,source=url)
        return data
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
        data=await self.request('eia',url,params={'api_key':self.cfg['EIA_API_KEY'],'frequency':'monthly','data[0]':'price','facets[stateid][]':'US','facets[sectorid][]':'ALL','length':1,'sort[0][column]':'period','sort[0][direction]':'desc'})
        self.persist('eia','energy',data,source=url); return data
