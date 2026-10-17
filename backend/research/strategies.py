"""Separate, chronological strategy experiments. No execution or promotion authority.

Cost-adjusted OHLCV returns are research proxies; actual fills require future quotes.
Current membership and capitalization are never presented as historical facts.
"""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge,LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss,mean_squared_error
from threadpoolctl import threadpool_limits
from backend.research.features import market_frame,backward,stable_hash
from backend.research.history import HistoryStore
from backend.research.universe import load_universe
from backend.research.filings import historical_features
from backend.schemas.contracts import now

VERSION='strategy-families-v1'
FAMILIES={
 'momentum':['return_5','return_20'],
 'trend_following':['ma20_to_ma60','trend_efficiency'],
 'mean_reversion':['rsi','bollinger_z'],
 'breakout':['breakout_20','range_location','volume_zscore'],
 'volatility':['bollinger_width','regime_vol_ratio','vol_of_vol'],
 'relative_strength':['relative_momentum','relative_volatility'],
 'cross_sectional_ranking':['momentum_rank','volatility_rank','liquidity_rank'],
 'insider_event':['insider_purchase_dollars_30d','insider_distinct_buyers_30d','insider_role_weighted_count_30d','insider_repeat_buyers_60d','insider_days_since_filing'],
 'macro_regime':['macro_FEDFUNDS','macro_UNRATE','macro_T10Y2Y','regime_trend'],
 'crypto_funding':['funding_paid','funding_premium','return_5'],
 'pairs_relative_value':['pair_zscore','pair_return_20'],
}
PAIRS={'XOM':'CVX','CVX':'XOM','KO':'PEP','PEP':'KO','V':'MA','MA':'V','GLD':'IAU','IAU':'GLD','SPY':'IVV','IVV':'SPY','MSFT':'AAPL','AAPL':'MSFT','JPM':'BAC','BAC':'JPM','XLE':'VDE','VDE':'XLE','BTC-USD':'ETH-USD','ETH-USD':'BTC-USD'}

