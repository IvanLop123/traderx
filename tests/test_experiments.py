import copy
import pytest
from test_platform import db,bars
from backend.research.experiments import ExperimentDefinition,ExperimentLab
from backend.schemas.contracts import now

def seed(db,bars):
    for i,b in enumerate(bars):db.put('bar',b,b['symbol'],record_id=str(i))

def test_declaration_seals_and_purges_holdout(db,bars):
    seed(db,bars);lab=ExperimentLab(db)
    result=lab.run(ExperimentDefinition(hypothesis='Momentum relates to return',universe=['BTC-USD'],strict_observed=False,horizon=2))
    assert result['holdout']['status']=='SEALED' and 'mean_net_return_after_costs' not in result['holdout']
    assert result['split']['purged']>0
    released=lab.release(result['definition_id']);assert released==lab.release(result['definition_id'])
    assert released['holdout']['samples']==result['holdout']['samples']
    assert lab.families()['registered_trials']==1 and lab.families()['released_holdouts']==1
    with pytest.raises(ValueError):lab.run(ExperimentDefinition(hypothesis='Strict history unavailable',universe=['BTC-USD']))
    counts=lab.families();assert counts['registered_trials']==2 and counts['failed_trials']==1
    assert len(counts['families']['declared_signals'])==2

def test_liquidity_filter_never_uses_future_volume(db,bars):
    seed(db,bars);lab=ExperimentLab(db);d=ExperimentDefinition(hypothesis='Prior volume controls eligibility',universe=['BTC-USD'],strict_observed=False,horizon=5,min_volume=100)
    rows,_=lab.dataset(d);assert rows[0]['selected']
    revised=copy.deepcopy(bars);revised[21]['volume']=0
    other=type(db)('sqlite://');from backend.storage.database import Base
    Base.metadata.create_all(other.engine);seed(other,revised)
    second,_=ExperimentLab(other).dataset(d)
    assert second[0]['selected']==rows[0]['selected']
    assert second[0]['capacity_units']==rows[0]['capacity_units']

def test_excess_benchmark_matches_same_open_close_window(db,bars):
    seed(db,bars)
    d=ExperimentDefinition(hypothesis='Self benchmark must have no excess',universe=['BTC-USD'],benchmark='BTC-USD',target='excess_return',strict_observed=False)
    rows,_=ExperimentLab(db).dataset(d)
    assert rows and all(abs(r['target'])<1e-12 for r in rows)

def test_future_evidence_not_backdated(db,bars):
    seed(db,bars)
    db.put('feature',{'name':'insider_score','value':1,'available_at':now().isoformat()},'BTC-USD')
    rows,_=ExperimentLab(db).dataset(ExperimentDefinition(hypothesis='Source must precede decision',universe=['BTC-USD'],signal='insider_score',strict_observed=False))
    assert rows==[]
