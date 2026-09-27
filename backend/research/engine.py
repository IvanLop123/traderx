"""Chronological research, explicit historical-data assumptions, cost-aware simulation."""
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import mean_squared_error, brier_score_loss
from backend.intelligence.quant import features, RESEARCH
from backend.schemas.contracts import Prediction, AssetIdentifier, TradeCandidate, now
from datetime import timedelta

FEATURES=['return_1','return_5','return_20','realized_volatility','volume_zscore','vwap_distance','rsi','bollinger_z']

def ordered_bars(bars):
    if not bars:raise ValueError('No completed market history is available for this asset')
    df=pd.DataFrame(bars).sort_values(['timestamp','observed_at']).drop_duplicates('timestamp',keep='last').reset_index(drop=True)
    if len(df)<65: raise ValueError('At least 65 completed bars are required')
    if set(df.interval_seconds)!={86400}:raise ValueError('These research models require completed daily bars; intraday data must use a separate model')
    timestamps=pd.to_datetime(df.timestamp,utc=True)
    if timestamps.duplicated().any(): raise ValueError('Duplicate timestamps')
    if ((pd.to_datetime(df.available_at,utc=True)-timestamps).dt.total_seconds()<df.interval_seconds).any(): raise ValueError('A bar cannot be available before it closes')
    return df

def performance(equity,periods_per_year=365):
    e=np.asarray(equity,dtype=float); r=e[1:]/e[:-1]-1
    volatility=float(np.std(r,ddof=1)*np.sqrt(periods_per_year)) if len(r)>1 else 0
    downside=r[r<0]; sd=float(np.sqrt(np.mean(np.minimum(r,0)**2))) if len(r) else 0
    return {'total_return':float(e[-1]/e[0]-1),'volatility':volatility,
            'sharpe':float(np.mean(r)*periods_per_year/volatility) if volatility>0 else None,
            'sortino':float(np.mean(r)*np.sqrt(periods_per_year)/sd) if sd>0 else None,
            'max_drawdown':float(np.min(e/np.maximum.accumulate(e)-1)),
            'positive_period_fraction':float(np.mean(r>0)) if len(r) else None}

