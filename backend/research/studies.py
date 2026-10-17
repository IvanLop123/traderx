"""Finite model/target research with purged walk-forward selection and explicit holdout release."""
import json
import time
from datetime import timedelta
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge,LogisticRegression
from sklearn.ensemble import RandomForestRegressor,RandomForestClassifier,HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.metrics import mean_squared_error,brier_score_loss,roc_auc_score,precision_score,recall_score
from threadpoolctl import threadpool_limits
from pydantic import Field
from backend.schemas.contracts import Contract,now,uid
from backend.storage.database import Setting
from backend.research.features import build_frame,select_features,stable_hash,VERSION,SOURCES
from backend.research.engine import performance

class StudyRequest(Contract):
    symbol:str=Field(default='BTC-USD',pattern=r'^[A-Z0-9_.-]{1,30}$')
    horizons:list[int]=Field(default_factory=lambda:[1,5,10],min_length=1,max_length=3)
    fee_bps:float=Field(default=5,ge=0,le=100)
    slippage_bps:float=Field(default=5,ge=0,le=100)
    spread_bps:float=Field(default=2,ge=0,le=100)

CONFIGS=[('linear',{'alpha':10,'C':.1}),('linear',{'alpha':100,'C':.01}),
         ('forest',{'depth':3,'leaf':25}),('forest',{'depth':5,'leaf':40}),
         ('boosting',{'leaves':5,'l2':10}),('boosting',{'leaves':9,'l2':30})]
TARGETS=['positive','after_cost','meaningful_move']
SEED=1729

def estimators(algorithm,params):
    if algorithm=='linear':return (make_pipeline(StandardScaler(),Ridge(alpha=params['alpha'])),make_pipeline(StandardScaler(),LogisticRegression(C=params['C'],max_iter=600,random_state=SEED)))
    if algorithm=='forest':
        args=dict(n_estimators=60,max_depth=params['depth'],min_samples_leaf=params['leaf'],random_state=SEED,n_jobs=1)
        return RandomForestRegressor(**args),RandomForestClassifier(**args)
    args=dict(max_iter=60,max_leaf_nodes=params['leaves'],l2_regularization=params['l2'],early_stopping=False,random_state=SEED)
    return HistGradientBoostingRegressor(**args),HistGradientBoostingClassifier(**args)

def targets(df,h,cost):
    y=df.open.shift(-h-2)/df.open.shift(-2)-1
    squared=np.log(df.open).diff().pow(2).rolling(h).sum().shift(-h-2)/h
    threshold=np.maximum(cost,np.log(df.close).diff().rolling(20).std()*np.sqrt(h)*.5)
    return y,{'positive':(y>0).astype(int),'after_cost':(y>cost).astype(int),'meaningful_move':(y>threshold).astype(int)},squared

def folds(n,h):
    # Fixed expanding windows in development. Labels and calibration are purged by h+2.
    gap=h+2;starts=[int(n*f) for f in (.45,.63,.81)];ends=starts[1:]+[n]
    result=[]
    for start,end in zip(starts,ends):
        fit_end=int((start-gap)*.8)
        fit=np.arange(60,fit_end-gap);cal=np.arange(fit_end,start-gap);val=np.arange(start,end-gap,h+2)
        if min(len(fit),len(cal),len(val))<8:continue
        result.append((fit,cal,val))
    if len(result)<3:raise ValueError('Insufficient nonoverlapping validation observations for this horizon')
    return result

def fit_bundle(x,y,labels,fit,cal,groups,allowed,algorithm,params):
    if len(fit)<64:raise ValueError('At least 64 usable fit rows required')
    names,medians,excluded=select_features(x,groups,fit,allowed)
    clean=x[names].fillna(medians)
    reg,clf=estimators(algorithm,params);reg.fit(clean.iloc[fit],y.iloc[fit])
    prior=float(labels.iloc[fit].mean());calibrator=None
    if labels.iloc[fit].nunique()==2:
        clf.fit(clean.iloc[fit],labels.iloc[fit]);raw=clf.predict_proba(clean.iloc[cal])[:,1]
        if len(cal)>=20 and labels.iloc[cal].nunique()==2:
            logit=np.log(np.clip(raw,.001,.999)/(1-np.clip(raw,.001,.999))).reshape(-1,1)
            calibrator=LogisticRegression(C=1,random_state=SEED).fit(logit,labels.iloc[cal])
    else:clf=None
    def predict(indices,override=None):
        values=clean.iloc[indices] if override is None else override
        returns=reg.predict(values);p=clf.predict_proba(values)[:,1] if clf else np.full(len(values),prior)
        if calibrator:p=calibrator.predict_proba(np.log(np.clip(p,.001,.999)/(1-np.clip(p,.001,.999))).reshape(-1,1))[:,1]
        return returns,np.clip(p,0,1)
    return predict,names,medians,excluded,prior,calibrator is not None,clean

