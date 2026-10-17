"""Trusted numerical operations only. Reuses causal features, splits and model primitives."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from backend.research.features import market_frame, select_features, stable_hash
from backend.research.point_in_time import join_features_asof
from backend.research.studies import folds, targets, estimators, metrics
from backend.research.governance import block_bootstrap
from backend.qualification.statistics import nonoverlapping
from backend.research.autonomous.schema import ExperimentSpec, FEATURES


def frames(spec, snapshot):
    result={}
    for symbol in spec.universe:
        bars=snapshot['assets'][symbol]['bars']
        df,x,_=market_frame(bars)
        # Price histories may be retrospective vintages. Narrative features ALWAYS use receipt time.
        external=join_features_asof(df.available_at,snapshot['assets'][symbol].get('features',[]))
        for name in external:
            if name not in x:x[name]=external[name]
        events=snapshot.get('news',[])
        for name in ('news_negative','news_materiality'):
            values=[]
            for at in pd.to_datetime(df.available_at,utc=True):
                current={}
                for e in events:
                    t=pd.Timestamp(e['available_at'])
                    if symbol in e['symbols'] and pd.Timedelta(0)<=at-t<=pd.Timedelta(hours=48):current[e['cluster_id']]=e
                # Missing collection is not a neutral event history.
                values.append(float(any(e['direction']=='negative' if name=='news_negative' else e['materiality']=='high' for e in current.values())) if current else np.nan)
            x[name]=values
        result[symbol]=(df,x)
    for symbol,(df,x) in result.items():
        peers=[]
        for other,(odf,ox) in result.items():
            if symbol!=other:
                aligned=pd.Series(ox.return_20.to_numpy(),index=pd.to_datetime(odf.timestamp,utc=True)).reindex(pd.to_datetime(df.timestamp,utc=True))
                peers.append(aligned.to_numpy())
        if peers:x['cross_sectional_momentum']=x.return_20-np.nanmean(np.array(peers),axis=0)
        for f in spec.features:
            if f.name not in x:x[f.name]=np.nan
            if f.transform=='signed_log':x[f.name]=np.sign(x[f.name])*np.log1p(np.abs(x[f.name]))
            if f.transform=='lag_5':x[f.name]=x[f.name].shift(5)
        result[symbol]=(df,x[[f.name for f in spec.features]].replace([np.inf,-np.inf],np.nan))
    return result


def fit(x,y,labels,fit_ix,cal_ix,strength):
    if len(fit_ix)<64 or len(cal_ix)<20:raise ValueError('insufficient_data')
    if not np.isfinite(y.iloc[np.r_[fit_ix,cal_ix]]).all():raise ValueError('insufficient_data')
    if any(x[n].iloc[fit_ix].notna().mean()<.8 for n in x):raise ValueError('insufficient_data')
    groups={n:'allowed' for n in x};names,medians,_,=select_features(x,groups,fit_ix,['allowed'])
    clean=x[names].fillna(medians)
    reg,clf=estimators('linear',{'alpha':strength,'C':1/strength})
    reg.fit(clean.iloc[fit_ix],y.iloc[fit_ix]);prior=float(labels.iloc[fit_ix].mean())
    if labels.iloc[fit_ix].nunique()<2:raise ValueError('poor_calibration')
    clf.fit(clean.iloc[fit_ix],labels.iloc[fit_ix]);raw=clf.predict_proba(clean.iloc[cal_ix])[:,1]
    if labels.iloc[cal_ix].nunique()<2:raise ValueError('poor_calibration')
    logit=np.log(np.clip(raw,.001,.999)/(1-np.clip(raw,.001,.999))).reshape(-1,1)
    calibrator=LogisticRegression(C=1,random_state=1729).fit(logit,labels.iloc[cal_ix])
    def export(pipe):
        scaler,model=pipe.steps[0][1],pipe.steps[1][1]
        return {'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'coef':model.coef_.reshape(-1).tolist(),'intercept':float(np.asarray(model.intercept_).reshape(-1)[0])}
    artifact={'features':names,'medians':medians,'regression':export(reg),'classification':export(clf),
              'calibration':{'coef':float(calibrator.coef_[0,0]),'intercept':float(calibrator.intercept_[0])},'prior':prior}
    return artifact


def predict(artifact,x):
    a=np.array([[float(row.get(n,artifact['medians'][n])) if pd.notna(row.get(n)) else artifact['medians'][n] for n in artifact['features']] for row in x.to_dict('records')])
    def linear(m):return ((a-np.array(m['mean']))/np.array(m['scale']))@np.array(m['coef'])+m['intercept']
    expected=linear(artifact['regression']);logits=linear(artifact['classification'])
    raw=1/(1+np.exp(-np.clip(logits,-40,40)));logit=np.log(np.clip(raw,.001,.999)/(1-np.clip(raw,.001,.999)))
    calibrated=artifact['calibration']['coef']*logit+artifact['calibration']['intercept']
    return expected,1/(1+np.exp(-np.clip(calibrated,-40,40)))


def observations(spec,df,x,y,labels,artifact,ix,cost,symbol):
    expected,p=predict(artifact,x.iloc[ix]);gross,_,_=targets(df,spec.horizon,cost);out=[]
    # A position is bounded by known trailing volume, never future realized volume.
    dollar=(df.close*df.volume).rolling(20).mean()
    trend=df.close.pct_change(20)
    for j,i in enumerate(ix):
        regime='uptrend' if trend.iloc[i]>.03 else 'downtrend' if trend.iloc[i]<-.03 else 'range'
        volume_ok=dollar.iloc[i]>=spec.minimum_dollar_volume and spec.hypothetical_notional<=dollar.iloc[i]*spec.maximum_participation
        known=pd.Timestamp(df.available_at.iloc[i])<pd.Timestamp(df.timestamp.iloc[i+2])
        complete=all(pd.notna(x.iloc[i][name]) for name in artifact['features'])
        selected=bool(known and complete and volume_ok and df.close.iloc[i]>=spec.minimum_price and (spec.regime=='all' or spec.regime==regime) and expected[j]>cost and p[j]>.55)
        out.append({'symbol':symbol,'decided_at':str(df.available_at.iloc[i]),'completed_at':str(df.available_at.iloc[i+spec.horizon+2]),
                    'net_return':float(gross.iloc[i]-cost) if selected else 0.,'benchmark_return':float(gross.iloc[i]-cost),
                    'gross_return':float(gross.iloc[i]) if selected else 0.,'selected':selected,'eligible':bool(known and complete and volume_ok),
                    'target':float(y.iloc[i]),'predicted':float(expected[j]),'label':int(labels.iloc[i]),'probability':float(p[j]),'prior':artifact['prior'],'regime':regime})
    return out


def summarize(rows):
    clusters=nonoverlapping(rows);returns=np.array([r['net_return'] for r in clusters]);excess=np.array([r['net_return']-np.mean([v['benchmark_return'] for v in r['rows']]) for r in clusters])
    if not len(returns):raise ValueError('insufficient_data')
    curve=np.r_[1.,np.cumprod(1+returns)];drawdown=float(np.max(1-curve/np.maximum.accumulate(curve)))
    values=[v for c in clusters for v in c['rows']];labels=np.array([v['label'] for v in values]);p=np.array([v['probability'] for v in values]);prior=np.array([v['prior'] for v in values]);y=np.array([v['target'] for v in values]);pred=np.array([v['predicted'] for v in values])
    return {'dates':len(clusters),'rows':len(values),'trades':sum(v['selected'] for v in values),'mean_net_return':float(returns.mean()),'mean_excess_return':float(excess.mean()),
            'mean_gross_return':float(np.mean([np.mean([v['gross_return'] for v in c['rows']]) for c in clusters])),
            'maximum_drawdown':drawdown,'brier':float(np.mean((labels-p)**2)),'base_brier':float(np.mean((labels-prior)**2)),
            'return_mse':float(np.mean((y-pred)**2)),'zero_return_mse':float(np.mean(y*y)),
            'return_inference':block_bootstrap(returns),'excess_inference':block_bootstrap(excess),
            'by_regime':{name:{'rows':len(v),'mean_net_return':float(np.mean([r['net_return'] for r in v]))} for name in ('uptrend','downtrend','range') if (v:=[r for r in values if r['regime']==name])},
            'signal_sketch':{c['date']:float(np.mean([v['predicted'] for v in c['rows']])) for c in clusters[:128]}}


def run(specification,snapshot):
    spec=ExperimentSpec.model_validate(specification);data=frames(spec,snapshot);cost=(2*spec.fee_bps+2*spec.slippage_bps+spec.spread_bps)/10000
    all_targets={s:targets(df,spec.horizon,cost)[0] for s,(df,x) in data.items()}
    best=None;trials=[];holdout_at=pd.Timestamp(snapshot['holdout_start']);prepared={}
    for symbol,(df,x) in data.items():
        gross=all_targets[symbol];y=gross.copy()
        if spec.target=='relative_return':
            peers=[pd.Series(all_targets[o].to_numpy(),index=pd.to_datetime(odf.timestamp,utc=True)).reindex(pd.to_datetime(df.timestamp,utc=True)).to_numpy() for o,(odf,ox) in data.items() if o!=symbol]
            y=y-np.mean(peers,axis=0)
        labels=(y>cost).astype(int);dev_end=int(np.searchsorted(pd.to_datetime(df.timestamp,utc=True),holdout_at))
        if dev_end<240:raise ValueError('insufficient_data')
        prepared[symbol]=(df,x,y,labels,dev_end)
    for strength in spec.trials:
        per_fold=[[],[],[]]
        for symbol,(df,x,y,labels,dev_end) in prepared.items():
            for j,(train,cal,val) in enumerate(folds(dev_end,spec.horizon)):
                artifact=fit(x,y,labels,train,cal,strength)
                per_fold[j]+=observations(spec,df,x,y,labels,artifact,val,cost,symbol)
        summaries=[summarize(r) for r in per_fold];score=float(np.mean([v['return_mse']/max(v['zero_return_mse'],1e-12)+v['brier']/max(v['base_brier'],1e-12) for v in summaries]))
        trial={'strength':strength,'score':score,'folds':summaries};trials.append(trial)
        if best is None or score<best['score']:best=trial
    # Nothing in the untouched partition selected the model or its parameters.
    holdout=[];artifacts={}
    for symbol,(df,x,y,labels,dev_end) in prepared.items():
        gap=spec.horizon+2;fit_end=int(dev_end*.8);train=np.arange(60,fit_end-gap);cal=np.arange(fit_end,dev_end-gap)
        artifact=fit(x,y,labels,train,cal,best['strength']);ix=np.arange(dev_end,len(df)-gap,gap)
        if len(ix)<5:raise ValueError('insufficient_data')
        holdout+=observations(spec,df,x,y,labels,artifact,ix,cost,symbol)
        artifact['uncertainty']=float(np.std(y.iloc[cal].to_numpy()-predict(artifact,x.iloc[cal])[0]));artifacts[symbol]=artifact
    result={'selected_strength':best['strength'],'trials':trials,'holdout':summarize(holdout),'artifacts':artifacts,'feature_families':sorted({FEATURES[n] for a in artifacts.values() for n in a['features']}),
            'point_in_time':{'entry_delay_bars':2,'purge_bars':spec.horizon+2,'external_features':'availability/expiry as-of; no backdating','holdout_start':snapshot['holdout_start']},
            'limitations':['Historical open-price scenarios include declared costs, not verified executable quotes. Spread/depth history is not fabricated.','Retrospective provider vintages and current universe can contain revisions and survivorship bias.','Frozen for this registration, not guaranteed globally unseen; prior manual research may have inspected these dates.','Bootstrap inference assumes weak stationarity. Only independent prospective evidence can qualify a challenger.']}
    return result


def classify(result,spec,alpha):
    s=spec.success;h=result['holdout'];reasons=[]
    if h['dates']<s.minimum_holdout_dates:reasons.append('insufficient_data')
    if h['trades']<10:reasons.append('capacity_or_liquidity_problem')
    if h['trades']>.8*h['rows'] and h['mean_net_return']<=0:reasons.append('excessive_turnover')
    if h['mean_gross_return']>0>=h['mean_net_return']:reasons.append('transaction_costs_removed_edge')
    if h['mean_net_return']<=s.minimum_mean_net_return or h['mean_excess_return']<=0:reasons.append('no_predictive_relationship')
    if h['brier']>s.maximum_brier or h['brier']>=h['base_brier']:reasons.append('poor_calibration')
    if h['maximum_drawdown']>s.maximum_drawdown:reasons.append('unstable_by_time')
    best=next(t for t in result['trials'] if t['strength']==result['selected_strength'])
    if sum(f['mean_net_return']>0 for f in best['folds'])<s.minimum_positive_folds:reasons.append('unstable_by_time')
    if any(v['rows']>=15 and v['mean_net_return']<-.005 for v in h['by_regime'].values()):reasons.append('unstable_by_regime')
    if any(h[k]['p_value'] is None or h[k]['p_value']>alpha for k in ('return_inference','excess_inference')):reasons.append('failed_holdout')
    if h['return_mse']>=h['zero_return_mse']:reasons.append('overfitting')
    return sorted(set(reasons))
