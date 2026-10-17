"""Deterministic exposure limits; forecasts cannot override cash, concentration or drawdown."""
from collections import defaultdict
import math
import numpy as np
import pandas as pd

def correlation_context(returns,minimum=60):
    if returns is None or returns.empty:return {'correlations':{},'observations':{},'method':'unavailable; assume full correlation for risk'}
    sample=returns.tail(90).replace([np.inf,-np.inf],np.nan);corr=sample.corr(min_periods=minimum);n=sample.notna().astype(int).T@sample.notna().astype(int)
    return {'correlations':{s:{t:float(v) for t,v in row.items() if pd.notna(v)} for s,row in corr.iterrows()},'observations':{s:{t:int(v) for t,v in row.items()} for s,row in n.iterrows()},'method':'90-date rolling Pearson; at least 60 paired dates; missing correlations treated as 1 for hard risk'}

def exposure(view,assets,links=None):
    equity=max(view['equity'],1e-9);positions=[];totals={k:defaultdict(float) for k in ['asset','sector','asset_class','strategy_group']};links=links or {}
    for p in view['positions']:
        a=assets.get(p['symbol'],{});w=max(p['market_value'],p['quantity']*p['average_cost'])/equity
        positions.append({'symbol':p['symbol'],'weight':w,'sector':a.get('sector') or 'unknown','asset_class':a.get('asset_class','unknown'),'groups':links.get(p['symbol'],['unknown'])})
    # Pending BUY notional consumes every limit before its fill, with no credit for pending sells.
    for o in view['orders']:
        if o['side']=='buy' and o['status'] in ('OPEN','PARTIALLY_FILLED'):
            a=assets.get(o['symbol'],{});positions.append({'symbol':o['symbol'],'weight':(o['quantity']-o['filled_quantity'])*o['reserve_price']/equity,'sector':a.get('sector') or 'unknown','asset_class':a.get('asset_class','unknown'),'groups':links.get(o['symbol'],['unknown'])})
    for p in positions:
        for name,key in [('asset','symbol'),('sector','sector'),('asset_class','asset_class')]:totals[name][p[key]]+=p['weight']
        for g in p['groups']:totals['strategy_group'][g]+=p['weight'] # conservative full attribution to each contributing group
    return {'by_'+k:dict(v) for k,v in totals.items()}|{'positions':positions,'gross':sum(p['weight'] for p in positions),'asset_hhi':sum(v*v for v in totals['asset'].values()),'position_count':len({p['symbol'] for p in positions})}

def size(candidate,view,assets,correlations,p,high_water,links=None,allow_existing=False,require_qualified=True):
    reasons=[];equity=view['equity'];e=exposure(view,assets,links);symbol=candidate['symbol'];a=assets.get(symbol,{})
    drawdown=max(0,1-equity/max(high_water,equity,1));groups=candidate.get('groups') or ['unknown'];vol=candidate.get('daily_volatility');uncertainty=candidate.get('uncertainty');prob=candidate.get('probability');edge=candidate.get('expected_edge')
    if drawdown>=p.maximum_drawdown:reasons.append('Portfolio drawdown hard stop')
    if require_qualified and not candidate.get('trade_eligible'):reasons.append('Strategy/evidence eligibility not met')
    if not require_qualified and candidate.get('ensemble',{}).get('action')!='BUY':reasons.append('Experimental ensemble did not recommend BUY')
    if candidate.get('score',0)<p.minimum_score:reasons.append('Opportunity below threshold')
    if prob is None or prob<p.minimum_probability:reasons.append('Probability below threshold')
    if len(groups)<p.minimum_independent_groups:reasons.append('Insufficient independent signal groups')
    if not all(v is not None and math.isfinite(v) and v>0 for v in [vol,uncertainty,edge]):reasons.append('Missing or nonpositive finite risk inputs')
    if not a.get('eligibility',{}).get('eligible',False):reasons.append('Universe eligibility unavailable')
    if e['position_count']>=p.maximum_positions and symbol not in e['by_asset']:reasons.append('Maximum positions')
    if symbol in e['by_asset'] and not allow_existing:reasons.append('No pyramiding; existing or pending exposure')
    if reasons:return {'notional':0.,'reasons':reasons,'drawdown':drawdown,'exposure':e,'limits':{},'sizing':p.sizing}
    corr=correlations.get('correlations',{}).get(symbol,{})
    redundant=sum(pos['weight'] for pos in e['positions'] if abs(corr.get(pos['symbol'],1.))>=p.correlation_threshold)
    confidence=max(0,min(1,(prob-.5)*2))*max(0,min(1,edge/(uncertainty+1e-12)))
    annual=vol*math.sqrt(365 if a.get('asset_class')=='crypto' else 252)
    proposed=p.maximum_position*confidence if p.sizing=='confidence_capped' else min(p.maximum_position,p.annual_volatility_target/max(annual,.01)/max(1,p.maximum_positions))*math.sqrt(confidence)
    limits={'proposed':equity*proposed,'cash':view['available_cash'],'position':equity*max(0,p.maximum_position-e['by_asset'].get(symbol,0)),'gross':equity*max(0,p.maximum_gross_exposure-e['gross']),'sector':equity*max(0,p.maximum_sector-e['by_sector'].get(a.get('sector') or 'unknown',0)),'asset_class':equity*max(0,p.maximum_asset_class-e['by_asset_class'].get(a.get('asset_class','unknown'),0)),'strategy_group':equity*min(max(0,p.maximum_strategy_group-e['by_strategy_group'].get(g,0)) for g in groups),'correlated_cluster':equity*max(0,p.maximum_correlated_cluster-redundant),'liquidity':(a.get('eligibility',{}).get('mean_dollar_volume') or 0)*p.maximum_adv_fraction}
    # Correlation also reduces size below the hard cluster ceiling; unknown pairs receive full penalty.
    limits['correlation_adjusted']=limits['proposed']/(1+4*redundant)
    notional=max(0,min(limits.values()));binding=min(limits,key=limits.get)
    return {'notional':notional,'reasons':[f'Bounded by {binding}; confidence and uncertainty discounted'],'drawdown':drawdown,'exposure':e,'limits':limits,'sizing':p.sizing,'correlated_exposure':redundant,'confidence_factor':confidence}

def exit_reason(position,context,p,session_count):
    """Triggers request a later quote fill, never a guaranteed stop price."""
    price=context.get('bid');cost=position['average_cost']
    if not price or price<=0:return None
    gain=price/cost-1;vol=context.get('daily_volatility') or 0;high=max(context.get('high_bid',price),price)
    if context.get('drawdown',0)>=p.maximum_drawdown:return 'portfolio_drawdown'
    if context.get('data_unreliable'):return 'required_data_unreliable'
    if session_count>=p.maximum_holding_sessions:return 'maximum_holding_sessions'
    if p.exit_policy=='fixed_horizon' and session_count>=p.horizon_sessions:return 'fixed_horizon'
    if p.exit_policy=='signal_reversal' and context.get('expected_edge') is not None and context['expected_edge']<=0:return 'signal_reversal'
    if p.exit_policy=='score_decay' and context.get('score',100)<p.score_decay_threshold:return 'score_decay'
    if p.exit_policy=='risk_stop' and gain<=-p.risk_stop:return 'risk_stop'
    if p.exit_policy=='volatility_stop' and vol>0 and gain<=-p.volatility_stop_multiple*vol:return 'volatility_stop'
    if p.exit_policy=='profit_target' and gain>=p.profit_target:return 'profit_target'
    if p.exit_policy=='trailing' and price/high-1<=-p.trailing_fraction:return 'trailing'
    return None
