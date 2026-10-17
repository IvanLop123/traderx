"""Qualification derives gates from immutable observations, never submitted pass/fail flags."""
from collections import Counter,defaultdict
import math
import numpy as np
import pandas as pd
from sqlalchemy import select
from backend.storage.database import Setting
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.selection.registry import calibration_quality
from backend.qualification.statistics import interval as raw_interval,nonoverlapping

def interval(values,**kwargs):
    return raw_interval(values,draws=99999,**kwargs)
from backend.qualification.integrity import implementation_hash


def mature(db,d):
    enroll=db.get(d['id']+'_enrollment');study_ids={sid for sid in (enroll['payload']['study_ids'] if enroll else []) if db.setting('forward_state_'+sid,{}).get('evidence_policy')=='quarantined_evaluation'};decisions={r['id']:r['payload'] for r in db.records('forward_decision',limit=None)};rows=[]
    for record in db.records('forward_outcome',limit=None):
        o=record['payload'];decision=decisions.get(o.get('decision_id'),{})
        if o.get('study_id') not in study_ids or decision.get('model_hash')!=d['model_hash']:continue
        if not pd.Timestamp(d['registered_at'])<=pd.Timestamp(decision.get('decided_at'))<=pd.Timestamp(o.get('completed_at'))<=pd.Timestamp(now()):continue
        if not decision.get('feature_available_at') or not pd.Timestamp(d['registered_at'])<=pd.Timestamp(decision['feature_available_at'])<=pd.Timestamp(decision['decided_at']):continue
        if o.get('status') not in ('COMPLETED','CASH_EVALUATED','UNFILLED'):continue
        value=o['realized_pnl']/o['entry_cost'] if o.get('entry_cost',0)>0 else 0.
        row={**o,'source_id':record['id'],'decided_at':decision['decided_at'],'probability':decision.get('probability'),'probability_target':decision.get('probability_target'),'net_return':value,'definition_id':d['id'],'evidence_policy':'quarantined_evaluation'}
        rid='qsample_'+stable_hash([d['id'],record['id']]);db.put('qualification_sample',row,o['symbol'],record_id=rid);rows.append(row)
    return rows

def comparison(db,definition_id,criteria,alpha):
    marks=[];definition=db.get(definition_id);initial=(definition or {}).get('payload',{}).get('risk_policy',{}).get('initial_cash',10000)
    with db.engine.connect() as conn:
        for value in conn.execute(select(Setting.value).where(Setting.key.like('qmark_%'))).scalars():
            if value.get('definition_id')==definition_id and value.get('scope')=='forward' and value.get('fresh'):marks.append(value)
    by=defaultdict(dict)
    for row in marks:by[row['arm']][row['date']]=row
    arms=['candidate',*criteria['benchmark_arms']];common=sorted(set.intersection(*(set(by[a]) for a in arms))) if all(by[a] for a in arms) else []
    common=common[:criteria['minimum_portfolio_blocks']*criteria['portfolio_block_days']]
    returns={a:([by[a][common[0]]['equity']/initial-1] if common else []) for a in arms};dates=common[:1]
    for before,after in zip(common,common[1:]):
        # Missing dates are allowed across market holidays, but not silently annualized as daily returns.
        if (pd.Timestamp(after)-pd.Timestamp(before)).days>4:continue
        dates.append(after)
        for a in arms:returns[a].append(by[a][after]['equity']/by[a][before]['equity']-1)
    n=len(dates);block=criteria['portfolio_block_days'];blocks=n//block
    def aggregate(values):return [float(np.prod(1+np.asarray(values[i:i+block]))-1) for i in range(0,len(values)-block+1,block)]
    candidate=aggregate(returns['candidate']);comparisons={}
    for arm in criteria['benchmark_arms']:
        other=aggregate(returns[arm]);comparisons[arm]=interval(np.array(candidate)-np.array(other),alpha=alpha,block=5)
    metrics={}
    for arm in arms:
        series=[by[arm][date] for date in common];equity=np.array([initial,*[v['equity'] for v in series]]) if series else np.array([]);r=np.asarray(returns[arm]);vol=float(r.std(ddof=1)) if len(r)>1 else 0.;down=float(np.sqrt(np.mean(np.minimum(r,0)**2))) if len(r) else 0.;consecutive=bool(len(common)>1 and (pd.to_datetime(common).diff()[1:]==pd.Timedelta(days=1)).all());annual=n>=60 and consecutive
        metrics[arm]={'days':len(common),'independent_blocks':blocks,'net_return':float(equity[-1]/equity[0]-1) if len(equity) else None,'maximum_drawdown':float((1-equity/np.maximum.accumulate(equity)).max()) if len(equity) else None,'turnover':series[-1]['turnover'] if series else None,'cost_drag':series[-1]['fees']/initial if series else None,'mean_exposure':float(np.mean([x['exposure'] for x in series])) if series else None,'mean_concentration':float(np.mean([x['concentration'] for x in series])) if series else None,'sharpe_like':float(r.mean()/vol*math.sqrt(365)) if annual and vol else None,'sortino_like':float(r.mean()/down*math.sqrt(365)) if annual and down else None,'annualization_warning':'Mixed calendar-day marks, 60 returns and no calendar gaps required; otherwise ratios hidden','by_regime':{g:{'dates':sum(v['regime']==g for v in series),'mean_exposure':float(np.mean([v['exposure'] for v in series if v['regime']==g])),'mean_net_daily_return':float(np.mean([value for date,value in zip(dates,r) if by[arm][date]['regime']==g])) if any(by[arm][date]['regime']==g for date in dates) else None} for g in {v['regime'] for v in series}}}
    outcomes=[r['payload'] for r in db.records('qualification_outcome',limit=None) if r['payload']['definition_id']==definition_id and r['payload']['arm']=='candidate' and r['payload']['scope']=='forward']
    cal=calibration_quality([(o['probability'],float(o['realized_pnl']>0)) for o in outcomes if o.get('probability') is not None],criteria['minimum_calibration_clusters'])
    return {'definition_id':definition_id,'dates':n,'independent_blocks':blocks,'net':interval(candidate,alpha=alpha,block=5),'comparisons':comparisons,'metrics':metrics,'calibration':cal,'calibration_clusters':len(nonoverlapping(outcomes)),'completed_trades':len(outcomes),'source_mark_count':len(marks),'alignment':'Same observed dates across all seven independently simulated books. Missing benchmark prices do not count as zero returns.'}

