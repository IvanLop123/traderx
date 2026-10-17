"""Regression checks for source comparisons, observed history and coverage gates."""
import json
from datetime import timedelta
import httpx
import pytest
from test_platform import db
from backend.schemas.contracts import now
from backend.llm.service import LLMService
from backend.intelligence.ingest import store_document
from backend.intelligence.comparisons import neighbors,compare
from backend.intelligence.social import window_metrics
from backend.research.datasets import HistoricalDataset,Coverage,coverage_report,store_dataset,replay_dataset
from test_replay import instrument,quote,action,intent,T
from backend.research.replay import ReplayRequest

@pytest.mark.asyncio
async def test_comparison_filters_quotes_order_and_cache(db):
    prior_text='Revenue guidance for nuclear power supply capacity remains stable.'
    current_text='Revenue guidance for nuclear power supply capacity is reduced.'
    a=store_document(db,text=prior_text,kind='transcript',title='Earlier',source_reference='fixture://prior',symbol='TEST',published_at=now()-timedelta(days=2))['id']
    b=store_document(db,text=current_text,kind='transcript',title='Current',source_reference='fixture://current',symbol='TEST',published_at=now()-timedelta(days=1))['id']
    assert [x['id'] for x in neighbors(db,b)]==[a] and not neighbors(db,a)
    output={'summary':'Guidance changed.','uncertainty':'Different periods may explain the change.','research':{'comparisons':[{'relation':'updates','prior_quote':prior_text,'current_quote':current_text,'explanation':'Reduced guidance.'}]}}
    calls=[]
    def handle(req):
        calls.append(req);return httpx.Response(200,json={'model':'fixture','choices':[{'message':{'content':json.dumps(output)}}]})
    llm=LLMService(db,credentials={},transport=httpx.MockTransport(handle));db.set_setting('ai',{'provider':'off'})
    assert (await compare(db,llm,b,a))['status']=='DISABLED' and not calls
    db.set_setting('ai',{'provider':'local','local_model':'fixture'})
    assert (await compare(db,llm,b,a))['status']=='COMPLETE'
    assert (await compare(db,llm,b,a))['status']=='CACHED' and len(calls)==1
    assert len(db.records('document_comparison'))==1
    output['research']['comparisons'][0].update(prior_quote=current_text,current_quote=prior_text)
    db.set_setting('ai',{'provider':'local','local_model':'fixture','prompt_version':'v2'})
    assert (await compare(db,llm,b,a))['status']=='INVALID_SOURCE_ATTRIBUTION'
    assert len(db.records('document_comparison'))==1

def social_window(start,n,observed=None,complete=True,engagement=1):
    end=start+timedelta(hours=1)
    return {'query':'nuclear','window':{'start':start.isoformat(),'end':end.isoformat(),'complete':complete},'observed_at':(observed or end+timedelta(minutes=1)).isoformat(),
        'data':[{'id':str(i),'text':'nuclear earnings','author_id':'a'+str(i),'created_at':(start+timedelta(minutes=10)).isoformat(),'public_metrics':{'like_count':engagement,'reply_count':0,'retweet_count':0,'quote_count':0}} for i in range(n)]}

def test_social_complete_history_and_matched_engagement(db):
    start=now()-timedelta(days=2)
    for i in range(8):
        d=social_window(start+timedelta(hours=i),i+1);d['metrics']=window_metrics(db,d);db.put('social',d)
    current=social_window(start+timedelta(hours=8),12,engagement=3);m=window_metrics(db,current)
    assert m['history_windows']==8 and m['historical_mention_zscore']>2 and m['complete_window_mentions']==12
    assert m['complete_window_acceleration_per_hour2']==4 and m['engagement_matched_posts']==8
    assert m['engagement_velocity'] is not None
    current['window']['complete']=False;m=window_metrics(db,current)
    assert m['historical_mention_zscore'] is None and m['complete_window_mentions'] is None
    current['window']['complete']=True
    for p in current['data']:p['public_metrics']['like_count']=0
    m=window_metrics(db,current);assert m['engagement_counter_revisions']==8 and m['engagement_velocity'] is None

def test_social_repeated_window_never_multiplies_history(db):
    start=now()-timedelta(days=2)
    for i in range(10):
        d=social_window(start,3,observed=start+timedelta(hours=1,minutes=i+1));d['metrics']=window_metrics(db,d);db.put('social',d)
    d=social_window(start+timedelta(hours=1),4);m=window_metrics(db,d)
    assert m['history_windows']==1 and m['historical_mention_zscore'] is None

def test_historical_coverage_blocks_gaps_and_preserves_actions(db):
    request=ReplayRequest(instruments=[instrument()],events=[quote(0),quote(1,volume=300),action('split',2,2),quote(3,price=50)],intents=[intent()],fee_bps=0,slippage_bps=0)
    d=HistoricalDataset(name='Fixture',source_reference='fixture://authorized-history',universe_definition='All fixture listings, including inactive members',membership_known_at={'TEST':T},request=request)
    r=store_dataset(db,d)
    assert r['coverage']['status']=='BLOCKED'
    with pytest.raises(ValueError,match='coverage blocked'):replay_dataset(db,r['id'])
    d.universe_includes_inactive=True;d.observation_policy='point_in_time';d.corporate_actions=[Coverage(symbol='TEST',start=T,end=T+timedelta(seconds=4),action_types=['split','dividend'],source_reference='fixture://actions',complete_for_window=True)]
    r=store_dataset(db,d);result=replay_dataset(db,r['id']);assert result['positions']['TEST']['quantity']==6
    assert store_dataset(db,d)['id']==r['id']
    d.membership_known_at={'TEST':T+timedelta(days=1)};assert 'FUTURE_MEMBERSHIP:TEST' in coverage_report(d)['issues']
    d.corporate_actions[0].end=T+timedelta(seconds=1);assert any(x.startswith('ACTION_COVERAGE_GAP') for x in coverage_report(d)['issues'])
