import asyncio
from unittest.mock import AsyncMock, Mock
import pytest
from backend.storage.database import Database,Base
from backend.workers.ingestion import ScheduledIngestion,VisibleText

@pytest.fixture
def db(tmp_path):
    d=Database('sqlite:///'+str(tmp_path/'ingestion.db'));Base.metadata.create_all(d.engine);return d

def settings():return {'enabled':True,'poll_seconds':{'alpha_vantage':21600},'equities':['AAPL','MSFT'],'sec_ciks':{'AAPL':'320193'},'max_filings_per_company':3}

async def test_unconfigured_scheduler_starts_no_network(db):
    p=Mock();p.cfg={}
    scheduler=ScheduledIngestion(db,p,Mock(),asyncio.Event(),settings())
    assert scheduler.start()==[]


async def test_sec_unchanged_source_fetched_once(db):
    p=Mock();p.cfg={'SEC_USER_AGENT':'Fixture contact@example.org'}
    p.sec=AsyncMock(return_value=[{'form':'10-Q','primaryDocument':'report.htm','accessionNumber':'0000320193-26-000001','filingDate':'2026-01-01','document_url':'https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/report.htm'}])
    p.sec_document=AsyncMock(return_value='<p>Revenue grew. Supply constraints limited capacity.</p><script>irrelevant executable content</script>')
    scheduler=ScheduledIngestion(db,p,Mock(),asyncio.Event(),settings())
    await scheduler.cycle('sec');await scheduler.cycle('sec')
    assert p.sec_document.await_count==1
    docs=db.records('document');assert len(docs)==1
    assert 'executable' not in docs[0]['payload']['text']
    assert docs[0]['symbol']=='AAPL'

async def test_ai_policy_pause_does_not_consume_inference_retries(db):
    from backend.workers.runner import Worker
    from backend.storage.database import Job
    from backend.llm.providers import TextTask
    from sqlalchemy.orm import Session
    llm=Mock();worker=Worker(db,Mock(),llm,Mock())
    async def paused(tasks):
        worker.stop.set()
        return [{'status':'DISABLED'}]
    llm.analyze_many=paused
    with db.transaction() as s:s.add(Job(id='fixture-paused',kind='text',payload=TextTask(task='news',text='Revenue rose',source_reference='fixture').model_dump()))
    await worker.run_jobs()
    with Session(db.engine) as s:
        job=s.get(Job,'fixture-paused')
        assert job.state=='queued' and job.attempts==0

async def test_completed_analysis_retains_document_asset(db):
    from backend.workers.runner import Worker
    from backend.intelligence.ingest import store_document
    from sqlalchemy.orm import Session
    from backend.storage.database import Job
    stored=store_document(db,text='Revenue rose.',kind='news',title='Fixture',source_reference='fixture',symbol='TEST')
    llm=Mock();worker=Worker(db,Mock(),llm,Mock())
    async def completed(tasks):
        worker.stop.set()
        return [{'status':'COMPLETE','provider':'local','model':'fixture-model','result':{'summary':'Revenue rose.'}}]
    llm.analyze_many=completed
    await worker.run_jobs()
    record=db.records('analysis','TEST')[0]
    assert record['payload']['document_id']==stored['id'] and record['payload']['provider']=='local'
    with Session(db.engine) as s:assert s.get(Job,stored['id']).state=='complete'

async def test_missing_quote_does_not_skip_stock_history(db):
    from backend.providers.market import ProviderError
    p=Mock();p.cfg={'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture'}
    p.alpaca_quote=AsyncMock(side_effect=ProviderError('MISSING_DATA','No two-sided IEX quote'))
    p.alpaca_bars=AsyncMock(return_value=[])
    cfg={**settings(),'lookback_days':730}
    scheduler=ScheduledIngestion(db,p,Mock(),asyncio.Event(),cfg)
    await scheduler.cycle('alpaca')
    assert p.alpaca_bars.await_count==2
    assert db.setting('provider_alpaca')['quote_status']=='MISSING_DATA'
    assert db.setting('provider_alpaca')['status']=='WORKING_READ_ONLY'
