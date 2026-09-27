"""Independent market polling and durable text jobs; Redis is optional transport."""
import asyncio
import json
import logging
from datetime import timedelta
from sqlalchemy import select
from backend.storage.database import Job, Record
from backend.schemas.contracts import now
from backend.llm.providers import TextTask
from backend.intelligence.quant import latest_features
from backend.intelligence.signals import persist_market_signals
from scripts.provider_common import config

logger=logging.getLogger('traderx.worker')

class Worker:
    def __init__(self,db,providers,llm,paper):
        self.db=db; self.providers=providers; self.llm=llm; self.paper=paper; self.stop=asyncio.Event(); self.refresh_lock=asyncio.Lock()
        self.last_slow=0
    async def refresh(self,history=False):
        async with self.refresh_lock:
            symbols=(config().get('MARKET_SYMBOLS') or 'BTC-USD,ETH-USD,SOL-USD').split(',')[:20]
            outcomes={}; quotes={}
            async def one(symbol):
                try:
                    q=await self.providers.coinbase_quote(symbol); quotes[symbol]=q
                    existing=self.db.records('bar',symbol,limit=1000)
                    if history or not existing: await self.providers.coinbase_bars(symbol,days=1095 if len(existing)<900 else 5)
                    bars=[r['payload'] for r in self.db.records('bar',symbol,limit=5000)]
                    if bars:
                        f=latest_features(bars); self.db.set_setting('features_'+symbol,f)
                        persist_market_signals(self.db,symbol,f,self.db.records('bar',symbol,limit=5000))
                    outcomes[symbol]='WORKING'
                except Exception: outcomes[symbol]='UNAVAILABLE'
            await asyncio.gather(*(one(s.strip()) for s in symbols if s.strip()))
            self.paper.mark(quotes)
            if history or not self.db.records('crypto',limit=1):
                for name,fn in [('hyperliquid',self.providers.hyperliquid),('kalshi',self.providers.kalshi)]:
                    try: await fn(); outcomes[name]='WORKING'
                    except Exception: outcomes[name]='UNAVAILABLE'
            self.db.set_setting('worker',{'status':'RUNNING','last_cycle':now().isoformat(),'outcomes':outcomes})
            try:
                import redis.asyncio as redis
                r=redis.from_url(config().get('REDIS_URL') or 'redis://localhost:6379/0',socket_connect_timeout=1,socket_timeout=1)
                await r.publish('traderx:updates',json.dumps({'type':'market_refresh','timestamp':now().isoformat()})); await r.aclose()
                self.db.set_setting('redis',{'status':'WORKING'})
            except Exception: self.db.set_setting('redis',{'status':'UNAVAILABLE','fallback':'Durable database jobs and websocket snapshots continue'})
            return outcomes
    async def run(self):
        interval=max(30,int(config().get('MARKET_POLL_SECONDS') or 60))
        cycle=0
        while not self.stop.is_set():
            try:
                await self.refresh(history=cycle%60==0); cycle+=1
            except Exception:
                logger.warning('market_cycle_failed',extra={'subsystem':'market'})
            try: await asyncio.wait_for(self.stop.wait(),timeout=interval)
            except asyncio.TimeoutError: pass
    async def run_jobs(self):
        # Inference has its own task. Small homogeneous documents share one request.
        while not self.stop.is_set():
            claimed=[]
            with self.db.transaction() as s:
                for expired in s.scalars(select(Job).where(Job.state=='running',Job.due_at<now().isoformat())):
                    expired.state='queued'
                available=list(s.scalars(select(Job).where(Job.state=='queued',Job.due_at<=now().isoformat()).order_by(Job.due_at).limit(50)))
                if available:
                    kind=available[0].payload.get('task')
                    for job in [j for j in available if j.payload.get('task')==kind][:8]:
                        job.state='running'; job.attempts+=1; job.due_at=(now()+timedelta(minutes=5)).isoformat(); claimed.append((job.id,job.payload))
            if claimed:
                try:
                    results=await self.llm.analyze_many([TextTask.model_validate(p) for _,p in claimed])
                    with self.db.transaction() as s:
                        for (jid,_),result in zip(claimed,results):
                            j=s.get(Job,jid)
                            if result['status'] in ('COMPLETE','CACHED','FILTERED_IRRELEVANT'):
                                source=s.get(Record,jid)
                                j.state='complete'; s.add(Record(kind='analysis',symbol=source.symbol if source else '',available_at=now().isoformat(),payload={**result,'document_id':jid}))
                            elif result['status'] in ('DISABLED','AUTOMATED_DISABLED','OPENAI_AUTOMATED_DISABLED','BUDGET_PAUSED','RATE_PAUSED','NOT_CONFIGURED'):
                                # A policy pause did not attempt inference and must not consume retry allowance.
                                j.attempts=max(0,j.attempts-1);j.state='queued'; j.due_at=(now()+timedelta(minutes=30)).isoformat(); j.error=result['status']
                            elif result['status']=='PROVIDER_UNAVAILABLE' and result.get('provider')=='local' and j.attempts<3:
                                j.state='queued';j.due_at=(now()+timedelta(minutes=5)).isoformat();j.error=result['status']
                            else: j.state='dead_letter'; j.error=result['status']
                except Exception:
                    with self.db.transaction() as s:
                        for jid,_ in claimed:
                            j=s.get(Job,jid); j.state='dead_letter'; j.error='ANALYSIS_FAILURE'
            try: await asyncio.wait_for(self.stop.wait(),timeout=2 if claimed else 10)
            except asyncio.TimeoutError: pass

    async def run_evidence(self):
        from backend.intelligence.evidence_features import refresh_evidence
        while not self.stop.is_set():
            try:await asyncio.to_thread(refresh_evidence,self.db)
            except Exception:
                self.db.set_setting('evidence_worker',{'status':'DEGRADED','last_cycle':now().isoformat()})
                logger.warning('evidence_cycle_failed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=300)
            except asyncio.TimeoutError:pass
