"""Bounded lexical retrieval before optional, cached cross-document text analysis."""
import hashlib
import re
from datetime import datetime,timedelta
from backend.schemas.contracts import now

STOP=set('the a an of and or to in is are was were for with on at by as it its we our this that from be has have will can not'.split())
def terms(text):return set(re.findall(r'\b[a-z][a-z0-9]{2,}\b',text.lower()))-STOP

def neighbors(db,rid):
    current=db.get(rid)
    if not current or current['kind']!='document':raise ValueError('Stored document required')
    p=current['payload'];published=p.get('published_at')
    if p['kind'] in ('form4','13f') or not p.get('symbol'):return []
    # Unknown publication dates cannot establish historical claim order.
    if not published or datetime.fromisoformat(published)>now():return []
    tokens=terms(p['text']);found=[]
    for row in db.records('document',p['symbol'],limit=500):
        q=row['payload'];prior=q.get('published_at')
        if row['id']==rid or q['hash']==p['hash'] or q['kind'] in ('form4','13f') or not prior:continue
        if not datetime.fromisoformat(prior)<datetime.fromisoformat(published):continue
        if q.get('entity_id') and p.get('entity_id') and q['entity_id']!=p['entity_id']:continue
        shared=tokens&terms(q['text']);union=tokens|terms(q['text']);score=len(shared)/max(1,len(union))
        if len(shared)<4 or score<.08:continue
        found.append({'id':row['id'],'title':q['title'],'published_at':prior,'similarity':score})
    return sorted(found,key=lambda r:(r['similarity'],r['published_at']),reverse=True)[:2]

async def compare(db,llm,rid,prior_id,automated=False):
    from backend.llm.providers import TextTask
    eligible=neighbors(db,rid)
    if prior_id not in {r['id'] for r in eligible}:return {'status':'FILTERED_NO_COMPARABLE_SOURCE'}
    current=db.get(rid)['payload'];prior=db.get(prior_id)['payload']
    text='PRIOR DOCUMENT\n'+prior['text']+'\nEND PRIOR DOCUMENT\nCURRENT DOCUMENT\n'+current['text']+'\nEND CURRENT DOCUMENT'
    result=await llm.analyze(TextTask(task='contradiction',text=text,source_reference='document-pair:'+prior_id+':'+rid,automated=automated,difficult=True))
    if result['status'] not in ('COMPLETE','CACHED'):return result
    items=(result['analysis'].get('research') or {}).get('comparisons',[])
    for item in items:
        q=item.get('prior_quote')
        if item['current_quote'] not in current['text'] or (q is not None and q not in prior['text']) or (item['relation']!='new_claim' and not q):
            return {'status':'INVALID_SOURCE_ATTRIBUTION','run_id':result['run_id']}
    key=hashlib.sha256(('comparison-v1:'+prior_id+rid+result['run_id']).encode()).hexdigest()
    available=max(datetime.fromisoformat(result['timestamp']),datetime.fromisoformat(current['received_at']),datetime.fromisoformat(prior['received_at']))
    payload={'prior_document_id':prior_id,'current_document_id':rid,'prior_title':prior['title'],'current_title':current['title'],
             'prior_source':prior['source_reference'],'current_source':current['source_reference'],'comparisons':items,
             'provider':result['provider'],'model':result['model'],'prompt_version':result['prompt_version'],'run_id':result['run_id'],
             'available_at':available.isoformat(),'scope':'Novelty is relative to this retrieved prior document only; semantic judgments are uncalibrated.'}
    db.put('document_comparison',payload,current['symbol'],record_id=key,available_at=available.isoformat())
    return {'status':result['status'],'id':key,**payload}

async def cycle(db,llm):
    """At most two pairs per cycle. Disabled analysis performs no retrieval or calls."""
    if llm.settings().provider=='off' or not llm.settings().automated:return
    attempted=0
    for row in db.records('document',limit=50):
        for prior in neighbors(db,row['id']):
            key='comparison_'+hashlib.sha256((prior['id']+row['id']).encode()).hexdigest()[:40]
            previous=db.setting(key,{})
            # Re-check cached results on the next day, allowing intentional model/prompt changes.
            if previous.get('due_at','')>now().isoformat():continue
            result=await compare(db,llm,row['id'],prior['id'],True);attempted+=1
            db.set_setting(key,{'status':result['status'],'due_at':(now()+timedelta(hours=24 if result['status'] in ('COMPLETE','CACHED') else 1)).isoformat()})
            if attempted>=2:return
