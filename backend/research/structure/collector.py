"""Read-only, quota-bounded adapters. No contract feed or options access invented."""
import asyncio,json,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from sqlalchemy import select,func,cast,Text
from backend.schemas.contracts import now
from backend.storage.database import Record
from backend.research.features import stable_hash
from backend.research.structure.intraday import Bars,derive,microstructure
from backend.research.structure.options import surface
from backend.providers.history import HistoricalBackfill
from backend.providers.market import ProviderError
ROOT=Path(__file__).resolve().parents[3]

def settings():
    x=json.loads((ROOT/'config/market_structure.json').read_text())
    if not 1<=x['lookback_days']<=31 or not 1<=len(x['symbols'])<=5 or not 24<=x['refresh_hours']<=168 or not 1<=x['max_requests_per_cycle']<=100 or not 1000000<=x['max_saved_bytes']<=1000000000:raise ValueError('Unsafe research collection bounds')
    if any(v not in (60,300,900,3600) for v in x['intervals']) or len(x['intervals'])>4:raise ValueError('Unsupported interval')
    if len(x['options_symbols'])>2 or x['options_feed']!='indicative':raise ValueError('Only bounded indicative options enabled here')
    if any(not re.fullmatch(r'[A-Z0-9.-]{1,30}',s) for s in x['symbols']+x['options_symbols']):raise ValueError('Invalid symbol')
    return x

