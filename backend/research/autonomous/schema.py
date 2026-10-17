"""Versioned finite experiment language; no expressions, imports, paths or code."""
from typing import Literal, Annotated
from pydantic import Field, model_validator
from backend.schemas.contracts import Contract

FEATURES = {
 'return_1':'price','return_5':'momentum','return_20':'momentum',
 'ma20_to_ma60':'trend','rsi':'mean_reversion','bollinger_z':'mean_reversion',
 'realized_volatility':'volatility','regime_vol_ratio':'regime',
 'volume_zscore':'liquidity','liquidity_stress_proxy':'liquidity',
 'news_negative':'news','news_materiality':'news',
 'insider_purchase_count_30d':'sec','macro_UNRATE':'macro',
 'options_atm_iv':'options','crypto_funding':'crypto',
 'cross_sectional_momentum':'cross_sectional',
}
Symbol=Annotated[str, Field(pattern=r'^[A-Z0-9.-]{1,30}$')]
class Feature(Contract):
    name: str
    transform: Literal['identity','signed_log','lag_5']='identity'
    @model_validator(mode='after')
    def allowed(self):
        if self.name not in FEATURES: raise ValueError('Unsupported feature; submit an implementation proposal for review')
        return self

class Criteria(Contract):
    minimum_holdout_dates: int=Field(default=60,ge=60,le=500)
    maximum_brier: float=Field(default=.25,gt=0,le=.25)
    maximum_drawdown: float=Field(default=.10,gt=0,le=.10)
    minimum_mean_net_return: float=Field(default=0,ge=0,le=.1)
    minimum_positive_folds: Literal[3]=3
    familywise_alpha: float=Field(default=.05,gt=0,le=.05)

class ExperimentSpec(Contract):
    version: Literal['autonomous-v1']='autonomous-v1'
    hypothesis: str=Field(min_length=30,max_length=1500)
    economic_mechanism: str=Field(min_length=30,max_length=1500)
    lineage: str=Field(pattern=r'^[a-z][a-z0-9_-]{2,60}$')
    universe: list[Symbol]=Field(min_length=1,max_length=3)
    asset_class: Literal['stock','etf','crypto']
    features: list[Feature]=Field(min_length=1,max_length=6)
    model_family: Literal['ridge_logistic']='ridge_logistic'
    target: Literal['after_cost_return','relative_return']='after_cost_return'
    horizon: Literal[1,5,10]=5
    regime: Literal['all','uptrend','downtrend','range']='all'
    portfolio: Literal['equal_weight_long_cash']='equal_weight_long_cash'
    benchmark: Literal['cash_and_equal_weight']='cash_and_equal_weight'
    training_window: int=Field(default=2000,ge=400,le=3000)
    validation: Literal['purged_walk_forward_then_frozen_holdout']='purged_walk_forward_then_frozen_holdout'
    trials: list[Literal[10,100]]=Field(default_factory=lambda:[10,100],min_length=1,max_length=2)
    fee_bps: float=Field(default=5,ge=0,le=100)
    slippage_bps: float=Field(default=10,ge=1,le=100)
    spread_bps: float=Field(default=5,ge=1,le=200)
    minimum_price: float=Field(default=5,gt=0,le=1000)
    minimum_dollar_volume: float=Field(default=1000000,ge=100000,le=1e10)
    maximum_participation: float=Field(default=.001,gt=0,le=.01)
    hypothetical_notional: float=Field(default=1000,gt=0,le=100000)
    success: Criteria=Field(default_factory=Criteria)
    @model_validator(mode='after')
    def coherent(self):
        if len(set(self.universe))!=len(self.universe):raise ValueError('Duplicate symbol')
        if len(set(self.trials))!=len(self.trials):raise ValueError('Duplicate trial')
        if len({f.name for f in self.features})!=len(self.features):raise ValueError('Duplicate feature')
        if (self.target=='relative_return' or any(f.name=='cross_sectional_momentum' for f in self.features)) and len(self.universe)<2:raise ValueError('Cross-sectional research requires peers')
        return self

class Budget(Contract):
    paused: bool=True
    director: Literal['off','local','cloud']='off'
    experiments_per_day: int=Field(default=1,ge=0,le=4)
    maximum_concurrent: Literal[1]=1
    cpu_seconds: int=Field(default=30,ge=5,le=120)
    wall_seconds: int=Field(default=60,ge=10,le=180)
    memory_mb: int=Field(default=768,ge=256,le=2048)
    maximum_trials: int=Field(default=2,ge=1,le=2)
    storage_mb: int=Field(default=64,ge=4,le=256)
    review_interval_hours: int=Field(default=6,ge=1,le=24)
    maximum_registrations: int=Field(default=500,ge=1,le=2000)

class ReviewProposal(Contract):
    rationale: str=Field(min_length=30,max_length=4000)
    proposed_patch: str=Field(default='',max_length=20000)
    tests: str=Field(min_length=10,max_length=6000)
    required_data: str=Field(min_length=10,max_length=4000)
    experiment_design: str=Field(min_length=30,max_length=6000)
class ReviewDecision(Contract):
    decision: Literal['approved_for_human_review','rejected']
    reason: str=Field(min_length=10,max_length=1000)
