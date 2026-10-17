import json
import httpx
import pytest
from test_platform import db
from backend.llm.service import LLMService
from backend.llm.providers import TextTask
from backend.intelligence.semantic import project_analysis
from backend.intelligence.ingest import store_document

@pytest.mark.asyncio
async def test_semantic_quotes_cache_provenance_and_features(db):
    text='Analyst: Is demand falling? Manager: We cannot give guidance. Supply is constrained by power.'
    output={'summary':'Management did not give guidance.','findings':[],'uncertainty':'Subjective extraction.','research':{'answers':[{'question_quote':'Is demand falling?','answer_quote':'We cannot give guidance.','question_topic':'demand','answer_topic':'guidance','directness':.1,'disagreement':.4}], 'bottlenecks':[{'company':'Fixture','type':'power','quote':'Supply is constrained by power.'}]}}
    calls=[]
    def handle(request):
        calls.append(request);return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(output)}}],'model':'local-fixture','usage':{'prompt_tokens':10,'completion_tokens':10}})
    service=LLMService(db,credentials={},transport=httpx.MockTransport(handle));db.set_setting('ai',{'provider':'local','local_model':'local-fixture'})
    doc=store_document(db,text=text,kind='transcript',title='Fixture',source_reference='fixture://semantic',symbol='TEST')
    task=TextTask(task='transcript',text=text,source_reference='fixture://semantic',automated=False)
    result=await service.analyze(task);assert result['status']=='COMPLETE'
    projected=project_analysis(db,result,doc['id']);assert projected['scores']['management_evasiveness']==.9
    cached=await service.analyze(task);project_analysis(db,cached,doc['id'])
    assert len(calls)==1 and len(db.records('semantic_research'))==1
    assert all(x['payload']['provider']=='local' for x in db.records('feature') if x['payload']['name']=='management_evasiveness')
    output['research']['bottlenecks'][0]['quote']='This is fabricated'
    invalid=await service.analyze(task.model_copy(update={'text':text+' Additional context.'}))
    assert invalid['status']=='INVALID_OUTPUT'