class Collector:
    def __init__(self,db,providers):self.db=db;self.p=providers;self.calls=0;self.cfg=settings();self.lock=asyncio.Lock()
    async def request(self,*a,**k):
        if self.calls>=self.cfg['max_requests_per_cycle']:raise ValueError('Per-cycle request budget reached')
        self.calls+=1
        with self.db.engine.connect() as c:
            used=c.execute(select(func.sum(func.length(cast(Record.payload,Text)))).where(Record.kind.in_(['structure_raw','intraday_archive','intraday_research','structure_options']))).scalar() or 0
        if used>=self.cfg['max_saved_bytes']-2000000:raise ValueError('Research storage budget reached')
        data=await self.p.request(*a,**k,persist_raw=False)
        self.save('structure_raw',{'provider':a[0],'source':a[1],'payload':data},'')
        return data
    def save(self,kind,payload,symbol):
        rid=kind+'_'+stable_hash(payload)
        if self.db.get(rid):return rid
        with self.db.transaction() as session:
            if session.get(Record,rid):return rid
            used=session.execute(select(func.sum(func.length(cast(Record.payload,Text)))).where(Record.kind.in_(['structure_raw','intraday_archive','intraday_research','structure_options']))).scalar() or 0
            if used+len(json.dumps(payload,ensure_ascii=True))>self.cfg['max_saved_bytes']:raise ValueError('Research storage budget reached; existing evidence preserved')
            session.add(Record(id=rid,kind=kind,symbol=symbol,payload=payload,available_at=now().isoformat()))
        return rid
    async def bars(self,symbol,interval):
        end=now()-timedelta(minutes=20);end=end.replace(hour=0,minute=0,second=0,microsecond=0);start=end-timedelta(days=self.cfg['lookback_days']);rows={};feed='exchange';crypto=symbol.endswith('-USD');provider='coinbase' if crypto else 'alpaca'
        if crypto:
            cursor=start
            while cursor<end:
                stop=min(end,cursor+timedelta(seconds=interval*290));data=await self.request('coinbase',f'https://api.exchange.coinbase.com/products/{symbol}/candles',params={'granularity':interval,'start':cursor.isoformat(),'end':stop.isoformat()})
                for t,lo,hi,op,cl,vol in data:
                    ts=datetime.fromtimestamp(t,timezone.utc)
                    if cursor<=ts<stop:rows[ts]={'timestamp':ts,'available_at':ts+timedelta(seconds=interval+1),'open':op,'high':hi,'low':lo,'close':cl,'volume':vol}
                cursor=stop
        else:
            headers=HistoricalBackfill(self.p).headers();feed=self.p.cfg.get('ALPACA_RESEARCH_FEED') or self.p.cfg.get('ALPACA_DATA_FEED') or 'iex';params={'symbols':symbol,'timeframe':{60:'1Min',300:'5Min',900:'15Min',3600:'1Hour'}[interval],'start':start.isoformat(),'end':end.isoformat(),'limit':10000,'feed':feed,'adjustment':'raw','sort':'asc'};seen=set()
            for _ in range(5):
                d=await self.request('alpaca','https://data.alpaca.markets/v2/stocks/bars',params=params,headers=headers)
                for b in d.get('bars',{}).get(symbol,[]):
                    t=datetime.fromisoformat(b['t'].replace('Z','+00:00'))
                    if start<=t<end:rows[t]={'timestamp':t,'available_at':t+timedelta(seconds=interval+1),'open':b['o'],'high':b['h'],'low':b['l'],'close':b['c'],'volume':b['v'],'vwap':b.get('vw'),'trades':b.get('n')}
                token=d.get('next_page_token')
                if not token:break
                if token in seen:raise ValueError('Repeated page token')
                seen.add(token);params['page_token']=token
            else:raise ValueError('Incomplete response exceeds page budget')
        bars=Bars(symbol=symbol,asset_class='crypto' if crypto else 'etf' if symbol in ('SPY','QQQ','IWM') else 'stock',provider=provider,feed=feed,interval_seconds=interval,rows=list(rows.values()));payload=bars.model_dump(mode='json');rid=self.save('intraday_archive',payload,symbol)
        sessions=[{**s,'label':s['date']} for s in self.db.setting('research_calendar',{}).get('sessions',[])];sessions=[{k:v for k,v in s.items() if k in ('label','open','close')} for s in sessions]
        result={**derive(bars,sessions),'archive_id':rid,'rows':len(bars.rows),'start':start.isoformat(),'end':end.isoformat(),'retrieved_at':now().isoformat()};self.save('intraday_research',result,symbol);return {'status':'AVAILABLE','rows':len(rows),'feed':feed,'interval':interval}
    async def options(self,symbol):
        # Explicitly request free indicative feed. Modified quotes cannot support arbitrage claims.
        headers=HistoricalBackfill(self.p).headers();params={'feed':'indicative','limit':1000,'expiration_date_gte':now().date().isoformat(),'expiration_date_lte':(now()+timedelta(days=90)).date().isoformat()};contracts=[];seen=set();complete=False
        for _ in range(3):
            d=await self.request('alpaca',f'https://data.alpaca.markets/v1beta1/options/snapshots/{symbol}',headers=headers,params=params)
            for cid,s in d.get('snapshots',{}).items():
                m=re.fullmatch(r'([A-Z]+)(\d{6})([CP])(\d{8})',cid);q=s.get('latestQuote') or {};g=s.get('greeks') or {}
                if not m or m[1]!=symbol or not q.get('t'):continue
                day=datetime.fromisoformat(q['t'].replace('Z','+00:00')).date().isoformat();expiry=datetime.strptime(m[2],'%y%m%d').date().isoformat()
                contracts.append({'symbol':symbol,'date':day,'expiration':expiry,'type':'call' if m[3]=='C' else 'put','strike':int(m[4])/1000,'contractID':cid,'bid':q.get('bp'),'ask':q.get('ap'),'implied_volatility':s.get('impliedVolatility'),**g})
            token=d.get('next_page_token')
            if not token:complete=True;break
            if token in seen:raise ValueError('Repeated option pagination')
            seen.add(token);params['page_token']=token
        if not contracts:raise ValueError('No dated option snapshots available')
        day=max(c['date'] for c in contracts);chain={'data':[c for c in contracts if c['date']==day]};history=[r['payload'] for r in self.db.records('structure_options',symbol,limit=260) if r['payload'].get('provider')=='alpaca_indicative'];from backend.research.history import HistoryStore
        import numpy as np
        bars=HistoryStore(self.db).read(symbol);prior=[b for b in bars if b['available_at'][:10]<day][-21:];rv=float(np.std(np.diff(np.log([b['close'] for b in prior])),ddof=1)*np.sqrt(252)) if len(prior)==21 else None
        result=surface(chain,symbol,history,underlying={'realized_volatility':rv});result.update(realized_volatility=rv,realized_window_end=prior[-1]['available_at'] if prior else None,provider='alpaca_indicative',feed='indicative — modified quotes / delayed trades',complete_chain=complete and all(c['date']==day for c in contracts),collected_at=now().isoformat(),source='https://data.alpaca.markets/v1beta1/options/snapshots/'+symbol,executable=False,parity_status='UNAVAILABLE — indicative quotes are modified; synchronized executable underlying missing',volume_oi_status='UNAVAILABLE — chain snapshots do not supply daily volume/open interest');self.save('structure_options',result,symbol);return {'status':'INDICATIVE_RESEARCH_ONLY','contracts':len(chain['data']),'observation_date':day}
    async def cycle(self,force=False):
        async with self.lock:
            old=self.db.setting('structure_collection',{})
            if not self.cfg['enabled']:return {'status':'DISABLED'}
            if not force and old.get('next_at','')>now().isoformat():return old
            self.calls=0;result={'at':now().isoformat(),'next_at':(now()+timedelta(hours=self.cfg['refresh_hours'])).isoformat(),'status':'RUNNING','outcomes':{}};self.db.set_setting('structure_collection',result)
            for s in self.cfg['symbols']:
                for interval in self.cfg['intervals']:
                    key=s+':'+str(interval)
                    try:result['outcomes'][key]=await self.bars(s,interval)
                    except (ProviderError,ValueError,KeyError,TypeError) as e:result['outcomes'][key]={'status':e.status if isinstance(e,ProviderError) else 'UNAVAILABLE','detail':e.detail if isinstance(e,ProviderError) else 'Missing, invalid or bounded data; no replacement fabricated'}
            for s in self.cfg['options_symbols']:
                try:result['outcomes'][s+':options']=await self.options(s)
                except (ProviderError,ValueError,KeyError,TypeError) as e:result['outcomes'][s+':options']={'status':e.status if isinstance(e,ProviderError) else 'UNAVAILABLE'}
            result.update(status='COMPLETE_WITH_LIMITATIONS' if any(v['status']=='UNAVAILABLE' or 'REQUIRED' in v['status'] for v in result['outcomes'].values()) else 'COMPLETE',requests=self.calls);self.db.set_setting('structure_collection',result);return result
