import numpy as np
from backend.research.governance import block_bootstrap,strategy_family,cscv_diagnostic,compare_forecasters

def test_bootstrap_reproducibility_and_family_adjustment():
    r=np.random.default_rng(2).normal(0,.01,200)
    a=block_bootstrap(r);assert a==block_bootstrap(r)
    assert a['mean_daily_return_ci_95'][0]<0<a['mean_daily_return_ci_95'][1]
    family=strategy_family({'a':r,'b':-r})
    for row in family['tests'].values():assert row['p_value']<=row['adjusted_p_value_by']<=1
    assert block_bootstrap(r[:10])['p_value'] is None

def test_cscv_tied_strategies_not_claimed_successful():
    r=np.random.default_rng(5).normal(0,.01,240)
    result=cscv_diagnostic({'a':r,'b':r})
    assert result['partitions']==70 and result['probability_below_oos_median']==1
