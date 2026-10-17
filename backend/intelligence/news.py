"""Forward-only, deterministic news evidence. No LLM or trading API is reachable."""
import asyncio
from datetime import timedelta
import hashlib
import html
import json
import re
from urllib.parse import urlsplit
import httpx
import websockets
from sqlalchemy import select
from backend.storage.database import Record, Setting
from backend.schemas.contracts import now
from backend.research.universe import load_universe
from scripts.provider_common import config

VERSION = 'news-rules-v1'
LIMITATIONS = ('Alpaca news (source attributed per story); coverage is not exhaustive. '
               'Stream entitlement does not establish measured delivery latency. '
               'Rule-based direction is uncertain, not a calibrated return forecast. '
               'Collected prospectively; excluded from historical backtests and automatic training.')
RULES = {
    'earnings/results': r'\b(earnings|eps|quarterly results|quarterly revenue|profit|loss per share)\b',
    'guidance': r'\b(guidance|outlook|forecasts?|projects? revenue)\b',
    'M&A': r'\b(merger|acquisition|acquires?|takeover|buyout|merges?)\b',
    'analyst actions': r'\b(upgrades?|downgrades?|price target|initiates? coverage|analyst rating)\b',
    'management changes': r'\b(ceo|cfo|chief executive|chief financial|resigns?|appoints?|leadership)\b',
    'financing/capital raises': r'\b(offering|capital raise|raises? capital|debt issuance|convertible notes|dilution|bankruptcy)\b',
    'regulatory/legal': r'\b(lawsuit|litigation|regulator|regulatory|sec charges|antitrust|investigation|fda|recall)\b',
    'product/business developments': r'\b(launch(?:es)?|partnership|contract|product|approval|expansion|supply chain)\b',
    'macro/industry events': r'\b(inflation|federal reserve|interest rates|tariffs?|gdp|employment|industry|oil prices|sector)\b',
}
POSITIVE = r'\b(raises guidance|raised guidance|beats? estimates|beats? expectations|upgrades?|record revenue|approval|approved)\b'
NEGATIVE = r'\b(cuts? guidance|lowers? guidance|misses? estimates|misses? expectations|downgrades?|bankruptcy|recall|sec charges|fraud)\b'

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def plain(value): return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]*>', ' ', str(value or '')))).strip()
def timestamp(value):
    from datetime import datetime, timezone
    try:
        v=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return v.astimezone(timezone.utc) if v.tzinfo else None
    except (ValueError, TypeError): return None

def classify(headline, summary=''):
    title=plain(headline).lower();text=title+' '+plain(summary).lower()
    categories=[k for k,p in RULES.items() if re.search(p,text)]
    # Direction uses the headline only; quotes/boilerplate in article bodies cannot cast votes.
    pos=bool(re.search(POSITIVE,title));neg=bool(re.search(NEGATIVE,title))
    ambiguous=bool(re.search(r'\b(not|denies?|rumou?r|reportedly|could|may|might)\b|\?',title))
    direction='uncertain' if ambiguous or (pos and neg) else 'negative' if neg else 'positive' if pos else 'neutral'
    materiality='high' if categories and (pos or neg or any(c in categories for c in ('guidance','M&A','financing/capital raises','regulatory/legal'))) else 'medium' if categories else 'low'
    return {'categories':categories or ['other'],'sentiment':direction,'direction':direction,'materiality':materiality,
            'uncertainty':'high' if ambiguous or direction in ('neutral','uncertain') else 'moderate',
            'method':VERSION,'model':None,'provider':'deterministic_python','predictive_weight':0.0}

def current_evidence(events, at=None):
    at=timestamp(at) if at is not None else now();items=[];seen=set()
    if at is None:return []
    for e in events:
        available=timestamp(e.get('available_at'));published=timestamp(e.get('published_at'))
        if not available or not published or not 0 <= (at-available).total_seconds() <= 48*3600 or not 0 <= (at-published).total_seconds() <= 48*3600:continue
        if e['cluster_id'] in seen:continue
        seen.add(e['cluster_id']);items.append(e)
    return items

def live_governance(db):
    # Read once per batch, never one database query for each of 500 symbols.
    g=db.setting('alpha_governance',{});events=db.setting('news_evidence',{})
    return {**g,'_news':events} if events else g

def attach(row, governance, at=None):
    events=governance.get('_news',{}).get(row.get('symbol'),[])
    return {**row,'news_evidence':current_evidence(events,at)} if events or 'news_evidence' in row else row

