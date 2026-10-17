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



def test_postgres_qualification_full_path_isolated_schema():
    from uuid import uuid4
    from sqlalchemy import text
    from backend.storage.database import Base
    import test_qualification as qualification
    assert URL.endswith('traderx_acceptance')
    schema='qualification_test_'+uuid4().hex
    db=Database(URL);original=db.engine
    with original.begin() as conn:conn.execute(text('CREATE SCHEMA '+schema))
    try:
        db.engine=original.execution_options(schema_translate_map={None:schema})
        Base.metadata.create_all(db.engine)
        qualification.test_full_source_qualification_and_registry_path(db)
    finally:
        with original.begin() as conn:conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        original.dispose()

def test_postgres_market_structure_storage_isolated_schema():
    from uuid import uuid4
    from sqlalchemy import text
    from backend.storage.database import Base
    from backend.research.structure.collector import Collector
    from backend.ensemble.lifecycle import Recommendations
    from test_ensemble import evidence
    from test_personal_paper import Market
    assert URL.endswith('traderx_acceptance')
    schema='structure_test_'+uuid4().hex;db=Database(URL);original=db.engine
    with original.begin() as c:c.execute(text('CREATE SCHEMA '+schema))
    try:
        db.engine=original.execution_options(schema_translate_map={None:schema});Base.metadata.create_all(db.engine)
        collector=Collector(db,None);rid=collector.save('structure_raw',{'test':'postgres'},'');assert db.get(rid)
        db.set_setting('model_opportunities',{'rows':[evidence()],'assets':{'BTC-USD':Market().lookup('BTC-USD')}});assert len(Recommendations(db).cycle())==1;assert Recommendations(db).cycle()==[]
    finally:
        with original.begin() as c:c.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        original.dispose()

def test_postgres_alpha_registry_isolated_schema():
    from uuid import uuid4
    from sqlalchemy import text
    from backend.storage.database import Base
    import test_alpha
    assert URL.endswith('traderx_acceptance')
    schema='alpha_test_'+uuid4().hex;db=Database(URL);original=db.engine
    with original.begin() as c:c.execute(text('CREATE SCHEMA '+schema))
    try:
        db.engine=original.execution_options(schema_translate_map={None:schema});Base.metadata.create_all(db.engine)
        test_alpha.test_alpha_versioning_preserves_old_definition_and_excludes_variants(db)
    finally:
        with original.begin() as c:c.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        original.dispose()
