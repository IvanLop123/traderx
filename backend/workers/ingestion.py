"""Independent, bounded read-only schedules. Keys activate feeds after restart."""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import PurePosixPath
from backend.schemas.contracts import now
from backend.intelligence.ingest import store_document
from backend.intelligence.quant import latest_features
from backend.intelligence.signals import persist_market_signals
from scripts.provider_common import ROOT

class VisibleText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('p','div','br','tr'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,text):
        if not self.hidden:self.parts.append(text)

class ScheduledIngestion:
    REQUIRED={'alpaca':['ALPACA_API_KEY','ALPACA_API_SECRET'],'alpha_vantage':['ALPHA_VANTAGE_API_KEY'],
              'sec':['SEC_USER_AGENT'],'fred':['FRED_API_KEY'],'eia':['EIA_API_KEY']}
    def __init__(self,db,providers,paper,stop,settings=None):
        self.db=db;self.providers=providers;self.paper=paper;self.stop=stop
        self.settings=settings if settings is not None else json.loads((ROOT/'config/ingestion.json').read_text())
    def configured(self,name):return all(self.providers.cfg.get(key) for key in self.REQUIRED[name])
    def start(self):
        if not self.settings.get('enabled'):return []
        return [asyncio.create_task(self.run_provider(name),name='ingestion_'+name) for name in self.REQUIRED if self.configured(name)]
    async def run_provider(self,name):
        interval=max(60,int(self.settings['poll_seconds'][name]))
        while not self.stop.is_set():
            previous=self.db.setting('schedule_'+name,{})
            due=datetime.fromisoformat(previous.get('next_run',now().isoformat()))
            if now()>=due:
                # Persist the next run before I/O: restarts cannot reset account rate limits.
                self.db.set_setting('schedule_'+name,{'last_attempt':now().isoformat(),'next_run':(now()+timedelta(seconds=interval)).isoformat(),'status':'RUNNING'})
                try:
                    await self.cycle(name);status='WORKING'
                except Exception:status='DEFERRED'
                self.db.set_setting('schedule_'+name,{**self.db.setting('schedule_'+name),'status':status})
            try:await asyncio.wait_for(self.stop.wait(),timeout=min(interval,60))
            except asyncio.TimeoutError:pass
    async def cycle(self,name):
        p=self.providers;c=self.settings
        if name=='alpaca':
            quotes={}
            for symbol in c['equities'][:20]:
                quotes[symbol]=await p.alpaca_quote(symbol)
                last=self.db.setting('stock_history_'+symbol,{})
                if last.get('date')!=now().date().isoformat():
                    await p.alpaca_bars(symbol,(now()-timedelta(days=c['lookback_days'])).date().isoformat(),now().date().isoformat())
                    rows=self.db.records('bar',symbol,limit=5000)
                    if rows:
                        f=latest_features([r['payload'] for r in rows]);self.db.set_setting('features_'+symbol,f)
                        persist_market_signals(self.db,symbol,f,rows)
                    self.db.set_setting('stock_history_'+symbol,{'date':now().date().isoformat()})
            self.paper.mark(quotes)
        elif name=='alpha_vantage':
            # One multi-symbol news request per cycle. Premium transcripts/options remain on demand.
            await p.alpha('news',','.join(c['equities'][:10]))
        elif name=='sec':
            for symbol,cik in list(c['sec_ciks'].items())[:20]:
                filings=await p.sec(cik)
                eligible=[f for f in filings if f['form'] in ('4','4/A','10-K','10-Q','8-K')][:c['max_filings_per_company']]
                for filing in eligible:
                    source=filing['document_url'];key='sec_seen_'+hashlib.sha256(source.encode()).hexdigest()[:48]
                    if self.db.setting(key):continue
                    filename=PurePosixPath(filing['primaryDocument']).name
                    text=await p.sec_document(cik,filing['accessionNumber'].replace('-',''),filename)
                    published=datetime.fromisoformat(filing['filingDate']).replace(tzinfo=timezone.utc)
                    kind='form4' if filing['form'].startswith('4') else 'filing'
                    if kind=='filing':
                        parser=VisibleText();parser.feed(text);text=' '.join(' '.join(parser.parts).split())
                    # Bounded sections preserve exact excerpts and avoid token-heavy entire filings.
                    sections=[text] if kind=='form4' else [text[i:i+12000] for i in range(0,min(len(text),120000),12000)]
                    for i,section in enumerate(sections):
                        if section:store_document(self.db,text=section,kind=kind,title=f"{symbol} {filing['form']} {filing['filingDate']} section {i+1}",source_reference=source+f'#section-{i+1}',symbol=symbol,published_at=published,provider='sec',period_end=filing.get('reportDate') or None)
                    self.db.set_setting(key,{'processed_at':now().isoformat(),'sections':len(sections),'characters':len(text),'truncated':len(text)>120000 and kind!='form4'})
        elif name=='fred':
            for series in c['fred_series'][:10]:await p.fred(series,now().date().isoformat())
        elif name=='eia':await p.eia()