def metrics(y,pred,labels,p,prior):
    y=np.asarray(y);labels=np.asarray(labels);pred=np.asarray(pred);p=np.asarray(p)
    bins=[]
    for a in np.arange(0,1,.2):
        mask=(p>=a)&(p<a+.2 if a<.79 else p<=1)
        if mask.any():bins.append({'from':round(float(a),1),'count':int(mask.sum()),'mean_probability':float(p[mask].mean()),'observed_frequency':float(labels[mask].mean())})
    mse=float(mean_squared_error(y,pred));zero=float(np.mean(y*y));brier=float(brier_score_loss(labels,p));base=float(brier_score_loss(labels,np.full(len(y),prior)))
    return {'samples':len(y),'return_mse':mse,'zero_return_mse':zero,'brier':brier,'base_rate_brier':base,
      'directional_accuracy':float(np.mean((pred>0)==(y>0))),'target_accuracy':float(np.mean((p>=.5)==labels)),
      'precision':float(precision_score(labels,p>=.5,zero_division=0)),'recall':float(recall_score(labels,p>=.5,zero_division=0)),
      'roc_auc':float(roc_auc_score(labels,p)) if len(set(labels))==2 else None,'reliability':bins,
      'calibration_error':sum(b['count']*abs(b['mean_probability']-b['observed_frequency']) for b in bins)/len(y),
      'objective':.5*mse/max(zero,1e-12)+.5*brier/max(base,1e-12)}

def evaluate(x,df,groups,allowed,h,target,algorithm,params,cost,dev_end):
    y,labels,_=targets(df,h,cost);rows=[]
    for fit,cal,val in folds(dev_end,h):
        predict,names,medians,excluded,prior,calibrated,clean=fit_bundle(x,y,labels[target],fit,cal,groups,allowed,algorithm,params)
        pred,p=predict(val);m=metrics(y.iloc[val],pred,labels[target].iloc[val],p,prior)
        rows.append({'fit_end':int(fit[-1]),'calibration_start':int(cal[0]),'calibration_end':int(cal[-1]),'validation_start':int(val[0]),'validation_end':int(val[-1]),'validation_start_date':str(df.iloc[val[0]].timestamp),'validation_end_date':str(df.iloc[val[-1]].timestamp),'metrics':m,'calibrated':calibrated,'feature_count':len(names)})
    return {'algorithm':algorithm,'parameters':params,'horizon':h,'target':target,'families':allowed,'folds':rows,
            'score':float(np.mean([r['metrics']['objective'] for r in rows])),'score_dispersion':float(np.std([r['metrics']['objective'] for r in rows]))}

def simulate(df,indices,choices,h,side_cost):
    """Long/cash only, decisions after completed bars; entry after one full completed bar, fixed-horizon exit."""
    equity=1.;curve=[1.];trades=[];turnover=0.;blocked_until=-1
    positions={int(i):bool(c) for i,c in zip(indices,choices)}
    shares=0.;exit_at=None;entry_equity=1.
    for j in range(int(indices[0])+2,min(len(df),int(indices[-1])+h+3)):
        if shares and j==exit_at:
            equity=shares*float(df.iloc[j].open)*(1-side_cost);shares=0.;turnover+=1
            trades.append(equity/entry_equity-1)
        i=j-2
        if positions.get(i) and not shares and j>=blocked_until:
            if pd.Timestamp(df.iloc[i].available_at)>pd.Timestamp(df.iloc[j].timestamp):continue
            entry_equity=equity;shares=equity/(float(df.iloc[j].open)*(1+side_cost));exit_at=j+h;blocked_until=exit_at;turnover+=1
        marked=shares*float(df.iloc[j].close) if shares else equity;curve.append(marked)
    if shares:equity=shares*float(df.iloc[min(len(df)-1,int(indices[-1])+h+3)].close)*(1-side_cost);curve[-1]=equity;turnover+=1;trades.append(equity/entry_equity-1)
    return {**performance(curve,365 if '-' in str(df.iloc[0].symbol) else 252),'turnover':turnover,'trades':len(trades),
      'win_fraction':float(np.mean(np.array(trades)>0)) if trades else None,'trade_quantiles':np.quantile(trades,[.05,.5,.95]).tolist() if trades else []}

