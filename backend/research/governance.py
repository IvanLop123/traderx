"""Bounded, reproducible diagnostics; no p-value grants permission to trade."""
from itertools import combinations
import hashlib
import numpy as np
from scipy.stats import false_discovery_control,rankdata
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
from backend.research.engine import ordered_bars,features,FEATURES

def block_bootstrap(returns,block_length=10,replicates=999,seed=1729):
    r=np.asarray(returns,dtype=float)
    if r.ndim!=1 or not np.isfinite(r).all():raise ValueError('Finite one-dimensional return series required')
    n=len(r)
    if n<max(60,block_length*6):return {'status':'INSUFFICIENT_OBSERVATIONS','samples':n,'p_value':None}
    rng=np.random.default_rng(seed);means=[];centered=r-r.mean();null=[];blocks=int(np.ceil(n/block_length))
    for _ in range(replicates):
        starts=rng.integers(0,n,size=blocks);indices=((starts[:,None]+np.arange(block_length))%n).ravel()[:n]
        means.append(float(r[indices].mean()));null.append(float(centered[indices].mean()))
    low,high=np.quantile(means,[.025,.975]);observed=float(r.mean())
    return {'status':'EXPLORATORY','samples':n,'block_length':block_length,'replicates':replicates,'seed':seed,'mean_daily_return':observed,
            'mean_daily_return_ci_95':[float(low),float(high)],'p_value':float((1+np.sum(np.asarray(null)>=observed))/(replicates+1)),
            'assumptions':'Circular block bootstrap of stationary weakly dependent returns; one-sided centered-null mean test. Regime shifts and block choice can invalidate inference.'}

def cscv_diagnostic(paths,blocks=8):
    names=list(paths);matrix=np.asarray([paths[n] for n in names],float).T
    if len(names)<2 or len(matrix)<blocks*10:return {'status':'INSUFFICIENT_OBSERVATIONS'}
    if not np.isfinite(matrix).all():raise ValueError('Nonfinite strategy paths')
    partitions=np.array_split(np.arange(len(matrix)),blocks);ranks=[]
    def score(a):
        sd=a.std(axis=0,ddof=1)
        return np.divide(a.mean(axis=0),sd,out=np.zeros(a.shape[1]),where=sd>1e-12)
    for inside in combinations(range(blocks),blocks//2):
        train=np.concatenate([partitions[j] for j in inside]);test=np.concatenate([partitions[j] for j in range(blocks) if j not in inside])
        selected=int(np.argmax(score(matrix[train])));rank=float(rankdata(score(matrix[test]),method='average')[selected]/(len(names)+1))
        ranks.append(rank)
    return {'status':'EXPLORATORY','method':'combinatorially_symmetric_cross_validation','strategies':names,'blocks':blocks,'partitions':len(ranks),
            'probability_below_oos_median':float(np.mean(np.asarray(ranks)<=.5)),
            'scope':'Fixed strategy family on development data only; does not include undocumented trials or certify future profitability.'}

def strategy_family(paths):
    details={name:block_bootstrap(values) for name,values in paths.items()}
    eligible=[n for n in details if details[n]['p_value'] is not None]
    if eligible:
        adjusted=false_discovery_control([details[n]['p_value'] for n in eligible],method='by')
        for name,p in zip(eligible,adjusted):details[name]['adjusted_p_value_by']=float(p)
    return {'family':list(paths),'tests':details,'adjustment':'Benjamini–Yekutieli within this declared strategy family only',
            'warning':'Approximate bootstrap p-values require their own assumptions. Adjustment does not repair biased data, reused holdouts, undocumented trials or nonstationarity. No automatic promotion.'}

def compare_forecasters(bars,horizon=5):
    df=ordered_bars(bars);x=features(df.to_dict('records'))[FEATURES];y=df.close.shift(-horizon)/df.close-1
    valid=x.notna().all(axis=1)&y.notna();indices=np.flatnonzero(valid.to_numpy())
    if len(indices)<250:raise ValueError('At least 250 labeled observations after warmup required')
    train_end=int(len(indices)*.6);val_end=int(len(indices)*.8)
    train=indices[:train_end-horizon];validation=indices[train_end:val_end-horizon];holdout=indices[val_end:]
    estimators={'ridge':make_pipeline(StandardScaler(),Ridge(alpha=10)),
                'random_forest':RandomForestRegressor(n_estimators=100,max_depth=4,min_samples_leaf=20,random_state=1729,n_jobs=1),
                'gradient_boosting':HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=7,l2_regularization=10,early_stopping=False,random_state=1729)}
    rows=[{'model':'zero_return','validation_mse':float(np.mean(y.iloc[validation]**2)),'holdout_mse':float(np.mean(y.iloc[holdout]**2))}]
    for name,model in estimators.items():
        model.fit(x.iloc[train],y.iloc[train]);v=model.predict(x.iloc[validation]);h=model.predict(x.iloc[holdout])
        rows.append({'model':name,'validation_mse':float(np.mean((v-y.iloc[validation])**2)),'holdout_mse':float(np.mean((h-y.iloc[holdout])**2))})
    selected=min(rows,key=lambda r:r['validation_mse'])['model']
    periods={name:{'start':str(df.iloc[ix[0]].timestamp),'end':str(df.iloc[ix[-1]].timestamp),'samples':len(ix)} for name,ix in [('training',train),('validation',validation),('holdout',holdout)]}
    return {'model_comparison':rows,'selected_on_validation_only':selected,'horizon':horizon,'splits':periods,'purge_bars':horizon,'dataset_hash':hashlib.sha256(df.to_json().encode()).hexdigest(),
            'status':'RESEARCH_ONLY','warnings':['Fixed hyperparameters, no random temporal split or early-stopping validation shuffle.','Selection uses validation only. Holdout scores are exploratory once inspected; reruns do not create new independent evidence.','Lower prediction error does not establish a cost-adjusted tradable strategy. Tree models are challengers, not automatically activated executors.']}
