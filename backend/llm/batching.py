"""Small homogeneous text batches with per-document claims and cache provenance."""
import json
from pydantic import Field
from sqlalchemy import select
from backend.schemas.contracts import Contract, uid, now
from backend.storage.database import LLMRun
from backend.llm.providers import Extraction, provider_for
from backend.llm.service import SYSTEM, digest, stats_from
from scripts.provider_common import ROOT

class BatchItem(Extraction):
    document_id:str
class BatchOutput(Contract):
    items:list[BatchItem]=Field(max_length=8)

async def batch_analyze(service,tasks):
    settings=service.settings()
    if len(tasks)<2 or settings.provider=='off' or not settings.automated:
        return [await service.analyze(t) for t in tasks]
    # Chat and difficult tasks remain individually routed; routine short texts can batch.
    if any(t.task!=tasks[0].task or not t.automated or t.difficult or t.task=='chat' for t in tasks):
        return [await service.analyze(t) for t in tasks]
    words=[x.lower() for x in settings.watch_terms]
    if any(t.task in ('news','theme','summary') and not any(w in t.text.lower() for w in words) for t in tasks):
        return [await service.analyze(t) for t in tasks]
    provider=provider_for(settings,service.credentials,tasks[0],service.transport)
    if not provider.model or (provider.name=='openai' and (not settings.openai_automated or not service.credentials.get('OPENAI_API_KEY'))):
        return [await service.analyze(t) for t in tasks]
    def key(t):
        return digest(json.dumps([digest(t.text),t.task,provider.name,provider.model,settings.local_base_url if provider.name=='local' else '',settings.prompt_version,digest(SYSTEM)],separators=(',',':')))
    keys=[key(t) for t in tasks]
    if len(set(keys))<len(keys): return [await service.analyze(t) for t in tasks]
    prices=json.loads((ROOT/'config/llm_prices.json').read_text())['usd_per_million_tokens']; price=prices.get(provider.model)
    if provider.name=='openai' and not price: return [await service.analyze(t) for t in tasks]
    system=SYSTEM+' For this batch return {"items":[{"document_id":string,"summary":string,"findings":array,"uncertainty":string}]}. Keep each document independent; include exactly one item per document ID.'
    text=json.dumps([{'document_id':digest(t.text),'text':t.text,'task':t.task} for t in tasks])
    if len(text)>settings.max_input_chars: return [await service.analyze(t) for t in tasks]
    input_bound=len((system+text).encode())+1024; output_bound=settings.max_output_tokens
    reserve=(input_bound*price['input']+output_bound*price['output'])/1e6 if provider.name=='openai' else 0
    ids=[]; fallback=False
    with service.db.transaction() as s:
        if s.scalar(select(LLMRun).where(LLMRun.cache_key.in_(keys)).limit(1)):
            fallback=True
        else:
            usage=stats_from(s.scalars(select(LLMRun)).all())
            if provider.name=='openai' and (usage['daily_cost']+reserve>settings.daily_budget or usage['monthly_cost']+reserve>settings.monthly_budget or usage['calls_last_hour']>=settings.calls_per_hour):
                fallback=True
            else:
                for i,(t,k) in enumerate(zip(tasks,keys)):
                    rid=uid();ids.append(rid)
                    s.add(LLMRun(id=rid,cache_key=k,input_hash=digest(t.text),provider=provider.name,model=provider.model,module=t.task,prompt_version=settings.prompt_version,
                                 reserved_cost=reserve if i==0 else 0,call_count=1 if i==0 else 0))
    if fallback: return [await service.analyze(t) for t in tasks]
    completion=None
    try:
        completion=await provider.complete(system,text,output_bound)
        output=BatchOutput.model_validate_json(completion.content)
        by_id={i.document_id:i for i in output.items}
        if len(output.items)!=len(tasks) or set(by_id)!={digest(t.text) for t in tasks}: raise ValueError('Batch IDs mismatch')
        results=[]
        for rid,t in zip(ids,tasks):
            item=by_id[digest(t.text)]
            if any(f.quote not in t.text for f in item.findings): raise ValueError('Unsupported quote')
            extraction=item.model_dump(exclude={'document_id'})
            payload={'run_id':rid,'batch_call_id':ids[0],'provider':provider.name,'model':completion.model,'configured_model':provider.model,
                     'prompt_version':settings.prompt_version,'input_hash':digest(t.text),'output_hash':digest(json.dumps(extraction,sort_keys=True)),
                     'timestamp':now().isoformat(),'source_reference':t.source_reference,'analysis':extraction}
            results.append(payload)
        with service.db.transaction() as s:
            for i,(rid,payload) in enumerate(zip(ids,results)):
                row=s.get(LLMRun,rid); row.status='complete'; row.payload=payload; row.output_hash=payload['output_hash']
                if i==0: service._settle(row,completion,price,reserve,input_bound,output_bound)
        return [{'status':'COMPLETE',**p} for p in results]
    except Exception:
        with service.db.transaction() as s:
            for i,rid in enumerate(ids):
                row=s.get(LLMRun,rid); row.status='invalid_output' if completion else 'uncertain'
                if i==0 and completion: service._settle(row,completion,price,reserve,input_bound,output_bound)
        return [{'status':'INVALID_OUTPUT' if completion else 'PROVIDER_UNAVAILABLE','run_id':rid} for rid in ids]
