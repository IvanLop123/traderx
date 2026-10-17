"""Immutable preregistrations referencing scientific cohorts; prior observations excluded."""
from collections import Counter,defaultdict
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.research.forward import ForwardStudies,EnrollRequest
from backend.selection.policy import policy,GROUPS
from backend.research.strategies import PAIRS
from backend.qualification.integrity import implementation_hash
from backend.qualification.policy import QualificationCriteria

FAMILIES=['momentum','trend_following','mean_reversion','breakout','volatility','cross_sectional_ranking','relative_strength','insider_event','macro_regime','pairs_relative_value','crypto_funding']

def representatives(registry):
    groups=defaultdict(list)
    for r in registry['rows']:
        if r['source_kind']=='strategy_model' and r.get('development_plan_current',True):groups[(r['family'],r['asset_class'])].append(r)
    selected=[]
    for key,rows in sorted(groups.items()):
        def score(r):
            v=r.get('validation') or {};return (v.get('mse') or 1e9)/max(v.get('zero_mse') or 1e-9,1e-9)+(v.get('brier') or 1e9)/max(v.get('base_rate_brier') or 1e-9,1e-9),r['id']
        selected.append(min(rows,key=score))
    return selected

def audit(db,registry):
    studies=ForwardStudies(db).studies();selected=representatives(registry);groups=defaultdict(list)
    for s in studies:groups[GROUPS.get(s['families'][0],'mixed_price_research')].append(s['id'])
    exact=defaultdict(list)
    for s in studies:exact[(s['model_id'],s['symbol'])].append(s['id'])
    r={'at':now().isoformat(),'scientific_studies':len(studies),'distinct_artifacts':len({s['model_id'] for s in studies}),'family_counts':dict(Counter('+'.join(s['families']) for s in studies)),'dependence_groups':dict(groups),'duplicate_model_asset_sets':[v for v in exact.values() if len(v)>1],'representatives':[{'id':s['id'],'family':s['family'],'asset_class':s['asset_class'],'group':s['dependence_group']} for s in selected],'variants_grouped':sum(r['source_kind']=='strategy_model' for r in registry['rows'])-len(selected),'removed_records':0,'unavailable_families':[f for f in FAMILIES if f not in {s['family'] for s in selected}],'independence_warning':'Semantic groups are conservative dependence controls. Empirical residual/prediction correlations must also be reported; shared price data does not create independent experiments.'}
    db.set_setting('qualification_audit',r);return r

def register(db,registry,assets):
    """One frozen definition per model version. Selection uses development evidence only."""
    reps=representatives(registry);criteria=QualificationCriteria();created=[];p=policy(db);fwd=ForwardStudies(db)
    for row in reps:
        mid=row['id'];rid='qualification_'+stable_hash([mid,criteria.model_dump(),implementation_hash()]);old=db.get(rid)
        if old:
            db.set_setting('qcurrent_'+stable_hash(mid)[:32],rid);created.append(old['payload']);continue
        symbols=sorted([a for a in assets if a['asset_class']==row['asset_class'] and a.get('eligibility',{}).get('eligible') and (row['family']!='pairs_relative_value' or a['symbol'] in PAIRS)],key=lambda a:(-(a['eligibility'].get('mean_dollar_volume') or 0),a['symbol']))
        # Three liquid sentinels for individual scientific execution. Portfolio comparison uses full frozen class universe.
        sentinels=[a['symbol'] for a in symbols[:3]]
        d={'id':rid,'model_id':mid,'model_hash':row['artifact_hash'],'family':row['family'],'group':row['dependence_group'],'asset_class':row['asset_class'],'registered_at':now().isoformat(),'implementation_hash':implementation_hash(),'criteria':criteria.model_dump(),'criteria_hash':stable_hash(criteria.model_dump()),'risk_policy':p.model_dump(),'risk_hash':stable_hash(p.model_dump()),'sentinels':sentinels,'universe':[a['symbol'] for a in symbols],'family_count':len(reps),'incumbent_ids':[r['id'] for r in registry['rows'] if r['eligibility']=='eligible' and r['asset_class']==row['asset_class']],'historical_results_already_observed':True,'state':'FORWARD_TESTING' if sentinels else 'RESEARCH_ONLY','evidence_policy':'quarantined_evaluation','phase_rule':'First 40 nonoverlapping completed-date clusters are frozen prospective holdout; subsequent 60 are forward evaluation. Portfolio comparisons collect concurrently but are evaluated last; not claimed as another independent sample.'}
        # Save criteria BEFORE enrollment or inspecting any subsequent result.
        previous=db.setting('qcurrent_'+stable_hash(mid)[:32])
        if not previous and db.get('qualification_'+stable_hash(mid)):previous='qualification_'+stable_hash(mid)
        if previous and previous!=rid:db.put('qualification_supersession',{'previous_id':previous,'new_id':rid,'at':now().isoformat(),'reason':'Model implementation or frozen criteria version changed; no earlier observations carried into the new qualification window'})
        db.put('qualification_definition',d,record_id=rid);db.set_setting('qcurrent_'+stable_hash(mid)[:32],rid)
        ids=[]
        for symbol in sentinels:ids.append(fwd.enroll(EnrollRequest(model_id=mid,symbol=symbol))['id'])
        db.put('qualification_enrollment',{'definition_id':rid,'study_ids':ids,'at':now().isoformat()},record_id=rid+'_enrollment');created.append(d)
    return created
