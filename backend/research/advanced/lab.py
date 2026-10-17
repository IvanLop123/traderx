"""Reproducible retrospective challenger comparisons, not a promotion service."""
import hashlib,json,math,platform
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit,logsumexp
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge,LogisticRegression
from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.covariance import LedoitWolf
from sklearn.metrics import mean_squared_error,brier_score_loss
from threadpoolctl import threadpool_limits
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.research.strategies import sample_intervals
from backend.research.advanced.models import deep_fit,allocation,by_adjust,block_test

FEATURES=['return_5','return_20','rsi','realized_volatility','ma20_to_ma60','momentum_rank','volatility_rank','liquidity_rank']
MODELS=['zero','historical_mean','momentum','mean_reversion','volatility','ridge','random_forest','gradient_boosting','pca_ridge','meta_label','stacking','ensemble_equal','ensemble_fixed','ensemble_dynamic','tcn','gru','transformer']
ALLOCATIONS=['equal','volatility_target','inverse_volatility','capped_edge','risk_parity','covariance_constrained']
EXITS=['reversal','edge_loss','deterioration','fixed_horizon','volatility_stop','risk_limit','trailing','profit_taking']
FOLDS=[('2022','2021-07-01','2022-01-01','2023-01-01'),('2023','2022-07-01','2023-01-01','2024-01-01'),('2024','2023-07-01','2024-01-01','2025-01-01')]

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [clean(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,np.integer):return int(value)
    return value

def datesample(p,start,end):
    x=p[(p.date>=pd.Timestamp(start,tz='UTC'))&(p.date<pd.Timestamp(end,tz='UTC'))&(p.label_end<pd.Timestamp(end,tz='UTC')-pd.Timedelta(days=7))];dates=sorted(x.date.unique());return sample_intervals(x,dates,0,len(dates)).copy()

def bounded(x,limit):
    return x.iloc[np.linspace(0,len(x)-1,min(limit,len(x)),dtype=int)].copy()

def sequences(full,frame,scaler,medians,length=12):
    positions={int(i):j for j,i in enumerate(frame.index)};out=np.zeros((len(frame),length,len(FEATURES)),np.float32)
    for symbol,g in full.groupby('symbol',sort=False):
        g=g.sort_values('date');x=scaler.transform(g[FEATURES].fillna(medians));idx={int(i):j for j,i in enumerate(g.index)}
        for i in frame.index[frame.symbol==symbol]:
            j=idx[int(i)];a=x[max(0,j-length+1):j+1];out[positions[int(i)],-len(a):]=a
    return out

def neutralize(frame,pred):
    z=frame.copy();z['pred']=pred;out=pd.Series(index=z.index,dtype=float)
    for _,g in z.groupby('date'):
        x=g[['momentum_rank','volatility_rank','liquidity_rank']].fillna(.5).to_numpy();x=np.column_stack([np.ones(len(x)),x]);out.loc[g.index]=g.pred-x@np.linalg.lstsq(x,g.pred,rcond=None)[0]
    return out.to_numpy()

def evaluate(frame,pred,cal,cpred):
    # Separate later calibration segment; probabilities are fitted only there.
    label=(cal.net_return>0).astype(int);prior=float(label.mean())
    if label.nunique()==2 and np.std(cpred)>1e-12:
        clf=LogisticRegression(C=1,max_iter=300).fit((cpred*100).reshape(-1,1),label);prob=clf.predict_proba((pred*100).reshape(-1,1))[:,1]
    else:prob=np.full(len(pred),prior)
    residual=np.abs(cal.net_return.to_numpy()-cpred);q=float(np.quantile(residual,min(1,math.ceil((len(residual)+1)*.9)/len(residual)),method='higher'))
    z=frame.copy();z['prediction']=pred;z['probability']=prob;ics=[];spreads=[];top=[];exposures=[];neutralics=[];previous=set();turnover=[];stability=[];priorranks=None
    npred=neutralize(frame,pred);z['neutral']=npred
    for _,g in z.groupby('date',sort=True):
        if len(g)<20 or g.prediction.nunique()<=1:continue
        if g.prediction.nunique()>1:ics.append(float(g.prediction.corr(g.gross_return,method='spearman')))
        if g.neutral.nunique()>1:neutralics.append(float(g.neutral.corr(g.gross_return,method='spearman')))
        k=max(1,len(g)//10);ranked=g.sort_values(['prediction','symbol']);lo=ranked.iloc[:k];hi=ranked.iloc[-k:];spreads.append(float(hi.gross_return.mean()-lo.gross_return.mean()-hi.cost.mean()-lo.cost.mean()));top.append(float(hi.net_return.mean()));selected=set(hi.symbol);turnover.append(len(selected^previous)/max(1,2*k));previous=selected
        ranks=g.set_index('symbol').prediction.rank(pct=True)
        if priorranks is not None:
            corr=ranks.corr(priorranks)
            if np.isfinite(corr):stability.append(float(corr))
        priorranks=ranks
        exposures.append({f:float(g.prediction.corr(g[f],method='spearman')) if g.prediction.nunique()>1 else None for f in ('momentum_rank','volatility_rank','liquidity_rank')})
    ece=0
    for lo in np.arange(0,1,.1):
        mask=(prob>=lo)&(prob<(lo+.1) if lo<.9 else prob<=1)
        if mask.any():ece+=mask.mean()*abs(prob[mask].mean()-(frame.net_return.to_numpy()[mask]>0).mean())
    curve=np.cumprod(1+np.array(top));dd=float(np.max(1-curve/np.maximum.accumulate(np.r_[1.,curve])[1:])) if len(curve) else 0
    by={key:{str(k):{'rows':len(g),'mse':float(np.mean((g.prediction-g.net_return)**2)),'mean_predicted_edge':float(g.prediction.mean()),'mean_net_return':float(g.net_return.mean())} for k,g in z.groupby(key)} for key in ['regime','liquidity_bucket','market_cap_bucket']}
    return {'rows':len(z),'assets':int(z.symbol.nunique()),'date_clusters':int(z.date.nunique()),'mse':float(mean_squared_error(z.net_return,pred)),'rank_ic':block_test(ics),'factor_neutral_rank_ic':block_test(neutralics),'rank_stability':float(np.mean(stability)) if stability else None,'top_decile_net_return':block_test(top),'long_short_decile_after_cost':block_test(spreads),'brier':float(brier_score_loss(z.net_return>0,prob)),'prior_brier':float(brier_score_loss(z.net_return>0,np.full(len(z),prior))),'ece':float(ece),'interval_90_radius':q,'interval_test_coverage':float((np.abs(z.net_return-pred)<=q).mean()),'positive_but_uncertain':int(((pred>0)&(pred<q)).sum()),'maximum_drawdown':dd,'top_decile_membership_turnover':float(np.mean(turnover)) if turnover else None,'mean_roundtrip_cost':float(z.cost.mean()),'factor_exposures':{f:float(np.nanmean([x[f] if x[f] is not None else np.nan for x in exposures])) if any(x[f] is not None for x in exposures) else None for f in ['momentum_rank','volatility_rank','liquidity_rank']},'by':by}

def statistical(full,train_end,test_start,test_end):
    from statsmodels.tsa.stattools import coint
    d=full.pivot_table(index='date',columns='symbol',values='close').sort_index();train=d[d.index<pd.Timestamp(train_end,tz='UTC')];test=d[(d.index>=pd.Timestamp(test_start,tz='UTC'))&(d.index<pd.Timestamp(test_end,tz='UTC'))];pairs=[]
    for a,b in [('XOM','CVX'),('KO','PEP'),('V','MA'),('GLD','IAU'),('MSFT','AAPL')]:
        if a not in d or b not in d:continue
        tr=np.log(train[[a,b]].dropna().tail(1000));te=np.log(test[[a,b]].dropna())
        if len(tr)<252 or len(te)<40:continue
        beta=np.linalg.lstsq(np.column_stack([np.ones(len(tr)),tr[b]]),tr[a],rcond=None)[0];p=float(coint(tr[a],tr[b],maxlag=5,autolag=None)[1]);residual=tr[a]-beta[0]-beta[1]*tr[b];scale=float(residual.std());spread=te[a]-beta[0]-beta[1]*te[b];z=(spread-residual.mean())/max(scale,1e-9)
        theta=beta.copy();cov=np.eye(2);innov=[];fixed=[]
        for _,row in te.iterrows():
            x=np.array([1.,row[b]]);err=row[a]-x@theta;innov.append(err);fixed.append(row[a]-x@beta);cov+=np.eye(2)*1e-5;k=cov@x/(.001+x@cov@x);theta+=k*err;cov-=np.outer(k,x)@cov
        # Two-leg next-open costs/borrow unavailable: descriptive spread reversion only.
        pairs.append({'pair':[a,b],'training_cointegration_p':p,'test_spread_lag1':float(spread.autocorr()),'test_zscore_std':float(z.std()),'kalman_one_step_rmse':float(np.sqrt(np.mean(np.array(innov)**2))),'fixed_relationship_rmse':float(np.sqrt(np.mean(np.array(fixed)**2))),'executable_pnl':None,'reason':'No validated two-leg borrow/fill archive; never treated as a tradable pair'})
    if pairs:
        for row,q in zip(pairs,by_adjust([r['training_cointegration_p'] for r in pairs])):row['cointegration_BY_q']=q
    # SPY known close-to-close return; forecasts made before each next return arrives.
    series=np.log(d['SPY'].dropna()).diff().dropna() if 'SPY' in d else pd.Series(dtype=float);tr=series[series.index<pd.Timestamp(test_start,tz='UTC')];te=series[(series.index>=pd.Timestamp(test_start,tz='UTC'))&(series.index<pd.Timestamp(test_end,tz='UTC'))];vol={};regime={}
    if len(tr)>500 and len(te)>50:
        from arch import arch_model
        from hmmlearn.hmm import GaussianHMM
        fit=arch_model(tr.to_numpy()*100,mean='Zero',vol='GARCH',p=1,q=1,rescale=False).fit(disp='off',show_warning=False);pars=fit.params;ew=float(tr.var());gv=float(fit.conditional_volatility[-1]**2/10000);last=float(tr.iloc[-1]);ep=[];gp=[]
        for value in te:
            ew=.94*ew+.06*last**2;gv=pars['omega']/10000+pars['alpha[1]']*last**2+pars['beta[1]']*gv;ep.append(ew);gp.append(gv);last=float(value)
        truth=te.to_numpy()**2;vol={'ewma_mse':float(np.mean((truth-ep)**2)),'garch_mse':float(np.mean((truth-gp)**2)),'observations':len(te),'target':'Next observed squared daily SPY log return; noisy variance proxy','garch_parameters':dict(pars)}
        hmm=GaussianHMM(2,covariance_type='diag',n_iter=100,random_state=41).fit((tr.to_numpy()*100).reshape(-1,1));posterior=hmm.startprob_;variances=hmm.covars_.reshape(-1);means=hmm.means_.reshape(-1);pred=[];counts=[0,0]
        for value in np.r_[tr.to_numpy(),te.to_numpy()]:
            forecast=posterior@hmm.transmat_;pred.append(float(forecast@(variances+means**2)/10000));loglik=-.5*(np.log(2*np.pi*variances)+(value*100-means)**2/variances);post=np.log(np.maximum(forecast,1e-30))+loglik;posterior=np.exp(post-logsumexp(post));counts[int(posterior.argmax())]+=1
        regime={'hmm_variance_mse':float(np.mean((truth-np.array(pred[-len(te):]))**2)),'states':2,'filter':'Forward-only filtering, never backward smoothing over future returns','training_converged':bool(hmm.monitor_.converged)}
    return {'pairs':pairs,'volatility':vol,'regime':regime}

def portfolio_compare(full,train,test,pred):
    symbols=sorted(test.symbol.unique());returns=full[full.symbol.isin(symbols)].pivot_table(index='date',columns='symbol',values='return_1').sort_index();hist=returns[returns.index<pd.Timestamp(test.date.min())].tail(252).reindex(columns=symbols).fillna(0);cov=LedoitWolf().fit(hist).covariance_;ids={s:i for i,s in enumerate(symbols)};z=test.copy();z['pred']=pred;values={m:[] for m in ALLOCATIONS}
    for date,g in z.groupby('date'):
        top=g[g.pred>0].nlargest(max(1,len(g)//10),'pred');ix=[ids[s] for s in top.symbol];c=cov[np.ix_(ix,ix)]
        for method in ALLOCATIONS:
            w=allocation(method,top.pred.to_numpy(),top.realized_volatility.to_numpy(),c,top.adv.to_numpy());values[method].append({'date':str(date),'net':float(w@top.net_return.to_numpy()),'cost':float(w@top.cost.to_numpy()),'gross_exposure':float(w.sum()),'maximum_weight':float(w.max()) if len(w) else 0.,'turnover':float(w.sum()*2)})
    result={}
    for m,rows in values.items():
        v=np.array([r['net'] for r in rows]);curve=np.cumprod(1+v);result[m]={'return':block_test(v),'cumulative_return':float(curve[-1]-1) if len(v) else 0.,'maximum_drawdown':float(np.max(1-curve/np.maximum.accumulate(np.r_[1.,curve])[1:])) if len(v) else 0.,'average_gross':float(np.mean([r['gross_exposure'] for r in rows])),'cost_drag':float(sum(r['cost'] for r in rows)),'turnover':float(sum(r['turnover'] for r in rows)),'maximum_position':max((r['maximum_weight'] for r in rows),default=0),'basis':'Nonoverlapping holding intervals, cash between intervals; full entry/exit costs; missing covariance observations use zero returns; this may understate risk and prevents qualification'}
    return result

def run(db,panel_path=None):
    from backend.research.universe import ROOT
    path=Path(panel_path) if panel_path else sorted((ROOT/'data/strategy_panels').glob('*.parquet'))[-1]
    identity={'version':'advanced-quant-v2','implementation':hashlib.sha256(b''.join(Path(__file__).with_name(f).read_bytes() for f in ['lab.py','models.py','exits.py'])).hexdigest(),'panel_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'folds':FOLDS,'models':MODELS,'features':FEATURES,'sequence_length':12,'deep_epochs':5,'max_fit_rows':18000,'max_cal_rows':8000,'embargo_days':7,'horizon_sessions':5,'allocations':ALLOCATIONS,'exit_rules':EXITS,'seed':41,'status':'Retrospective development; historical periods inspected in earlier phases','promotion_eligible':False}
    rid='advanced_'+stable_hash(identity);saved=db.get(rid)
    if saved:return saved['payload']
    db.put('advanced_plan',{'id':rid,'registered_at':now().isoformat(),'identity':identity,'future_untouched_holdout':'Only subsequently preregistered scientific evidence qualifies; manual/shadow outcomes never imported'},record_id=rid+'_plan')
    full=pd.read_parquet(path)
    from backend.research.history import HistoryStore
    store=HistoryStore(db);full['execution_open']=np.nan
    for symbol,g in full.groupby('symbol'):
        bars=store.read(symbol)
        if bars:
            # Same source close identifies each panel row; use ordered timestamps, never guess a price.
            from backend.research.features import market_frame
            daily,_,_=market_frame(bars);mapping=dict(zip(pd.to_datetime(daily.available_at,utc=True).dt.ceil('D'),daily.open));full.loc[g.index,'execution_open']=g.date.map(mapping)
    full=full[full.asset_class.isin(['stock','etf'])].sort_values(['date','symbol']);eligible=full[full.eligible & full.net_return.notna() & full[FEATURES].notna().all(axis=1)];folds=[];failures=[]
    with threadpool_limits(limits=2):
        for name,cal_start,start,end in FOLDS:
            print('Advanced fold',name,flush=True);train=bounded(datesample(eligible,'2015-01-01',cal_start),18000);cal=bounded(datesample(eligible,cal_start,start),8000);test=datesample(eligible,start,end)
            cd=sorted(cal.date.unique());cut=cd[len(cd)//2];ca=cal[cal.label_end<cut-pd.Timedelta(days=7)];cb=cal[cal.date>=cut];med=train[FEATURES].median();sc=StandardScaler().fit(train[FEATURES].fillna(med));x=sc.transform(train[FEATURES]);a=sc.transform(ca[FEATURES]);b=sc.transform(cb[FEATURES]);t=sc.transform(test[FEATURES]);y=train.net_return.to_numpy();yp=ca.net_return.to_numpy();preds={};ap={};bp={};details={};feature_importance={}
            for key,value in [('zero',0.),('historical_mean',float(y.mean()))]:ap[key]=np.full(len(a),value);bp[key]=np.full(len(b),value);preds[key]=np.full(len(t),value)
            models={'ridge':Ridge(alpha=100),'random_forest':RandomForestRegressor(n_estimators=60,max_depth=5,min_samples_leaf=100,n_jobs=2,random_state=41),'gradient_boosting':HistGradientBoostingRegressor(max_iter=60,max_leaf_nodes=15,l2_regularization=100,random_state=41)}
            for key,model in models.items():
                model.fit(x,y);ap[key]=model.predict(a);bp[key]=model.predict(b);preds[key]=model.predict(t)
                feature_importance[key]=dict(zip(FEATURES,(model.coef_ if hasattr(model,'coef_') else model.feature_importances_).tolist())) if hasattr(model,'coef_') or hasattr(model,'feature_importances_') else {'unavailable':'No impurity importance; use separate perturbation research'}
            pca=PCA(4,random_state=41).fit(x);reg=Ridge(alpha=100).fit(pca.transform(x),y);ap['pca_ridge']=reg.predict(pca.transform(a));bp['pca_ridge']=reg.predict(pca.transform(b));preds['pca_ridge']=reg.predict(pca.transform(t));details['pca_ridge']={'explained_variance':pca.explained_variance_ratio_.tolist(),'loadings':pca.components_.tolist()}
            family_columns={'momentum':[0,1],'mean_reversion':[2],'volatility':[3,6]};family={}
            for key,ix in family_columns.items():
                m=Ridge(alpha=100).fit(x[:,ix],y);family[key]=(m.predict(a[:,ix]),m.predict(b[:,ix]),m.predict(t[:,ix]));ap[key],bp[key],preds[key]=family[key]
            # Fixed and contextual weights use only earlier calibration A, then freeze.
            raw=np.array([max(.25,min(1,1-mean_squared_error(yp,f[0])/max(np.mean(yp**2),1e-12))) for f in family.values()]);fw=raw/raw.sum();details['ensemble_fixed']={'weights':dict(zip(family,fw.tolist())),'fit_period':'earlier calibration A'}
            for name2 in ['ensemble_equal','ensemble_fixed','ensemble_dynamic']:
                w=np.ones(3)/3 if name2=='ensemble_equal' else fw
                ap[name2]=np.column_stack([f[0] for f in family.values()])@w;bp[name2]=np.column_stack([f[1] for f in family.values()])@w;preds[name2]=np.column_stack([f[2] for f in family.values()])@w
                if name2=='ensemble_dynamic':
                    conditional={}
                    for field in ['asset_class','regime','liquidity_bucket']:
                        for value,g in ca.groupby(field):
                            n=g.date.nunique()
                            if n<30:continue
                            ids=ca.index.get_indexer(g.index);errors=np.array([np.mean((g.net_return-f[0][ids])**2) for f in family.values()]);skill=1/np.maximum(errors,1e-6);skill/=skill.sum();w2=(n/(n+120))*skill+(120/(n+120))*fw;conditional[field+':'+str(value)]=w2.tolist()
                    for frame,dest,index in [(cb,bp,1),(test,preds,2)]:
                        mats=np.column_stack([f[index] for f in family.values()]);ws=np.tile(fw,(len(frame),1))
                        for i,(_,row) in enumerate(frame.iterrows()):
                            allowed=[conditional[field+':'+str(row[field])] for field in ['asset_class','regime','liquidity_bucket'] if field+':'+str(row[field]) in conditional]
                            if allowed:ws[i]=np.mean(allowed,axis=0)
                        dest[name2]=(mats*ws).sum(axis=1)
                    details[name2]={'conditional_weights':conditional,'minimum_independent_dates':30,'prior_dates':120,'unavailable':['Dated sector/industry','Prospective calibration not available in retrospective folds'],'fallback':'Fixed weights when evidence insufficient'}
            keys=['ridge','random_forest','gradient_boosting'];stack=Ridge(alpha=10).fit(np.column_stack([ap[k] for k in keys])*100,yp);bp['stacking']=stack.predict(np.column_stack([bp[k] for k in keys])*100);preds['stacking']=stack.predict(np.column_stack([preds[k] for k in keys])*100)
            meta=LogisticRegression(C=.1,max_iter=300).fit(np.column_stack([ap[k] for k in keys])*100,yp>0)
            for source in [bp,preds]:gate=meta.predict_proba(np.column_stack([source[k] for k in keys])*100)[:,1]>=.55;source['meta_label']=source['ridge']*gate
            print('Numerical baselines fitted',flush=True);seqx=sequences(full,train,sc,med);seqb=sequences(full,cb,sc,med);seqt=sequences(full,test,sc,med)
            for key in ['tcn','gru','transformer']:
                try:bp[key],preds[key],details[key]=deep_fit(key,seqx,y,seqb,seqt);print(key,'fitted',flush=True)
                except ImportError as e:failures.append({'fold':name,'model':key,'status':'DEPENDENCY_UNAVAILABLE','reason':str(e)})
            results={k:evaluate(test,v,cb,bp[k]) for k,v in preds.items() if k in MODELS};corr=pd.DataFrame(preds).corr().replace({np.nan:None}).to_dict();alloc=portfolio_compare(full,train,test,preds['ridge'])
            from backend.research.advanced.exits import compare
            exits=compare(full,train,cal_start,start,end,FEATURES,sc)
            out={'exit_comparison':exits,'fold':name,'train':{'start':str(train.date.min()),'end':str(train.label_end.max()),'rows':len(train)},'calibration_A_end':str(ca.label_end.max()),'calibration_B':{'start':str(cb.date.min()),'end':str(cb.label_end.max())},'test':{'start':str(test.date.min()),'end':str(test.label_end.max()),'rows':len(test),'assets':int(test.symbol.nunique())},'results':results,'model_details':details,'feature_importance':feature_importance,'prediction_correlations':corr,'allocations':alloc,'statistics':statistical(full,cal_start,start,end)}
            folds.append(out);db.put('advanced_fold',clean(out),record_id=rid+'_'+name)
    hypotheses=[(f,k,r) for f in folds for k,r in f['results'].items()];pvals=[r['rank_ic']['p'] for _,_,r in hypotheses];total=len(FOLDS)*(len(MODELS)+len(ALLOCATIONS)+len(EXITS)+7)
    for (_,_,r),q in zip(hypotheses,by_adjust(pvals,total)):r['rank_ic_BY_q']=q
    result={'id':rid,'created_at':now().isoformat(),'identity':identity,'folds':folds,'failures':failures,'declared_test_count':total,'multiple_testing':'Circular date-block bootstrap and Benjamini–Yekutieli including failed/unavailable/reserved exit/portfolio/statistical hypotheses. Remaining temporal dependence and researcher choices still limit inference.','qualification':'CHALLENGERS ONLY; no promotion path in this runner','genuine_generalization_improvement':False,'conclusion':'Retrospective chronological results cannot establish untouched prospective generalization; compare folds and costs before registering a new challenger.','limitations':['Historical universe includes current membership: survivorship bias remains; delisting returns unavailable.','Historical market capitalization and dated sector exposures unavailable; never backfill current classifications. Factor-neutral comparisons use only contemporaneous ranks.','Daily-open return labels with fixed conservative costs are research diagnostics, not executable fills.','Split-conformal residual intervals measured empirically; exchangeability is not assumed for dependent financial data.','Family-group comparisons are statistical combinations, not proof of independent alpha.','No manual, experimental-shadow, or released prospective holdout samples used.','Filings/ALFRED remain PIT in source panel; these bounded price-only challengers do not fabricate missing text/macro features.','XGBoost/LightGBM not installed; skipped rather than altering required application dependencies.','Exit comparisons use delayed daily opens and conservative cost estimates; historical depth and intraday execution paths are unavailable.'],'environment':{'python':platform.python_version()},'promotion_eligible':False}
    result=clean(result);db.put('advanced_result',result,record_id=rid);db.set_setting('advanced_research_result',result);return result
