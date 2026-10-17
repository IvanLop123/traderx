"""Bounded public/read-only historical adapters; no order or language-model calls."""
from datetime import datetime,timedelta,timezone
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo
import hashlib,json,re
from backend.providers.market import ProviderError
from backend.research.history import HistoryStore
from backend.schemas.contracts import now

UTC=timezone.utc
class HistoricalBackfill:
    def __init__(self,providers):self.p=providers;self.db=providers.db;self.store=HistoryStore(self.db)
    def headers(self):
        self.p.require('Alpaca','ALPACA_API_KEY','ALPACA_API_SECRET')
        return {'APCA-API-KEY-ID':self.p.cfg['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':self.p.cfg['ALPACA_API_SECRET']}
    async def coinbase(self,symbol,start='2015-01-01'):
        beginning=datetime.fromisoformat(start).replace(tzinfo=UTC);end=now().replace(hour=0,minute=0,second=0,microsecond=0);cursor=beginning;rows=[]
        while cursor<end:
            stop=min(end,cursor+timedelta(days=290))
            data=await self.p.request('coinbase',f'https://api.exchange.coinbase.com/products/{symbol}/candles',params={'granularity':86400,'start':cursor.isoformat(),'end':stop.isoformat()})
            for t,low,high,op,close,vol in data:
                ts=datetime.fromtimestamp(t,UTC)
                if cursor<=ts<stop:rows.append(dict(symbol=symbol,provider='coinbase',timestamp=ts,available_at=ts+timedelta(days=1),open=op,high=high,low=low,close=close,volume=vol))
            cursor=stop
        return self.store.save(symbol,'coinbase',rows,metadata={'requested_start':start,'gaps_not_filled':True})
    async def alpaca(self,symbols,start='2016-01-01',feed=None):
        if not 1<=len(symbols)<=50:raise ValueError('Backfill batch must contain 1–50 symbols')
        end=(now()-timedelta(days=1)).date().isoformat();feed=feed or self.p.cfg.get('ALPACA_RESEARCH_FEED') or self.p.cfg.get('ALPACA_DATA_FEED') or 'iex';result=[]
        for adjustment in ['raw','all']:
            params={'symbols':','.join(symbols),'timeframe':'1Day','start':start,'end':end,'limit':10000,'feed':feed,'adjustment':adjustment,'sort':'asc'};rows={s:[] for s in symbols};tokens=set()
            for _ in range(100):
                data=await self.p.request('alpaca','https://data.alpaca.markets/v2/stocks/bars',params=params,headers=self.headers())
                for s,bars in data.get('bars',{}).items():
                    if s not in rows:raise ValueError('Unexpected symbol')
                    for b in bars:
                        ts=datetime.fromisoformat(b['t'].replace('Z','+00:00'));rows[s].append(dict(symbol=s,provider='alpaca',timestamp=ts,available_at=ts+timedelta(days=1),open=b['o'],high=b['h'],low=b['l'],close=b['c'],volume=b['v']))
                token=data.get('next_page_token')
                if not token:break
                if token in tokens:raise ValueError('Repeated history pagination token')
                tokens.add(token);params['page_token']=token
            else:raise ValueError('Backfill page cap reached; incomplete series not activated')
            for s,values in rows.items():
                if values:result.append(self.store.save(s,'alpaca',values,adjustment=adjustment,feed=feed,metadata={'requested_start':start,'corporate_actions':'Provider all-adjusted price/volume vintage; raw execution and eligibility remain separate','historical_membership':'unverified'}))
        return result
    async def calendar(self):
        data=await self.p.request('alpaca','https://paper-api.alpaca.markets/v2/calendar',params={'start':'2015-01-01','end':(now()+timedelta(days=90)).date().isoformat()},headers=self.headers())
        sessions=[]
        for r in data:
            def ts(field):
                value=r[field]
                return datetime.fromisoformat(r['date']+'T'+value).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(UTC).isoformat()
            sessions.append({'date':r['date'],'open':ts('open'),'close':ts('close')})
        self.db.set_setting('research_calendar',{'provider':'alpaca','observed_at':now().isoformat(),'sessions':sessions});return {'sessions':len(sessions)}
    async def instruments(self):
        # Preserve inactive listings; never discard them because today's watchlist is active.
        counts={}
        for status in ['active','inactive']:
            data=await self.p.request('alpaca','https://paper-api.alpaca.markets/v2/assets',params={'status':status,'asset_class':'us_equity'},headers=self.headers())
            rid='instruments_'+hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
            self.db.put('instrument_snapshot',{'provider':'alpaca','status':status,'known_at':now().isoformat(),'instruments':data,'historical_membership_verified':False},record_id=rid);counts[status]=len(data)
        return counts
    async def corporate_actions(self,symbols):
        params={'symbols':','.join(symbols),'start':'2016-01-01','end':now().date().isoformat(),'limit':1000};count=0;seen=set()
        for _ in range(100):
            data=await self.p.request('alpaca','https://data.alpaca.markets/v1/corporate-actions',params=params,headers=self.headers())
            groups=data.get('corporate_actions',{})
            for kind,actions in groups.items():
                for a in actions:
                    rid='action_'+hashlib.sha256(json.dumps([kind,a],sort_keys=True).encode()).hexdigest();self.db.put('corporate_action',{'action_type':kind,'data':a,'provider':'alpaca','observed_at':now().isoformat(),'historical_announcement_time_verified':False},a.get('symbol') or a.get('old_symbol') or '',record_id=rid);count+=1
            token=data.get('next_page_token')
            if not token:break
            if token in seen:raise ValueError('Repeated action pagination')
            seen.add(token);params['page_token']=token
        else:raise ValueError('Corporate action page cap reached')
        return {'actions':count,'announcement_PIT':False}
    async def macro(self,series,start=2010):
        self.p.require('FRED','FRED_API_KEY');existing=self.db.records('macro_initial',series,limit=1);rows={r['date']:r for r in existing[0]['payload']['observations'] if r['value']!='.'} if existing else {};url='https://api.stlouisfed.org/fred/series/observations'
        # Small real-time windows avoid ALFRED's 2,000-vintage ceiling for daily series.
        for year in range(start,now().year+1,3):
            params={'api_key':self.p.cfg['FRED_API_KEY'],'file_type':'json','series_id':series,'output_type':4,'realtime_start':f'{year}-01-01','realtime_end':min(now().date().isoformat(),f'{year+2}-12-31'),'observation_start':f'{start}-01-01','limit':100000}
            data=await self.p.request('fred',url,params=params)
            if data.get('count',0)>len(data.get('observations',[])):raise ValueError('Truncated ALFRED history')
            for o in data.get('observations',[]):
                if o['value']=='.':continue
                key=o['date']
                if key not in rows or o['realtime_start']<rows[key]['realtime_start']:rows[key]=o
        observations=[rows[k] for k in sorted(rows)]
        self.p.persist('fred','macro_initial',{'series':series,'observations':observations,'policy':'initial_release_only_next_NY_midnight','requested_start':f'{start}-01-01'},series,source=url)
        return {'series':series,'count':len(observations),'start':observations[0]['date'] if observations else None}
    async def funding(self,coin,start='2023-01-01',max_pages=100):
        cursor=int(datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp()*1000);end=int(now().timestamp()*1000);existing=self.db.records('funding_history',coin,limit=1);values={int(r['time']):r for r in existing[0]['payload']['rows']} if existing else {};complete=False
        for _ in range(max_pages):
            data=await self.p.request('hyperliquid','https://api.hyperliquid.xyz/info',method='POST',body={'type':'fundingHistory','coin':coin,'startTime':cursor,'endTime':end})
            if not data:complete=True;break
            for r in data:
                if cursor<=int(r['time'])<=end:values[int(r['time'])]=r
            latest=max(int(r['time']) for r in data)
            if latest<cursor:raise ValueError('Funding pagination did not advance')
            cursor=latest+1
        rid='funding_'+hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()
        payload={'provider':'hyperliquid','coin':coin,'rows':[values[k] for k in sorted(values)],'complete_to_requested_end':complete,'observed_at':now().isoformat(),'policy':'Real timestamped paid funding; no historical OI or basis inferred'}
        self.db.put('funding_history',payload,coin,record_id=rid);return {'coin':coin,'count':len(values),'complete':complete}
    async def sec_form4(self,symbol,cik,max_documents=250):
        from backend.intelligence.documents import parse_form4
        self.p.require('SEC','SEC_USER_AGENT');headers={'User-Agent':self.p.cfg['SEC_USER_AGENT']}
        data=await self.p.request('sec',f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json',headers=headers)
        chunks=[data['filings']['recent']]
        # The index is paginated by published archive files, not guessed URL dates.
        for f in data.get('filings',{}).get('files',[])[:10]:
            if not re.fullmatch(r'CIK\d+-submissions-\d+\.json',f['name']):continue
            chunks.append(await self.p.request('sec','https://data.sec.gov/submissions/'+f['name'],headers=headers))
        filings={}
        for chunk in chunks:
            for i,form in enumerate(chunk.get('form',[])):
                if form in ('4','4/A'):
                    p={k:v[i] for k,v in chunk.items() if isinstance(v,list) and len(v)>i};filings[p['accessionNumber']]=p
        selected=sorted(filings.values(),key=lambda x:x.get('acceptanceDateTime') or x['filingDate'],reverse=True)[:max_documents];success=[];failed=[]
        for f in selected:
            rid='historical_form4_'+f['accessionNumber'];existing=self.db.get(rid)
            if existing:success.append(existing['payload']);continue
            acceptance=f.get('acceptanceDateTime')
            if not acceptance:failed.append(f['accessionNumber']);continue
            try:
                published=datetime.fromisoformat(acceptance.replace('Z','+00:00'))
                if published.tzinfo is None:published=published.replace(tzinfo=ZoneInfo('America/New_York'))
                published=published.astimezone(UTC)
                source=await self.p.sec_document(cik,f['accessionNumber'].replace('-',''),PurePosixPath(f['primaryDocument']).name)
                parsed=parse_form4(source)
                payload={'symbol':symbol,'cik':cik,'accession':f['accessionNumber'],'form':f['form'],'published_at':published.isoformat(),'observed_at':now().isoformat(),'source_hash':hashlib.sha256(source.encode()).hexdigest(),'transactions':parsed,'public_availability_policy':'SEC acceptance timestamp; historical public-information reconstruction'}
                self.db.put('historical_form4',payload,symbol,record_id=rid);success.append(payload)
            except (ProviderError,ValueError,KeyError):failed.append(f['accessionNumber'])
        # Zero is legitimate only inside a fully retrieved filing window. Exclude oldest boundary date.
        earliest=min((p['published_at'] for p in success),default=None)
        payload={'symbol':symbol,'indexed_filings':len(filings),'requested':len(selected),'downloaded':len(success),'failed':len(failed),'start':earliest,'end':now().isoformat(),'complete_window':bool(success) and not failed,'limited_to_recent_documents':len(selected)<len(filings),'amendments':sum(p['form']=='4/A' for p in success)}
        previous=self.db.setting('form4_coverage_'+symbol,{})
        if previous.get('complete_window'):
            if payload['complete_window'] and earliest<=previous['end']:
                payload['start']=min(previous['start'],earliest)
            elif not payload['complete_window']:
                payload={**previous,'latest_attempt':now().isoformat(),'latest_attempt_failed_documents':len(failed)}
        self.db.set_setting('form4_coverage_'+symbol,payload);return payload