def backtest(bars,lookback=20,fee_bps=5,slippage_bps=5,spread_bps=2,latency_bars=1,strict_observed=False,initial_cash=100000):
    df=ordered_bars(bars)
    if not 2<=lookback<=min(252,len(df)-3): raise ValueError('Lookback does not fit the history')
    if latency_bars<1: raise ValueError('At least one bar of execution latency is required')
    if min(fee_bps,slippage_bps,spread_bps)<0: raise ValueError('Costs cannot be negative')
    momentum=df.close.pct_change(lookback)
    cash=float(initial_cash); shares=0.; equity=[cash]; curve=[]; fills=[]; total_cost=0; turnover=0
    fee=fee_bps/1e4; impact=(slippage_bps+spread_bps/2)/1e4
    start=lookback+latency_bars
    for i in range(start,len(df)):
        signal_index=i-latency_bars; bar=df.iloc[i]; signal=df.iloc[signal_index]
        available=pd.Timestamp(signal.available_at)
        if strict_observed: available=max(available,pd.Timestamp(signal.observed_at))
        if available>pd.Timestamp(bar.timestamp): desired=0
        else: desired=int(momentum.iloc[signal_index]>0)
        p=float(bar.open)
        if desired and shares==0:
            execution=p*(1+impact); shares=cash/(execution*(1+fee)); cost=shares*execution*fee
            total_cost+=cost+shares*(execution-p); turnover+=shares*p
            cash=0.; fills.append({'timestamp':bar.timestamp,'side':'buy','price':execution,'quantity':shares,'fee':cost,'signal_timestamp':signal.timestamp})
        elif not desired and shares>0:
            execution=p*(1-impact); cost=shares*execution*fee
            cash+=shares*execution-cost; total_cost+=cost+shares*(p-execution); turnover+=shares*p
            fills.append({'timestamp':bar.timestamp,'side':'sell','price':execution,'quantity':shares,'fee':cost,'signal_timestamp':signal.timestamp}); shares=0
        marked=cash+shares*float(bar.close); equity.append(marked)
        curve.append({'timestamp':bar.timestamp,'equity':marked,'benchmark':initial_cash*float(bar.close)/float(df.iloc[start].open)})
    if shares:
        p=float(df.iloc[-1].close); execution=p*(1-impact); cost=shares*execution*fee
        total_cost+=cost+shares*(p-execution); turnover+=shares*p
        equity[-1]=shares*execution-cost; curve[-1]['equity']=equity[-1]
        fills.append({'timestamp':df.iloc[-1].available_at,'side':'sell','price':execution,'quantity':shares,'fee':cost,'reason':'terminal_liquidation'})
    annual=365 if '-' in str(df.iloc[0].symbol) else 252
    metrics=performance(equity,annual)
    return {'strategy':'lagged_momentum_v1','symbol':df.iloc[0].symbol,'metrics':metrics,'curve':curve,'fills':fills,
            'total_cost':total_cost,'turnover':turnover/initial_cash,'bar_count':len(df),'parameters':{'lookback':lookback,'fee_bps':fee_bps,'slippage_bps':slippage_bps,'spread_bps':spread_bps,'latency_bars':latency_bars},
            'data_policy':'strict_first_observed' if strict_observed else 'retrospective_completed_bars',
            'warnings':['Research simulation, not a validated strategy.','Single asset; survivorship and market impact are not resolved.',
                        'Retrospective downloaded bars may contain provider revisions; not certified point-in-time.' if not strict_observed else 'Downloaded history unavailable before its first observed time.'],
            'dataset_hash':hashlib.sha256(df.to_json().encode()).hexdigest()}

