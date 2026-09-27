"""Opt-in integration checks against a migrated disposable acceptance database."""
import os
import pytest
from backend.storage.database import Database
from backend.providers.market import MarketProviders
from backend.intelligence.ingest import store_document
from backend.llm.service import LLMService
from backend.llm.providers import TextTask
from backend.core.config import AISettings
import httpx
URL=os.environ.get('TRADERX_TEST_POSTGRES_URL','')
pytestmark=pytest.mark.skipif(not URL,reason='Set TRADERX_TEST_POSTGRES_URL to the dedicated acceptance database')

async def test_postgres_transactions_provenance_and_ai_off():
    assert URL.endswith('traderx_acceptance')
    db=Database(URL)
    providers=MarketProviders(db,{},httpx.MockTransport(lambda req:httpx.Response(200,json={'price':'100','bid':'99.9','ask':'100.1','volume':'2000','time':'2026-09-25T12:00:00Z'})))
    await providers.coinbase_quote('TEST-PG')
    assert db.records('quote','TEST-PG')[0]['payload']['price']==100
    stored=store_document(db,text='Nuclear supply constraints persist.',kind='theme',title='Integration fixture',source_reference='fixture://postgres',symbol='TEST-PG')
    assert db.get(stored['id'])['kind']=='document'
    db.set_setting('ai',AISettings().model_dump())
    assert (await LLMService(db,{}).analyze(TextTask(task='news',text='Revenue growth',source_reference='fixture')))['status']=='DISABLED'
