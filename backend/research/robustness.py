"""Fixed research challengers, chronological selection and cost robustness checks."""
import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from backend.research.engine import ordered_bars, features, FEATURES, performance

STRATEGIES=['cash','buy_hold','momentum_20','multi_horizon_trend','volatility_target_trend','mean_reversion']

def weights_for(df,strategy):
    close=df.close; returns=close.pct_change(); vol=returns.rolling(20).std()*np.sqrt(365 if '-' in str(df.iloc[0].symbol) else 252)
    if strategy=='cash':w=pd.Series(0.,index=df.index)
    elif strategy=='buy_hold':w=pd.Series(1.,index=df.index)
    elif strategy=='momentum_20':w=(close.pct_change(20)>0).astype(float)
    elif strategy=='multi_horizon_trend':
        # A transparent fixed baseline, not equal-weight fusion of unrelated evidence.
        scores=pd.concat([close.pct_change(n) for n in [20,60,120]],axis=1)
        w=(scores>0).sum(axis=1)/scores.notna().sum(axis=1).replace(0,np.nan)
    elif strategy=='volatility_target_trend':w=(close.pct_change(60)>0).astype(float)*(.15/vol.replace(0,np.nan)).clip(upper=1)
    elif strategy=='mean_reversion':
        z=(close-close.rolling(20).mean())/close.rolling(20).std().replace(0,np.nan)
        w=(-z-1).clip(lower=0,upper=1)
    else:raise ValueError('Unknown research strategy')
    return w.fillna(0).clip(0,1)

def simulate_weights(df,weights,fee_bps=5,slippage_bps=5,spread_bps=2,start=61,end=None):
    """Weights observed at close t-1; execute t open. Long/cash, fees on turnover."""
    end=len(df) if end is None else end
    cash=100000.;quantity=0.;equity=[cash];turnover=0.;cost=0.;curve=[];fee=fee_bps/1e4;impact=(slippage_bps+spread_bps/2)/1e4
    for i in range(start,end):
        row=df.iloc[i]; opening=float(row.open); close=float(row.close);wealth=cash+quantity*opening
        signal=i-1
        if pd.Timestamp(df.iloc[signal].available_at)>pd.Timestamp(row.timestamp):target=0.
        else:target=float(weights.iloc[signal])
        target_quantity=wealth*target/opening
        delta=target_quantity-quantity
        if abs(delta)>1e-8:
            direction=1 if delta>0 else -1;price=opening*(1+direction*impact)
            if delta>0:delta=min(delta,cash/(price*(1+fee)))
            traded=abs(delta)*price;paid=traded*fee
            cash-=delta*price+paid;quantity+=delta;turnover+=abs(delta)*opening
            cost+=paid+abs(delta)*abs(price-opening)
        if cash < -1e-6 or quantity < -1e-8:raise ValueError('Simulation violated unlevered long/cash constraints')
        value=cash+quantity*close;equity.append(value);curve.append({'timestamp':row.timestamp,'equity':value,'weight':target})
    if quantity:
        closing=float(df.iloc[end-1].close);exit_price=closing*(1-impact);exit_fee=quantity*exit_price*fee
        cost+=exit_fee+quantity*(closing-exit_price);turnover+=quantity*closing
        equity[-1]=cash+quantity*exit_price-exit_fee;curve[-1]['equity']=equity[-1]
    annual=365 if '-' in str(df.iloc[0].symbol) else 252
    r=np.diff(np.asarray(equity))/np.asarray(equity[:-1])
    return {'metrics':performance(equity,annual),'curve':curve,'returns':r.tolist(),'estimated_cost':cost,'turnover':turnover/100000}

def probabilistic_sharpe(returns,benchmark=0.):
    r=np.asarray(returns,float);n=len(r)
    if n<20 or np.std(r,ddof=1)==0:return None
    sr=float(r.mean()/r.std(ddof=1));s=float(skew(r,bias=False));k=float(kurtosis(r,fisher=False,bias=False))
    denominator=1-s*sr+(k-1)*sr**2/4
    if not np.isfinite(denominator) or denominator<=0:return None
    return float(norm.cdf((sr-benchmark)*np.sqrt(n-1)/np.sqrt(denominator)))