class Studies:
    def __init__(self,db):self.db=db
    def list(self):
        return [self.view(r['id']) for r in self.db.records('ml_study',limit=30)]
    def view(self,rid):
        row=self.db.get(rid)
        if not row or row['kind']!='ml_study':raise ValueError('Research study not found')
        return {'id':rid,**row['payload'],'holdout':self.db.setting('holdout_'+rid[:40],{'status':'LOCKED'})}
    def run(self,request):
        token=uid();key='study_lease_'+stable_hash(request.symbol)[:32]
        with self.db.transaction() as session:
            lease=session.get(Setting,key)
            if lease and lease.value['until']>now().isoformat():raise ValueError('A comparison is already running for this asset')
            session.merge(Setting(key=key,value={'token':token,'until':(now()+timedelta(minutes=20)).isoformat()}))
        try:return self._run(request)
        except Exception:
            self.db.put('audit',{'action':'ml_study_failed','request':request.model_dump()},request.symbol)
            raise
        finally:
            with self.db.transaction() as session:
                lease=session.get(Setting,key)
                if lease and lease.value['token']==token:session.delete(lease)
    def _run(self,request):
        if len(set(request.horizons))!=len(request.horizons) or any(h not in (1,5,10) for h in request.horizons):raise ValueError('Use unique horizons from 1, 5, 10')
        df,x,groups,notes=build_frame(self.db,request.symbol)
        if len(df)<400:raise ValueError('At least 400 daily bars required')
        data={'bars':df.to_dict('records'),'matrix':json.loads(x.to_json(orient='split',double_precision=15)),'groups':groups}
        # Fingerprint excludes arrival-only changes while preserving all actual inputs.
        identity={**data,'bars':[{k:v for k,v in r.items() if k not in ('observed_at','id')} for r in data['bars']], 'request':request.model_dump(),'version':VERSION}
        rid=stable_hash(identity)
        if self.db.get(rid):return self.view(rid)
        dev_end=int(len(df)*.8);cost=2*(request.fee_bps+request.slippage_bps+request.spread_bps/2)/1e4
        start=time.monotonic();trials=[];ablations=[]
        with threadpool_limits(limits=1):
            # Family selection uses development folds only. Keep the same simple estimator for fair ablations.
            available=sorted(set(groups.values()));families=[['price'],['price','technical'],['price','technical','regime']]
            families += [['price',f] for f in available if f not in ('price','technical','regime')]
            families.append(available)
            for allowed in families:
                try:
                    row=evaluate(x,df,groups,allowed,5,'positive',*CONFIGS[0],cost,dev_end);ablations.append(row)
                except ValueError:ablations.append({'families':allowed,'status':'INSUFFICIENT_DATA','score':None})
            valid=[a for a in ablations if a.get('score') is not None];chosen=min(valid,key=lambda a:a['score'])['families']
            for h in request.horizons:
                for target in TARGETS:
                    for algorithm,params in CONFIGS:
                        try:row=evaluate(x,df,groups,chosen,h,target,algorithm,params,cost,dev_end)
                        except ValueError:row={'algorithm':algorithm,'parameters':params,'horizon':h,'target':target,'status':'INSUFFICIENT_DATA','score':None}
                        trials.append(row)
                        self.db.put('ml_trial',{'study_id':rid,**row},request.symbol,record_id=stable_hash([rid,'trial',len(trials)]))
            eligible=[t for t in trials if t.get('score') is not None];winner=min(eligible,key=lambda t:t['score'])
            h=winner['horizon'];fit_end=int(dev_end*.8);gap=h+2
            fit=np.arange(60,fit_end-gap);cal=np.arange(fit_end,dev_end-gap)
            y,labels,vol=targets(df,h,cost)
            predict,names,medians,excluded,prior,calibrated,clean=fit_bundle(x,y,labels[winner['target']],fit,cal,groups,chosen,winner['algorithm'],winner['parameters'])
            pred,prob=predict([len(df)-1])
            volatility=make_pipeline(StandardScaler(),Ridge(alpha=10)).fit(clean.iloc[fit],vol.iloc[fit])
            # Block-shift permutation on the last DEVELOPMENT validation fold, not the holdout.
            f,c,v=folds(dev_end,h)[-1]
            fn,nn,mm,ee,pp,cc,xx=fit_bundle(x,y,labels[winner['target']],f,c,groups,chosen,winner['algorithm'],winner['parameters'])
            baseline=mean_squared_error(y.iloc[v],fn(v)[0]);importance=[]
            for name in nn:
                changes=[]
                for fraction in (.25,.5,.75):
                    rotated=xx.iloc[v].copy();rotated[name]=np.roll(rotated[name].to_numpy(),max(1,int(len(v)*fraction)))
                    changes.append(float(mean_squared_error(y.iloc[v],fn(v,rotated)[0])-baseline))
                importance.append({'feature':name,'family':groups[name],'mse_increase':float(np.mean(changes)),'dispersion':float(np.std(changes)),'method':'three_development_block_shifts'})
            importance.sort(key=lambda r:-r['mse_increase'])
        from backend.research.history import HistoryStore
        historical_dataset=HistoryStore(self.db).manifest(request.symbol)
        result={'historical_dataset':historical_dataset,'symbol':request.symbol,'version':VERSION,'created_at':now().isoformat(),'status':'RESEARCH_ONLY','request':request.model_dump(),
          'data':{'bars':len(df),'start':str(df.iloc[0].timestamp),'end':str(df.iloc[-1].timestamp),'last_observed_at':str(df.observed_at.max()),'hash':rid},
          'periods':{'training':{'start':str(df.iloc[fit[0]].timestamp),'end':str(df.iloc[fit[-1]].timestamp)},'calibration':{'start':str(df.iloc[cal[0]].timestamp),'end':str(df.iloc[cal[-1]].timestamp)},
                     'holdout':{'start':str(df.iloc[dev_end].timestamp),'end':str(df.iloc[-1].timestamp)},'development_end_index':dev_end},
          'selected':winner,'features':names,'feature_families':sorted({groups[n] for n in names}),'feature_sources':{f:SOURCES[f] for f in set(groups[n] for n in names)},
          'excluded':excluded,'unavailable_families':notes,'imputation':medians,'ablations':ablations,'trials':trials,'importance':importance,
          'calibration':'separate_purged_sigmoid' if calibrated else 'uncalibrated','latest':{'expected_return':float(pred[0]),'target_probability':float(prob[0]),'target':winner['target'],'daily_realized_volatility':float(np.sqrt(max(0,volatility.predict(clean.iloc[[-1]])[0]))),'horizon':h,'development_residual_std':float(np.std(y.iloc[cal]-predict(cal)[0]))},
          'execution_delay_bars':2,
          'runtime_seconds':round(time.monotonic()-start,2),'seed':SEED,'trial_count':len(trials),'promotion_eligible':False,
          'limitations':['Current selected universe; survivorship bias unresolved.','Versioned provider-adjusted equity history when available; retrospective adjustment vintage may be revised. Raw and adjusted series never mixed.',
          'Macro uses archived first releases, not latest revised values; availability conservatively delayed to next New York midnight.',
          'Development estimates include family/target/parameter selection and are optimistic; final holdout is withheld until explicit release.',
          'Historical dates may have been inspected in earlier baseline research. Only future forward studies provide fresh evidence.',
          'No ensemble or pooled/regime-specific fit is justified without complementary signal and larger independent samples.','Model probabilities are not opportunity scores or trade permissions.']}
        self.db.put('ml_study_input',data,request.symbol,record_id='input-'+rid)
        self.db.put('ml_study',result,request.symbol,record_id=rid)
        return self.view(rid)
    def release(self,rid):
        result=self.view(rid);key='holdout_'+rid[:40]
        if result['holdout']['status']!='LOCKED':return result
        data=self.db.get('input-'+rid)['payload'];df=pd.DataFrame(data['bars']);x=pd.DataFrame(data['matrix']['data'],columns=data['matrix']['columns']).astype(float);groups=data['groups']
        w=result['selected'];h=w['horizon'];request=StudyRequest(**result['request']);cost=2*(request.fee_bps+request.slippage_bps+request.spread_bps/2)/1e4
        dev_end=result['periods']['development_end_index'];fit_end=int(dev_end*.8);fit=np.arange(60,fit_end-h-2);cal=np.arange(fit_end,dev_end-h-2)
        y,labels,vol=targets(df,h,cost);ix=np.arange(dev_end,len(df)-h-2,h+2)
        with threadpool_limits(limits=1):
            predict,names,medians,excluded,prior,calibrated,clean=fit_bundle(x,y,labels[w['target']],fit,cal,groups,w['families'],w['algorithm'],w['parameters'])
            pred,p=predict(ix);scores=metrics(y.iloc[ix],pred,labels[w['target']].iloc[ix],p,prior)
            choices=(pred>cost)&(p>.55);trade=simulate(df,ix,choices,h,cost/2)
            benchmarks={'no_trade':simulate(df,ix,np.zeros(len(ix),bool),h,cost/2),
              'long_each_window':simulate(df,ix,np.ones(len(ix),bool),h,cost/2),
              'momentum':simulate(df,ix,(x.return_20.iloc[ix]>0).to_numpy(),h,cost/2),
              'mean_reversion':simulate(df,ix,(x.return_5.iloc[ix]<0).to_numpy(),h,cost/2)}
            entry=int(ix[0])+2;end=int(ix[-1])+h+2
            bh=np.r_[1,df.close.iloc[entry:end].to_numpy()/df.open.iloc[entry]/(1+cost/2),df.open.iloc[end]/df.open.iloc[entry]*(1-cost/2)/(1+cost/2)]
            benchmarks['buy_and_hold']={**performance(bh,365 if '-' in request.symbol else 252),'turnover':2}
            linear=fit_bundle(x,y,labels[w['target']],fit,cal,groups,w['families'],*CONFIGS[0]);lp,lprob=linear[0](ix)
            baseline_linear=metrics(y.iloc[ix],lp,labels[w['target']].iloc[ix],lprob,linear[4])
            vol_model=make_pipeline(StandardScaler(),Ridge(alpha=10)).fit(clean.iloc[fit],vol.iloc[fit]);vol_pred=np.maximum(0,vol_model.predict(clean.iloc[ix]))
            vol_scores={'squared_volatility_mse':float(mean_squared_error(vol.iloc[ix],vol_pred)),'training_mean_mse':float(mean_squared_error(vol.iloc[ix],np.full(len(ix),vol.iloc[fit].mean())))}
            regimes={}
            for regime,mask in {**{name:x.regime_trend.iloc[ix].to_numpy()==v for name,v in [('downtrend',-1),('range',0),('uptrend',1)]},'high_volatility':x.regime_vol_ratio.iloc[ix].to_numpy()>1.25,'low_volatility':x.regime_vol_ratio.iloc[ix].to_numpy()<.8,**({'peer_risk_on':x.peer_risk_breadth.iloc[ix].to_numpy()>=.7,'peer_risk_off':x.peer_risk_breadth.iloc[ix].to_numpy()<=.3} if 'peer_risk_breadth' in x else {})}.items():
                if mask.any():regimes[regime]=metrics(y.iloc[ix][mask],pred[mask],labels[w['target']].iloc[ix][mask],p[mask],prior)
            gates={'at_least_200_nonoverlapping_holdout':len(ix)>=200,'beats_zero_return':scores['return_mse']<scores['zero_return_mse'],
              'beats_base_rate_brier':scores['brier']<scores['base_rate_brier'],'calibrated':calibrated,
              'beats_linear_mse':scores['return_mse']<=baseline_linear['return_mse'],
              'positive_net_return':trade['total_return']>0,'beats_buy_and_hold':trade['total_return']>benchmarks['buy_and_hold']['total_return'],
              'future_validation_required':False}
        holdout={'status':'RELEASED_ONCE','released_at':now().isoformat(),'metrics':scores,'strategy':trade,'benchmarks':benchmarks,'linear_baseline':baseline_linear,
                 'volatility':vol_scores,'by_regime':regimes,'gates':gates,'promotion_eligible':False,'cash_reasons':{'weak_probability':int((p<=.5).sum()),'probability_below_policy_threshold':int(((p>.5)&(p<=.55)).sum()),'nonpositive_expected_net_return':int((pred<=cost).sum()),'eligible_trade_windows':int(choices.sum())},
                 'warning':'Explicit one-time historical diagnostic; reuse is not new evidence. Future validation remains mandatory.'}
        self.db.set_setting(key,holdout);self.db.put('audit',{'action':'ml_holdout_released','study_id':rid},request.symbol)
        return self.view(rid)
