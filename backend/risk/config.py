"""Validated risk configuration; omitted new limits receive conservative defaults."""
import json
from pydantic import Field
from backend.schemas.contracts import Contract
from scripts.provider_common import ROOT

class RiskLimits(Contract):
    initial_cash:float=Field(default=100000,gt=0)
    max_position_fraction:float=Field(default=.10,gt=0,le=1)
    max_gross_fraction:float=Field(default=.50,gt=0,le=1)
    max_net_fraction:float=Field(default=.50,gt=0,le=1)
    max_asset_class_fraction:float=Field(default=.35,gt=0,le=1)
    max_sector_fraction:float=Field(default=.25,gt=0,le=1)
    max_daily_loss_fraction:float=Field(default=.02,gt=0,le=.5)
    max_weekly_loss_fraction:float=Field(default=.05,gt=0,le=.5)
    max_drawdown_fraction:float=Field(default=.10,gt=0,le=.9)
    max_spread_bps:float=Field(default=50,ge=0,le=10000)
    max_quote_age_seconds:int=Field(default=120,gt=0,le=3600)
    max_candidate_age_seconds:int=Field(default=300,gt=0,le=86400)
    max_participation:float=Field(default=.01,gt=0,le=.1)
    fee_bps:float=Field(default=5,ge=0,le=1000)
    slippage_bps:float=Field(default=5,ge=0,le=1000)
    max_portfolio_annual_volatility:float=Field(default=.25,gt=0,le=2)
    max_correlated_group_fraction:float=Field(default=.35,gt=0,le=1)
    correlation_threshold:float=Field(default=.8,ge=.5,le=1)
    correlation_min_observations:int=Field(default=60,ge=20,le=500)
    require_covariance_for_entry:bool=False

def load_limits():return RiskLimits.model_validate(json.loads((ROOT/'config/risk.json').read_text())).model_dump()
