"""Auditable inventory and fail-closed challenger gates. Legacy results are never new holdouts."""
from collections import Counter,defaultdict
import numpy as np
import pandas as pd
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.selection.policy import policy,policy_hash,GROUPS

KINDS=('model','ml_study','ml_trial','cross_study','strategy_study','strategy_model','strategy_comparison','experiment_study','experiment','model_comparison')

def clustered_evidence(observations,minimum=60):
    """One equally weighted return per completed UTC date; no cross-asset pseudo replication."""
    buckets=defaultdict(list)
    for o in observations:
        value=o.get('net_return');date=o.get('completed_at')
        if value is not None and date and np.isfinite(value):buckets[str(date)[:10]].append(float(value))
    values=np.array([np.mean(buckets[k]) for k in sorted(buckets)])
    result={'observations':len(observations),'date_clusters':len(values),'mean_net_return':float(values.mean()) if len(values) else None,'lower_bound':None,'positive_evidence':False,'scope':'UTC date clusters; serial and cross-asset dependence remain'}
    if len(values)>=minimum:
        # Fixed five-date circular block bootstrap, not an IID standard error.
        rng=np.random.default_rng(1729);n=len(values);starts=rng.integers(0,n,(999,int(np.ceil(n/5))));ix=((starts[:,:,None]+np.arange(5))%n).reshape(999,-1)[:,:n]
        result['lower_bound']=float(np.quantile(values[ix].mean(axis=1),.025));result['positive_evidence']=result['lower_bound']>0
    return result

def calibration_quality(pairs,minimum=30):
    """Five predefined probability bins; errors cannot cancel across bins."""
    clean=[(float(p),float(y)) for p,y in pairs if np.isfinite(p) and 0<=p<=1 and y in (0,1)]
    if len(clean)<minimum:return {'observations':len(clean),'expected_calibration_error':None,'brier':None,'bins':[]}
    bins=[]
    for i in range(5):
        values=[(p,y) for p,y in clean if min(int(p*5),4)==i]
        if values:bins.append({'lower':i/5,'upper':(i+1)/5,'n':len(values),'mean_probability':float(np.mean([p for p,y in values])),'observed_frequency':float(np.mean([y for p,y in values]))})
    return {'observations':len(clean),'expected_calibration_error':sum(v['n']*abs(v['mean_probability']-v['observed_frequency']) for v in bins)/len(clean),'brier':float(np.mean([(p-y)**2 for p,y in clean])),'bins':bins,'scope':'Descriptive fixed-bin calibration; minimum independent-date gate applied separately'}

