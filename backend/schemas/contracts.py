from datetime import datetime, timezone
from typing import Literal, Any
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class AssetIdentifier(Contract):
    symbol: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:/-]+$')
    asset_class: Literal['stock','etf','option','crypto','perpetual','prediction'] = 'crypto'
    exchange: str | None = None
    cik: str | None = None
    figi: str | None = None
    occ: str | None = None
    wallet: str | None = None
    market_id: str | None = None

class RawRecord(Contract):
    id: str = Field(default_factory=uid)
    provider: str
    source_reference: str
    received_at: AwareDatetime = Field(default_factory=now)
    payload: dict | list

class Event(Contract):
    id: str = Field(default_factory=uid)
    source: str
    provider: str
    event_type: str
    assets: list[AssetIdentifier] = Field(default_factory=list)
    event_at: AwareDatetime
    published_at: AwareDatetime
    first_observed_at: AwareDatetime = Field(default_factory=now)
    ingested_at: AwareDatetime = Field(default_factory=now)
    processed_at: AwareDatetime = Field(default_factory=now)
    payload: dict = Field(default_factory=dict)
    text: str | None = None
    source_reference: str
    quality: dict = Field(default_factory=dict)
    schema_version: int = 1

    def available_at(self):
        return max(self.published_at, self.first_observed_at, self.ingested_at, self.processed_at)

class Evidence(Contract):
    id: str = Field(default_factory=uid)
    event_id: str
    source_reference: str
    quote: str | None = None
    confidence: float = Field(default=1, ge=0, le=1)

class Feature(Contract):
    id: str = Field(default_factory=uid)
    asset: AssetIdentifier
    name: str
    value: float | str | None
    as_of: AwareDatetime
    available_at: AwareDatetime
    evidence_ids: list[str]
    model: str = 'deterministic-v1'
    provider: str = 'python'
    expires_at: AwareDatetime | None = None
    quality: dict = Field(default_factory=dict)

class Signal(Contract):
    id: str = Field(default_factory=uid)
    asset: AssetIdentifier
    type: str
    value: float
    direction: Literal['bullish','bearish','neutral','volatility','informational']
    confidence: float = Field(ge=0, le=1)
    horizon: str
    generated_at: AwareDatetime = Field(default_factory=now)
    as_of: AwareDatetime
    evidence_ids: list[str]
    feature_ids: list[str] = Field(default_factory=list)
    model: str
    freshness_seconds: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)

class Prediction(Contract):
    id: str = Field(default_factory=uid)
    asset: AssetIdentifier
    expected_return: float
    probability_positive: float = Field(ge=0, le=1)
    expected_volatility: float = Field(ge=0)
    downside: float
    uncertainty: float = Field(ge=0)
    horizon: str
    model: str
    as_of: AwareDatetime
    calibration: dict
    evidence_ids: list[str]
    contributions: dict[str,float] = Field(default_factory=dict)

class TradeCandidate(Contract):
    id: str = Field(default_factory=uid)
    asset: AssetIdentifier
    prediction_id: str
    direction: Literal['buy','sell']
    horizon: str
    entry_price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    expected_edge: float
    expected_costs: float = Field(ge=0)
    expected_downside: float
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    created_at: AwareDatetime = Field(default_factory=now)
    expires_at: AwareDatetime
    liquidity: dict

class RiskAssessment(Contract):
    id: str = Field(default_factory=uid)
    candidate_id: str
    approved: bool
    reasons: list[str]
    assessed_at: AwareDatetime = Field(default_factory=now)
    limits: dict

class ApprovedOrder(Contract):
    id: str = Field(default_factory=uid)
    candidate_id: str
    assessment_id: str
    asset: AssetIdentifier
    side: Literal['buy','sell']
    quantity: float = Field(gt=0)
    limit_price: float = Field(gt=0)
    expires_at: AwareDatetime
    venue: Literal['internal_paper','alpaca_paper'] = 'internal_paper'

class RejectedOrder(Contract):
    candidate_id: str
    assessment_id: str
    reasons: list[str]

class ExecutionReport(Contract):
    id: str = Field(default_factory=uid)
    order_id: str
    status: Literal['filled','rejected']
    quantity: float = Field(ge=0)
    price: float = Field(gt=0)
    fee: float = Field(ge=0)
    timestamp: AwareDatetime = Field(default_factory=now)
    venue: Literal['internal_paper'] = 'internal_paper'

class Bar(Contract):
    symbol: str
    provider: str
    timestamp: AwareDatetime
    available_at: AwareDatetime
    observed_at: AwareDatetime = Field(default_factory=now)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    interval_seconds: int = Field(default=86400, gt=0)
    @model_validator(mode='after')
    def prices(self):
        if self.high < max(self.open,self.close,self.low) or self.low > min(self.open,self.close):
            raise ValueError('Inconsistent OHLC prices')
        return self

class FairProbabilityEstimate(Contract):
    probability: float = Field(ge=0,le=1)
    lower: float = Field(ge=0,le=1)
    upper: float = Field(ge=0,le=1)
    evidence_ids: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    timestamp: AwareDatetime = Field(default_factory=now)
    calibration: dict
    @model_validator(mode='after')
    def interval(self):
        if not self.lower<=self.probability<=self.upper: raise ValueError('Probability must lie within its interval')
        return self

class OpportunityEstimate(Contract):
    instrument: AssetIdentifier
    market_value: float
    fair_value: float
    raw_edge: float
    uncertainty: float = Field(ge=0)
    estimated_costs: float = Field(ge=0)
    estimated_net_edge: float
    liquidity: float = Field(ge=0)
    expiration: AwareDatetime
    evidence_ids: list[str]