class NewsService:
    def __init__(self, db, cfg=None, transport=None):
        self.db=db;self.cfg=cfg if cfg is not None else config();self.transport=transport
    def configured(self):return bool(self.cfg.get('ALPACA_API_KEY') and self.cfg.get('ALPACA_API_SECRET'))
    def enabled(self):return self.cfg.get('ALPACA_NEWS_ENABLED','true')=='true'
    def headers(self):return {'APCA-API-KEY-ID':self.cfg['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':self.cfg['ALPACA_API_SECRET']}
    def update_status(self, **values):
        with self.db.transaction() as s:
            old=s.get(Setting,'alpaca_news_status')
            s.merge(Setting(key='alpaca_news_status',value={**(old.value if old else {}),**values,'checked_at':now().isoformat()}))
    def status(self):
        value=self.db.setting('alpaca_news_status',{})
        if not self.enabled():value={**value,'status':'DISABLED','entitlement':'Disabled'}
        elif not self.configured():value={**value,'status':'NOT_CONFIGURED','entitlement':'No usable access — credentials missing'}
        else:
            value={'status':'NOT_CHECKED','entitlement':'Not yet verified',**value}
            if value.get('status')=='STREAMING' and (not timestamp(value.get('stream_heartbeat_at')) or (now()-timestamp(value['stream_heartbeat_at'])).total_seconds()>120):value={**value,'status':'STALE','connection':'No recent collector heartbeat'}
        return {'provider':'Alpaca News','limitations':LIMITATIONS,'collection':'Continuous while TraderX is running, including premarket, after-hours and weekends','evidence_policy':'forward_collected_only','classifier':VERSION,**value}
    def recent(self,symbol=None,limit=20,important=False):
        events=list(self.db.setting('news_recent',{}).get('events',[]))
        events=[e for e in events if (not symbol or symbol in e['symbols']) and (not important or e['materiality']=='high')]
        return {'status':self.status(),'events':events[:max(1,min(limit,50))]}
    def ingest(self, articles, received=None):
        received=received or now();u=load_universe(self.db);known={i.symbol for i in u.instruments};aliases={s.replace('-',''):s for s in known}
        aliases.update({i.symbol.split('-')[0]:i.symbol for i in u.instruments if i.asset_class=='crypto'})
        normalized=[]
        for a in articles:
            title=plain(a.get('headline'))[:1500];published=timestamp(a.get('created_at'));updated=timestamp(a.get('updated_at')) or published
            if not title or not published or not updated or max(published,updated)>received+timedelta(minutes=5) or not a.get('id'):continue
            symbols=sorted({s if s in known else aliases.get(s,'') for s in a.get('symbols',[]) if isinstance(s,str)}-{''})
            evidence=classify(title,a.get('summary',''))
            # Deterministic relevance filter: configured asset OR a classified macro event.
            if not symbols and 'macro/industry events' not in evidence['categories']:continue
            canonical=re.sub(r'[^a-z0-9]+',' ',title.lower()).strip()
            url=str(a.get('url') or '');url=url if urlsplit(url).scheme in ('http','https') and not urlsplit(url).username else ''
            cluster='news_'+digest(canonical+'|'+published.date().isoformat())[:40]
            available=max(received,published,updated)
            event={**evidence,'cluster_id':cluster,'provider_article_id':str(a['id']),'source':plain(a.get('source','Alpaca'))[:120],'url':url,'headline':title,'summary':plain(a.get('summary',''))[:3000],'symbols':symbols,'scope':'mapped assets' if symbols else 'macro context; no inferred ticker mapping','published_at':published.isoformat(),'updated_at':updated.isoformat(),'received_at':received.isoformat(),'available_at':available.isoformat(),'publication_age_seconds':max(0,(received-published).total_seconds()),'revision_age_seconds':max(0,(received-updated).total_seconds()),'forward_collected':True,'novelty':'new story'}
            event['id']='news_revision_'+digest(json.dumps({k:v for k,v in event.items() if k not in ('received_at','available_at','publication_age_seconds','revision_age_seconds','novelty','provider_article_id')},sort_keys=True))[:48]
            normalized.append(event)
        affected=set();accepted=[]
        with self.db.transaction() as s:
            recent=s.get(Setting,'news_recent');items=list(recent.value.get('events',[]) if recent else [])
            for e in normalized:
                prior=next((x for x in items if x['provider_article_id']==e['provider_article_id'] or x['cluster_id']==e['cluster_id'] or (x['url'] and x['url']==e['url'])),None)
                if prior:
                    if e['updated_at']<prior['updated_at']:continue
                    if e['headline']==prior['headline'] and e['summary']==prior['summary'] and e['symbols']==prior['symbols']:continue
                    e['cluster_id']=prior['cluster_id'];e['novelty']='revision; replaces prior evidence'
                if s.get(Record,e['id']):continue
                s.add(Record(id=e['id'],kind='news_event',symbol=e['symbols'][0] if e['symbols'] else '',available_at=e['available_at'],payload=e));accepted.append(e);affected.update(e['symbols']);affected.update(prior['symbols'] if prior else [])
                items=[x for x in items if x['cluster_id']!=e['cluster_id']];items.insert(0,e)
            # Cap hot state. Immutable receipts are retained for forward evaluation.
            items=sorted(items,key=lambda e:e['available_at'],reverse=True)[:500]
            if accepted:
                evidence={}
                for e in current_evidence(items,received):
                    for symbol in e['symbols']:evidence.setdefault(symbol,[]).append(e)
                s.merge(Setting(key='news_recent',value={'events':items,'updated_at':received.isoformat()}))
                s.merge(Setting(key='news_evidence',value=evidence))
        return sorted(affected),accepted
    async def consume(self,articles):
        affected,accepted=await asyncio.to_thread(self.ingest,articles)
        if affected:
            from backend.ensemble.lifecycle import Recommendations
            await asyncio.to_thread(Recommendations(self.db).cycle,symbols=set(affected))
        if accepted:self.update_status(last_relevant_story_at=accepted[-1]['received_at'],last_publication_age_seconds=accepted[-1]['publication_age_seconds'],last_revision_age_seconds=accepted[-1]['revision_age_seconds'])
        return accepted
    async def poll(self):
        cursor=self.db.setting('alpaca_news_cursor',{}).get('updated_at');start=timestamp(cursor) or now()-timedelta(hours=24)
        params={'limit':50,'sort':'asc','start':(start-timedelta(minutes=5)).isoformat(),'include_content':'false','exclude_contentless':'false'};count=0;latest=None
        async with httpx.AsyncClient(timeout=20,transport=self.transport) as client:
            # Bounded recovery: continuation cursor is persisted, never silently skip a backlog.
            cursor_state=self.db.setting('alpaca_news_cursor',{})
            if cursor_state.get('page_token'):params=cursor_state['params'];params={**params,'page_token':cursor_state['page_token']}
            for _ in range(4):
                response=await client.get('https://data.alpaca.markets/v1beta1/news',headers=self.headers(),params=params)
                if response.status_code!=200:
                    self.update_status(rest_status='ENTITLEMENT_UNAVAILABLE' if response.status_code in (401,403) else 'UNAVAILABLE',rest_http=response.status_code)
                    return
                articles=response.json().get('news',[]);await self.consume(articles);count+=len(articles)
                dates=[timestamp(a.get('updated_at') or a.get('created_at')) for a in articles];dates=[v for v in dates if v and v<=now()]
                if dates:latest=max([latest] + dates) if latest else max(dates)
                token=response.json().get('next_page_token')
                self.db.set_setting('alpaca_news_cursor',{'updated_at':max(timestamp(cursor) or start,latest or start).isoformat(),'page_token':token,'params':{k:v for k,v in params.items() if k!='page_token'}})
                if not token:break
                params['page_token']=token
        self.update_status(rest_status='WORKING',rest_error=None,rest_http=200,last_poll_at=now().isoformat(),last_poll_count=count,recovery_pending=bool(token))
    async def run(self,stop):
        if not self.enabled() or not self.configured():return
        async def polling():
            while not stop.is_set():
                try:await self.poll()
                except Exception:self.update_status(rest_status='UNAVAILABLE',rest_error='Collection failed; retry scheduled')
                try:await asyncio.wait_for(stop.wait(),timeout=60)
                except TimeoutError:pass
        task=asyncio.create_task(polling())
        try:
            while not stop.is_set():
                try:
                    async with websockets.connect('wss://stream.data.alpaca.markets/v1beta1/news',extra_headers=self.headers(),open_timeout=15,ping_interval=20,ping_timeout=20,max_size=2**21) as ws:
                        self.update_status(status='CONNECTING',connection='Authenticating')
                        while not stop.is_set():
                            try:messages=json.loads(await asyncio.wait_for(ws.recv(),timeout=30))
                            except TimeoutError:
                                self.update_status(stream_heartbeat_at=now().isoformat());continue
                            batch=[]
                            for m in messages:
                                if m.get('T')=='success' and m.get('msg')=='authenticated':await ws.send(json.dumps({'action':'subscribe','news':['*']}))
                                elif m.get('T')=='subscription' and '*' in m.get('news',[]):self.update_status(status='STREAMING',entitlement='Real-time stream access verified',connection='Subscribed',stream_verified_at=now().isoformat(),stream_heartbeat_at=now().isoformat())
                                elif m.get('T')=='error':
                                    code=m.get('code');self.update_status(status='UNAVAILABLE',connection='Stream rejected',stream_error_code=code,entitlement='No usable streaming entitlement' if code in (402,409) else 'Streaming unavailable; access not verified');raise ConnectionError('Stream rejected')
                                elif m.get('T')=='n':batch.append(m)
                            if batch:
                                receipt=now();ages=[(receipt-timestamp(m['created_at'])).total_seconds() for m in batch if timestamp(m.get('created_at'))]
                                self.update_status(last_stream_story_at=receipt.isoformat(),stream_heartbeat_at=receipt.isoformat(),observed_stream_publication_age_seconds=max(ages) if ages else None)
                                await self.consume(batch)
                except asyncio.CancelledError:raise
                except Exception:self.update_status(status='RECONNECTING',connection='Disconnected; REST recovery remains independent')
                try:await asyncio.wait_for(stop.wait(),timeout=30)
                except TimeoutError:pass
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
