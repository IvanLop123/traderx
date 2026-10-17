"""Bounded chronological family improvements, ranking and meta-labeling diagnostics.

All dates here were already available/inspected. Results never count as untouched forward evidence.
"""
import json,hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.research.strategies import FAMILIES,PAIRS,fit_model,predict,metrics
from backend.qualification.statistics import interval
from backend.selection.registry import calibration_quality

FOLDS=[('2022-01-01','2023-01-01'),('2023-01-01','2024-01-01'),('2024-01-01','2025-04-16')]

def sample(p,start,end):
    start=pd.Timestamp(start);end=pd.Timestamp(end);start=start.tz_localize('UTC') if start.tzinfo is None else start;end=end.tz_localize('UTC') if end.tzinfo is None else end
    z=p[(p.date>=start)&(p.date<end)&(p.label_end<end)&p.eligible&p.net_return.notna()].copy();ends=z.groupby('date').label_end.max();dates=[];last=None
    for date,label_end in ends.items():
        if last is None or date>last:dates.append(date);last=label_end
    return z[z.date.isin(dates)].copy()

def fit_variant(a,b,names,variant):
    if variant=='robust':
        names=[c for c in names if c in a];lo=a[names].quantile(.01);hi=a[names].quantile(.99);a=a.copy();b=b.copy();a[names]=a[names].clip(lo,hi,axis=1);b[names]=b[names].clip(lo,hi,axis=1)
    m=fit_model(a,b,names)
    if variant=='robust':m['clip_lower']={c:float(lo[c]) for c in m['columns']};m['clip_upper']={c:float(hi[c]) for c in m['columns']}
    return m

def scored(m,z):
    z=z.copy();z['predicted'],z['probability']=predict(m,z);z['prior']=m['prior'];z['model_uncertainty']=m['uncertainty'];z['target_baseline']=0.;z['missing_features']=z.reindex(columns=m['columns']).isna().any(axis=1);return z

def summary(z,mask=None):
    mask=(z.predicted>0)&(z.probability>=.55)&~z.missing_features if mask is None else mask
    by=z.net_return.where(mask,0).groupby(z.date).mean();m=metrics(z);m.update(interval=interval(by.to_numpy()),calibration=calibration_quality(list(zip(z.probability,(z.net_return>0).astype(float)))),cost_rule='110bps stock/limited liquidity; 22bps other round trip; diagnostic next-open labels')
    m['positive_dates']=int((by>0).sum());m['selected_rows']=int(mask.sum());return m

def meta_experiment(p,family,names,start,end):
    start=pd.Timestamp(start,tz='UTC');meta_start=start-pd.DateOffset(years=2);cal_start=meta_start-pd.DateOffset(months=6)
    a=sample(p,'2016-01-01',cal_start);b=sample(p,cal_start,meta_start);train=sample(p,meta_start,start);test=sample(p,start,end)
    try:m=fit_model(a,b,names);train=scored(m,train);test=scored(m,test)
    except ValueError as e:return {'status':'INSUFFICIENT_EVIDENCE','reason':str(e)}
    candidate=(train.predicted>0)&(train.probability>=.55)&~train.missing_features;rows=train[candidate];dates=rows.date.nunique();features=['predicted','probability','realized_volatility','return_20','rsi'];labels=(rows.net_return>0).astype(int)
    if len(rows)<200 or dates<60 or labels.nunique()<2:return {'status':'INSUFFICIENT_EVIDENCE','candidate_rows':len(rows),'nonoverlapping_dates':int(dates),'reason':'Requires 200 candidate rows, 60 nonoverlapping candidate dates and two outcome classes, all after base fitting/calibration.'}
    if rows[features].isna().any().any():return {'status':'INSUFFICIENT_EVIDENCE','reason':'Missing secondary features'}
    model=make_pipeline(StandardScaler(),LogisticRegression(C=.01,max_iter=300));model.fit(rows[features],labels);base=(test.predicted>0)&(test.probability>=.55)&~test.missing_features;valid=test[features].notna().all(axis=1);prob=pd.Series(0.,index=test.index);prob.loc[valid]=model.predict_proba(test.loc[valid,features])[:,1];meta=base&(prob>=.6);simple=base&(test.predicted>=m['uncertainty']*.25)
    return {'status':'TESTED','candidate_rows':len(rows),'nonoverlapping_dates':int(dates),'base':summary(test,base),'simple_uncertainty_gate':summary(test,simple),'meta_label_gate':summary(test,meta),'threshold':.6,'scope':'Secondary candidate-only logistic gate; separate from selector; primary fit and calibration precede meta training, which precedes test.'}

