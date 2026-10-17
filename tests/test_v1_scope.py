from pathlib import Path
import pytest
from sqlalchemy import inspect,select
from fastapi.testclient import TestClient
from backend.api.main import create_app
from backend.storage.database import Database,Setting
from backend.research.universe import Instrument
from test_platform import db

def test_v1_scope_and_retired_routes(db):
    client=TestClient(create_app(db,start_workers=False))
    for path in ('/api/v1/chat/x','/api/v1/auth/chatgpt/status','/api/v1/structure/schemas','/api/v1/execution/kalshi'):
        assert client.get(path).status_code==404
    assert {x['provider'] for x in client.get('/api/v1/providers').json()}=={'coinbase','hyperliquid','alpaca','sec','fred','eia','manual'}
    assert all(x['classification'] in ('working','optional','disabled','unavailable due to entitlement') for x in client.get('/api/v1/providers').json())
    with pytest.raises(ValueError):Instrument(symbol='ES',asset_class='future')
    assert not any('futures' in path for path in client.app.openapi()['paths'])

def test_v1_migration_preserves_ledger_and_cleans_old_settings(tmp_path,monkeypatch):
    from alembic.config import Config
    from alembic import command
    url='sqlite:///'+str(tmp_path/'migration.db')
    monkeypatch.setenv('DATABASE_URL',url)
    cfg=Config('alembic.ini');command.upgrade(cfg,'0004')
    d=Database(url);rid=d.put('experiment',{'negative_result':True},record_id='preserve')
    d.set_setting('ai',{'provider':'off','openai_auth_mode':'chatgpt','chat_cloud_enabled':False})
    d.set_setting('research_universe',{'instruments':[{'symbol':'AAPL','asset_class':'stock','tick_size':None,'multiplier':None,'contract_expiration':None}]})
    command.upgrade(cfg,'head')
    assert d.get(rid)['payload']=={'negative_result':True}
    assert d.setting('ai')=={'provider':'off'}
    assert d.setting('research_universe')['instruments']==[{'symbol':'AAPL','asset_class':'stock'}]
    assert {'ix_records_kind_created','ix_records_kind_symbol_created'} <= {v['name'] for v in inspect(d.engine).get_indexes('records')}
