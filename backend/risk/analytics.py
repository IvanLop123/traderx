"""Local portfolio exposures, synchronized historical covariance and stress scenarios."""
import json
import math
import numpy as np
import pandas as pd
from scripts.provider_common import ROOT
from backend.schemas.contracts import now

SECTOR_PATH=ROOT/'config/asset_sectors.json'

def sectors():return json.loads(SECTOR_PATH.read_text()) if SECTOR_PATH.exists() else {}

def portfolio_risk(db,state,limits,candidate=None):
    equity=float(state['equity']);positions=json.loads(json.dumps(state['positions']));sector_map=sectors()
    if equity<=0 or not math.isfinite(equity):raise ValueError('Positive finite portfolio equity required')
    if candidate:
        p=positions.setdefault(candidate.asset.symbol,{'quantity':0,'market_price':candidate.entry_price,'asset_class':candidate.asset.asset_class})
        p['quantity']+=candidate.quantity*(1 if candidate.direction=='buy' else -1);p['market_price']=candidate.entry_price
    weights={s:p['quantity']*p['market_price']/equity for s,p in positions.items() if p['quantity']}
    classes={};by_sector={};returns={};missing=[]
    for symbol,weight in weights.items():
        p=positions[symbol];asset_class=p['asset_class'];classes[asset_class]=classes.get(asset_class,0)+abs(weight)
        sector=sector_map.get(symbol,'UNCLASSIFIED') if asset_class in ('stock','etf') else asset_class.upper()
        by_sector[sector]=by_sector.get(sector,0)+abs(weight)
        rows=[r['payload'] for r in db.records('bar',symbol,limit=1000) if r['payload'].get('interval_seconds',86400)==86400]
        if rows:
            frame=pd.DataFrame(rows);frame['time']=pd.to_datetime(frame.timestamp,utc=True)
            frame=frame[pd.to_datetime(frame.available_at,utc=True)<=pd.Timestamp(now())].sort_values('time').drop_duplicates('time',keep='last')
            closes=frame.set_index('time').close.astype(float)
            closes=closes.where(np.isfinite(closes)&(closes>0))
            series=closes.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan)
            series.index=series.index.normalize();returns[symbol]=series[~series.index.duplicated(keep='last')]
        else:missing.append(symbol)
    aligned=pd.DataFrame(returns).dropna() if returns else pd.DataFrame()
    available=len(aligned)>=limits['correlation_min_observations'] and not missing
    corr=aligned.corr() if available else None
    groups=[]
    if available:
        unseen=set(weights)
        while unseen:
            group={unseen.pop()};expanded=True
            while expanded:
                neighbors={s for s in unseen if any(pd.notna(corr.loc[s,g]) and corr.loc[s,g]>=limits['correlation_threshold'] for g in group)}
                expanded=bool(neighbors);group|=neighbors;unseen-=neighbors
            groups.append({'symbols':sorted(group),'gross_fraction':sum(abs(weights[s]) for s in group)})
    annual=365 if weights and all(positions[s]['asset_class'] in ('crypto','perpetual') for s in weights) else 252
    volatility=None;var=None;es=None
    if available:
        w=np.array([weights[s] for s in aligned.columns]);series=aligned.to_numpy()@w
        volatility=float(np.std(series,ddof=1)*np.sqrt(annual));threshold=float(np.quantile(series,.05))
        var=max(0,-threshold)*equity;es=max(0,-float(series[series<=threshold].mean()))*equity
    elif not weights:volatility=var=es=0
    scenarios={'equity_selloff':{'stock':-.20,'etf':-.20,'crypto':-.30,'perpetual':-.30},'crypto_shock':{'crypto':-.50,'perpetual':-.50,'stock':-.05,'etf':-.05},'broad_risk_off':{'stock':-.25,'etf':-.25,'crypto':-.40,'perpetual':-.40}}
    stress=[{'scenario':name,'estimated_pnl':equity*sum(w*shocks.get(positions[s]['asset_class'],-.20) for s,w in weights.items()),'assumed_returns':shocks} for name,shocks in scenarios.items()]
    return {'equity':equity,'gross_fraction':sum(abs(w) for w in weights.values()),'net_fraction':sum(weights.values()),'asset_class_fractions':classes,'sector_fractions':by_sector,
            'annualized_volatility':volatility,'historical_daily_var_95_usd':var,'historical_daily_expected_shortfall_95_usd':es,
            'covariance_available':available or not weights,'aligned_observations':len(aligned),'missing_assets':missing,
            'correlations':corr.astype(object).where(pd.notna(corr),None).to_dict() if available else {},'correlated_groups':groups,'stress_scenarios':stress,
            'warnings':['Historical covariance uses current weights, not a reconstructed portfolio return history.','Stress shocks are explicit assumptions, not forecasts.','Raw equity prices require corporate-action review. Missing covariance is never reported as zero risk.']}
