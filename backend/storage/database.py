"""Append-only research records, durable cache/usage, and transactional paper state."""
from contextlib import contextmanager
from datetime import datetime
from sqlalchemy import create_engine, Index, String, Float, Integer, Text, JSON, select, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy.pool import StaticPool
from backend.core.config import database_url
from backend.schemas.contracts import now, uid

class Base(DeclarativeBase): pass

class Record(Base):
    __tablename__ = 'records'
    __table_args__ = (Index('ix_records_kind_created','kind','created_at'), Index('ix_records_kind_available','kind','available_at'), Index('ix_records_kind_symbol_created','kind','symbol','created_at'))
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(128), default='', index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=lambda: now().isoformat(), index=True)
    available_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON)

class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

class LLMRun(Base):
    __tablename__ = 'llm_runs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    output_hash: Mapped[str] = mapped_column(String(64), default='')
    provider: Mapped[str] = mapped_column(String(20), index=True)
    model: Mapped[str] = mapped_column(String(120))
    module: Mapped[str] = mapped_column(String(40), index=True)
    prompt_version: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[str] = mapped_column(String(40), default=lambda: now().isoformat(), index=True)
    status: Mapped[str] = mapped_column(String(30), default='reserved')
    call_count: Mapped[int] = mapped_column(Integer, default=1)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0)
    reserved_cost: Mapped[float] = mapped_column(Float, default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[str] = mapped_column(String(40), default=lambda: now().isoformat())
    payload: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String(100), default='')

class Database:
    def __init__(self, url=None):
        url = url or database_url()
        kwargs = {'connect_args': {'check_same_thread': False, 'timeout': 30}} if url.startswith('sqlite') else {}
        if url in ('sqlite://', 'sqlite:///:memory:'): kwargs['poolclass'] = StaticPool
        self.engine = create_engine(url, **kwargs)
        if url.startswith('sqlite'):
            @event.listens_for(self.engine, 'connect')
            def pragmas(connection, _):
                connection.execute('PRAGMA journal_mode=WAL')
                connection.execute('PRAGMA foreign_keys=ON')

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as s:
            # Serialize writes and cost reservations across processes, not just threads.
            if self.engine.dialect.name == 'sqlite': s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            else: s.connection().exec_driver_sql('SELECT pg_advisory_xact_lock(735291)')
            try:
                yield s
                s.commit()
            except BaseException:
                s.rollback()
                raise

    def setting(self, key, default=None):
        with Session(self.engine) as s:
            v = s.get(Setting, key)
            return v.value if v else default

    def set_setting(self, key, value):
        with self.transaction() as s: s.merge(Setting(key=key,value=value))

    def put(self, kind, payload, symbol='', record_id=None, available_at=None):
        if hasattr(payload,'model_dump'): payload=payload.model_dump(mode='json')
        rid = record_id or payload.get('id') or uid()
        with self.transaction() as s:
            if not s.get(Record,rid):
                s.add(Record(id=rid,kind=kind,symbol=symbol,payload=payload,available_at=available_at or now().isoformat()))
        return rid

    def records(self, kind=None, symbol=None, limit=5000, as_of=None):
        stmt=select(Record)
        if kind: stmt=stmt.where(Record.kind==kind)
        if symbol: stmt=stmt.where(Record.symbol==symbol)
        if as_of: stmt=stmt.where(Record.available_at<=as_of.isoformat())
        with Session(self.engine) as s:
            return [dict(id=r.id,kind=r.kind,symbol=r.symbol,created_at=r.created_at,available_at=r.available_at,payload=r.payload) for r in s.scalars(stmt.order_by(Record.created_at.desc()).limit(limit))]

    def get(self, rid):
        with Session(self.engine) as s:
            r=s.get(Record,rid)
            return None if not r else {'id':r.id,'kind':r.kind,'payload':r.payload}
