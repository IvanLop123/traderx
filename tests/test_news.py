import asyncio
from datetime import timedelta
import httpx
import pytest
from test_platform import db
from test_ensemble import evidence
from test_personal_paper import Market
from backend.schemas.contracts import now
from backend.intelligence.news import NewsService,classify,current_evidence,live_governance
from backend.research.alpha.registry import context
from backend.ensemble.engine import decide
from backend.ensemble.lifecycle import Recommendations

def article(at=None,**kw):
    t=(at or now()).isoformat()
    return {'id':123,'headline':'Bitcoin cuts guidance after earnings miss','summary':'Outlook lowered','symbols':['BTCUSD'],'created_at':t,'updated_at':t,'source':'fixture','url':'https://example.com/news/123',**kw}

@pytest.mark.parametrize('text,category',[
 ('Earnings results beat estimates','earnings/results'),('Company lowers guidance','guidance'),
 ('A merger acquisition agreed','M&A'),('Analyst upgrades shares','analyst actions'),
 ('CEO resigns','management changes'),('Convertible notes offering announced','financing/capital raises'),
 ('SEC charges issuer','regulatory/legal'),('Company launches product partnership','product/business developments'),
 ('Federal Reserve interest rates unchanged','macro/industry events')])
def test_classification_categories(text,category):assert category in classify(text)['categories']

def test_ambiguous_negation_and_no_calibrated_claim():
    for title in ['Company denies bankruptcy','Company may cut guidance','Upgrade or downgrade?']:
        c=classify(title);assert c['direction']=='uncertain';assert c['predictive_weight']==0

def test_dedup_revisions_mapping_and_receipt_time(db):
    svc=NewsService(db,{});t=now();a=article(t-timedelta(hours=1))
    affected,items=svc.ingest([a,a],t);assert affected==['BTC-USD'];assert len(items)==1;assert items[0]['available_at']==t.isoformat()
    assert svc.ingest([a],t+timedelta(seconds=5))==([],[])
    b={**a,'id':456,'headline':a['headline'].upper()+'!'}
    svc.ingest([b],t);assert len(svc.recent('BTC-USD')['events'])==1
    c={**a,'updated_at':(t+timedelta(seconds=1)).isoformat(),'headline':'Bitcoin raises guidance'}
    svc.ingest([c],t+timedelta(seconds=2));events=svc.recent('BTC-USD')['events'];assert len(events)==1;assert events[0]['direction']=='positive'
    assert len(db.records('news_event'))==3
    assert svc.ingest([a],t+timedelta(seconds=10))==([],[])
    assert not current_evidence(events,t-timedelta(seconds=1))
    assert not current_evidence(events,t+timedelta(days=3))
    assert current_evidence(events,(t+timedelta(seconds=3)).isoformat())==events

def test_relevance_future_and_unknown_tickers(db):
    svc=NewsService(db,{})
    assert svc.ingest([article(symbols=['NOT_A_REAL_TICKER'])])==([],[])
    assert svc.ingest([article(now()+timedelta(days=1))])==([],[])
    affected,items=svc.ingest([article(symbols=[],headline='Federal Reserve holds interest rates')]);assert not affected;assert items[0]['scope'].startswith('macro')

def test_news_recomputes_only_affected_and_never_creates_forecast(db):
    t=now();row=evidence(t);asset=Market().lookup('BTC-USD');other=evidence(t,symbol='ETH-USD')
    db.set_setting('model_opportunities',{'rows':[row,other],'assets':{'BTC-USD':asset,'ETH-USD':{**asset,'symbol':'ETH-USD'}}})
    initial=decide(row,asset,at=t);assert initial['action']=='BUY'
    svc=NewsService(db,{})
    asyncio.run(svc.consume([article(t)]))
    changes=Recommendations(db).recent();assert len(changes)==1;assert changes[0]['symbol']=='BTC-USD';assert changes[0]['after']['action']=='NO TRADE'
    e=decide(context(row,live_governance(db)),asset);assert e['edge']==initial['edge'];assert e['family_weights']==initial['family_weights'];assert len(e['news_revision_ids'])==1
    assert e['evidence_families'][0]['predictive_weight']==0
    assert not Recommendations(db).cycle(symbols={'BTC-USD'})
    svc.ingest([article(t+timedelta(seconds=1),headline='Bitcoin raises guidance')],t+timedelta(seconds=2))
    later=decide(context(row,live_governance(db),t+timedelta(seconds=3)),asset,at=t+timedelta(seconds=3));assert later['action']=='BUY'
    # Historical timestamps never receive newly collected events.
    assert decide(context(row,live_governance(db),t-timedelta(seconds=1)),asset,at=t-timedelta(seconds=1))['news_revision_ids']==[]

def test_entitlement_status_and_disabled_missing_keys(db):
    assert NewsService(db,{}).status()['status']=='NOT_CONFIGURED'
    svc=NewsService(db,{'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture','ALPACA_NEWS_ENABLED':'false'})
    assert svc.status()['status']=='DISABLED'
    asyncio.run(svc.run(asyncio.Event()))
    svc.cfg['ALPACA_NEWS_ENABLED']='true';svc.update_status(status='STREAMING',entitlement='Real-time stream access verified',stream_heartbeat_at=(now()-timedelta(minutes=3)).isoformat())
    assert svc.status()['status']=='STALE';assert 'verified' in svc.status()['entitlement']

def test_rest_collection_is_not_session_gated_and_unavailable_is_graceful(db):
    seen=[];a=article()
    def handle(req):
        seen.append(req);return httpx.Response(200,json={'news':[a],'next_page_token':None})
    svc=NewsService(db,{'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture'},httpx.MockTransport(handle))
    asyncio.run(svc.poll());assert len(seen)==1;assert svc.status()['rest_status']=='WORKING';assert len(svc.recent()['events'])==1
    svc.transport=httpx.MockTransport(lambda req:httpx.Response(403,json={}))
    asyncio.run(svc.poll());assert svc.status()['rest_status']=='ENTITLEMENT_UNAVAILABLE';assert len(svc.recent()['events'])==1

    svc.update_status(rest_error='Collection failed; retry scheduled')
    svc.transport=httpx.MockTransport(handle)
    asyncio.run(svc.poll());assert svc.status()['rest_status']=='WORKING';assert svc.status()['rest_error'] is None
