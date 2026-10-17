"""Capped deterministic position sizing. Never unconstrained Kelly."""
from typing import Literal
from pydantic import Field
from backend.schemas.contracts import Contract

class SizingRequest(Contract):
    method:Literal['fixed_fraction','volatility_target','risk_budget','fractional_kelly']='fixed_fraction'
    equity:float=Field(gt=0);price:float=Field(gt=0);available_cash:float=Field(ge=0)
    fraction:float=Field(default=.02,ge=0,le=.1)
    annual_volatility:float|None=Field(default=None,gt=0)
    target_volatility:float=Field(default=.10,gt=0,le=.30)
    downside_fraction:float|None=Field(default=None,gt=0,le=1)
    risk_budget_fraction:float=Field(default=.002,gt=0,le=.01)
    probability_win:float|None=Field(default=None,ge=0,le=1)
    win_loss_ratio:float|None=Field(default=None,gt=0)
    kelly_fraction:float=Field(default=.10,ge=0,le=.25)
    whole_units:bool=False

def position_size(request,limits):
    p=request
    if p.method=='fixed_fraction':fraction=p.fraction
    elif p.method=='volatility_target':
        if p.annual_volatility is None:raise ValueError('A measured annual volatility is required')
        fraction=p.target_volatility/p.annual_volatility
    elif p.method=='risk_budget':
        if p.downside_fraction is None:raise ValueError('A downside assumption is required')
        fraction=p.risk_budget_fraction/p.downside_fraction
    else:
        if p.probability_win is None or p.win_loss_ratio is None:raise ValueError('Calibrated probability and payoff ratio are required')
        fraction=max(0,p.probability_win-(1-p.probability_win)/p.win_loss_ratio)*p.kelly_fraction
    capped=min(fraction,limits['max_position_fraction'],limits['max_gross_fraction'])
    notional=min(p.equity*capped,p.available_cash/(1+(limits['fee_bps']+limits['slippage_bps'])/10000))
    quantity=notional/p.price
    if p.whole_units:quantity=int(quantity)
    return {'method':p.method,'uncapped_fraction':fraction,'capped_fraction':capped,'quantity':quantity,'notional':quantity*p.price,
            'status':'SIZING_ESTIMATE_ONLY','warning':'Existing exposures, liquidity and fresh quotes still require deterministic risk approval.'}