def train_fusion(bars,horizon=1,feature_records=None):
    df=ordered_bars(bars); x=features(df.to_dict('records'))[FEATURES]
    y=df.close.shift(-horizon)/df.close-1
    valid=x.notna().all(axis=1)&y.notna(); indices=np.flatnonzero(valid.to_numpy())
    if len(indices)<90: raise ValueError('At least 90 labeled observations after feature warmup are required')
    # Purge horizon labels at each boundary. Holdout is never used for fitting/calibration.
    train_end=int(len(indices)*.6); val_end=int(len(indices)*.8)
    train=indices[:train_end-horizon]; val=indices[train_end:val_end-horizon]; holdout=indices[val_end:]
    if min(len(train),len(val),len(holdout))<10: raise ValueError('Insufficient chronological split')
    from backend.research.point_in_time import join_features_asof
    external=join_features_asof(df.available_at,feature_records or [])
    included=[]; unavailable=[]
    for name in external:
        if name in FEATURES:continue
        # Decide feature eligibility using training coverage only, never holdout.
        if external[name].iloc[train].notna().mean()>=.8:
            median=float(external[name].iloc[train].median()); x[name]=external[name].fillna(median);included.append(name)
        else:unavailable.append(name)
    feature_names=list(x.columns)

    model=make_pipeline(StandardScaler(),Ridge(alpha=10))
    model.fit(x.iloc[train],y.iloc[train]); vp=model.predict(x.iloc[val]); hp=model.predict(x.iloc[holdout])
    labels=(y>0).astype(int)
    classifier=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=1000))
    if labels.iloc[train].nunique()<2: raise ValueError('Training history must include up and down outcomes')
    classifier.fit(x.iloc[train],labels.iloc[train])
    # Sigmoid calibration uses validation only, never holdout.
    raw_val=classifier.decision_function(x.iloc[val]).reshape(-1,1)
    calibration=None
    if labels.iloc[val].nunique()==2:
        calibration=LogisticRegression(C=1).fit(raw_val,labels.iloc[val])
    def probability(data):
        return calibration.predict_proba(classifier.decision_function(data).reshape(-1,1))[:,1] if calibration else classifier.predict_proba(data)[:,1]
    sigma=float(np.std(y.iloc[val].to_numpy()-vp,ddof=1))
    volatility_model=make_pipeline(StandardScaler(),Ridge(alpha=10))
    volatility_model.fit(x.iloc[train],y.iloc[train]**2)
    latest=x.iloc[[-1]]
    if latest.isna().any(axis=None): raise ValueError('Latest features are incomplete')
    scaled=model[0].transform(latest)[0]; coefficients=model[1].coef_
    contributions=dict(zip(feature_names,map(float,scaled*coefficients)))
    expected_return=float(model.predict(latest)[0])
    prediction={'expected_return':expected_return,'probability_positive':float(probability(latest)[0]),
                'expected_volatility':float(np.sqrt(max(0,volatility_model.predict(latest)[0]-expected_return**2))),'downside':float(np.quantile(y.iloc[train],.05)),
                'uncertainty':1.96*sigma,'contributions':contributions}
    def linear_artifact(pipeline):
        return {'mean':pipeline[0].mean_.tolist(),'scale':pipeline[0].scale_.tolist(),'coef':np.asarray(pipeline[1].coef_).reshape(-1).tolist(),'intercept':float(np.asarray(pipeline[1].intercept_).reshape(-1)[0])}
    artifact={'format_version':2,'return':linear_artifact(model),'direction':linear_artifact(classifier),'volatility':linear_artifact(volatility_model),
              'calibration':{'coef':float(calibration.coef_[0][0]),'intercept':float(calibration.intercept_[0])} if calibration else None,
              'uncertainty':1.96*sigma,'downside':float(np.quantile(y.iloc[train],.05)),
              'imputation':{name:float(external[name].iloc[train].median()) for name in included}}
    split=lambda ii:{'start':df.iloc[ii[0]].timestamp,'end':df.iloc[ii[-1]].timestamp,'samples':len(ii)}
    holdout_mse=float(mean_squared_error(y.iloc[holdout],hp))
    zero_mse=float(np.mean(y.iloc[holdout].to_numpy()**2))
    brier=float(brier_score_loss(labels.iloc[holdout],probability(x.iloc[holdout])))
    baseline_brier=float(brier_score_loss(labels.iloc[holdout],np.full(len(holdout),labels.iloc[train].mean())))
    gates={'return_forecast_beats_zero':holdout_mse<zero_mse,'direction_beats_training_prior':brier<baseline_brier,
           'holdout_at_least_200':len(holdout)>=200,'calibration_available':calibration is not None}
    return {'model':'ridge-logistic-v2','artifact':artifact,'features':feature_names,'optional_evidence_features':included,'insufficient_historical_coverage':unavailable,'hyperparameters':{'ridge_alpha':10,'logistic_C':.1,'horizon':horizon},
        'splits':{'training':split(train),'validation':split(val),'holdout':split(holdout),'purge_bars':horizon},
        'validation_mse':float(mean_squared_error(y.iloc[val],vp)),'holdout_mse':holdout_mse,'holdout_zero_forecast_mse':zero_mse,
        'holdout_brier':brier,'holdout_training_prior_brier':baseline_brier,'research_candidate_gates':gates,'research_candidate_eligible':all(gates.values()),
        'calibration':'validation_sigmoid' if calibration else 'uncalibrated_insufficient_classes','prediction':prediction,
        'dataset_hash':hashlib.sha256(df.to_json().encode()).hexdigest(),'activation':'research_only',
        'trained_at':now().isoformat(),'as_of':df.iloc[-1].available_at,
        'warning':'One fixed baseline, untouched chronological holdout for this run; repeated runs on the same holdout are not independent validation.'}

