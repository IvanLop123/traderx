"""Local research API. No endpoint accepts broker credentials or live orders."""
import asyncio
import csv
import hashlib
import io
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field, AwareDatetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.core.config import AISettings
from backend.storage.database import Database, Record, Job, LLMRun
from backend.schemas.contracts import Contract, Prediction, TradeCandidate, ApprovedOrder, AssetIdentifier, now, uid
from backend.providers.market import MarketProviders, ProviderError
from backend.llm.service import LLMService
from backend.llm.providers import TextTask
from backend.workers.runner import Worker
from backend.intelligence.quant import latest_features, black_scholes, parity, trader_metrics, social_metrics
from backend.intelligence.ingest import store_document
from backend.intelligence.documents import narrative_features, parse_form4, parse_13f, theme_graph, question_answer
from backend.research.engine import backtest, train_fusion, infer_registered, signal_evaluation, ordered_bars
from backend.research.retraining import Retrainer, TrainingSchedule
from backend.risk.engine import PaperEngine
from backend.research.robustness import compare_strategies
from scripts.provider_common import config, ROOT

class LogFormatter(logging.Formatter):
    def format(self,record): return json.dumps({'timestamp':now().isoformat(),'level':record.levelname,'subsystem':record.name,'message':record.getMessage()})
handler=logging.StreamHandler(); handler.setFormatter(LogFormatter()); logging.getLogger('traderx').addHandler(handler)

class BacktestRequest(Contract):
    symbol: str = Field(default='BTC-USD',pattern=r'^[A-Z0-9.-]{1,30}$')
    lookback: int = Field(default=20,ge=2,le=252)
    fee_bps: float = Field(default=5,ge=0,le=1000)
    slippage_bps: float = Field(default=5,ge=0,le=1000)
    spread_bps: float = Field(default=2,ge=0,le=1000)
    latency_bars: int = Field(default=1,ge=1,le=10)
    strict_observed: bool = False

class ResearchRequest(Contract):
    symbol: str = Field(default='BTC-USD',pattern=r'^[A-Z0-9.-]{1,30}$')
    horizon: int = Field(default=5,ge=1,le=20)
    hypothesis: str = Field(default='Does 20-bar momentum relate to forward returns?',max_length=2000)

class DocumentRequest(Contract):
    symbol: str = Field(default='',max_length=128,pattern=r'^[A-Za-z0-9_.:/-]*$')
    kind: Literal['transcript','filing','news','theme','summary','form4','13f']='transcript'
    title: str = Field(min_length=1,max_length=200)
    text: str = Field(min_length=1,max_length=100000)
    source_reference: str = Field(min_length=1,max_length=1000)
    published_at: AwareDatetime | None = None
    period_end: date | None = None
    entity_id: str = Field(default='',max_length=80)
    value_unit: Literal['unknown','dollars','thousands']='unknown'

class OptionRequest(Contract):
    spot:float=Field(gt=0); strike:float=Field(gt=0); years:float=Field(gt=0,le=50)
    rate:float=Field(default=.04,ge=-1,le=1); volatility:float=Field(default=.3,gt=0,le=10)
    kind:Literal['call','put']='call'; dividend:float=Field(default=0,ge=0,le=1)

class ImportRequest(Contract):
    csv_text: str = Field(min_length=1,max_length=1000000)
    source: str = Field(default='User-authorized CSV',max_length=1000)

class FetchRequest(Contract):
    provider: Literal['sec','fred','eia','alpaca','hyperliquid']
    symbol: str = Field(default='AAPL',pattern=r'^[A-Z0-9_.-]{1,30}$')
    kind: Literal['news','transcript','options']='news'
    quarter: str = Field(default='',pattern=r'^(\d{4}Q[1-4])?$')
    observation_date: date | None = None
    cik: str = Field(default='0000320193',pattern=r'^\d{1,10}$')
    vintage: date = Field(default_factory=date.today)
    start: date = Field(default_factory=lambda:date(2025,1,1))
    end: date = Field(default_factory=date.today)
    query: str = Field(default='$AAPL',min_length=1,max_length=300)


