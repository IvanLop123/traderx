"""Versioned hard controls. No provider credentials or execution switches."""
import json
from pathlib import Path
from typing import Literal
from pydantic import Field
from backend.schemas.contracts import Contract
from backend.research.features import stable_hash
ROOT=Path(__file__).resolve().parents[2]
class PortfolioPolicy(Contract):
    enabled:bool=True
    initial_cash:float=Field(default=10000,ge=100,le=1e7)
    minimum_score:float=Field(default=65,ge=50,le=100)
    minimum_probability:float=Field(default=.55,ge=.5,le=.99)
    minimum_independent_groups:int=Field(default=2,ge=2,le=10)
    maximum_position:float=Field(default=.1,gt=0,le=.2)
    maximum_sector:float=Field(default=.3,gt=0,le=.4)
    maximum_asset_class:float=Field(default=.6,gt=0,le=.8)
    maximum_strategy_group:float=Field(default=.3,gt=0,le=.4)
    maximum_correlated_cluster:float=Field(default=.25,gt=0,le=.35)
    maximum_gross_exposure:float=Field(default=.8,gt=0,le=.9)
    maximum_positions:int=Field(default=8,ge=1,le=20)
    maximum_drawdown:float=Field(default=.1,gt=0,le=.2)
    annual_volatility_target:float=Field(default=.1,gt=0,le=.2)
    maximum_adv_fraction:float=Field(default=.0001,gt=0,le=.0001)
    correlation_threshold:float=Field(default=.7,ge=.5,le=.9)
    minimum_correlation_observations:int=Field(default=60,ge=60)
    minimum_validation_dates:int=Field(default=40,ge=40)
    minimum_forward_dates:int=Field(default=60,ge=60)
    minimum_portfolio_dates:int=Field(default=60,ge=60)
    minimum_conditional_dates:int=Field(default=30,ge=30)
    shrinkage_prior_dates:int=Field(default=60,ge=60)
    maximum_calibration_error:float=Field(default=.1,gt=0,le=.1)
    maximum_feature_z:float=Field(default=8,gt=0,le=8)
    maximum_data_age_days:int=Field(default=4,ge=1,le=4)
    sizing:Literal['volatility_targeted','confidence_capped']='volatility_targeted'
    exit_policy:Literal['fixed_horizon','signal_reversal','score_decay','risk_stop','volatility_stop','profit_target','trailing']='fixed_horizon'
    horizon_sessions:int=Field(default=5,ge=1,le=20)
    risk_stop:float=Field(default=.05,gt=0,le=.1)
    volatility_stop_multiple:float=Field(default=2,ge=1,le=4)
    profit_target:float=Field(default=.1,gt=0,le=.25)
    trailing_fraction:float=Field(default=.05,gt=0,le=.1)
    score_decay_threshold:float=Field(default=40,ge=0,le=60)
    maximum_holding_sessions:int=Field(default=20,ge=5,le=60)
    maximum_quote_requests_per_cycle:int=Field(default=12,ge=1,le=25)

def policy(db=None):
    return PortfolioPolicy(**((db.setting('model_portfolio_policy') if db else None) or json.loads((ROOT/'config/model_portfolio.json').read_text())))
def policy_hash(p):return stable_hash(p.model_dump())
# Conservative grouping: related price transformations never count as independent votes.
GROUPS={'momentum':'price_trend','trend_following':'price_trend','breakout':'price_trend','relative_strength':'price_trend','cross_sectional_ranking':'price_trend','mean_reversion':'price_reversion','pairs_relative_value':'price_reversion','volatility':'price_volatility','macro_regime':'macro','insider_event':'insider','crypto_funding':'funding'}
