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
                for name,fn in [('hyperliquid',self.providers.hyperliquid)]:
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
                    from backend.intelligence.semantic import project_analysis
                    for (jid,_),result in zip(claimed,results):project_analysis(self.db,result,jid)
                except Exception:
                    with self.db.transaction() as s:
                        for jid,_ in claimed:
                            j=s.get(Job,jid); j.state='dead_letter'; j.error='ANALYSIS_FAILURE'
            try:
                from backend.intelligence.comparisons import cycle
                await cycle(self.db,self.llm)
            except Exception:
                logger.warning('document_comparison_cycle_failed')
            try: await asyncio.wait_for(self.stop.wait(),timeout=2 if claimed else 10)
            except asyncio.TimeoutError: pass

    async def run_evidence(self):
        from backend.intelligence.evidence_features import refresh_evidence
        while not self.stop.is_set():
            try:
                await asyncio.to_thread(refresh_evidence,self.db)
                from backend.research.registry import ModelRegistry
                await asyncio.to_thread(ModelRegistry(self.db).refresh)
            except Exception:
                self.db.set_setting('evidence_worker',{'status':'DEGRADED','last_cycle':now().isoformat()})
                logger.warning('evidence_cycle_failed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=300)
            except asyncio.TimeoutError:pass

    async def run_training(self):
        from backend.research.retraining import Retrainer
        while not self.stop.is_set():
            try:
                await asyncio.to_thread(Retrainer(self.db).cycle)
            except Exception:
                self.db.set_setting('training_worker', {'status':'DEGRADED','checked_at':now().isoformat()})
                logger.warning('training_cycle_failed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=3600)
            except asyncio.TimeoutError:pass

    async def run_forward(self):
        from backend.research.forward import ForwardStudies
        service=ForwardStudies(self.db)
        while not self.stop.is_set():
            try:
                await service.cycle(self.providers)
                self.db.set_setting('forward_worker',{'status':'RUNNING','last_cycle':now().isoformat()})
            except Exception:self.db.set_setting('forward_worker',{'status':'DEGRADED','last_cycle':now().isoformat()})
            try:await asyncio.wait_for(self.stop.wait(),timeout=30)
            except asyncio.TimeoutError:pass

    async def run_history(self):
        from backend.providers.history import HistoricalBackfill
        from backend.research.history import HistoryStore
        from backend.research.universe import load_universe
        while not self.stop.is_set():
            due=self.db.setting('archive_refresh',{})
            if due.get('next_at','')<=now().isoformat():
                self.db.set_setting('archive_refresh',{'next_at':(now()+timedelta(days=1)).isoformat(),'status':'RUNNING'})
                outcomes={};h=HistoricalBackfill(self.providers);store=HistoryStore(self.db);u=load_universe(self.db)
                # Refresh only explicitly backfilled assets; changing the universe does not launch an unbounded job.
                equities=[i.symbol for i in u.instruments if i.asset_class in ('stock','etf') and store.manifest(i.symbol)]
                try:await h.calendar();outcomes['calendar']='COMPLETE'
                except Exception:outcomes['calendar']='UNAVAILABLE'
                for offset in range(0,len(equities),u.backfill_batch_size):
                    batch=equities[offset:offset+u.backfill_batch_size]
                    for name,fn in [('equities_'+str(offset),lambda batch=batch:h.alpaca(batch,feed=self.providers.cfg.get('ALPACA_RESEARCH_FEED') or store.manifest(batch[0])['feed'])),('actions_'+str(offset),lambda batch=batch:h.corporate_actions(batch))]:
                        try:await fn();outcomes[name]='COMPLETE'
                        except Exception:outcomes[name]='UNAVAILABLE'
                for instrument in u.instruments:
                    if instrument.asset_class!='crypto' or not store.manifest(instrument.symbol):continue
                    try:
                        old=store.read(instrument.symbol);recent=await self.providers.coinbase_bars(instrument.symbol,days=5)
                        rows={r['timestamp']:r for r in old}
                        for r in recent:rows[r['timestamp']]=r
                        store.save(instrument.symbol,'coinbase',list(rows.values()));outcomes[instrument.symbol]='COMPLETE'
                    except Exception:outcomes[instrument.symbol]='UNAVAILABLE'
                for coin in ['BTC','ETH','SOL']:
                    history=self.db.records('funding_history',coin,limit=1)
                    if history and history[0]['payload']['rows']:
                        try:
                            from datetime import datetime,timezone
                            last=max(r['time'] for r in history[0]['payload']['rows'])
                            await h.funding(coin,datetime.fromtimestamp(last/1000,timezone.utc).date().isoformat(),max_pages=5);outcomes['funding_'+coin]='COMPLETE'
                        except Exception:outcomes['funding_'+coin]='UNAVAILABLE'
                for symbol,cik in {**{'AAPL':'320193','MSFT':'789019','NVDA':'1045810'},**self.db.setting('universe_ciks',{})}.items():
                    coverage=self.db.setting('form4_coverage_'+symbol,{})
                    if coverage.get('complete_window') and coverage.get('end','')<(now()-timedelta(days=7)).isoformat():
                        try:await h.sec_form4(symbol,cik);outcomes['sec_'+symbol]='COMPLETE'
                        except Exception:outcomes['sec_'+symbol]='UNAVAILABLE'
                self.db.set_setting('universe_coverage_cache',{})
                self.db.set_setting('product_summary_cache',{})
                try:
                    from scripts.research.activate_product_studies import refresh
                    if self.db.setting('strategy_latest'):await asyncio.to_thread(refresh,self.db)
                except Exception:outcomes['product_research']='UNAVAILABLE; previous dated forecasts retained'
                self.db.set_setting('archive_refresh',{'next_at':(now()+timedelta(days=1)).isoformat(),'status':'COMPLETE','outcomes':outcomes,'last_cycle':now().isoformat()})
            try:await asyncio.wait_for(self.stop.wait(),timeout=3600)
            except asyncio.TimeoutError:pass

    async def run_manual(self,service):
        from backend.product.cockpit import Cockpit
        journal=Cockpit(self.db,service)
        while not self.stop.is_set():
            try:
                await service.cycle(self.providers)
                from backend.ensemble.portfolio import ManualExits
                await ManualExits(self.db,service).cycle(self.providers)
                await asyncio.to_thread(journal.observe)
                self.db.set_setting('manual_paper_worker',{'status':'RUNNING','last_cycle':now().isoformat()})
            except Exception:
                self.db.set_setting('manual_paper_worker',{'status':'DEGRADED','last_cycle':now().isoformat()})
            try:await asyncio.wait_for(self.stop.wait(),timeout=3)
            except asyncio.TimeoutError:pass

    async def run_model_portfolio(self,service):
        while not self.stop.is_set():
            try:await service.cycle()
            except Exception:
                self.db.set_setting('model_portfolio_control',{**self.db.setting('model_portfolio_control',{}),'entries_blocked':True,'data_error':True,'at':now().isoformat(),'reason':'Portfolio worker requires review'})
                self.db.set_setting('model_portfolio_worker',{'status':'DEGRADED','last_cycle':now().isoformat()})
                logger.warning('model_portfolio_cycle_failed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=30)
            except asyncio.TimeoutError:pass

    async def run_qualification(self,service):
        while not self.stop.is_set():
            try:await service.cycle()
            except Exception:
                self.db.set_setting('qualification_worker',{'status':'DEGRADED','last_cycle':now().isoformat(),'message':'Comparison collection unavailable; no promotion. Other collectors continue.'})
                logger.warning('qualification_cycle_failed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=30)
            except asyncio.TimeoutError:pass

    async def run_ensemble_shadow(self,service):
        while not self.stop.is_set():
            try:await service.cycle()
            except Exception:
                self.db.set_setting('ensemble_shadow_worker',{'status':'DEGRADED','at':now().isoformat(),'message':'Shadow simulation unavailable; other collectors continue','external_execution':False})
                logger.exception('ensemble_shadow_cycle_failed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=5)
            except asyncio.TimeoutError:pass

    async def run_recommendations(self):
        from backend.ensemble.lifecycle import Recommendations
        while not self.stop.is_set():
            try:await asyncio.to_thread(Recommendations(self.db).cycle)
            except Exception:self.db.set_setting('recommendation_worker',{'status':'DEGRADED','at':now().isoformat()})
            try:await asyncio.wait_for(self.stop.wait(),timeout=60)
            except asyncio.TimeoutError:pass

    async def run_structure(self,collector):
        while not self.stop.is_set():
            try:await collector.cycle()
            except Exception:self.db.set_setting('structure_worker',{'status':'DEGRADED','at':now().isoformat()})
            try:await asyncio.wait_for(self.stop.wait(),timeout=60)
            except asyncio.TimeoutError:pass

    async def run_alpha(self):
        from backend.research.alpha.forward import AlphaForward
        service=AlphaForward(self.db,self.providers)
        while not self.stop.is_set():
            try:await service.cycle()
            except Exception:
                self.db.set_setting('alpha_worker',{'status':'DEGRADED','at':now().isoformat(),'external_execution':False})
                logger.exception('alpha_cycle_failed')
            try:await asyncio.wait_for(self.stop.wait(),timeout=60)
            except asyncio.TimeoutError:pass