def run(db):
    source=db.get(db.setting('strategy_latest')['id'])['payload']['identity'];snap=source['snapshot'];path=Path('data/strategy_panels')/(snap['panel_hash']+'.parquet')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=snap['file_hash']:raise ValueError('Archived panel integrity failed')
    definition={'version':'qualification-research-v2','correction':'Supersedes v1 threshold diagnostics: each prediction uses its own earlier fitted fold uncertainty, not final fold uncertainty','at':now().isoformat(),'panel_hash':snap['panel_hash'],'variants':['baseline','robust'],'improvement':'Training-only 1st/99th percentile clipping with identical features; no neural networks or new indicator search','families':FAMILIES,'folds':FOLDS,'diagnostic':['2025-04-16','2026-10-10'],'thresholds':[50,60,65,70,80],'ranking_k':[1,3,10],'meta_minimum_dates':60,'meta_minimum_rows':200,'selection':'Variant comparison uses development folds only; no promotion, no holdout-driven retuning','scope':'Previously observed retrospective history; never independent qualification evidence'}
    rid='qresearch_'+stable_hash({k:v for k,v in definition.items() if k!='at'});old=db.get(rid)
    if old:return old['payload']
    db.put('qualification_research_plan',definition,record_id=rid+'_plan');p=pd.read_parquet(path);p['date']=pd.to_datetime(p.date,utc=True);p['label_end']=pd.to_datetime(p.label_end,utc=True);results=[];ranking=[];meta=[];family_records=[];development_predictions={}
    with threadpool_limits(limits=1):
        for cls in ['stock','etf','crypto']:
            cp=p[p.asset_class==cls]
            for family,names in FAMILIES.items():
                fp=cp[cp.symbol.isin(PAIRS)] if family=='pairs_relative_value' else cp
                for variant in definition['variants']:
                    item={'family':family,'asset_class':cls,'variant':variant,'folds':[]};pieces=[];last_model=None
                    for start,end in FOLDS:
                        t=pd.Timestamp(start,tz='UTC');cal=t-pd.DateOffset(months=6);a=sample(fp,'2016-01-01',cal);b=sample(fp,cal,t);z=sample(fp,t,end)
                        try:
                            model=fit_variant(a,b,names,variant)
                            if family=='crypto_funding' and not any(c.startswith('funding_') for c in model['columns']):raise ValueError('Historical funding/basis unavailable; price-only fallback prohibited')
                            if family=='macro_regime' and not any(c.startswith('macro_') for c in model['columns']):raise ValueError('Historical macro coverage unavailable')
                            z=scored(model,z)
                            if z.empty:raise ValueError('No eligible chronological test rows')
                            result=summary(z);item['folds'].append({'start':start,'end':end,**result});pieces.append(z);last_model=model
                        except (ValueError,KeyError) as e:item['folds'].append({'start':start,'end':end,'status':'UNAVAILABLE','reason':str(e)})
                    if len(pieces)!=3:item['status']='INSUFFICIENT_EVIDENCE';results.append(item);continue
                    z=pd.concat(pieces);item.update(status='TESTED',validation=summary(z));item['conditions']={k:{str(v):summary(g) for v,g in z.groupby(k)} for k in ['regime','liquidity_bucket','market_cap_bucket']}
                    # Same score terms as the opportunity layer, studied one primary family at a time; not production votes.
                    score=(z.predicted/z.model_uncertainty*25).clip(0,25)+((z.probability-.5)*60).clip(0,15)+10+(np.log10(z.adv.clip(lower=1)/1e6)/3).clip(0,1)*10+(1-z.model_uncertainty/.2).clip(0,1)*10+(1-z.realized_volatility/.1).clip(0,1)*10+(1-z.cost/.02).clip(0,1)*10+10
                    item['thresholds']=[{'threshold':threshold,**summary(z,(score>=threshold)&(z.predicted>0)&(z.probability>=.55)&~z.missing_features)} for threshold in definition['thresholds']]
                    diagnostic=scored(last_model,sample(fp,*definition['diagnostic']));item['diagnostic']=summary(diagnostic) if len(diagnostic) else None
                    if family=='cross_sectional_ranking' and cls!='crypto':
                        for k in definition['ranking_k']:
                            by=[];ics=[];assetrows=0
                            for _,day in z[~z.missing_features].groupby('date'):
                                if len(day)<max(k,4):continue
                                ordered=day.sort_values('predicted',ascending=False).head(k);by.append(float(ordered.net_return.mean()));assetrows+=len(ordered);ic=day.predicted.corr(day.net_return,method='spearman')
                                if np.isfinite(ic):ics.append(ic)
                            ranking.append({'asset_class':cls,'variant':variant,'top_k':k,'interval':interval(by),'rank_ic':interval(ics),'asset_rows':assetrows,'binary_gate':item['validation'],'scope':'Equal-weight nonoverlapping next-open label diagnostic after costs, not guaranteed fills; cash is allowed in binary comparator.'})
                    if variant=='baseline':development_predictions[family+'_'+cls]=z.set_index(['date','symbol']).predicted
                    try:
                        cutoff=pd.Timestamp('2026-10-10',tz='UTC');cal=cutoff-pd.DateOffset(months=6);final=fit_variant(sample(fp,'2016-01-01',cal),sample(fp,cal,cutoff),names,variant)
                        mid='qmodel_'+stable_hash([rid,family,cls,variant]);final.update(id=mid,family=family,asset_class=cls,horizon=5,variant=variant,fitted_at=now().isoformat(),feature_available_before=cutoff.isoformat(),data_version=rid,promotion_eligible=False);db.put('strategy_model',final,record_id=mid)
                        positive=all(f.get('interval',{}).get('lower') is not None and f['interval']['lower']>0 and f['mse']<f['zero_mse'] and f['brier']<f['base_rate_brier'] for f in item['folds']);dev={'model_id':mid,'model_hash':stable_hash(final),'plan_id':rid+'_plan','folds':item['folds'],'passed':positive,'at':now().isoformat(),'scope':'Historical chronological development only; fresh holdout still required'};db.put('qualification_development',dev,record_id='qdevelopment_'+stable_hash(mid));item['model_id']=mid
                        family_records.append({'model_id':mid,'family':family,'asset_class':cls,'validation':item['validation'],'development_improved':positive,'validation_by':item['conditions']})
                    except ValueError as e:item['refit_error']=str(e)
                    results.append(item);print(cls,family,variant,'done',flush=True)
                if family=='momentum' and cls in ('stock','etf'):
                    for start,end in FOLDS:meta.append({'family':family,'asset_class':cls,'start':start,'end':end,**meta_experiment(fp,family,names,start,end)})
    correlations=[]
    for cls in ['stock','etf','crypto']:
        names=[n for n in development_predictions if n.endswith('_'+cls)]
        for i,a in enumerate(names):
            for b in names[i+1:]:
                x,y=development_predictions[a].align(development_predictions[b],join='inner');rho=x.corr(y)
                if np.isfinite(rho):correlations.append({'first':a,'second':b,'prediction_correlation':float(rho),'paired_rows':len(x),'date_clusters':int(x.index.get_level_values(0).nunique())})
    result={'id':rid,'definition':definition,'results':results,'cross_sectional':ranking,'meta_labeling':meta,'dependence':correlations,'promotion_eligible':False,'warning':'All historical diagnostics are retrospective. Costs, universe survivorship, covariance and selected-trial dependence limit inference; only new preregistered observations qualify.'};result=json.loads(json.dumps(result,default=lambda v:v.item()))
    db.put('qualification_research',result,record_id=rid);db.set_setting('qualification_research',result);db.put('strategy_study',{'identity':{'boundaries':FOLDS,'cost_rule':source['cost_rule'],'universe':source['universe']},'family_results':family_records,'source_plan':rid+'_plan','promotion_eligible':False},record_id=rid+'_families');return result
