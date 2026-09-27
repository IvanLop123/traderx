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
from backend.research.engine import backtest, train_fusion, infer_registered, signal_evaluation, candidate_from_prediction
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
    symbol: str = Field(default='',max_length=40,pattern=r'^[A-Za-z0-9_.:/-]*$')
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
    provider: Literal['sec','fred','eia','alpha_vantage','alpaca','x','hyperliquid','kalshi']
    symbol: str = Field(default='AAPL',pattern=r'^[A-Z0-9_.-]{1,30}$')
    kind: Literal['news','transcript','options']='news'
    quarter: str = Field(default='',pattern=r'^(\d{4}Q[1-4])?$')
    observation_date: date | None = None
    cik: str = Field(default='0000320193',pattern=r'^\d{1,10}$')
    vintage: date = Field(default_factory=date.today)
    start: date = Field(default_factory=lambda:date(2025,1,1))
    end: date = Field(default_factory=date.today)
    query: str = Field(default='$AAPL',min_length=1,max_length=300)

class ChatRequest(Contract):
    message: str = Field(min_length=1,max_length=12000)

class HaltRequest(Contract):
    halted:bool=True

class WalletRequest(Contract):
    address:str=Field(pattern=r'^0x[a-fA-F0-9]{40}$')

class QARequest(Contract):
    question:str=Field(max_length=20000); answer:str=Field(max_length=20000)

def create_app(db=None,start_workers=True,transport=None):
    db=db or Database(); providers=MarketProviders(db,transport=transport); llm=LLMService(db,transport=transport); paper=PaperEngine(db); worker=Worker(db,providers,llm,paper)
    @asynccontextmanager
    async def lifespan(app):
        tasks=[]
        if start_workers:
            if config().get('ENABLE_MARKET_POLLING','true')=='true': tasks.append(asyncio.create_task(worker.run()))
            if config().get('ENABLE_MARKET_POLLING','true')=='true':
                from backend.workers.ingestion import ScheduledIngestion
                scheduled=ScheduledIngestion(db,providers,paper,worker.stop)
                tasks.extend(scheduled.start())
            tasks.append(asyncio.create_task(worker.run_jobs()))
            tasks.append(asyncio.create_task(worker.run_evidence()))
        yield
        worker.stop.set()
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    app=FastAPI(title='TraderX',version='0.1.0',lifespan=lifespan)
    app.state.db=db; app.state.providers=providers; app.state.llm=llm; app.state.paper=paper
    origins=['http://localhost:3000','http://127.0.0.1:3000','http://localhost:8000','http://127.0.0.1:8000']
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver','backend'])
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','PUT'],allow_headers=['Content-Type','X-TraderX-Client'])
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
    @app.get('/api/v1/health')
    def health():
        with Session(db.engine) as s: s.execute(select(Record.id).limit(1))
        return {'status':'WORKING','database':db.engine.dialect.name,'live_trading':False,'execution':'internal_paper_only','worker':db.setting('worker',{'status':'STARTING'}),'evidence_worker':db.setting('evidence_worker',{'status':'STARTING'}),'redis':db.setting('redis',{'status':'NOT_CHECKED'}),'ai':llm.status(),
                'ingestion':{name:db.setting('schedule_'+name,{'status':'NOT_CONFIGURED_OR_NOT_SCHEDULED'}) for name in ('alpaca','alpha_vantage','sec','fred','eia')}}
    @app.get('/api/v1/overview')
    def overview():
        return {'portfolio':paper.snapshot(),'quotes':list(quotes().values()),'providers':providers.status(),'ai':llm.status(),
                'features':{symbol:db.setting('features_'+symbol,{}) for symbol in quotes()},
                'signals':db.records('signal',limit=12),'candidates':db.records('candidate',limit=12),'activity':db.records('event',limit=12),
                'worker':db.setting('worker',{}),'live_trading':False}
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
    def records(kind:str,symbol:str|None=None): return db.records(kind,symbol,limit=200)
    @app.get('/api/v1/evidence/{rid}')
    def evidence(rid:str):
        r=db.get(rid)
        if not r: raise HTTPException(404,'Evidence not found')
        return r
    @app.get('/api/v1/settings/ai')
    def ai_settings(): return llm.status()
    @app.put('/api/v1/settings/ai')
    def update_ai(settings:AISettings):
        db.set_setting('ai',settings.model_dump()); db.put('audit',{'action':'ai_settings_changed','settings':settings.model_dump()})
        return llm.status()
    @app.post('/api/v1/settings/ai/local-health')
    async def local_health(): return await llm.local_health()
    @app.post('/api/v1/chat')
    async def chat(request:ChatRequest):
        return await llm.analyze(TextTask(task='chat',text=request.message,source_reference='user://chat',automated=False))
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
        if result['status'] in ('COMPLETE','CACHED'): db.put('analysis',{**result,'document_id':rid},p.get('symbol',''))
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
    @app.post('/api/v1/models/train')
    def train(request:ResearchRequest):
        result=train_fusion(bars(request.symbol),request.horizon,db.records('feature',request.symbol)); model_id=db.put('model',result,request.symbol)
        asset=AssetIdentifier(symbol=request.symbol,asset_class='crypto' if '-' in request.symbol else 'stock')
        evidence_ids=[r['id'] for r in db.records('bar',request.symbol,limit=300)]
        pred=Prediction(asset=asset,**result['prediction'],horizon=f'{request.horizon} bars',model=model_id,
                        as_of=datetime.fromisoformat(result['as_of']),calibration={'method':result['calibration'],'holdout_brier':result['holdout_brier']},evidence_ids=evidence_ids)
        db.put('prediction',pred,request.symbol)
        quote=quotes().get(request.symbol)
        candidate=candidate_from_prediction(pred,quote,paper.snapshot()['equity']) if quote and result['research_candidate_eligible'] else None
        if candidate: db.put('candidate',candidate,request.symbol)
        return {'model_id':model_id,'result':result,'prediction':pred.model_dump(mode='json'),'candidate':candidate.model_dump(mode='json') if candidate else None,'decision':'CANDIDATE' if candidate else 'NO_TRADE'}
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
    def risk(): return {'portfolio':paper.snapshot(),'limits':paper.limits,'assessments':db.records('risk_assessment',limit=100),'live_trading':False}
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
    def execute(rid:str):
        row=db.get(rid)
        if not row or row['kind']!='approved_order': raise HTTPException(409,'Only a persisted risk-approved order can execute')
        order=ApprovedOrder.model_validate(row['payload']); q=get_quote(order.asset.symbol)
        healthy=db.setting('provider_'+q.get('provider','coinbase'),{}).get('status','').startswith('WORKING')
        return paper.execute(order,q,healthy)
    @app.post('/api/v1/options/calculate')
    def options(request:OptionRequest): return black_scholes(**request.model_dump())
    @app.post('/api/v1/options/{rid}/research')
    def options_research(rid:str):
        from backend.intelligence.options import derive_options
        return derive_options(db,rid)
    @app.post('/api/v1/intelligence/question-answer')
    def qa(request:QARequest): return question_answer(request.question,request.answer)
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
        elif p=='alpha_vantage': result=await providers.alpha(request.kind,request.symbol,request.quarter,request.observation_date)
        elif p=='alpaca': result=await providers.alpaca_bars(request.symbol,request.start.isoformat(),request.end.isoformat())
        elif p=='x': result=await providers.social(request.query)
        elif p=='hyperliquid': result=await providers.hyperliquid()
        else: result=await providers.kalshi()
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