def evaluate(db,d,portfolio):
    c=d['criteria'];samples=mature(db,d);clusters=nonoverlapping(samples);nh=c['minimum_holdout_clusters'];nf=c['minimum_forward_clusters'];hold=clusters[:nh];forward=clusters[nh:nh+nf];alpha=c['familywise_alpha']/max(1,d['family_count']*(len(c['benchmark_arms'])+4))
    h=interval([r['net_return'] for r in hold],alpha=alpha,block=5);f=interval([r['net_return'] for r in forward],alpha=alpha,block=5);traded=[o for group in forward for o in group['rows'] if o.get('entry_cost',0)>0];cal_pairs=[(o['probability'],float(o['realized_pnl']>0)) for o in traded if o.get('probability_target')=='positive_after_cost' and o.get('probability') is not None];cal=calibration_quality(cal_pairs,c['minimum_calibration_clusters']);cal_clusters=sum(any(o.get('entry_cost',0)>0 for o in g['rows']) for g in forward)
    regimes=defaultdict(list)
    for g in forward:
        for regime in {r.get('regime','unknown') for r in g['rows']}:regimes[regime].append(float(np.mean([r['net_return'] for r in g['rows'] if r.get('regime','unknown')==regime])))
    regimes={k:interval(v,alpha=alpha,block=5) for k,v in regimes.items()};covered=[v for k,v in regimes.items() if k!='unknown' and v['n']>=c['minimum_regime_clusters']]
    artifact=db.get(d['model_id']);historical=db.get('qdevelopment_'+stable_hash(d['model_id']));historical=historical['payload'] if historical else {}
    data_minima={'holdout':len(hold)>=nh,'forward':len(forward)>=nf,'trades':len(traded)>=c['minimum_completed_trades'],'calibration':cal_clusters>=c['minimum_calibration_clusters'],'regimes':len(covered)>=c['minimum_regimes'],'portfolio':portfolio.get('independent_blocks',0)>=c['minimum_portfolio_blocks'],'ensemble_calibration':portfolio.get('calibration_clusters',0)>=c['minimum_calibration_clusters']}
    prior=float(artifact['payload'].get('prior',.5)) if artifact else .5;prior_brier=float(np.mean([(prior-y)**2 for _,y in cal_pairs])) if cal_pairs else None
    gates={'implementation_unchanged':d.get('implementation_hash')==implementation_hash(),'criteria_unchanged':stable_hash(c)==d['criteria_hash'],'artifact_unchanged':bool(artifact and stable_hash(artifact['payload'])==d['model_hash']),'historical_walk_forward':development_valid(db,historical,d),'holdout_after_cost':h['lower'] is not None and h['lower']>0,'forward_after_cost':f['lower'] is not None and f['lower']>0,'calibration':cal['expected_calibration_error'] is not None and cal['expected_calibration_error']<=c['maximum_calibration_error'] and cal['brier']<=prior_brier,'regime_robustness':len(covered)>=c['minimum_regimes'] and all(v['mean']>=c['minimum_regime_mean_return'] for v in covered),'portfolio_after_cost':portfolio.get('net',{}).get('lower') is not None and portfolio['net']['lower']>0,'portfolio_benchmarks':len(portfolio.get('comparisons',{}))==len(c['benchmark_arms']) and all(v.get('lower') is not None and v['lower']>0 for v in portfolio.get('comparisons',{}).values()),'portfolio_drawdown':portfolio.get('metrics',{}).get('candidate',{}).get('maximum_drawdown') is not None and portfolio['metrics']['candidate']['maximum_drawdown']<=c['maximum_drawdown'],'ensemble_calibration':portfolio.get('calibration',{}).get('expected_calibration_error') is not None and portfolio['calibration']['expected_calibration_error']<=c['maximum_calibration_error']}
    ready=all(data_minima.values());terminal_id='qterminal_'+stable_hash(d['id']);old=db.get(terminal_id)
    result={'model_id':d['model_id'],'definition_id':d['id'],'family':d['family'],'asset_class':d['asset_class'],'model_hash':d['model_hash'],'criteria_hash':d['criteria_hash'],'registered_at':d['registered_at'],'at':now().isoformat(),'state':'QUALIFIED_FOR_MODEL_PAPER' if ready and all(gates.values()) else 'FAILED' if ready else 'FORWARD_TESTING' if not samples else 'INSUFFICIENT_EVIDENCE','samples':len(samples),'independent_clusters':len(clusters),'holdout':h,'forward':f,'regimes':regimes,'calibration':cal,'prior_brier':prior_brier,'portfolio':portfolio,'minima':data_minima,'gates':gates,'remaining':{'holdout_clusters':max(0,nh-len(hold)),'forward_clusters':max(0,nf-len(forward)),'portfolio_blocks':max(0,c['minimum_portfolio_blocks']-portfolio.get('independent_blocks',0)),'completed_trades':max(0,c['minimum_completed_trades']-len(traded))},'alpha_per_comparison':alpha,'real_money_authorized':False,'evidence_policy':'quarantined_evaluation','warning':'Intervals are weak below minimum samples. Nonoverlapping date clusters and block resampling reduce, but cannot eliminate, market dependence.'}
    if ready and not old:db.put('qualification_terminal',result,record_id=terminal_id);old=db.get(terminal_id)
    if old:result={**result,'state':old['payload']['state'],'terminal_receipt_id':terminal_id,'terminal_at':old['payload']['at'],'terminal_gates':old['payload']['gates']}
    if not gates['artifact_unchanged'] or not gates['implementation_unchanged'] or not gates['criteria_unchanged']:result.update(state='RESEARCH_ONLY',suspended_reason='Frozen model, implementation or criteria changed; new preregistration required')
    if not d.get('sentinels'):result.update(state='RESEARCH_ONLY',suspended_reason='No eligible scientific sentinel assets')
    recent=clusters[-30:];recent_trades=[o for g in recent for o in g['rows'] if o.get('entry_cost',0)>0];recent_cal=calibration_quality([(o['probability'],float(o['realized_pnl']>0)) for o in recent_trades if o.get('probability') is not None],30)
    result['monitoring']={'clusters':len(recent),'calibration':recent_cal,'mean_net_return':float(np.mean([g['net_return'] for g in recent])) if recent else None,'suspended':bool(len(recent)>=30 and (recent_cal['expected_calibration_error'] is not None and recent_cal['expected_calibration_error']>c['maximum_calibration_error'] or np.mean([g['net_return'] for g in recent])<c['minimum_regime_mean_return']))}
    db.set_setting('qstatus_'+stable_hash(d['model_id'])[:32],result);return result


def development_valid(db,historical,d):
    plan=db.get(historical.get('plan_id',''))
    folds=historical.get('folds',[])
    return bool(plan and plan['kind']=='qualification_research_plan' and historical.get('model_hash')==d['model_hash'] and len(folds)==3 and all(f.get('interval',{}).get('lower') is not None and f['interval']['lower']>0 and f.get('mse',1)>=0 and f['mse']<f.get('zero_mse',0) and f.get('brier',1)<f.get('base_rate_brier',0) for f in folds))