def compare_strategies(bars,trial_count=1):
    df=ordered_bars(bars)
    if len(df)<180:raise ValueError('At least 180 daily bars are required for this comparison')
    start=61;cut=int(len(df)*.75);dev_end=cut
    rows=[];paths={};development_paths={};holdout_returns={};development=[];annual=365 if '-' in str(df.iloc[0].symbol) else 252
    for name in STRATEGIES:
        weights=weights_for(df,name)
        development_result=simulate_weights(df,weights,start=start,end=dev_end)
        holdout=simulate_weights(df,weights,start=cut)
        stress=simulate_weights(df,weights,start=cut,fee_bps=10,slippage_bps=15,spread_bps=4)
        dev=development_result['metrics']['sharpe']
        development.append(dev if dev is not None else -1e9)
        rows.append({'strategy':name,'development':development_result['metrics'],'holdout':holdout['metrics'],
                     'holdout_cost_stress':stress['metrics'],'estimated_cost':holdout['estimated_cost'],'turnover':holdout['turnover'],
                     'probabilistic_sharpe_vs_zero':probabilistic_sharpe(holdout['returns']),
                     'return_observations':len(holdout['returns'])})
        paths[name]=holdout['curve']
        if name not in ('cash','buy_hold'):
            development_paths[name]=development_result['returns'];holdout_returns[name]=holdout['returns']
    # Choose using development only; holdout comparisons are reporting, not optimization.
    eligible=[i for i,n in enumerate(STRATEGIES) if n not in ('cash','buy_hold')]
    selected=max(eligible,key=lambda i:development[i])
    # Walk-forward regularized return forecast on development data, with explicit label purge.
    x=features(df.to_dict('records'))[FEATURES];y=df.close.shift(-1)/df.close-1
    valid=x.notna().all(axis=1)&y.notna()&(df.index+1<cut)
    xx=x.loc[valid];yy=y.loc[valid];indices=np.flatnonzero(valid.to_numpy());folds=[]
    for train,test in TimeSeriesSplit(n_splits=3,gap=1).split(xx):
        model=make_pipeline(StandardScaler(),Ridge(alpha=10));model.fit(xx.iloc[train],yy.iloc[train]);pred=model.predict(xx.iloc[test]);actual=yy.iloc[test].to_numpy()
        folds.append({'train_start':df.iloc[indices[train[0]]].timestamp,'train_end':df.iloc[indices[train[-1]]].timestamp,
                      'test_start':df.iloc[indices[test[0]]].timestamp,'test_end':df.iloc[indices[test[-1]]].timestamp,
                      'purge_bars':1,'mse':float(np.mean((pred-actual)**2)),'zero_forecast_mse':float(np.mean(actual**2)),
                      'direction_accuracy':float(np.mean((pred>0)==(actual>0)))})
    from backend.research.governance import strategy_family,cscv_diagnostic
    return {'statistical_governance':strategy_family(holdout_returns),'development_cscv':cscv_diagnostic(development_paths),'strategies':rows,'selected_on_development_only':STRATEGIES[selected],'holdout_curves':paths,'walk_forward_folds':folds,
            'split':{'development_start':df.iloc[start].timestamp,'development_end':df.iloc[cut-1].timestamp,'holdout_start':df.iloc[cut].timestamp,'holdout_end':df.iloc[-1].timestamp},
            'trial_count':trial_count,'tested_strategy_count':len(STRATEGIES),'deployment_status':'RESEARCH_ONLY','data_policy':'retrospective_completed_daily_bars',
            'warnings':['No universally best trading algorithm is established by this comparison.',
                        'Short single-market sample; not a replication of multi-decade diversified market research.',
                        'Holdout results become exploratory once inspected or reused. No automatic promotion to trading.',
                        'Probabilistic Sharpe assumes sufficiently independent observations; autocorrelation and multiple trials weaken the inference.',
                        'The CSCV diagnostic covers this fixed development family only. No deflated Sharpe or undocumented-trial correction is claimed.']}
