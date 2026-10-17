from datetime import timedelta
import pytest
from backend.schemas.contracts import now
from backend.research.copyability import CopyReplayRequest,replay_copyability
from backend.intelligence.social import analyze_posts
from backend.intelligence.quant import trader_metrics

def request(delay=0):
    t=now()-timedelta(days=1)
    q=lambda second,price:{'id':str(second),'symbol':'BTC','kind':'quote','event_at':t+timedelta(seconds=second),'available_at':t+timedelta(seconds=second),'source_reference':'fixture://tape','bid':price-.01,'ask':price+.01,'volume':10000}
    fill=lambda i,side,second:{'id':i,'symbol':'BTC','side':side,'quantity':1,'price':100 if side=='buy' else 110,'fill_at':t+timedelta(seconds=second),'public_at':t+timedelta(seconds=second+delay),'ingested_at':t+timedelta(seconds=second+delay),'source_reference':'fixture://fills'}
    return CopyReplayRequest(fills=[fill('buy','buy',0),fill('sell','sell',20)],analysis_seconds=0,limit_tolerance_bps=2000,original_realized_pnl=10,market={'instruments':[{'symbol':'BTC','asset_class':'crypto','eligible_from':t}], 'events':[q(1,100),q(11,105),q(21,110),q(31,109)],'fee_bps':0,'slippage_bps':0,'initial_cash':1000,'max_position_fraction':1,'max_gross_fraction':1})

def test_publication_delay_changes_replication_and_preserves_clock():
    instant=replay_copyability(request());delayed=replay_copyability(request(10))
    assert instant['copyability']['score']>delayed['copyability']['score']>0
    assert delayed['copyability']['delay_stages'][0]['public_delay_seconds']==10
    assert delayed['fills'][0]['timestamp']>=delayed['copyability']['delay_stages'][0]['earliest_execution_at']

def test_copy_visibility_cannot_precede_fill():
    r=request().model_dump();r['fills'][0]['public_at']-=timedelta(seconds=1)
    with pytest.raises(ValueError):CopyReplayRequest.model_validate(r)

def test_social_dedup_coordination_and_unknown_metrics():
    t=now();p={'id':'1','author_id':'a','text':'$TEST bullish earnings','created_at':t.isoformat(),'public_metrics':{'like_count':3}}
    result=analyze_posts([p,p,{**p,'id':'2','author_id':'b'}],t)
    assert result['mentions']==2 and result['duplicate_text_fraction']==.5
    assert result['mention_velocity_per_hour']==2 and result['cashtags']=={'TEST':2}
    assert result['historical_mention_zscore'] is None and result['semantic_disagreement'] is None

def test_trader_metrics_do_not_fabricate_equity_returns():
    r=trader_metrics([{'pnl':-5,'notional':100,'symbol':'BTC'},{'pnl':9,'notional':200,'symbol':'ETH'}])
    assert r['sharpe'] is None and r['size_increases_after_losses']==1
    assert r['performance_by_asset']['ETH']['realized_pnl']==9
