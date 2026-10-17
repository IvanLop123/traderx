"""Qualification criteria are frozen in each registration, never edited in place."""
from pydantic import Field
from backend.schemas.contracts import Contract

class QualificationCriteria(Contract):
    version:str='qualification-v1'
    minimum_holdout_clusters:int=Field(default=40,ge=40)
    minimum_forward_clusters:int=Field(default=60,ge=60)
    minimum_portfolio_blocks:int=Field(default=60,ge=60)
    portfolio_block_days:int=Field(default=5,ge=5)
    minimum_completed_trades:int=Field(default=30,ge=30)
    minimum_calibration_clusters:int=Field(default=30,ge=30)
    minimum_regime_clusters:int=Field(default=15,ge=15)
    minimum_regimes:int=Field(default=2,ge=2)
    maximum_calibration_error:float=Field(default=.1,gt=0,le=.1)
    maximum_drawdown:float=Field(default=.1,gt=0,le=.1)
    minimum_regime_mean_return:float=Field(default=-.005,ge=-.005)
    familywise_alpha:float=Field(default=.05,gt=0,le=.05)
    maximum_mark_age_minutes:int=Field(default=60,ge=1,le=60)
    minimum_training_release_days:int=Field(default=90,ge=90)
    thresholds:list[int]=[50,60,65,70,80]
    benchmark_arms:list[str]=['cash','buy_hold','momentum','mean_reversion','equal_weight','incumbent']
    terminal_review:str='once after all predefined evidence minima; no favorable repeated retesting'