class HaltRequest(Contract):
    halted:bool=True

class WalletRequest(Contract):
    address:str=Field(pattern=r'^0x[a-fA-F0-9]{40}$')

class QARequest(Contract):
    question:str=Field(max_length=20000); answer:str=Field(max_length=20000)

def create_app(db=None,start_workers=True,transport=None,additional_ui_origins=None):
    db=db or Database(); providers=MarketProviders(db,transport=transport); llm=LLMService(db,transport=transport); paper=PaperEngine(db); worker=Worker(db,providers,llm,paper)
    from backend.intelligence.news import NewsService
    news=NewsService(db,transport=transport)
    from backend.research.autonomous.service import AutonomousResearch
    research_llm=LLMService(db,credentials={k:v for k,v in llm.credentials.items() if k in ('OPENAI_API_KEY','LOCAL_LLM_API_KEY')},transport=transport)
    autonomous=AutonomousResearch(db,research_llm)
    from backend.execution.paper_broker import PaperBroker
    broker=PaperBroker(db,paper,config(),transport)
    @asynccontextmanager
    async def lifespan(app):
        tasks=[]
        if start_workers:
            db.set_setting('alpha_required',True)
            governance=db.setting('alpha_governance',{})
            if governance:db.set_setting('alpha_governance',{**governance,'at':'1970-01-01T00:00:00+00:00'}) # Fresh worker review required after restart.
            if config().get('COINBASE_STREAM_ENABLED','true')=='true' and config().get('ENABLE_MARKET_POLLING','true')=='true':
                from backend.providers.streaming import CoinbaseStream
                tasks.append(asyncio.create_task(CoinbaseStream(db,providers,worker.stop,config()).run()))
            if config().get('ENABLE_MARKET_POLLING','true')=='true': tasks.append(asyncio.create_task(worker.run()))
            if config().get('ENABLE_MARKET_POLLING','true')=='true':
                from backend.workers.ingestion import ScheduledIngestion
                scheduled=ScheduledIngestion(db,providers,paper,worker.stop)
                tasks.extend(scheduled.start())
            tasks.append(asyncio.create_task(news.run(worker.stop)))
            tasks.append(asyncio.create_task(autonomous.run(worker.stop)))
            tasks.append(asyncio.create_task(worker.run_jobs()))
            tasks.append(asyncio.create_task(worker.run_evidence()))
            tasks.append(asyncio.create_task(worker.run_training()))
            tasks.append(asyncio.create_task(worker.run_forward()))
            tasks.append(asyncio.create_task(worker.run_manual(manual_paper)))
            tasks.append(asyncio.create_task(worker.run_model_portfolio(model_portfolio)))
            tasks.append(asyncio.create_task(worker.run_ensemble_shadow(ensemble_shadow)))
            tasks.append(asyncio.create_task(worker.run_structure(structure_collector)))
            tasks.append(asyncio.create_task(worker.run_recommendations()))
            tasks.append(asyncio.create_task(worker.run_alpha()))
            tasks.append(asyncio.create_task(worker.run_qualification(qualification)))
            tasks.append(asyncio.create_task(worker.run_history()))
            from backend.workers.reconciliation import reconcile_paper_broker
            tasks.append(asyncio.create_task(reconcile_paper_broker(broker,worker.stop)))
        yield
        worker.stop.set()
        if coverage_task is not None and not coverage_task.done():tasks.append(coverage_task)
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    app=FastAPI(title='TraderX',version='1.0.0',lifespan=lifespan)
    from backend.research.autonomous.routes import routes as autonomous_routes
    app.include_router(autonomous_routes(autonomous))
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware,minimum_size=1000,compresslevel=4)
    from backend.product.routes import product_routes
    product_router,manual_paper=product_routes(db,providers)
    app.include_router(product_router)
    app.state.manual_paper=manual_paper
    from backend.selection.portfolio import ModelPortfolio
    from backend.selection.routes import selection_routes
    model_portfolio=ModelPortfolio(db,providers)
    app.state.model_portfolio=model_portfolio
    app.include_router(selection_routes(model_portfolio))
    from backend.ensemble.portfolio import ShadowPortfolio
    from backend.ensemble.routes import ensemble_routes
    ensemble_shadow=ShadowPortfolio(db,providers);app.state.ensemble_shadow=ensemble_shadow
    app.include_router(ensemble_routes(ensemble_shadow,manual_paper))
    from backend.research.structure.collector import Collector
    from backend.research.structure.routes import routes as structure_routes
    structure_collector=Collector(db,providers)
    app.include_router(structure_routes(db,structure_collector))
    from backend.research.alpha.routes import routes as alpha_routes
    app.include_router(alpha_routes(db))
    from backend.qualification.engine import QualificationEngine
    from backend.qualification.routes import qualification_routes
    qualification=QualificationEngine(db,providers);app.state.qualification=qualification
    app.include_router(qualification_routes(qualification))
    from backend.api.execution import execution_routes
    app.include_router(execution_routes(db,broker))
    app.state.db=db; app.state.providers=providers; app.state.llm=llm; app.state.paper=paper
    origins=['http://localhost:3000','http://127.0.0.1:3000','http://localhost:8000','http://127.0.0.1:8000']
    origins+=additional_ui_origins or []
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver','backend'])
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','PUT'],allow_headers=['Content-Type','X-TraderX-Client'])
    @app.get('/api/v1/news')
    def recent_news(symbol:str|None=None,limit:int=20,important:bool=False):return news.recent(symbol,limit,important)
    @app.middleware('http')
    async def safe_mutations(request:Request,call_next):
        if request.method in ('POST','PUT','PATCH','DELETE'):
            if request.headers.get('origin') and request.headers['origin'] not in origins:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403,content={'detail':'Untrusted origin'})
            if request.headers.get('x-traderx-client')!='local-ui':
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403,content={'detail':'Local client header required'})
        correlation=uid()
        response=await call_next(request); response.headers['X-Request-ID']=correlation; return response
    @app.exception_handler(ProviderError)
    async def provider_error(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503,content={'status':exc.status,'detail':exc.detail})
    @app.exception_handler(ValueError)
    async def value_error(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422,content={'detail':str(exc)[:300]})
    def bars(symbol): return [r['payload'] for r in db.records('bar',symbol)]
    def quotes():
        result={}
        for r in db.records('quote',limit=1000):
            if r['symbol'] not in result: result[r['symbol']]=r['payload']
        return result
    def get_quote(symbol):
        q=quotes().get(symbol)
        if not q: raise HTTPException(409,'No current quote; refresh market data first')
        return q
    from backend.execution.providers import InternalPaperProvider,CoinbaseReadOnlyProvider,HyperliquidReadOnlyProvider
    def internal_quote(symbol):
        q=get_quote(symbol)
        return q,db.setting('provider_'+q.get('provider','coinbase'),{}).get('status','').startswith('WORKING')
    internal_execution=InternalPaperProvider(paper,internal_quote)
    readonly_venues={'coinbase':CoinbaseReadOnlyProvider(providers),'hyperliquid':HyperliquidReadOnlyProvider(providers)}
    @app.get('/api/v1/execution/venues')
    def execution_venues():
        return {'live_trading':False,'venues':[{'venue':'internal_paper','mode':'simulation','supports_orders':True,'enabled':not paper.snapshot()['kill_switch']},
                {'venue':'alpaca_paper','mode':'paper','supports_orders':True,'enabled':broker.provider.configured() and broker.provider.cfg.get('ALPACA_PAPER_EXECUTION_ENABLED')=='true' and not paper.snapshot()['kill_switch']},
                *[{'venue':v,'mode':'public_read_only','supports_orders':False,'enabled':False} for v in readonly_venues]]}
    @app.post('/api/v1/execution/venues/{venue}/refresh')
    async def venue_snapshot(venue:str):
        if venue not in readonly_venues:raise HTTPException(404,'Read-only venue not found')
        return await readonly_venues[venue].snapshot()
    from backend.research.replay import ReplayRequest,PortfolioReplayRequest,EventReplay,replay_portfolio
    from backend.research.experiments import ExperimentLab,ExperimentDefinition
    lab=ExperimentLab(db)
    @app.post('/api/v1/research/experiments')
    def declared_experiment(request:ExperimentDefinition):return lab.run(request)
    @app.post('/api/v1/research/experiments/{rid}/holdout')
    def release_experiment(rid:str):return lab.release(rid)
    @app.get('/api/v1/research/experiments/families')
    def experiment_families():return lab.families()
    @app.post('/api/v1/research/model-comparison')
    def model_comparison(request:ResearchRequest):
        from backend.research.governance import compare_forecasters
        result=compare_forecasters(bars(request.symbol),request.horizon)
        result['prior_comparisons']=len(db.records('model_comparison',request.symbol))
        rid=db.put('model_comparison',result,request.symbol)
        return {'id':rid,**result}
    from backend.research.datasets import HistoricalDataset,store_dataset,replay_dataset
    @app.post('/api/v1/research/datasets')
    def import_dataset(request:HistoricalDataset):return store_dataset(db,request)
    @app.post('/api/v1/research/datasets/{rid}/replay')
    def run_dataset(rid:str):return replay_dataset(db,rid)
    @app.post('/api/v1/research/replay')
    def replay(request:ReplayRequest):
        result=EventReplay(request).run();result['input_record_id']=db.put('replay_input',request.model_dump(mode='json'));rid=db.put('replay',result)
        return {'id':rid,**result}
    @app.post('/api/v1/research/portfolio-replay')
    def portfolio_replay(request:PortfolioReplayRequest):
        result=replay_portfolio(db,request);rid=db.put('replay',result)
        return {'id':rid,**result}
    @app.get('/api/v1/health')
    def health():
        with Session(db.engine) as s: s.execute(select(Record.id).limit(1))
        return {'status':'WORKING','database':db.engine.dialect.name,'live_trading':False,'execution':'internal_and_alpaca_paper' if broker.provider.cfg.get('ALPACA_PAPER_EXECUTION_ENABLED')=='true' else 'internal_paper_only','worker':db.setting('worker',{'status':'STARTING'}),'evidence_worker':db.setting('evidence_worker',{'status':'STARTING'}),'redis':db.setting('redis',{'status':'NOT_CHECKED'}),'ai':llm.status(),
                'stream':db.setting('stream_coinbase',{'status':'NOT_STARTED'}),
                'ingestion':{name:db.setting('schedule_'+name,{'status':'NOT_CONFIGURED_OR_NOT_SCHEDULED'}) for name in ('alpaca','sec','fred','eia')}}
    @app.get('/api/v1/overview')
    def overview():
        return {'portfolio':paper.snapshot(),'providers':providers.status(),'ai':llm.status(),
                'worker':db.setting('worker',{}),'stream':db.setting('stream_coinbase',{'status':'NOT_STARTED'}),'live_trading':False}
    @app.get('/api/v1/providers')
    def provider_status(): return providers.status()
    @app.post('/api/v1/market/refresh')
    async def refresh(): return await worker.refresh(history=True)
    @app.get('/api/v1/assets/{symbol}')
    def asset(symbol:str):
        return {'symbol':symbol,'quote':quotes().get(symbol),'bars':sorted(bars(symbol),key=lambda x:x['timestamp']),
                'features':db.setting('features_'+symbol,{}),'signals':db.records('signal',symbol),'predictions':db.records('prediction',symbol),
                'documents':db.records('document',symbol),'evidence':db.records('event',symbol,limit=30)}
    @app.get('/api/v1/records/{kind}')
    def records(kind:str,symbol:str|None=None):
        if kind=='ml_study_input':raise HTTPException(403,'Holdout inputs are internal; use explicit study release')
        return db.records(kind,symbol,limit=200)
    @app.get('/api/v1/evidence/{rid}')
    def evidence(rid:str):
        r=db.get(rid)
        if not r: raise HTTPException(404,'Evidence not found')
        if r['kind']=='ml_study_input':raise HTTPException(403,'Holdout inputs are internal; use explicit study release')
        return r
    @app.get('/api/v1/settings/ai')
    def ai_settings(): return llm.status()
    @app.put('/api/v1/settings/ai')
    def update_ai(settings:AISettings):
        db.set_setting('ai',settings.model_dump()); db.put('audit',{'action':'ai_settings_changed','settings':settings.model_dump()})
        return llm.status()
    @app.post('/api/v1/settings/ai/local-health')
    async def local_health(): return await llm.local_health()
    @app.post('/api/v1/documents')
    def document(request:DocumentRequest):
        return store_document(db,**request.model_dump())
    @app.post('/api/v1/documents/{rid}/analyze')
    async def analyze_document(rid:str):
        row=db.get(rid)
        if not row or row['kind']!='document': raise HTTPException(404,'Document not found')
        p=row['payload']
        if p.get('published_at') and datetime.fromisoformat(p['published_at'])>now():raise HTTPException(409,'Document is not yet published')
        if p['kind'] in ('form4','13f'): raise HTTPException(422,'Structured filings use deterministic parsing')
        result=await llm.analyze(TextTask(task=p['kind'],text=p['text'],source_reference=p['source_reference'],automated=False))
        if result['status'] in ('COMPLETE','CACHED'):
            db.put('analysis',{**result,'document_id':rid},p.get('symbol',''))
            from backend.intelligence.semantic import project_analysis
            project_analysis(db,result,rid)
        return result
    @app.get('/api/v1/intelligence/insiders/{symbol}')
    def insiders(symbol:str):
        from backend.intelligence.evidence_features import insider_snapshot
        AssetIdentifier(symbol=symbol,asset_class='stock')
        return insider_snapshot(db,symbol)
    @app.get('/api/v1/intelligence/institutions')
    def institutions(period_end:date|None=None):
        from backend.intelligence.evidence_features import institutional_consensus
        return institutional_consensus(db,period_end.isoformat() if period_end else None)
    @app.post('/api/v1/documents/{rid}/research')
    def document_research(rid:str):
        from backend.intelligence.evidence_features import derive_document
        return derive_document(db,rid)
    @app.get('/api/v1/documents/{rid}/neighbors')
    def document_neighbors(rid:str):
        from backend.intelligence.comparisons import neighbors
        return neighbors(db,rid)
    @app.post('/api/v1/documents/{rid}/compare/{prior_id}')
    async def compare_documents(rid:str,prior_id:str):
        from backend.intelligence.comparisons import compare
        return await compare(db,llm,rid,prior_id)
    @app.get('/api/v1/jobs')
    def jobs():
        with Session(db.engine) as s: return [{'id':j.id,'kind':j.kind,'state':j.state,'attempts':j.attempts,'error':j.error,'due_at':j.due_at} for j in s.scalars(select(Job).limit(200))]
    @app.post('/api/v1/backtests')
    def run_backtest(request:BacktestRequest):
        args=request.model_dump(); symbol=args.pop('symbol'); result=backtest(bars(symbol),**args)
        result['id']=db.put('backtest',result,symbol); return result
    @app.post('/api/v1/experiments')
    def experiment(request:ResearchRequest):
        result={'definition':request.model_dump(),'result':signal_evaluation(bars(request.symbol),request.horizon),'hypothesis_count':len(db.records('experiment'))+1}
        result['id']=db.put('experiment',result,request.symbol); return result
    @app.post('/api/v1/research/compare')
    def compare(request:ResearchRequest):
        result=compare_strategies(bars(request.symbol),len(db.records('strategy_comparison'))+1)
        result['id']=db.put('strategy_comparison',result,request.symbol)
        return result
    from backend.research.registry import ModelRegistry
    registry=ModelRegistry(db)
    from backend.research.studies import Studies,StudyRequest
    studies=Studies(db)
    @app.get('/api/v1/research/studies')
    def study_list():return studies.list()
    @app.post('/api/v1/research/studies')
    def study_run(request:StudyRequest):return studies.run(request)
    @app.post('/api/v1/research/studies/{rid}/release')
    def study_release(rid:str):return studies.release(rid)
    from backend.research.forward import ForwardStudies,EnrollRequest,ReleaseRequest
    from backend.research.universe import Universe,load_universe
    forward=ForwardStudies(db)
    @app.get('/api/v1/research/cross-sectional')
    def cross_sectional_view():
        pointer=db.setting('cross_latest')
        return db.get(pointer['id'])['payload'] if pointer else None
    @app.get('/api/v1/research/universe')
    def universe_get():return load_universe(db).model_dump(mode='json')
    @app.put('/api/v1/research/universe')
    def universe_save(request:Universe):
        db.set_setting('research_universe',request.model_dump(mode='json'));return request
    coverage_task=None
    coverage_error=False
    @app.get('/api/v1/research/coverage')
    async def comprehensive_coverage():
        nonlocal coverage_task,coverage_error
        from backend.research.universe import load_universe
        from backend.research.features import stable_hash
        from backend.research.coverage import universe_coverage
        universe=load_universe(db).model_dump(mode='json');cached=db.setting('universe_coverage_cache',{})
        if cached.get('signature')==stable_hash(universe):return {**cached['result'],'refresh_status':'CURRENT'}
        async def refresh():
            nonlocal coverage_error
            try:await asyncio.to_thread(universe_coverage,db);coverage_error=False
            except Exception:coverage_error=True
        if coverage_task is None or coverage_task.done():coverage_task=asyncio.create_task(refresh())
        previous=cached.get('result',{})
        return {**previous,'universe':universe,'assets':previous.get('assets',[]),'families':previous.get('families',[]),'backfill':previous.get('backfill',{}),'extensions':previous.get('extensions',{}),'limitations':previous.get('limitations',[]),'updated_at':previous.get('updated_at'),'refresh_status':'RETRYING' if coverage_error else 'REFRESHING'}
    @app.get('/api/v1/research/forward')
    def forward_list():return forward.view()
    @app.post('/api/v1/research/forward')
    def forward_enroll(request:EnrollRequest):return forward.enroll(request)
    @app.post('/api/v1/research/forward/{sid}/retire')
    def forward_retire(sid:str):return forward.retire(sid)
    @app.post('/api/v1/research/forward/release-training')
    def forward_release(request:ReleaseRequest):return forward.release(request)
    @app.get('/api/v1/system/research')
    def research_health():
        symbols=Retrainer(db).settings().symbols
        coverage=[]
        for symbol in symbols:
            history=db.records('bar',symbol)
            if history:
                frame=ordered_bars([r['payload'] for r in history])
                coverage.append({'symbol':symbol,'bars':len(frame),'start':str(frame.iloc[0].timestamp),'end':str(frame.iloc[-1].available_at),'last_observed':str(frame.observed_at.max())})
        return {'coverage':coverage,'training':Retrainer(db).status(),'evidence_worker':db.setting('evidence_worker',{}),
                'ingestion':{n:db.setting('schedule_'+n,{}) for n in ('alpaca','sec','fred','eia')},
                'macro_initial_series':[s for s in __import__('backend.research.features',fromlist=['MACRO']).MACRO if db.records('macro_initial',s,limit=1)]}
    @app.get('/api/v1/system/features/{symbol}')
    def feature_health(symbol:str):
        from backend.research.coverage import feature_coverage
        return feature_coverage(db,symbol)
    @app.get('/api/v1/models/registry')
    def registry_status():return registry.status()
    @app.post('/api/v1/models/{rid}/shadow')
    def shadow_model(rid:str):return registry.start(rid)
    @app.post('/api/v1/models/{rid}/promote')
    def promote_model(rid:str):return registry.promote(rid)
    @app.post('/api/v1/models/{rid}/retire')
    def retire_model(rid:str):return registry.retire(rid)
    @app.post('/api/v1/models/train')
    def train(request:ResearchRequest):
        result=train_fusion(bars(request.symbol),request.horizon,db.records('feature',request.symbol)); model_id=db.put('model',result,request.symbol)
        asset=AssetIdentifier(symbol=request.symbol,asset_class='crypto' if '-' in request.symbol else 'stock')
        evidence_ids=[r['id'] for r in db.records('bar',request.symbol,limit=300)]
        pred=Prediction(asset=asset,**result['prediction'],horizon=f'{request.horizon} bars',model=model_id,
                        as_of=datetime.fromisoformat(result['as_of']),calibration={'method':result['calibration'],'holdout_brier':result['holdout_brier']},evidence_ids=evidence_ids)
        db.put('prediction',pred,request.symbol)
        # Research predictions cannot create candidates outside the canonical ensemble.
        return {'model_id':model_id,'result':result,'prediction':pred.model_dump(mode='json'),'candidate':None,'decision':'NO_TRADE'}
    @app.get('/api/v1/settings/training')
    def training_settings(): return Retrainer(db).status()
    @app.put('/api/v1/settings/training')
    def configure_training(settings:TrainingSchedule): return Retrainer(db).configure(settings)
    @app.post('/api/v1/models/check-training')
    def check_training(): return {'outcomes':Retrainer(db).cycle(), **Retrainer(db).status()}
    @app.post('/api/v1/models/{rid}/predict')
    def predict_registered(rid:str):
        row=db.get(rid)
        if not row or row['kind']!='model': raise HTTPException(404,'Model not found')
        model=row['payload']
        if 'artifact' not in model: raise HTTPException(409,'This earlier model record predates saved coefficients; train a new version')
        symbol=db.records('model',limit=5000)
        symbol=next(r['symbol'] for r in symbol if r['id']==rid)
        result=infer_registered(model,bars(symbol),db.records('feature',symbol))
        record={'model_id':rid,'symbol':symbol,'as_of':now().isoformat(),'prediction':result,'status':'RESEARCH_PREDICTION'}
        db.put('model_inference',record,symbol)
        return record
    @app.get('/api/v1/portfolio')
    def portfolio(): return paper.snapshot()
    @app.post('/api/v1/portfolio/{symbol}/close-candidate')
    def close_candidate(symbol:str):
        position=paper.snapshot()['positions'].get(symbol)
        if not position or position['quantity']<=0:raise HTTPException(409,'No long paper position exists for this asset')
        q=get_quote(symbol)
        c=TradeCandidate(asset=AssetIdentifier(symbol=symbol,asset_class=position['asset_class']),prediction_id='user-requested-position-exit',direction='sell',horizon='immediate',
                         entry_price=q['price'],quantity=position['quantity'],expected_edge=0,expected_costs=(paper.limits['fee_bps']+paper.limits['slippage_bps'])/1e4,
                         expected_downside=0,confidence=0,evidence_ids=[r['id'] for r in db.records('fill',symbol)],expires_at=now()+timedelta(minutes=5),liquidity=q)
        db.put('candidate',c,symbol)
        return {'candidate_id':c.id,'status':'RISK_REVIEW_REQUIRED','detail':'Review the exit in Orders. It must pass fresh risk checks before any internal paper fill.'}
    @app.get('/api/v1/risk')
    def risk():
        from backend.risk.analytics import portfolio_risk
        state=paper.snapshot()
        return {'portfolio':state,'limits':paper.limits,'analytics':portfolio_risk(db,state,paper.limits),'assessments':db.records('risk_assessment',limit=100),'live_trading':False}
    from backend.risk.sizing import SizingRequest,position_size
    @app.post('/api/v1/risk/size')
    def size(request:SizingRequest):return position_size(request,paper.limits)
    @app.post('/api/v1/risk/halt')
    def halt(request:HaltRequest): return paper.halt(request.halted)
    @app.post('/api/v1/candidates/{rid}/assess')
    def assess(rid:str):
        row=db.get(rid)
        if not row or row['kind']!='candidate': raise HTTPException(404,'Candidate not found')
        c=TradeCandidate.model_validate(row['payload']); q=get_quote(c.asset.symbol)
        healthy=db.setting('provider_'+q.get('provider','coinbase'),{}).get('status','').startswith('WORKING')
        return paper.assess(c,q,healthy)
    @app.post('/api/v1/orders/{rid}/execute')
    async def execute(rid:str):
        row=db.get(rid)
        if not row or row['kind']!='approved_order': raise HTTPException(409,'Only a persisted risk-approved order can execute')
        order=ApprovedOrder.model_validate(row['payload'])
        return await internal_execution.submit(order,order.id)
    @app.post('/api/v1/options/calculate')
    def options(request:OptionRequest): return black_scholes(**request.model_dump())
    @app.post('/api/v1/options/{rid}/research')
    def options_research(rid:str):
        from backend.intelligence.options import derive_options
        return derive_options(db,rid)
    @app.post('/api/v1/intelligence/question-answer')
    def qa(request:QARequest): return question_answer(request.question,request.answer)
    from backend.research.copyability import CopyReplayRequest,replay_copyability
    @app.post('/api/v1/traders/copy-replay')
    def copy_replay(request:CopyReplayRequest):
        result=replay_copyability(request)
        result['input_record_id']=db.put('copy_replay_input',request.model_dump(mode='json'))
        return {'id':db.put('copy_replay',result),**result}
    @app.post('/api/v1/traders/import')
    def import_trades(request:ImportRequest):
        rows=list(csv.DictReader(io.StringIO(request.csv_text)))
        if not rows or not {'pnl','notional'}.issubset(rows[0]): raise HTTPException(422,'CSV requires pnl,notional columns; optional timestamp,symbol')
        if len(rows)>10000: raise HTTPException(422,'Maximum 10,000 rows')
        for row in rows:
            for key in ['pnl','notional']:
                number=float(row[key])
                if not __import__('math').isfinite(number): raise HTTPException(422,'Finite numeric values required')
        result={'source':request.source,'trades':rows,'metrics':trader_metrics(rows)}; rid=db.put('trader',result)
        return {'id':rid,**result}
    @app.post('/api/v1/traders/wallet')
    async def wallet(request:WalletRequest):
        result=await providers.wallet(request.address); result['metrics']=trader_metrics(result['fills']); return result
    @app.post('/api/v1/providers/fetch')
    async def fetch(request:FetchRequest):
        p=request.provider
        if p=='sec': result=await providers.sec(request.cik)
        elif p=='fred': result=await providers.fred(request.symbol,request.vintage.isoformat())
        elif p=='eia': result=await providers.eia()
        elif p=='alpaca': result=await providers.alpaca_bars(request.symbol,request.start.isoformat(),request.end.isoformat())
        elif p=='hyperliquid': result=await providers.hyperliquid()
        return {'status':'STORED','provider':p,'result':result}
    @app.websocket('/api/v1/ws')
    async def websocket(ws:WebSocket):
        if ws.headers.get('origin') not in origins: await ws.close(code=1008); return
        await ws.accept()
        try:
            while True:
                await ws.send_json({'type':'snapshot','quotes':list(quotes().values()),'worker':db.setting('worker',{}),'portfolio':paper.snapshot()})
                await asyncio.sleep(10)
        except (WebSocketDisconnect,RuntimeError): pass
    return app

app=create_app()
