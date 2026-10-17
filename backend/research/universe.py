"""Instrument and membership contracts independent of any execution venue."""
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol
import json
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

ROOT=Path(__file__).resolve().parents[2]
class Instrument(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    symbol:str=Field(pattern=r'^[A-Za-z0-9./_-]{1,40}$')
    asset_class:Literal['stock','etf','crypto']
    instrument_id:str|None=None
    exchange:str|None=None
    currency:str='USD'
    membership_known_at:AwareDatetime|None=None
    active:bool=True
    inactive_known_at:AwareDatetime|None=None
    sector:str|None=None
    name:str|None=None
    market_cap:float|None=Field(default=None,gt=0)
    market_cap_known_at:AwareDatetime|None=None
    halted:bool=False

class Eligibility(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    minimum_price:float=Field(default=5,gt=0)
    minimum_daily_dollar_volume:float=Field(default=1_000_000,ge=0)
    minimum_daily_volume:float=Field(default=10_000,ge=0)
    maximum_spread_bps:float=Field(default=50,gt=0)
    minimum_history:int=Field(default=252,ge=65)
    minimum_coverage:float=Field(default=.95,gt=0,le=1)
    liquidity_window:int=Field(default=20,ge=5,le=252)

class Universe(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    name:str='Diversified research watchlist'
    instruments:list[Instrument]=Field(min_length=1,max_length=5000)
    filters:Eligibility=Field(default_factory=Eligibility)
    filters_by_asset_class:dict[Literal['stock','etf','crypto'],Eligibility]=Field(default_factory=lambda:{'crypto':Eligibility(minimum_daily_volume=100)})
    def filters_for(self,instrument):return self.filters_by_asset_class.get(instrument.asset_class,self.filters)
    backfill_batch_size:int=Field(default=24,ge=1,le=50)
    maximum_training_assets:int=Field(default=24,ge=1,le=500)
    policy:Literal['retrospective_watchlist','archived_membership']='retrospective_watchlist'
    @model_validator(mode='after')
    def unique(self):
        if len({x.symbol for x in self.instruments})!=len(self.instruments):raise ValueError('Duplicate universe symbols')
        if self.policy=='archived_membership' and any(x.membership_known_at is None for x in self.instruments):raise ValueError('Archived membership requires known-at dates')
        return self

class HistoricalProvider(Protocol):
    """Future providers normalize into the same instrument/series contracts."""
    async def history(self,instrument:Instrument,start:datetime,end:datetime,adjustment:str): ...
    def capabilities(self)->dict: ...

def load_universe(db=None):
    saved=db.setting('research_universe') if db else None
    data=saved or json.loads((ROOT/'config/research_universe.json').read_text())
    return Universe.model_validate(data)

def eligible_at(instrument,bars,at,filters,*,spread_bps=None,expected_sessions=None,strict_membership=False):
    """Trailing RAW prices/volume only. Missing spread never implies zero spread."""
    t=pd.Timestamp(at);reasons=[]
    if t.tzinfo is None:raise ValueError('Eligibility time must include timezone')
    if instrument.halted:reasons.append('Security halted')
    if strict_membership and (instrument.membership_known_at is None or pd.Timestamp(instrument.membership_known_at)>t):reasons.append('Historical membership unknown at decision time')
    if not instrument.active and (instrument.inactive_known_at is None or pd.Timestamp(instrument.inactive_known_at)<=t):reasons.append('Inactive security')
    rows=[b for b in bars if pd.Timestamp(b['available_at'])<=t]
    rows=sorted({b['timestamp']:b for b in rows}.values(),key=lambda b:b['timestamp'])
    if any(b.get('adjustment','raw')!='raw' for b in rows):raise ValueError('Eligibility requires raw prices and volume')
    tail=rows[-filters.liquidity_window:]
    if len(rows)<filters.minimum_history:reasons.append('Insufficient history')
    price=float(rows[-1]['close']) if rows else None
    volume=float(np.mean([b['volume'] for b in tail])) if tail else None
    dollars=float(np.mean([b['close']*b['volume'] for b in tail])) if tail else None
    if price is None or price<filters.minimum_price:reasons.append('Price below minimum')
    if volume is None or volume<filters.minimum_daily_volume:reasons.append('Volume below minimum')
    if dollars is None or dollars<filters.minimum_daily_dollar_volume:reasons.append('Dollar liquidity below minimum')
    observed={pd.Timestamp(b['timestamp']).date() for b in rows}
    expected={pd.Timestamp(d).date() for d in (expected_sessions or []) if pd.Timestamp(d).date()<=t.date() and (not rows or pd.Timestamp(d).date()>=pd.Timestamp(rows[0]['timestamp']).date())}
    coverage=len(observed&expected)/len(expected) if expected else None
    if coverage is None:reasons.append('Session coverage unverified')
    elif coverage<filters.minimum_coverage:reasons.append('Excessive missing observations')
    execution_reasons=list(reasons)
    if spread_bps is None:execution_reasons.append('Spread unavailable')
    elif not np.isfinite(spread_bps) or spread_bps<0 or spread_bps>filters.maximum_spread_bps:execution_reasons.append('Spread outside limits')
    return {'symbol':instrument.symbol,'eligible':not reasons,'executable':not execution_reasons,'reasons':reasons,'execution_reasons':execution_reasons,'bars':len(rows),'price':price,'mean_volume':volume,'mean_dollar_volume':dollars,'coverage':coverage,'spread_bps':spread_bps,'liquidity_basis':'Provider feed volume; IEX is not consolidated US volume'}
