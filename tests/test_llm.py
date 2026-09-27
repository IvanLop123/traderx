import asyncio
import json
import httpx
import pytest
from backend.core.config import AISettings
from backend.storage.database import Database, Base
from backend.llm.service import LLMService
from backend.llm.providers import TextTask

@pytest.fixture
def setup(tmp_path):
    db=Database('sqlite:///'+str(tmp_path/'test.db')); Base.metadata.create_all(db.engine)
    return db

def configure(db,**kwargs):
    db.set_setting('ai',AISettings(provider='local',local_model='test-local',automated=True,**kwargs).model_dump())

def response(req):
    return httpx.Response(200,json={'model':'test-local','choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'Summary','findings':[{'topic':'demand','value':'strong','quote':'Revenue increased','confidence':0.8}],'uncertainty':'Unverified management statement'})}}],'usage':{'prompt_tokens':100,'completion_tokens':50}})

def task(**kwargs): return TextTask(task='transcript',text='Revenue increased due to strong demand.',source_reference='fixture://transcript',**kwargs)

async def test_off_zero_calls(setup):
    def fail(_): pytest.fail('Network called in off mode')
    service=LLMService(setup,{},httpx.MockTransport(fail))
    assert (await service.analyze(task()))['status']=='DISABLED'
    assert (await service.local_health())['status']=='DISABLED'
    assert service.usage()['calls']==0

def test_environment_change_takes_effect_on_restart(setup,monkeypatch):
    first=LLMService(setup,{})
    assert first.settings().provider=='off'
    setup.set_setting('ai',AISettings(provider='hybrid',local_model='old').model_dump())
    assert LLMService(setup,{}).settings().provider=='hybrid'
    monkeypatch.setenv('LLM_PROVIDER','local')
    monkeypatch.setenv('LOCAL_LLM_MODEL','new-local')
    restarted=LLMService(setup,{})
    assert restarted.settings().provider=='local'
    assert restarted.settings().local_model=='new-local'

async def test_local_server_can_recover_without_losing_failed_attempt_audit(setup):
    configure(setup)
    def unavailable(req):raise httpx.ConnectError('Local server offline')
    first=LLMService(setup,{},httpx.MockTransport(unavailable))
    assert (await first.analyze(task(automated=False)))['status']=='PROVIDER_UNAVAILABLE'
    recovered=LLMService(setup,{},httpx.MockTransport(response))
    assert (await recovered.analyze(task(automated=False)))['status']=='COMPLETE'
    assert (await recovered.analyze(task(automated=False)))['status']=='CACHED'
    assert recovered.usage()['calls']==2 and recovered.usage()['estimated_cost']==0

async def test_local_no_key_and_permanent_cache(setup):
    configure(setup); calls=[]
    def handle(req):
        assert 'authorization' not in req.headers
        assert req.url.host=='localhost'; calls.append(1); return response(req)
    service=LLMService(setup,{},httpx.MockTransport(handle))
    assert (await service.analyze(task()))['status']=='COMPLETE'
    fresh=LLMService(setup,{},httpx.MockTransport(handle))
    assert (await fresh.analyze(task()))['status']=='CACHED'
    assert len(calls)==1 and fresh.usage()['estimated_cost']==0
    s=fresh.settings(); s.prompt_version='v2'; setup.set_setting('ai',s.model_dump())
    assert (await fresh.analyze(task()))['status']=='COMPLETE'
    assert len(calls)==2

async def test_budget_pauses_before_request(setup):
    s=AISettings(provider='openai',automated=True,openai_automated=True,daily_budget=0)
    setup.set_setting('ai',s.model_dump())
    def fail(_): pytest.fail('Budget gate bypassed')
    service=LLMService(setup,{'OPENAI_API_KEY':'test'},httpx.MockTransport(fail))
    assert (await service.analyze(task()))['status']=='BUDGET_PAUSED'

async def test_concurrent_duplicates_and_cost(setup):
    setup.set_setting('ai',AISettings(provider='openai',automated=True,openai_automated=True).model_dump())
    service=LLMService(setup,{'OPENAI_API_KEY':'test'},httpx.MockTransport(response))
    outcomes=await asyncio.gather(*(service.analyze(task()) for _ in range(5)))
    assert sum(r['status']=='COMPLETE' for r in outcomes)==1
    assert service.usage()['calls']==1
    assert service.usage()['daily_cost']==pytest.approx(0.0000825)

async def test_hybrid_never_falls_back(setup):
    setup.set_setting('ai',AISettings(provider='hybrid',local_model='local',automated=True,escalation=True,escalation_model='gpt-5.4-nano').model_dump())
    def fail(req):
        assert req.url.host=='localhost'
        raise httpx.ConnectError('offline')
    service=LLMService(setup,{'OPENAI_API_KEY':'test'},httpx.MockTransport(fail))
    assert (await service.analyze(task()))['status']=='PROVIDER_UNAVAILABLE'
    assert service.usage()['estimated_cost']==0

async def test_filter_and_chat_are_explicit(setup):
    configure(setup)
    service=LLMService(setup,{},httpx.MockTransport(response))
    irrelevant=TextTask(task='news',text='A recipe for a birthday cake.',source_reference='fixture://news')
    assert (await service.analyze(irrelevant))['status']=='FILTERED_IRRELEVANT'
    s=service.settings(); s.automated=False; setup.set_setting('ai',s.model_dump())
    assert (await service.analyze(task()))['status']=='AUTOMATED_DISABLED'
    assert (await service.analyze(task(automated=False)))['status']=='COMPLETE'

async def test_bad_quotes_quarantined(setup):
    configure(setup); service=LLMService(setup,{},httpx.MockTransport(response))
    bad=TextTask(task='filing',text='No supported revenue claim here.',source_reference='fixture://bad')
    assert (await service.analyze(bad))['status']=='INVALID_OUTPUT'
    assert (await service.analyze(bad))['status']=='PREVIOUS_INVALID_OUTPUT'

@pytest.mark.parametrize('kind',['ohlcv','tick','pnl','risk','options','portfolio','indicator'])
def test_quant_workloads_rejected(kind):
    with pytest.raises(ValueError): TextTask(task=kind,text='100',source_reference='fixture')

def test_remote_url_not_local():
    with pytest.raises(ValueError): AISettings(local_base_url='https://api.openai.com/v1')

async def test_economical_batch_keeps_individual_permanent_cache(setup):
    configure(setup)
    def handle(req):
        body=json.loads(req.content); documents=json.loads(body['messages'][1]['content'])
        items=[{'document_id':d['document_id'],'summary':'Extracted','findings':[], 'uncertainty':'Limited'} for d in documents]
        return httpx.Response(200,json={'model':'test-local','choices':[{'message':{'content':json.dumps({'items':items})}}],'usage':{'prompt_tokens':200,'completion_tokens':90}})
    service=LLMService(setup,{},httpx.MockTransport(handle))
    a=task(); b=TextTask(task='transcript',text='Margins declined during the quarter.',source_reference='fixture://two')
    results=await service.analyze_many([a,b])
    assert all(r['status']=='COMPLETE' for r in results)
    assert service.usage()['calls']==1
    assert (await service.analyze(b))['status']=='CACHED'
    assert service.usage()['input_tokens']==200

async def test_failed_remote_charge_reserved_and_not_retried(setup):
    setup.set_setting('ai',AISettings(provider='openai',automated=True,openai_automated=True).model_dump())
    calls=[]
    def timeout(req):
        calls.append(1);raise httpx.ReadTimeout('Unknown remote completion')
    service=LLMService(setup,{'OPENAI_API_KEY':'fixture'},httpx.MockTransport(timeout))
    assert (await service.analyze(task()))['status']=='PROVIDER_UNAVAILABLE'
    assert service.usage()['daily_cost']>0
    assert (await service.analyze(task()))['status']=='PREVIOUS_UNCERTAIN'
    assert len(calls)==1

async def test_hourly_limit_even_with_remaining_budget(setup):
    setup.set_setting('ai',AISettings(provider='openai',automated=True,openai_automated=True,calls_per_hour=1).model_dump())
    service=LLMService(setup,{'OPENAI_API_KEY':'fixture'},httpx.MockTransport(response))
    assert (await service.analyze(task()))['status']=='COMPLETE'
    another=task().model_copy(update={'text':'Revenue increased again'})
    assert (await service.analyze(another))['status']=='RATE_PAUSED'

async def test_unknown_price_blocks_model(setup):
    setup.set_setting('ai',AISettings(provider='openai',openai_model='unknown',automated=True,openai_automated=True).model_dump())
    service=LLMService(setup,{'OPENAI_API_KEY':'fixture'},httpx.MockTransport(response))
    assert (await service.analyze(task()))['status']=='PRICING_NOT_CONFIGURED'

async def test_hybrid_budget_gate_stays_local(setup):
    setup.set_setting('ai',AISettings(provider='hybrid',local_model='test-local',automated=True,openai_automated=True,escalation=True,
        escalation_model='gpt-5.4-nano',daily_budget=0,escalation_min_chars=1000).model_dump())
    hosts=[]
    def handle(req):hosts.append(req.url.host);return response(req)
    service=LLMService(setup,{'OPENAI_API_KEY':'fixture'},httpx.MockTransport(handle))
    t=TextTask(task='contradiction',text='Revenue increased. '*100,source_reference='fixture://complex',difficult=True)
    assert (await service.analyze(t))['provider']=='local'
    assert hosts==['localhost']

async def test_explicit_difficult_hybrid_routing(setup):
    setup.set_setting('ai',AISettings(provider='hybrid',local_model='test-local',automated=True,openai_automated=True,escalation=True,
        escalation_model='gpt-5.4-nano',escalation_min_chars=1000).model_dump())
    hosts=[]
    def handle(req):hosts.append(req.url.host);return response(req)
    service=LLMService(setup,{'OPENAI_API_KEY':'fixture'},httpx.MockTransport(handle))
    t=TextTask(task='contradiction',text='Revenue increased. '*100,source_reference='fixture://complex',difficult=True)
    assert (await service.analyze(t))['provider']=='openai'
    assert hosts==['api.openai.com']
