"""Canonical provider contract. No consuming module imports an OpenAI SDK."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal
import httpx
from pydantic import Field
from backend.schemas.contracts import Contract
from backend.core.config import AISettings

Task = Literal['transcript','filing','news','contradiction','bottleneck','theme','semantic_disagreement','summary','chat']
class TextTask(Contract):
    task: Task
    text: str = Field(min_length=1, max_length=100000)
    source_reference: str = Field(min_length=1, max_length=1000)
    automated: bool = True
    difficult: bool = False

class Finding(Contract):
    topic: str = Field(max_length=100)
    value: str | None = Field(default=None,max_length=2000)
    quote: str = Field(min_length=1,max_length=2000)
    confidence: float = Field(ge=0,le=1)

class Extraction(Contract):
    summary: str = Field(max_length=6000)
    findings: list[Finding] = Field(default_factory=list,max_length=30)
    uncertainty: str = Field(max_length=2000)

@dataclass
class Completion:
    content: str
    input_tokens: int | None
    output_tokens: int | None
    model: str

class LLMProvider(ABC):
    name: str
    model: str
    @abstractmethod
    async def complete(self, system: str, text: str, max_tokens: int) -> Completion: ...

class DisabledLLMProvider(LLMProvider):
    name='off'; model='none'
    async def complete(self, system, text, max_tokens):
        raise RuntimeError('AI_DISABLED')

class LocalLLMProvider(LLMProvider):
    name='local'
    def __init__(self, base_url, model, api_key='', transport=None):
        self.base_url=base_url.rstrip('/'); self.model=model; self.api_key=api_key; self.transport=transport
    async def complete(self, system, text, max_tokens):
        headers={'Authorization':'Bearer '+self.api_key} if self.api_key else {}
        payload={'model':self.model,'messages':[{'role':'system','content':system},{'role':'user','content':text}],
                 'max_tokens':max_tokens,'temperature':0,'response_format':{'type':'json_object'}}
        return await self._request(payload,headers)
    async def _request(self,payload,headers):
        # No retry: a timeout may already have consumed tokens.
        async with httpx.AsyncClient(timeout=90,trust_env=False,follow_redirects=False,transport=self.transport) as c:
            r=await c.post(self.base_url+'/chat/completions',headers=headers,json=payload)
            r.raise_for_status(); data=r.json()
        choice=data['choices'][0]
        if choice.get('finish_reason') not in ('stop',None): raise ValueError('Incomplete response')
        usage=data.get('usage') or {}
        return Completion(choice['message']['content'],usage.get('prompt_tokens'),usage.get('completion_tokens'),data.get('model',self.model))

class OpenAILLMProvider(LocalLLMProvider):
    name='openai'
    def __init__(self,model,api_key,transport=None):
        super().__init__('https://api.openai.com/v1',model,api_key,transport)
    async def complete(self,system,text,max_tokens):
        payload={'model':self.model,'store':False,'messages':[{'role':'system','content':system},{'role':'user','content':text}],
                 'max_completion_tokens':max_tokens,'response_format':{'type':'json_object'}}
        return await self._request(payload,{'Authorization':'Bearer '+self.api_key})

class HybridLLMProvider(LLMProvider):
    name='hybrid'
    def __init__(self,local,openai,settings):
        self.local=local; self.openai=openai; self.settings=settings; self.model=local.model
    def route(self,task:TextTask):
        qualifies=(self.settings.escalation and task.difficult and task.task in self.settings.escalation_tasks
                   and len(task.text)>=self.settings.escalation_min_chars and bool(self.openai.model))
        return self.openai if qualifies else self.local
    async def complete(self,system,text,max_tokens):
        # Explicit default. Failures/quality never trigger escalation.
        return await self.local.complete(system,text,max_tokens)

def provider_for(settings:AISettings, credentials:dict, task:TextTask, transport=None)->LLMProvider:
    local=LocalLLMProvider(settings.local_base_url,settings.local_model,credentials.get('LOCAL_LLM_API_KEY',''),transport)
    remote=OpenAILLMProvider(settings.openai_model,credentials.get('OPENAI_API_KEY',''),transport)
    if settings.provider=='off': return DisabledLLMProvider()
    if settings.provider=='local': return local
    if settings.provider=='openai': return remote
    escalation=OpenAILLMProvider(settings.escalation_model,credentials.get('OPENAI_API_KEY',''),transport)
    return HybridLLMProvider(local,escalation,settings).route(task)