def signal_evaluation(bars,horizon=5):
    df=ordered_bars(bars); x=features(df.to_dict('records'))['return_20']; y=df.close.shift(-horizon)/df.close-1
    mask=x.notna()&y.notna(); xv=x[mask].to_numpy(); yv=y[mask].to_numpy()
    if len(xv)<20: raise ValueError('Insufficient observations')
    ic=float(spearmanr(xv,yv).statistic)
    rng=np.random.default_rng(42); block=max(horizon,5); means=[]
    for _ in range(250):
        starts=rng.integers(0,len(yv)-block+1,size=math_ceil(len(yv)/block))
        sample=np.concatenate([yv[s:s+block] for s in starts])[:len(yv)]; means.append(float(sample.mean()))
    return {'signal':'return_20','horizon_bars':horizon,'samples':len(yv),'coverage':len(yv)/len(df),
            'information_coefficient':ic if np.isfinite(ic) else None,'mean_forward_return':float(yv.mean()),
            'median_forward_return':float(np.median(yv)),'hit_rate':float(np.mean(yv>0)),
            'block_bootstrap_95':list(map(float,np.quantile(means,[.025,.975]))),
            'warning':'Unconditional forward returns and exploratory rank correlation; not causal or deployable evidence.'}

def math_ceil(x): return int(np.ceil(x))

def fdr(pvalues):
    p=np.asarray(pvalues); order=np.argsort(p); result=np.empty(len(p)); adjusted=p[order]*len(p)/np.arange(1,len(p)+1)
    result[order]=np.minimum.accumulate(adjusted[::-1])[::-1].clip(0,1); return result.tolist()

def candidate_from_prediction(prediction:Prediction,quote,equity=100000):
    costs=RESEARCH['estimated_round_trip_cost']; edge=prediction.expected_return-costs
    if edge<=prediction.uncertainty or prediction.probability_positive<RESEARCH['candidate_probability_min']: return None
    price=float(quote['price']); budget=equity*RESEARCH['candidate_fraction']
    return TradeCandidate(asset=prediction.asset,prediction_id=prediction.id,direction='buy',horizon=prediction.horizon,
        entry_price=price,quantity=budget/price,expected_edge=edge,expected_costs=costs,expected_downside=prediction.downside,
        confidence=prediction.probability_positive,evidence_ids=prediction.evidence_ids,expires_at=now()+timedelta(seconds=RESEARCH['candidate_ttl_seconds']),liquidity=quote)


def infer_registered(model_record,bars,feature_records=None):
    """Portable JSON coefficients; never deserialize arbitrary pickle code."""
    from scipy.special import expit
    df=ordered_bars(bars)
    frame=features(df.to_dict('records'))
    from backend.research.point_in_time import join_features_asof
    external=join_features_asof(df.available_at,feature_records or [])
    for name,median in model_record['artifact'].get('imputation',{}).items():
        frame[name]=external[name].fillna(median) if name in external else median
    latest=frame[model_record['features']].iloc[-1]
    if latest.isna().any(): raise ValueError('Insufficient features for registered model')
    artifact=model_record['artifact']
    def linear(name):
        m=artifact[name]; contributions=(latest.to_numpy()-np.array(m['mean']))/np.array(m['scale'])*np.array(m['coef'])
        return float(contributions.sum()+m['intercept']),dict(zip(model_record['features'],map(float,contributions)))
    expected,contributions=linear('return'); score,_=linear('direction'); variance,_=linear('volatility')
    if artifact['calibration']:score=score*artifact['calibration']['coef']+artifact['calibration']['intercept']
    variance=variance-expected**2 if artifact.get('format_version',1)>=2 else variance
    return {'expected_return':expected,'probability_positive':float(expit(score)),'expected_volatility':float(np.sqrt(max(0,variance))),
            'downside':artifact['downside'],'uncertainty':artifact['uncertainty'],'contributions':contributions}
