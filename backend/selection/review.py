"""Read-only challenger review receipts. A review cannot grant execution authority.

Existing, already inspected history never becomes a fresh holdout. Portfolio qualification
must be evaluated in a separately preregistered challenger comparison, before deployment;
incumbent auto trades are monitoring evidence, not a prerequisite for first qualification.
"""
from backend.schemas.contracts import now
from backend.research.features import stable_hash

def review_registry(db,registry):
    rows=[]
    for row in registry['rows']:
        if row['source_kind']!='strategy_model':continue
        stages=[
            {'stage':'historical_walk_forward','status':'incomplete','reason':'Legacy family summaries are development diagnostics; three frozen chronological folds with matched benchmarks are required.'},
            {'stage':'frozen_holdout','status':'blocked','reason':'Inspected legacy history is not independent. Freeze a new evaluation definition before its reserved timestamps.'},
            {'stage':'forward','status':'passed' if row['forward']['positive_evidence'] else 'collecting','observations':row['forward']['date_clusters'],'minimum':registry['criteria']['minimum_forward_dates']},
            {'stage':'portfolio_comparison','status':'passed' if row['portfolio']['positive_evidence'] else 'waiting','observations':row['portfolio']['date_clusters'],'minimum':registry['criteria']['minimum_portfolio_dates'],'reason':'Separate preregistered challenger portfolio versus frozen incumbent; automatic production trades cannot authorize their own strategy.'},
            {'stage':'eligibility','status':row['eligibility'],'reasons':row['reasons']}]
        item={'model_id':row['id'],'artifact_hash':row['artifact_hash'],'criteria_hash':registry['criteria_hash'],'at':now().isoformat(),'stages':stages,'eligible':row['eligibility']=='eligible','incumbent':registry['incumbent'],'review_only':True}
        rid='selection_review_'+stable_hash({k:v for k,v in item.items() if k!='at'});db.put('selection_review',item,record_id=rid);rows.append({**item,'id':rid})
    result={'at':now().isoformat(),'rows':rows,'incumbent':registry['incumbent'],'warning':'No forced promotion. New evidence adapters must provide frozen source-linked receipts; existing inspected summaries cannot pass the prospective gates.'}
    db.set_setting('selection_reviews',result);return result