def make_panel(db,horizon=5):
    store=HistoryStore(db);u=load_universe(db);parts=[];series={};daily={};calendar=db.setting('research_calendar',{}).get('sessions',[]);expected=pd.DatetimeIndex([v['date'] for v in calendar]);macro={}
    for name in ['FEDFUNDS','UNRATE','T10Y2Y']:
        records=db.records('macro_initial',name,limit=1)
        if records:
            macro[name]=[{'time':(pd.Timestamp(o['realtime_start']).tz_localize('America/New_York')+pd.Timedelta(days=1)).tz_convert('UTC'),'value':float(o['value'])} for o in records[0]['payload']['observations'] if o['value']!='.']
    for i in u.instruments:
        bars=store.read(i.symbol);raw=store.read(i.symbol,'raw')
        if min(len(bars),len(raw))<400:continue
        d,x,_=market_frame(bars);r=pd.DataFrame(raw).set_index('timestamp').reindex(d.timestamp).reset_index(drop=True);f=u.filters_for(i);adv=(r.close*r.volume).rolling(f.liquidity_window).mean();daily[i.symbol]=d
        liquid=(r.close>=f.minimum_price)&(r.volume.rolling(f.liquidity_window).mean()>=f.minimum_daily_volume)&(adv>=f.minimum_daily_dollar_volume)&(d.index>=f.minimum_history)
        if not i.active or i.halted:liquid&=False
        dates=pd.to_datetime(d.timestamp,utc=True).dt.tz_convert('America/New_York' if i.asset_class!='crypto' else 'UTC').dt.tz_localize(None).dt.normalize()
        sessions=pd.date_range(dates.iloc[0],dates.iloc[-1],freq='D') if i.asset_class=='crypto' else expected
        present=pd.Series(1.,index=pd.DatetimeIndex(dates)).groupby(level=0).max().reindex(sessions,fill_value=0)
        cov=present.rolling(60,min_periods=60).mean().reindex(pd.DatetimeIndex(dates)).to_numpy();liquid&=np.nan_to_num(cov)>=f.minimum_coverage
        known=pd.to_datetime(d.available_at,utc=True).dt.ceil('D')
        if u.policy=='archived_membership':liquid&=known>=pd.Timestamp(i.membership_known_at)
        x['breakout_20']=d.close/d.high.rolling(20).max().shift(1)-1;x['date']=known;x['label_end']=pd.to_datetime(d.timestamp.shift(-horizon-2),utc=True)
        x['gross_return']=d.open.shift(-horizon-2)/d.open.shift(-2)-1;x['symbol']=i.symbol;x['asset_class']=i.asset_class
        x['liquidity_bucket']=np.where(adv>=100e6,'deep',np.where(adv>=20e6,'liquid','limited'));x['market_cap_bucket']='unknown';x['adv']=adv
        # No verified historical market-cap archive: conservatively cost all stocks as unknown-cap.
        x['cost']=np.where((adv<20e6)|(i.asset_class=='stock'),.011,.0022);x['net_return']=x.gross_return-x.cost
        x['regime']=np.where(x.regime_trend==1,'uptrend',np.where(x.regime_trend==-1,'downtrend','range'))
        for name,rows in macro.items():x['macro_'+name]=backward(d.available_at,rows,'100 days').value
        if db.setting('form4_coverage_'+i.symbol,{}).get('complete_window'):
            sec=historical_features(db,i.symbol,d.available_at)
            for name in sec:x[name]=sec[name]
        funding=db.records('funding_history',i.symbol.split('-')[0],limit=1) if i.asset_class=='crypto' else []
        if funding:
            z=[{'time':pd.Timestamp(v['time'],unit='ms',tz='UTC')+pd.Timedelta(hours=1),'funding_paid':float(v['fundingRate']),'funding_premium':float(v['premium'])} for v in funding[0]['payload']['rows']];aligned=backward(d.available_at,z,'2 hours')
            for name in ['funding_paid','funding_premium']:x[name]=aligned[name]
        x['eligible']=liquid;x['close']=d.close;parts.append(x);series[i.symbol]=store.manifest(i.symbol)['id']
    p=pd.concat(parts,ignore_index=True).sort_values(['date','symbol'])
    # Strictly contemporaneous transforms, by asset class; no future returns used in features.
    for name in ['return_20','realized_volatility','adv']:
        rank={'return_20':'momentum_rank','realized_volatility':'volatility_rank','adv':'liquidity_rank'}[name]
        p[rank]=p[name].where(p.eligible).groupby([p.date,p.asset_class]).rank(pct=True)
    p['relative_momentum']=p.return_20-p.return_20.where(p.eligible).groupby([p.date,p.asset_class]).transform('median')
    p['relative_volatility']=p.realized_volatility/p.realized_volatility.where(p.eligible).groupby([p.date,p.asset_class]).transform('median').replace(0,np.nan)
    p['pair_zscore']=np.nan;p['pair_return_20']=np.nan
    for symbol,peer in PAIRS.items():
        if peer not in daily:continue
        ids=p.index[p.symbol==symbol];a=p.loc[ids];b=daily[peer];aligned=backward(a.date,[{'time':pd.Timestamp(t),'close':float(c)} for t,c in zip(b.available_at,b.close)],'4 days');ratio=np.log(a.close.to_numpy()/aligned.close.to_numpy());v=pd.Series(ratio)
        p.loc[ids,'pair_zscore']=((v-v.rolling(60).mean())/v.rolling(60).std()).to_numpy();p.loc[ids,'pair_return_20']=v.diff(20).to_numpy()
    # Benchmark labels are aligned by future realized holding interval, not the decision date alone.
    spy=daily.get('SPY');benchmark={}
    if spy is not None:
        for t,y in zip(pd.to_datetime(spy.available_at,utc=True).dt.ceil('D'),spy.open.shift(-horizon-2)/spy.open.shift(-2)-1):benchmark[t]=y
    p['benchmark_return']=p.date.map(benchmark)
    p['relative_return']=p.gross_return-p.gross_return.where(p.eligible).groupby([p.date,p.asset_class]).transform('mean')
    p['future_rank']=p.gross_return.where(p.eligible).groupby([p.date,p.asset_class]).rank(pct=True)
    p['excess_after_cost']=p.net_return-p.benchmark_return
    return p.replace([np.inf,-np.inf],np.nan),series