class SelectionRegistry:
    def __init__(self,db):self.db=db
    def refresh(self):
        p=policy(self.db);records=[r for kind in KINDS for r in self.db.records(kind,limit=100000)];lookup={r['id']:r for r in records};family_metrics={}
        for r in records:
            if r['kind']=='strategy_study':
                for f in r['payload'].get('family_results',[]):
                    if f.get('model_id') and (f.get('holdout') or f['model_id'] not in family_metrics):family_metrics[f['model_id']]=(f,r['payload'])
        forward=defaultdict(list)
        for row in self.db.records('forward_outcome',limit=100000):
            x=row['payload'];forward[x['model_id']].append({**x,'net_return':x['realized_pnl']/x['entry_cost'] if x.get('entry_cost',0)>0 else 0.})
        decisions={r['id']:r['payload'] for r in self.db.records('forward_decision',limit=100000)}
        portfolio=defaultdict(list)
        for row in self.db.records('selection_portfolio_daily',limit=None):
            x=row['payload']
            definition=self.db.get(x.get('definition_id',''))
            if not definition or definition['kind']!='selection_portfolio_definition':continue
            frozen=definition['payload']
            if not frozen.get('registered_at','')<x.get('completed_at','') or x.get('criteria_hash')!=frozen.get('criteria_hash'):continue
            for mid in x.get('model_ids',[]):
                artifact=self.db.get(mid)
                if artifact and frozen.get('model_hashes',{}).get(mid)==stable_hash(artifact['payload']):portfolio[mid].append(x)
        rows=[]
        for rec in records:
            x=rec['payload'];rid=rec['id'];kind=rec['kind'];f,study=family_metrics.get(rid,({},{}));parent=lookup.get(x.get('study_id',''),{}).get('payload',{})
            families=x.get('feature_families') or x.get('families') or [x.get('family') or x.get('model') or kind]
            family=x.get('family') or '+'.join(families);group=GROUPS.get(family,'mixed_price_research')
            universe=study.get('identity',{}).get('universe',{}).get('instruments',[])
            assets=[i['symbol'] for i in universe if i['asset_class']==x.get('asset_class')] or x.get('assets') or ([rec['symbol']] if rec['symbol'] else [parent['symbol']] if parent.get('symbol') else [])
            validation=f.get('validation') or x.get('validation') or {'mse':x.get('validation_mse'),'folds':x.get('folds') or x.get('trials',[])}
            holdout=f.get('holdout') or x.get('holdout') or {'mse':x.get('holdout_mse'),'brier':x.get('holdout_brier'),'base_rate_brier':x.get('holdout_training_prior_brier')}
            fe=clustered_evidence(forward[rid],p.minimum_forward_dates);pe=clustered_evidence(portfolio[rid],p.minimum_portfolio_dates)
            registration=self.db.get('challenger_'+stable_hash(rid))
            if not registration:
                self.db.put('selection_challenger',{'model_id':rid,'registered_at':now().isoformat(),'artifact_hash':stable_hash(x),'criteria_hash':policy_hash(p),'criteria':p.model_dump(),'incumbent':'cash','state':'challenger','legacy_history_already_observed':True},record_id='challenger_'+stable_hash(rid))
                registration=self.db.get('challenger_'+stable_hash(rid))
            reg=registration['payload']
            recent_dates=sorted({str(o.get('completed_at',''))[:10] for o in forward[rid]})[-60:]
            recent=[o for o in forward[rid] if str(o.get('completed_at',''))[:10] in recent_dates]
            recent_evidence=clustered_evidence(recent,p.minimum_conditional_dates)
            calibrated=[]
            for o in recent:
                decision=decisions.get(o.get('decision_id'),{})
                if decision.get('probability_target')=='positive_after_cost' and o.get('entry_cost',0)>0:
                    calibrated.append((float(decision['probability']),float(o['realized_pnl']>0)))
            calibration=calibration_quality(calibrated,p.minimum_conditional_dates)
            calibration_error=calibration['expected_calibration_error'] if recent_evidence['date_clusters']>=p.minimum_conditional_dates else None
            evaluation=self.db.get(self.db.setting('selection_approval_'+stable_hash([rid,reg['criteria_hash']]),''))
            # Approvals can only come from the audited prospective comparison evaluator below.
            verified=bool(evaluation and evaluation['kind']=='selection_eligibility' and evaluation['payload'].get('eligible') and evaluation['payload'].get('artifact_hash')==stable_hash(x))
            reasons=[]
            if kind!='strategy_model':reasons.append('Audit-only legacy study/variant; no compatible frozen strategy adapter')
            if not f.get('development_improved'):reasons.append('Development improvement gates not passed')
            if not holdout.get('nonoverlapping_date_clusters',0)>=p.minimum_validation_dates:reasons.append('Insufficient comparable held-out dates')
            if not fe['positive_evidence']:reasons.append('Insufficient positive independent forward evidence')
            if not pe['positive_evidence']:reasons.append('Insufficient positive preregistered challenger-portfolio evidence')
            if calibration_error is not None and calibration_error>p.maximum_calibration_error:reasons.append('Forward calibration drift exceeds limit')
            if not verified:reasons.append('No preregistered chronological challenger approval; incumbent remains cash')
            qualified=self.db.setting('qstatus_'+stable_hash(rid)[:32],{})
            terminal=self.db.get(qualified.get('terminal_receipt_id',''))
            definition=self.db.get(qualified.get('definition_id',''))
            if definition:
                from backend.qualification.integrity import implementation_hash,quarantined
                bound=bool(quarantined(self.db,definition['payload']) and terminal and terminal['kind']=='qualification_terminal' and terminal['payload'].get('state')=='QUALIFIED_FOR_MODEL_PAPER' and terminal['payload'].get('model_hash')==stable_hash(x) and qualified.get('criteria_hash')==definition['payload']['criteria_hash'] and definition['payload'].get('implementation_hash')==implementation_hash())
                recent_status=bool(qualified.get('at') and 0<=(pd.Timestamp(now())-pd.Timestamp(qualified['at'])).total_seconds()<=7200)
                reasons=[] if bound and recent_status and qualified.get('execution_allowed') and kind=='strategy_model' else ['Qualification: '+qualified.get('state','FORWARD_TESTING'),*qualified.get('suspension_reasons',[])]
            eligible=not reasons
            rows.append({'id':rid,'development_plan_current':bool(x.get('data_version')==self.db.setting('qualification_research',{}).get('id')) if kind=='strategy_model' and self.db.setting('qualification_research') else True,'qualification_state':qualified.get('state','RESEARCH_ONLY'),'source_kind':kind,'artifact_hash':stable_hash(x),'family':family,'dependence_group':group,'assets':assets,'asset_class':x.get('asset_class','mixed'),'target':x.get('target') or x.get('selected',{}).get('target','return'),'horizon':x.get('horizon') or x.get('hyperparameters',{}).get('horizon') or x.get('selected',{}).get('horizon'),'features':x.get('columns') or x.get('features') or parent.get('features',[]),'training_period':x.get('splits',{}).get('training') or x.get('periods') or {'available_before':x.get('feature_available_before'),'boundaries':study.get('identity',{}).get('boundaries',[])},'validation':validation,'holdout':holdout,'forward':fe,'recent_forward':recent_evidence,'forward_calibration_error':calibration_error,'forward_calibration':calibration,'portfolio':pe,'applicable_regimes':list(f.get('validation_by',{}).get('regime',{})),'conditional_validation':{k:v for k,v in f.get('validation_by',{}).items() if k!='symbol'},'transaction_costs':study.get('identity',{}).get('cost_rule') or x.get('request') or 'See source record; not assumed free','calibration':x.get('calibration') or {'brier':holdout.get('brier'),'base_rate_brier':holdout.get('base_rate_brier'),'method':'earlier temporal sigmoid' if kind=='strategy_model' else 'unavailable'},'eligibility':'eligible' if eligible else 'challenger_blocked','reasons':reasons,'meta_weight':1. if eligible else 0.,'registration':reg,'stages':{'historical_walk_forward':'source audit; three frozen folds required','frozen_holdout':'legacy dates already inspected; future preregistration required','forward':fe,'portfolio_comparison':pe,'eligibility':'passed' if eligible else 'blocked'},'missing_context':['dated market capitalization','sector-conditional independent evidence','correlation-regime performance']})
        result={'as_of':now().isoformat(),'rows':rows,'count':len(rows),'by_kind':dict(Counter(r['source_kind'] for r in rows)),'eligible':sum(r['eligibility']=='eligible' for r in rows),'incumbent':'cash' if not any(r['eligibility']=='eligible' for r in rows) else 'explicitly approved challengers','dependence_groups':GROUPS,'criteria':p.model_dump(),'criteria_hash':policy_hash(p),'warning':'Variants and price-derived families are correlated. Group counts are conservative voting units, not proof of statistical independence.'}
        self.db.set_setting('selection_registry',result);return result
    def get(self):return self.db.setting('selection_registry') or self.refresh()
    def evaluate(self,model_id,evidence_id):
        """Accept only internally generated, preregistered prospective evaluation receipts."""
        reg=self.db.get('challenger_'+stable_hash(model_id));ev=self.db.get(evidence_id);artifact=self.db.get(model_id)
        if not reg or not ev or ev['kind']!='selection_evaluation' or not artifact:raise ValueError('Registered challenger and saved evaluation required')
        r=reg['payload'];e=ev['payload']
        expected={'definition_id':'selection_definition','walk_forward_id':'selection_walk_forward','holdout_id':'selection_holdout','forward_id':'selection_forward','portfolio_id':'selection_portfolio_comparison'}
        sources={key:self.db.get(e.get(key,'')) for key in expected}
        linked=all(source and source['kind']==expected[key] and source['payload'].get('model_id')==model_id and source['payload'].get('artifact_hash')==r['artifact_hash'] and source['payload'].get('criteria_hash')==r['criteria_hash'] for key,source in sources.items())
        gates={
            'model_binding':e.get('model_id')==model_id,
            'prospective_source_receipts':linked,
            'ensemble_calibration':linked and 0<=sources['portfolio_id']['payload'].get('ensemble_calibration_error',1)<=r['criteria']['maximum_calibration_error'],
            'frozen_before_evaluation':e.get('definition_at','')>=r['registered_at'] and e.get('definition_at','')<e.get('holdout_start',''),
            'artifact_unchanged':e.get('artifact_hash')==r['artifact_hash']==stable_hash(artifact['payload']),
            'criteria_unchanged':e.get('criteria_hash')==r['criteria_hash'],
            'walk_forward':e.get('walk_forward_folds',0)>=3 and e.get('walk_forward_passed') is True,
            'frozen_holdout':e.get('holdout_dates',0)>=r['criteria']['minimum_validation_dates'] and e.get('holdout_lower_bound',-1)>0,
            'forward':e.get('forward_dates',0)>=r['criteria']['minimum_forward_dates'] and e.get('forward_lower_bound',-1)>0,
            'portfolio':e.get('portfolio_dates',0)>=r['criteria']['minimum_portfolio_dates'] and e.get('portfolio_excess_lower_bound',-1)>0,
            'calibration':0<=e.get('calibration_error',1)<=r['criteria']['maximum_calibration_error']}
        decision={'model_id':model_id,'evidence_id':evidence_id,'gates':gates,'eligible':all(gates.values()),'at':now().isoformat(),'artifact_hash':r['artifact_hash'],'criteria_hash':r['criteria_hash']}
        receipt_id='selection_eligibility_'+stable_hash(decision)
        self.db.put('selection_eligibility',decision,record_id=receipt_id)
        self.db.set_setting('selection_approval_'+stable_hash([model_id,r['criteria_hash']]),receipt_id)
        return decision
