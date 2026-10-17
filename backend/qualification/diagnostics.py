"""Overlapping gates and counterfactual screens, not causal claims or execution overrides."""
from collections import Counter
from math import isfinite
from backend.schemas.contracts import now
from backend.selection.policy import policy
from backend.research.features import stable_hash

THRESHOLDS=(50,60,65,70,80)

def finite(x):return isinstance(x,(int,float)) and isfinite(x)

def diagnose(decisions,p):
    counts=Counter();details=Counter();thresholds={s:0 for s in THRESHOLDS};raw_scores=[];only_qualification=0;unique=set();families=Counter()
    for d in decisions:
        c=d.get('candidate',{});risk=d.get('risk',{});edge=c.get('expected_edge');prob=c.get('probability');unc=c.get('uncertainty');vol=c.get('daily_volatility');cost=c.get('estimated_roundtrip_cost');health=c.get('health',[])+[h for v in c.get('votes',[]) for h in v.get('health',[])];groups=c.get('research_groups',[]);score=c.get('research_score',0)
        unique.add((d.get('symbol'),c.get('feature_available_at')))
        flags={
            'qualification':not c.get('trade_eligible',False),
            'display_score_below_cutoff':c.get('score',0)<p.minimum_score,
            'uncapped_research_score_below_cutoff':score<p.minimum_score,
            'edge_nonpositive':finite(edge) and edge<=0,
            'edge_unavailable':not finite(edge),
            'probability_below_cutoff':finite(prob) and prob<p.minimum_probability,
            'probability_unavailable':not finite(prob),
            'uncertainty_invalid':not finite(unc) or unc<=0,
            'volatility_invalid':not finite(vol) or vol<=0,
            'asset_eligibility':'Universe eligibility unavailable' in risk.get('reasons',[]) or 'Universe eligibility failed' in health,
            'stale_data':any('stale' in h.lower() for h in health),
            'missing_or_invalid_features':any(any(v in h.lower() for v in ['missing','nonfinite','schema','no current feature']) for h in health),
            'feature_drift_or_extreme':any('shift' in h.lower() or 'extreme' in h.lower() for h in health),
            'calibration_drift':any('calibration' in h.lower() for h in health),
            'calibration_qualification_not_evaluated':not c.get('trade_eligible',False),
            'insufficient_research_groups':len(groups)<p.minimum_independent_groups,
            'disagreement_observed':bool(groups) and c.get('agreement',1)<1,
            'estimated_cost_removes_gross_edge':finite(edge) and finite(cost) and edge<=0<edge+cost,
            'drawdown_limit':any('drawdown' in r.lower() for r in risk.get('reasons',[])),
            'position_limit':any('Maximum positions' in r for r in risk.get('reasons',[])),
            'existing_or_pending_position':any('pyramiding' in r for r in risk.get('reasons',[])),
            'quote_not_evaluated':'quote' not in d,
            'risk_capacity_not_evaluated':not risk.get('limits'),
            'capacity_exhausted':bool(risk.get('limits')) and risk.get('notional',0)<=0,
        }
        counts.update(k for k,v in flags.items() if v);details.update(risk.get('reasons',[]));raw_scores.append(score)
        for v in c.get('votes',[]):families.update([v['family']])
        clean=not c.get('health',[]) and len(groups)>=p.minimum_independent_groups and finite(edge) and edge>0 and finite(prob) and prob>=p.minimum_probability and finite(unc) and unc>0 and finite(vol) and vol>0
        for s in THRESHOLDS:thresholds[s]+=bool(clean and score>=s)
        only_qualification+=bool(clean and score>=p.minimum_score and not c.get('trade_eligible'))
    n=len(decisions)
    return {'decisions':n,'unique_asset_feature_timestamps':len(unique),'decision_statuses':dict(Counter(d.get('status','unknown') for d in decisions)),'gates':[{'gate':k,'count':counts[k],'fraction':counts[k]/n if n else 0} for k in flags] if n else [],'raw_reasons':dict(details),'thresholds':[{'threshold':s,'research_screen_passes':v,'qualification_bypassed_for_diagnostic_only':True,'orders_created':0} for s,v in thresholds.items()],'passes_other_observed_screen_except_qualification':only_qualification,'family_vote_counts':dict(families),'interpretation':'Gates overlap; counts must not be added. Research thresholds remove the qualification score cap only for diagnostics. Unrequested quotes, calibration tests and later capacity checks are unknown, not passed. Repeated snapshots are not independent observations.','feature_health_scope':'Feature/drift counts mean at least one family vote was excluded, not necessarily the entire candidate; other healthy groups may remain.', 'disagreement_rule':'Disagreement reduces score; it is not a separate hard rejection. Family dependence groups remain required.','uncertainty_rule':'Missing/nonpositive uncertainty rejects; finite uncertainty discounts score and size rather than using an extra arbitrary cutoff.'}

CURRENT_LIMIT=1000

def refresh_diagnostics(db):
    # Diagnostics do not need every historical feature vector on each polling cycle.
    # All original records remain immutable; only the current display window is bounded.
    from sqlalchemy import select,func
    from backend.storage.database import Record
    p=policy(db);previous=db.setting('qualification_diagnostics',{});original=db.setting('qualification_original_decisions')
    with db.transaction() as session:
        if original is None:
            original=list(session.scalars(select(Record.id).where(Record.kind=='auto_decision').order_by(Record.created_at,Record.id).limit(3514)))
        total=session.scalar(select(func.count()).select_from(Record).where(Record.kind=='auto_decision'))
    if db.setting('qualification_original_decisions') is None:db.set_setting('qualification_original_decisions',original)
    digest=stable_hash(original)
    if previous.get('original_ids_hash')==digest and previous.get('policy')==p.model_dump():baseline=previous['original']
    else:
        baseline_rows=[]
        with db.transaction() as session:
            for offset in range(0,len(original),250):
                baseline_rows.extend(session.scalars(select(Record.payload).where(Record.kind=='auto_decision',Record.id.in_(original[offset:offset+250]))))
        baseline=diagnose(baseline_rows,p)
    rows=db.records('auto_decision',limit=CURRENT_LIMIT)
    current_signature=stable_hash([r['id'] for r in rows])
    current=previous.get('current') if previous.get('current_signature')==current_signature and previous.get('policy')==p.model_dump() else diagnose([r['payload'] for r in rows],p)
    result={'at':now().isoformat(),'original':baseline,'current':current,'original_ids_hash':digest,'policy':p.model_dump(),'current_signature':current_signature,'current_scope':f'Most recent {len(rows):,} of {total:,} recorded decisions; complete history retained.','total_decisions':total,'current_limit':CURRENT_LIMIT}
    db.set_setting('qualification_diagnostics',result);return result