def fit_model(train,cal,features,target='net_return',label_target='net_return'):
    names=[c for c in features if c in train and train[c].notna().mean()>=.8 and train[c].nunique()>1]
    if not names or len(train)<64 or len(cal)<20:raise ValueError('Insufficient training-only family coverage')
    train=train.dropna(subset=[target,label_target]);cal=cal.dropna(subset=[target,label_target]);medians=train[names].median();scaler=StandardScaler();x=scaler.fit_transform(train[names].fillna(medians));z=scaler.transform(cal[names].fillna(medians));y=train[target].to_numpy();label=(train[label_target]>0).astype(int)
    if label.nunique()<2 or (cal[label_target]>0).nunique()<2:raise ValueError('Insufficient label classes')
    reg=Ridge(alpha=100).fit(x,y);clf=LogisticRegression(C=.01,max_iter=300).fit(x,label)
    calibrator=LogisticRegression(C=1,max_iter=300).fit(clf.decision_function(z).reshape(-1,1),(cal[label_target]>0).astype(int))
    residual=float(np.std(cal[target]-reg.predict(z)));prior=float(label.mean())
    return {'columns':names,'medians':medians.to_dict(),'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'return_coef':reg.coef_.tolist(),'return_intercept':float(reg.intercept_),'logit_coef':clf.coef_[0].tolist(),'logit_intercept':float(clf.intercept_[0]),'calibration_coef':float(calibrator.coef_[0][0]),'calibration_intercept':float(calibrator.intercept_[0]),'uncertainty':residual,'prior':prior,'target':target,'label_target':label_target,'target_baseline':float(train[target].mean()) if target=='future_rank' else 0.}

def predict(model,frame):
    names=model['columns'];x=frame.reindex(columns=names).fillna(pd.Series(model['medians']));x=x.clip(pd.Series(model['clip_lower']),pd.Series(model['clip_upper']),axis=1) if model.get('clip_lower') else x;x=(x.to_numpy()-model['mean'])/model['scale'];expected=x@np.array(model['return_coef'])+model['return_intercept'];raw=x@np.array(model['logit_coef'])+model['logit_intercept'];prob=1/(1+np.exp(-np.clip(raw*model['calibration_coef']+model['calibration_intercept'],-35,35)));return expected,prob

def metrics(z,model=None,target='net_return',label_target='net_return'):
    if z.empty:return None
    z=z.dropna(subset=[target,label_target,'predicted','probability']);trade=(z.predicted>0)&(z.probability>.55)&~z.missing_features
    if target!='net_return':trade=pd.Series(False,index=z.index)
    strategy=z.net_return.where(trade,0);by_date=strategy.groupby(z.date).mean()
    return {'trade_rule_available':target=='net_return','asset_rows':len(z),'nonoverlapping_date_clusters':int(z.date.nunique()),'mse':float(mean_squared_error(z[target],z.predicted)),'zero_mse':float(np.mean((z[target]-z.get('target_baseline',0))**2)),'brier':float(brier_score_loss(z[label_target]>0,z.probability)),'base_rate_brier':float(brier_score_loss(z[label_target]>0,z.prior)),'trade_observations':int(trade.sum()),'no_trade_observations':int((~trade).sum()),'mean_net_strategy_return':float(by_date.mean()),'cash_return':0.,'mean_buy_hold_return':float(z.groupby('date').gross_return.mean().mean()),'simple_momentum_after_cost':float(z.net_return.where(z.return_20>0,0).groupby(z.date).mean().mean()),'simple_mean_reversion_after_cost':float(z.net_return.where(z.rsi<30,0).groupby(z.date).mean().mean()),'mean_predicted_target':float(z.predicted.mean())}

def sample_intervals(panel,dates,lo,hi):
    candidates=panel[panel.date.isin(dates[lo:hi])];ends=candidates.groupby('date').label_end.max();chosen=[];last=None
    for date,end in ends.items():
        if last is None or date>last:chosen.append(date);last=end
    return candidates[candidates.date.isin(chosen)]

def prepare(db):
    p,series=make_panel(db)
    digest=hashlib.sha256(pd.util.hash_pandas_object(p,index=True).values.tobytes()).hexdigest()
    from backend.research.universe import ROOT
    path=ROOT/'data/strategy_panels'/(digest+'.parquet');path.parent.mkdir(exist_ok=True,parents=True)
    if not path.exists():p.to_parquet(path,index=False)
    return p,series,{'panel_hash':digest,'file_hash':hashlib.sha256(path.read_bytes()).hexdigest(),'evidence_ids':{kind:sorted(r['id'] for r in db.records(kind,limit=20000)) for kind in ['historical_form4','macro_initial','funding_history']}}

def run(db,release=False,prepared=None):
    p,series,snapshot=prepared or prepare(db);p=p[p.eligible & p.net_return.notna()];dates=sorted(p.loc[p.asset_class!='crypto','date'].unique());n=len(dates);gap=7;fit_end=int(n*.60);cal_end=int(n*.70);val_end=int(n*.85)
    # Choose nonoverlapping label intervals, not a 7-calendar-day weekday alias.
    def sample(lo,hi):return sample_intervals(p,dates,lo,hi)
    fit=sample(60,fit_end-gap);fit=fit[fit.label_end<dates[fit_end]]
    cal=sample(fit_end,cal_end-gap);cal=cal[cal.label_end<dates[cal_end]]
    val=sample(cal_end,val_end-gap);val=val[val.label_end<dates[val_end]]
    test=sample(val_end,n-gap)
    identity={'version':VERSION,'series':series,'universe':load_universe(db).model_dump(mode='json'),'horizon':5,'sampling':'nonoverlapping maximum label-end intervals','families':FAMILIES,'snapshot':snapshot,'boundaries':[str(dates[k]) for k in [fit_end,cal_end,val_end]],'cost_rule':'110 bps round trip limited-liquidity or unknown-cap stock; otherwise 22 bps'};rid='strategies_'+stable_hash(identity);previous=db.get(rid);released=db.get(rid+'_released')
    if released:return released['payload']
    if previous and not release:return previous['payload']
    trials=[];models=[]
    with threadpool_limits(limits=1):
        for family,names in FAMILIES.items():
            for asset_class in ['stock','etf','crypto']:
                a=fit[fit.asset_class==asset_class];b=cal[cal.asset_class==asset_class]
                if family=='pairs_relative_value':a=a[a.symbol.isin(PAIRS)];b=b[b.symbol.isin(PAIRS)]
                try:
                    model=fit_model(a,b,names)
                    if family=='crypto_funding' and not any(c.startswith('funding_') for c in model['columns']):raise ValueError('Funding unavailable in early training period')
                    if family=='macro_regime' and not any(c.startswith('macro_') for c in model['columns']):raise ValueError('Macro family lacks training coverage')
                except ValueError as e:trials.append({'family':family,'asset_class':asset_class,'status':'INELIGIBLE','reason':str(e)});continue
                mid='strategy_model_'+stable_hash([rid,family,asset_class]);model.update({'id':mid,'family':family,'asset_class':asset_class,'data_version':rid,'fitted_at':now().isoformat(),'horizon':5,'promotion_eligible':False,'feature_available_before':str(dates[cal_end])})
                result={'family':family,'asset_class':asset_class,'status':'RESEARCH_ONLY','model_id':mid,'features':model['columns'],'training_rows':len(a),'training_date_clusters':int(a.date.nunique()),'calibration_date_clusters':int(b.date.nunique())}
                for label,data in [('validation',val),*([('holdout',test)] if release else [])]:
                    z=data[data.asset_class==asset_class].copy();z=z.dropna(subset=['net_return'])
                    if family=='pairs_relative_value':z=z[z.symbol.isin(PAIRS)]
                    if z.empty:continue
                    z['predicted'],z['probability']=predict(model,z);z['prior']=model['prior'];z['target_baseline']=model['target_baseline'];z['missing_features']=z.reindex(columns=model['columns']).isna().any(axis=1);result[label]=metrics(z)
                    result[label+'_by']={field:{str(k):metrics(group) for k,group in z.groupby(field)} for field in ['regime','liquidity_bucket','market_cap_bucket','symbol']}
                result['development_improved']=bool(result.get('validation') and result['validation']['mse']<result['validation']['zero_mse'] and result['validation']['brier']<result['validation']['base_rate_brier'] and result['validation']['mean_net_strategy_return']>0)
                trials.append(result);models.append(model)
        # Compare per-asset, asset-class pooled and cross-sectional ranks for multiple labels.
        approaches=[];columns=['return_5','return_20','rsi','realized_volatility','ma20_to_ma60'];usfit=fit[fit.asset_class!='crypto'];uscal=cal[cal.asset_class!='crypto']
        for target,label_target in [('relative_return','relative_return'),('future_rank','relative_return'),('excess_after_cost','excess_after_cost')]:
            individual={};excluded={}
            for symbol,a in usfit.groupby('symbol'):
                try:individual[symbol]=fit_model(a,uscal[uscal.symbol==symbol],columns,target,label_target)
                except ValueError as e:excluded[symbol]=str(e)
            common=set(individual);target_fit=usfit[usfit.symbol.isin(common)];target_cal=uscal[uscal.symbol.isin(common)]
            for scope in ['per_asset','asset_class','cross_sectional_ranking']:
                features=columns+(['momentum_rank','volatility_rank','liquidity_rank'] if scope=='cross_sectional_ranking' else []);key='symbol' if scope=='per_asset' else 'asset_class' if scope=='asset_class' else None;groups=list(target_fit.groupby(key)) if key else [('pooled',target_fit)];pieces={'validation':[],'holdout':[]};skipped={}
                for name,a in groups:
                    b=target_cal[target_cal[key]==name] if key else target_cal
                    try:model=individual[name] if scope=='per_asset' else fit_model(a,b,features,target,label_target)
                    except ValueError as e:
                        skipped[str(e)]=skipped.get(str(e),0)+1;continue
                    for label,data in [('validation',val),*([('holdout',test)] if release else [])]:
                        z=data[(data.asset_class!='crypto') & data.symbol.isin(common) & (data[key]==name if key else True)].dropna(subset=[target,label_target]).copy()
                        if z.empty:continue
                        z['predicted'],z['probability']=predict(model,z);z['prior']=model['prior'];z['target_baseline']=model['target_baseline'];z['missing_features']=z.reindex(columns=model['columns']).isna().any(axis=1);pieces[label].append(z)
                item={'scope':scope,'common_asset_count':len(common),'excluded_assets':excluded,'target':target,'probability_target':label_target,'algorithm':'standardized ridge + logistic + separate temporal sigmoid calibration','promotion_eligible':False}
                for label in ['validation',*(['holdout'] if release else [])]:
                    if not pieces[label]:item[label]=None;continue
                    z=pd.concat(pieces[label]);value=metrics(z,target=target,label_target=label_target);ics=[];winner=[]
                    for _,day in z.groupby('date'):
                        if len(day)<4:continue
                        ic=day.predicted.corr(day[target],method='spearman')
                        if np.isfinite(ic):ics.append(float(ic))
                        winner.append(float(day.sort_values('predicted').iloc[-1].net_return))
                    value['rank_ic']=float(np.mean(ics)) if ics else None;value['top_rank_mean_net_return']=float(np.mean(winner)) if winner else None;item[label]=value
                item['skipped_groups']=skipped;approaches.append(item)
                print(scope,target,'completed',flush=True)
    selection={t:{k:v for k,v in min([a for a in approaches if a['target']==t and a.get('validation')],key=lambda a:a['validation']['mse']/max(a['validation']['zero_mse'],1e-12)+a['validation']['brier']/max(a['validation']['base_rate_brier'],1e-12)).items() if k in ('scope','target','algorithm')} for t in ['relative_return','future_rank','excess_after_cost']}
    result={'id':rid,'created_at':now().isoformat(),'identity':identity,'asset_count':int(p.symbol.nunique()),'history_rows':len(p),'family_results':trials,'approaches':approaches,'selection':selection,'holdout_status':'RELEASED_ONCE' if release else 'LOCKED','independent_clusters':{'fit':int(fit.date.nunique()),'calibration':int(cal.date.nunique()),'validation':int(val.date.nunique()),'holdout':int(test.date.nunique())},'unavailable':{'earnings_event':'No verified timestamped historical earnings-surprise archive','13f':'No verified historical CUSIP-to-instrument mapping and amended-holdings panel','historical_basis_open_interest':'Funding premium is not a dated derivative basis or historical open-interest series'},'promotion_eligible':False,'limitations':['Retrospective universe; no survivorship-free membership or delisting-return guarantee.','Daily-open labels are return diagnostics, not executable prices. No arbitrary-size OHLCV fills.','Date clusters have nonoverlapping outcomes, but serial, regime and cross-asset dependence remains.','Current market caps are unavailable; all historical market-cap buckets stay unknown.','Pairs use predefined relative-value features, not a validated cointegration or executable two-leg strategy.','Calibration is fit in a separate earlier period; it can drift and is not a guarantee.','No holdout-driven architecture selection or automatic promotion.']}
    if release:
        if not previous or previous['payload']['selection']!=selection:raise ValueError('Freeze unchanged development selection before release')
        db.put('strategy_study',result,record_id=rid+'_released');db.set_setting('strategy_latest',{'id':rid+'_released'})
    else:
        for model in models:db.put('strategy_model',model,record_id=model['id'])
        db.put('strategy_study',result,record_id=rid);db.set_setting('strategy_latest',{'id':rid})
    return result

_LATEST={}
def strategy_prediction(db,model_id,symbol):
    model=db.get(model_id)['payload'];u=load_universe(db);manifests={i.symbol:(HistoryStore(db).manifest(i.symbol) or {}).get('id') for i in u.instruments};signature=stable_hash([manifests,now().date().isoformat()])
    if _LATEST.get('signature')!=signature:
        panel,_=make_panel(db);_LATEST.update(signature=signature,rows=available_panel(panel).sort_values('date').groupby('symbol').tail(1).set_index('symbol'))
    row=_LATEST['rows'].loc[[symbol]];expected,probability=predict(model,row);missing=[c for c in model['columns'] if c not in row or pd.isna(row.iloc[0][c])];values=row.reindex(columns=model['columns']).iloc[0].fillna(pd.Series(model['medians']));cost=float(row.iloc[0]['cost'])
    return {'model_id':model_id,'model_hash':stable_hash(model),'symbol':symbol,'features':{k:float(v) for k,v in values.items()},'imputed_features':missing,'feature_available_at':str(row.iloc[0].date),'feature_families':[model['family']],'strategy_family':model['family'],'liquidity_bucket':row.iloc[0].liquidity_bucket,'market_cap_bucket':'unknown','asset_class':row.iloc[0].asset_class,'data_version':manifests[symbol],'entry_delay_bars':2,'prediction':float(expected[0]+cost),'expected_return_after_cost':float(expected[0]),'estimated_research_cost':cost,'probability':float(probability[0]),'probability_target':'positive_after_cost','uncertainty':model['uncertainty'],'horizon':5,'regime':row.iloc[0].regime}

def available_panel(panel,at=None):
    """Conservative daily availability buckets must have elapsed before live use."""
    return panel[pd.to_datetime(panel.date,utc=True)<=pd.Timestamp(at or now())]

def publish_current_forecasts(db,prepared=None):
    """Publish descriptive research forecasts without creating orders or evaluation outcomes."""
    pointer=db.setting('strategy_latest')
    if not pointer:return {'count':0}
    study=db.get(pointer['id'])['payload'];p,manifests=prepared or make_panel(db);latest=available_panel(p).sort_values('date').groupby('symbol').tail(1);count=0
    for asset_class in ['stock','etf','crypto']:
        candidates=[r for r in study['family_results'] if r['asset_class']==asset_class and r.get('validation') and r['family']!='pairs_relative_value']
        if not candidates:continue
        winner=min(candidates,key=lambda r:r['validation']['mse']/max(r['validation']['zero_mse'],1e-12)+r['validation']['brier']/max(r['validation']['base_rate_brier'],1e-12));model=db.get(winner['model_id'])['payload']
        rows=latest[latest.asset_class==asset_class];expected,prob=predict(model,rows)
        for (_,row),value,probability in zip(rows.iterrows(),expected,prob):
            missing=[c for c in model['columns'] if c not in row or pd.isna(row[c])]
            if missing or not row.eligible:continue
            forecast={'symbol':row.symbol,'model_id':model['id'],'model_hash':stable_hash(model),'strategy_family':model['family'],'model_prediction':float(value),'probability':float(probability),'uncertainty':model['uncertainty'],'feature_available_at':str(row.date),'published_at':now().isoformat(),'features':{c:float(row[c]) for c in model['columns']},'history_id':manifests[row.symbol],'horizon':5,'target':'return after estimated costs','probability_target':'positive return after estimated costs','regime':row.regime,'promotion_eligible':False,'selection':'lowest development-only normalized MSE plus Brier; never holdout selection','status':'experimental research forecast; not a trade recommendation'}
            rid='research_forecast_'+stable_hash([model['id'],forecast['history_id'],forecast['feature_available_at'],forecast['features']]);db.put('research_forecast',forecast,row.symbol,record_id=rid);count+=1
    db.set_setting('product_summary_cache',{});return {'count':count,'study':study['id']}
