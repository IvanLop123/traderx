import httpx
import pytest
from backend.storage.database import Database,Base
from backend.intelligence.options import option_chain_research,derive_options
from backend.providers.market import MarketProviders

@pytest.fixture
def db(tmp_path):
    d=Database('sqlite:///'+str(tmp_path/'options.db'));Base.metadata.create_all(d.engine);return d

def contract(kind='call',**kwargs):
    return {'symbol':'TEST','contractID':kind,'date':'2025-01-02','expiration':'2025-02-21','type':kind,'strike':'100','bid':'2','ask':'3',
            'volume':'40','open_interest':'20','delta':'.25' if kind=='call' else '-.25','implied_volatility':'.3' if kind=='call' else '.4',**kwargs}

def test_chain_ratios_skew_liquidity_and_source_contracts():
    data={'data':[contract(),contract('put',volume='80')]}
    r=option_chain_research(data,'TEST')
    assert r['totals']['put_call_volume_ratio']==2
    assert r['expirations'][0]['put_minus_call_25_delta_iv']==pytest.approx(.1)
    assert set(r['expirations'][0]['skew_contract_ids'])=={'call','put'}
    assert r['expirations'][0]['near_50_delta_iv'] is None
    assert r['expirations'][0]['median_spread_fraction']==.4
    assert r['activity_rankings'][0]['type']=='put'

def test_missing_zero_and_crossed_not_invented():
    r=option_chain_research({'data':[contract(bid='4',ask='3'),contract('put',open_interest='0',volume='')]},'TEST')
    assert r['totals']['put_call_volume_ratio'] is None
    assert r['expirations'][0]['put_minus_call_25_delta_iv'] is None
    assert r['quote_coverage']['crossed']==1
    assert r['contracts'][1]['volume_to_oi'] is None

def test_invalid_rows_partial_and_all_invalid_rejected():
    r=option_chain_research({'data':[contract(),contract('put',delta='NaN')]},'TEST')
    assert r['status']=='PARTIAL_DATA' and len(r['rejected_rows'])==1
    with pytest.raises(ValueError):option_chain_research({'data':[contract(symbol='OTHER')]},'TEST')
    with pytest.raises(ValueError):option_chain_research({'data':[contract(),contract('put',date='2025-01-03')]},'TEST')

def test_duplicates_do_not_inflate_counts():
    r=option_chain_research({'data':[contract(),contract(),contract('put')]},'TEST')
    assert r['contract_count']==2 and r['totals']['call_volume']==40

def test_old_chains_not_current_features_and_idempotent(db):
    rid=db.put('options',{'data':[contract(),contract('put')]},'TEST')
    r=derive_options(db,rid)
    assert r['feature_ids']==[] and r['evidence_ids']==[rid]
    assert derive_options(db,rid)==r and len(db.records('options_research'))==1
