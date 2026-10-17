"""One deterministic decision boundary for price/text-derived quantitative forecasts.

Variants never earn extra votes. Dependence groups are conservative hypotheses,
not proof of independence. No forecast here authorizes an external order.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
import math
import pandas as pd
from backend.research.features import stable_hash
from backend.schemas.contracts import now
from backend.selection.policy import GROUPS

VERSION='ensemble-v5'
# No demonstrated forward advantage for complex weighting; alternatives remain explicit research modes.
DEFAULT_MODE='equal'
FAMILY_GROUPS={**GROUPS,'advanced_ml':'price_trend'}
FAMILIES=tuple(FAMILY_GROUPS)

def finite(v):return isinstance(v,(int,float)) and math.isfinite(v)

def reliability(v,mode):
    """Bounded evidence discount, never an unconstrained recent-winner reward."""
    if mode=='equal':return 1.
    history=v.get('historical_reliability') or {};n=history.get('nonoverlapping_date_clusters',0)
    skill=1-min(1,(history.get('mse') or 1)/max(history.get('zero_mse') or 1,1e-12))
    prior=.5+(n/(n+120)*max(0,skill) if n>=40 else 0)
    if mode=='fixed':return prior
    factors=[]
    for c in v.get('conditional',{}).values():
        n=c.get('date_clusters',0)
        if n>=30 and c.get('usable'):
            mix=n/(n+120);factors.append(1-mix*.5 if c.get('shrunk_net_return',0)<=0 else 1)
    f=v.get('forward_reliability') or {};n=f.get('date_clusters',0)
    if n>=30 and (f.get('mean_net_return') or 0)<=0:factors.append(1-n/(n+120)*.5)
    e=v.get('forward_calibration_error')
    if n>=30 and finite(e):factors.append(max(.5,1-e))
    return max(.25,min(1,prior*min(factors,default=1)))

@dataclass(frozen=True)
class FamilyForecast:
    family:str
    group:str
    direction:str
    edge:float|None
    probability:float|None
    uncertainty:float|None
    applicable:bool
    horizon:int
    historical_reliability:dict
    forward_reliability:dict
    model_ids:list
    weight:float
    abstention:list
    qualified:bool

def forecasts(votes,mode=DEFAULT_MODE,qualified_only=False,horizon=5):
    if horizon not in (1,2,5,10,20):raise ValueError('Unsupported forecast horizon')
    buckets=defaultdict(list)
    for v in votes:
        if v.get('family') in FAMILY_GROUPS:buckets[v['family']].append(v)
    out=[]
    for family in FAMILIES:
        # Deterministic representative, not an average affected by duplicate count.
        unique={stable_hash({k:x for k,x in v.items() if k not in ('model_id','artifact_hash')}):v for v in buckets[family]}
        pool=[v for v in unique.values() if not v.get('health') and (not qualified_only or v.get('eligible')) and v.get('horizon',5)==horizon and all(finite(v.get(k)) for k in ('prediction_after_cost','probability','uncertainty')) and 0<=v['probability']<=1 and v['uncertainty']>0]
        pool.sort(key=lambda v:(-reliability(v,'fixed'),stable_hash({k:x for k,x in v.items() if k not in ('model_id','artifact_hash')})))
        v=pool[0] if pool else {};edge=v.get('prediction_after_cost');valid=bool(v)
        out.append(FamilyForecast(family,FAMILY_GROUPS[family],('positive' if edge>0 else 'negative' if edge<0 else 'neutral') if valid else 'abstain',edge,v.get('probability'),v.get('uncertainty'),valid,horizon,v.get('historical_reliability',{}),v.get('forward_reliability',{}),[v['model_id']] if valid else [],reliability(v,'fixed' if mode=='dynamic' and 'alpha_id' in v else mode)*(max(.001,min(2.,v.get('adaptive_multiplier',1.))) if mode=='dynamic' else 1.) if valid else 0,[] if valid else [f'No healthy compatible {horizon}-session forecast'],bool(v.get('eligible'))))
    return out

def decide(row,asset=None,held=False,at=None,mode=DEFAULT_MODE,qualified_only=False):
    if mode not in ('equal','fixed','dynamic'):raise ValueError('Unknown weighting method')
    asset=asset or row;at=at or now();fs=forecasts(row.get('votes',[]),mode,qualified_only,row.get('horizon_sessions',5));groups=defaultdict(list)
    # Dependence profiles must describe these exact model artifacts, not proxy ranks.
    profile=row.get('strategy_return_dependence') or {};merged={g:g for g in FAMILY_GROUPS.values()};used=[]
    def root(g):
        while merged[g]!=g:g=merged[g]
        return g
    try:usable_profile=profile.get('horizon_sessions')==row.get('horizon_sessions',5) and pd.Timestamp(profile['end_at'])<pd.Timestamp(row['feature_available_at']) and pd.Timestamp(profile['known_at'])<=pd.Timestamp(at)
    except (KeyError,ValueError,TypeError):usable_profile=False
    if usable_profile:
        models={m:f.group for f in fs if f.applicable for m in f.model_ids}
        for pair in profile.get('pairs',[]):
            a,b=pair.get('model_a'),pair.get('model_b');corr=pair.get('return_correlation')
            if a in models and b in models and pair.get('nonoverlapping_dates',0)>=40 and finite(corr) and .8<=corr<=1:
                ga,gb=root(models[a]),root(models[b]);merged[gb]=ga;used.append(pair)
    fs=[replace(f,group=root(f.group)) for f in fs]
    current_cost=row.get('current_roundtrip_cost');prior_cost=row.get('estimated_roundtrip_cost');cost_adjustment=0.
    if finite(current_cost) and finite(prior_cost) and current_cost>=0 and prior_cost>=0:
        cost_adjustment=current_cost-prior_cost
        fs=[replace(f,edge=f.edge-cost_adjustment,direction='positive' if f.edge-cost_adjustment>0 else 'negative' if f.edge-cost_adjustment<0 else 'neutral') if f.applicable else f for f in fs]
    for f in fs:
        if f.applicable:groups[f.group].append(f)
    gs=[]
    for group,items in sorted(groups.items()):
        # Family weights sum to one within each dependence group; adding trend variants
        # cannot add independent confirmation or increase that group's external budget.
        total=sum(f.weight for f in items)
        gs.append({'group':group,'edge':sum(f.edge*f.weight for f in items)/total,'probability':sum(f.probability*f.weight for f in items)/total,'uncertainty':sum(f.uncertainty*f.weight for f in items)/total,'raw_weight':min(f.weight for f in items),'families':[f.family for f in items]})
    weights=[g['raw_weight'] for g in gs]
    # Cap any dependence group at 50%; two groups must have equal weight.
    if len(weights)>=2:
        total=sum(weights)
        for i in range(len(weights)):
            weights[i]=min(weights[i],sum(weights)-weights[i])
    total=sum(weights)
    for g,w in zip(gs,weights):g['weight']=w/total if total else 0
    edge=sum(g['edge']*g['weight'] for g in gs) if gs else None
    prob=sum(g['probability']*g['weight'] for g in gs) if gs else None
    # No fictitious sqrt(N) confidence gain from correlated forecasts.
    unc=math.sqrt(sum(g['weight']*(g['uncertainty']**2+(g['edge']-edge)**2) for g in gs)) if gs else None
    reasons=[]
    try:fresh=0<=(pd.Timestamp(at)-pd.Timestamp(row['feature_available_at'])).total_seconds()<=4*86400
    except (KeyError,ValueError,TypeError):fresh=False
    if len(gs)<2:reasons.append('At least two distinct dependence groups required')
    if not fresh:reasons.append('Feature evidence unavailable or stale')
    if row.get('health'):reasons+=row['health']
    if not asset.get('eligibility',{}).get('eligible',False):reasons.append('Liquidity or data eligibility failed')
    positive=[g for g in gs if g['edge']>0];negative=[g for g in gs if g['edge']<0]
    if len(gs)<2 or not fresh:action='INSUFFICIENT EVIDENCE'
    elif reasons:action='NO TRADE'
    elif edge<=0 and len(negative)>=2:action='SELL' if held else 'NO TRADE';reasons.append('Nonpositive long-side edge; selling only existing holdings')
    elif edge>0 and prob>=.55 and edge>=unc*.25 and len(positive)>=2 and sum(g['weight'] for g in positive)>=.6:action='HOLD' if held else 'BUY'
    else:action='NO TRADE';reasons.append('Insufficient agreement, calibrated probability or edge relative to uncertainty')
    from backend.intelligence.news import current_evidence
    news=current_evidence(row.get('news_evidence',[]),at)
    adverse=[e for e in news if e['materiality']=='high' and e['direction']=='negative']
    if adverse and action=='BUY':
        action='NO TRADE';reasons.append('Material adverse news requires review; unvalidated news cannot authorize entry')
    family_weights={f.family:next(g['weight'] for g in gs if g['group']==f.group)*f.weight/sum(z.weight for z in fs if z.applicable and z.group==f.group) for f in fs if f.applicable}
    value={'version':VERSION,'mode':mode,'action':action,'edge':edge,'probability':prob,'uncertainty':unc,'uncertainty_method':'Residual scale plus group disagreement; not a coverage-guaranteed interval','horizon_sessions':row.get('horizon_sessions',5),'cost_adjustment':cost_adjustment,'families':[dict(vars(f)) for f in fs],'groups':gs,'family_weights':family_weights,'supporting':[g['group'] for g in positive],'opposing':[g['group'] for g in negative],'reasons':reasons,'status':'EXPERIMENTAL — NOT VALIDATED','qualified_input_only':qualified_only,'return_dependence':{'merged_pairs':used,'basis':'Exact-model realized return streams, minimum 40 nonoverlapping dates; only conservative group merging','status':'APPLIED' if used else 'NO_MATCHING_DEPENDENCE_EVIDENCE'},'external_execution':False,'feature_available_at':row.get('feature_available_at'),'symbol':row.get('symbol',asset.get('symbol')),'regime':row.get('regime'),'regime_compatible':row.get('regime_compatible',True)}
    value['independent_support']=[{'family':max((f for f in fs if f.group==g['group'] and f.applicable),key=lambda f:f.edge).family,'group':g['group'],'edge':g['edge']} for g in sorted(positive,key=lambda g:g['edge'],reverse=True)];value['independent_opposition']=[{'family':min((f for f in fs if f.group==g['group'] and f.applicable),key=lambda f:f.edge).family,'group':g['group'],'edge':g['edge']} for g in sorted(negative,key=lambda g:g['edge'])]
    value['alpha_sources']=[{'alpha_id':v.get('alpha_id'),'family':v['family'],'state':v.get('alpha_state'),'model_id':v.get('model_id')} for v in row.get('votes',[]) if v.get('alpha_id')];value['adaptive_epoch']=row.get('alpha_context',{}).get('weight_epoch')
    value['news_revision_ids']=sorted(e['id'] for e in news)
    value['evidence_families']=[{'family':'news_events','group':'news_events','events':news,'predictive_weight':0.0,'entry_guard':bool(adverse),'validation':'Forward-collected, uncalibrated rule-based evidence; no historical alpha claim'}]
    value['id']='ensemble_'+stable_hash(value);return value

def candidate(row,asset=None,held=False,at=None,qualified_only=False):
    e=decide(row,asset,held,at,qualified_only=qualified_only)
    return {**row,'ensemble':e,'expected_edge':e['edge'],'probability':e['probability'],'uncertainty':e['uncertainty'],'groups':[g['group'] for g in e['groups']],'trade_eligible':bool(row.get('trade_eligible') and e['action']=='BUY'),'would_trade':bool(row.get('would_trade') and e['action']=='BUY')}
