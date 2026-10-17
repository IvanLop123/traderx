"""Bounded cross-sectional comparison on contemporaneously eligible US assets.

Rows share a decision timestamp; dates, not securities, are split and counted as
independent evidence. This is retrospective-watchlist research, never promotion.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error,brier_score_loss
from threadpoolctl import threadpool_limits
from backend.research.history import HistoryStore
from backend.research.universe import load_universe
from backend.research.features import market_frame,stable_hash
from backend.research.studies import estimators
from backend.schemas.contracts import now

FEATURES=['return_1','return_5','return_20','realized_volatility','rsi','atr_fraction','ma20_to_ma60']
CONFIGS=[('linear',{'alpha':100,'C':.01}),('forest',{'depth':3,'leaf':25}),('boosting',{'leaves':5,'l2':10})]

def panel(db,horizon=5):
    u=load_universe(db);store=HistoryStore(db);parts=[];manifests={}
    for instrument in [i for i in u.instruments if i.asset_class in ('stock','etf')][:u.maximum_training_assets]:
        adjusted=store.read(instrument.symbol);raw=store.read(instrument.symbol,'raw')
        if min(len(adjusted),len(raw))<400:continue
        d,x,_=market_frame(adjusted);r=pd.DataFrame(raw).set_index('timestamp').reindex(d.timestamp).reset_index(drop=True);f=u.filters
        # Eligibility at t uses only trailing unadjusted volume/prices. No terminal rank screen.
        liquid=(r.close>=f.minimum_price)&(r.volume.rolling(f.liquidity_window).mean()>=f.minimum_daily_volume)&((r.close*r.volume).rolling(f.liquidity_window).mean()>=f.minimum_daily_dollar_volume)
        known=pd.to_datetime(d.available_at,utc=True).dt.ceil('D');calendar=db.setting('research_calendar',{}).get('sessions',[])
        expected=pd.DatetimeIndex([s['date'] for s in calendar]);dates=pd.to_datetime(d.timestamp,utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
        # Each rolling 60-session window must meet coverage; timestamps are never filled with future data.
        observed=pd.Series(1.,index=pd.DatetimeIndex(dates)).groupby(level=0).max().reindex(expected,fill_value=0.)
        coverage=observed.rolling(60,min_periods=60).mean().reindex(pd.DatetimeIndex(dates)).to_numpy()
        liquid&=np.nan_to_num(coverage)>=f.minimum_coverage
        if u.policy=='archived_membership':liquid&=known>=pd.Timestamp(instrument.membership_known_at)
        if not instrument.active:
            if instrument.inactive_known_at:liquid&=known<pd.Timestamp(instrument.inactive_known_at)
            else:liquid&=False
        p=x[FEATURES].copy();p['date']=known;p['symbol']=instrument.symbol;p['asset_class']=instrument.asset_class
        p['gross_return']=d.open.shift(-horizon-2)/d.open.shift(-2)-1;p['label_end']=pd.to_datetime(d.timestamp.shift(-horizon-2),utc=True)
        p=p[liquid & (d.index>=f.minimum_history)].dropna();parts.append(p);manifests[instrument.symbol]=store.manifest(instrument.symbol)['id']
    if len(parts)<4:raise ValueError('At least four sufficiently covered US assets required')
    p=pd.concat(parts,ignore_index=True).sort_values(['date','symbol']);p=p[p.groupby('date').symbol.transform('count')>=4]
    p['universe_return']=p.groupby('date').gross_return.transform('mean');p['relative_return']=p.gross_return-p.universe_return;p['outperform']=(p.relative_return>0).astype(int)
    # Cross-sectional transforms use only that timestamp's feature values, never future labels.
    for feature in FEATURES:p[feature+'_rank']=p.groupby('date')[feature].rank(pct=True)
    return p,manifests

def compare(db,horizon=5,release=False):
    p,manifests=panel(db,horizon);columns=FEATURES+[n+'_rank' for n in FEATURES];dates=sorted(p.date.unique());n=len(dates)
    if n<400:raise ValueError('Insufficient independent dates')
    train_end=int(n*.65);hold_start=int(n*.8);gap=horizon+2
    fit_dates=dates[60:train_end-gap];val_dates=dates[train_end:hold_start-gap:gap];test_dates=dates[hold_start:n-gap:gap]
    fit=p[p.date.isin(fit_dates)&(p.label_end<dates[train_end])];val=p[p.date.isin(val_dates)];test=p[p.date.isin(test_dates)]
    identity={'version':'cross-sectional-v1','series':manifests,'universe':load_universe(db).model_dump(mode='json'),'horizon':horizon,'columns':columns,'dates':[str(d) for d in dates]};rid='cross_'+stable_hash(identity)
    released=db.get(rid+'_released')
    if release and released:return released['payload']
    existing=db.get(rid)
    if existing and (not release or existing['payload'].get('holdout_status')=='RELEASED_ONCE'):return existing['payload']
    trials=[];cost=.0022
    with threadpool_limits(limits=1):
        for scope in ['individual','asset_class','pooled']:
            group_key='symbol' if scope=='individual' else 'asset_class' if scope=='asset_class' else None
            for algorithm,params in CONFIGS:
                predictions={'validation':[],'holdout':[]};groups=list(fit.groupby(group_key)) if group_key else [('all',fit)]
                for name,train in groups:
                    if len(train)<252 or train.outperform.nunique()<2:continue
                    reg,clf=estimators(algorithm,params);reg.fit(train[columns],train.relative_return);clf.fit(train[columns],train.outperform)
                    for label,data in [('validation',val),*([('holdout',test)] if release else [])]:
                        selected=data[data[group_key]==name].copy() if group_key else data.copy()
                        if selected.empty:continue
                        selected['predicted_relative']=reg.predict(selected[columns]);selected['probability_outperform']=clf.predict_proba(selected[columns])[:,1];selected['prior']=train.outperform.mean();predictions[label].append(selected)
                def scores(parts):
                    if not parts:return None
                    z=pd.concat(parts);ics=[];top=[]
                    for _,day in z.groupby('date'):
                        if len(day)<4:continue
                        ic=day.predicted_relative.corr(day.relative_return,method='spearman')
                        if np.isfinite(ic):ics.append(float(ic))
                        winner=day.sort_values('predicted_relative').iloc[-1]
                        # Relative prediction alone is not an absolute-return forecast. No trading permission.
                        top.append(float(winner.gross_return-cost))
                    return {'raw_asset_rows':len(z),'independent_date_clusters':z.date.nunique(),'return_mse':float(mean_squared_error(z.relative_return,z.predicted_relative)),'zero_relative_mse':float(np.mean(z.relative_return**2)),'brier':float(brier_score_loss(z.outperform,z.probability_outperform)),'base_rate_brier':float(brier_score_loss(z.outperform,z.prior)),'mean_rank_ic':float(np.mean(ics)) if ics else None,'top_rank_mean_return_after_estimated_cost':float(np.mean(top)) if top else None,'equal_weight_mean_return_after_estimated_cost':float(z.groupby('date').gross_return.mean().mean()-cost),'cash_return':0.}
                trials.append({'scope':scope,'algorithm':algorithm,'parameters':params,'validation':scores(predictions['validation']),'holdout':scores(predictions['holdout']) if release else None})
    selected=min([t for t in trials if t['validation']],key=lambda t:t['validation']['return_mse']/max(t['validation']['zero_relative_mse'],1e-12)+t['validation']['brier']/max(t['validation']['base_rate_brier'],1e-12))
    result={'id':rid,'created_at':now().isoformat(),'data':identity,'assets':sorted(p.symbol.unique()),'target':'Five-session future return relative to the eligible observed universe; probability of outperformance','selection':{k:selected[k] for k in ['scope','algorithm','parameters']},'trials':trials,'holdout_status':'RELEASED_ONCE' if release else 'LOCKED','promotion_eligible':False,'limitations':['Retrospective selected watchlist, not a survivorship-free constituent archive.','Independent date clusters are separated by horizon plus execution delay; cross-asset rows are correlated.','Observed OHLCV open-based return proxies with estimated costs are not executable-price guarantees.','Top-rank returns are a diagnostic, not an absolute-return trading model or permission to trade.','Unresolved delisting return coverage can bias retrospective labels; no promotion allowed.']}
    if release:
        if not existing:raise ValueError('Freeze validation selection before releasing cross-sectional holdout')
        if existing['payload']['selection']!=result['selection']:raise ValueError('Frozen selection changed')
        self_id=rid+'_released';db.put('cross_study',result,record_id=self_id);db.set_setting('cross_latest',{'id':self_id})
    else:db.put('cross_study',result,record_id=rid);db.set_setting('cross_latest',{'id':rid})
    return result
