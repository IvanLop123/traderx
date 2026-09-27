"""Deduplicated source documents feed deterministic parsing and optional text jobs."""
import hashlib
import calendar
import json
from datetime import datetime,date,timezone
from backend.schemas.contracts import now,Event,RawRecord,AssetIdentifier
from backend.storage.database import Job
from backend.llm.providers import TextTask
from backend.intelligence.documents import narrative_features, parse_form4, parse_13f, theme_graph

def store_document(db,*,text,kind,title,source_reference,symbol='',published_at=None,period_end=None,entity_id='',value_unit='unknown',provider='manual'):
    if kind not in ('form4','13f','transcript','filing','news','theme','summary'):raise ValueError('Unsupported document kind')
    if value_unit not in ('unknown','dollars','thousands'):raise ValueError('Unsupported reported-value unit')
    deterministic=parse_form4(text) if kind=='form4' else parse_13f(text) if kind=='13f' else narrative_features(text)
    received=now()
    if kind=='form4' and not symbol and deterministic:symbol=deterministic[0].get('issuer_symbol','')
    if published_at and not isinstance(published_at,datetime):published_at=datetime.fromisoformat(published_at.replace('Z','+00:00'))
    if published_at and published_at.tzinfo is None:raise ValueError('Publication time requires a timezone')
    available=max(received,published_at or received)
    if period_end:period_end=date.fromisoformat(str(period_end)).isoformat()
    asset=AssetIdentifier(symbol=symbol,asset_class='crypto' if symbol.endswith(('-USD','-USDT')) else 'stock') if symbol else None
    identity=[text,kind,source_reference,symbol,period_end,entity_id,value_unit,published_at.isoformat() if published_at else None]
    rid=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()
    existing=db.get(rid)
    if existing:
        from backend.intelligence.evidence_features import derive_document
        return {'id':rid,'status':'ALREADY_STORED','deterministic':existing['payload']['deterministic'],'research':derive_document(db,rid)}
    payload={'text':text,'kind':kind,'title':title,'source_reference':source_reference,'symbol':symbol,
             'published_at':published_at.isoformat() if published_at else None,'period_end':period_end,'entity_id':entity_id,'value_unit':value_unit,'provider':provider,
             'hash':hashlib.sha256(text.encode()).hexdigest(),'received_at':received.isoformat(),'deterministic':deterministic}
    db.put('raw',RawRecord(id=rid+'raw',provider=provider,source_reference=source_reference,payload={'text':text}),symbol,record_id=rid+'raw',available_at=available.isoformat())
    event=Event(id=rid+'event',source=source_reference,provider=provider,event_type=kind,assets=[asset] if asset else [],event_at=published_at or received,published_at=published_at or received,
                first_observed_at=received,ingested_at=received,processed_at=received,payload={'document_id':rid,'period_end':period_end},source_reference=source_reference,quality={'publication_time_known':published_at is not None})
    db.put('event',event,symbol,record_id=event.id,available_at=available.isoformat())
    db.put('document',payload,symbol,record_id=rid,available_at=available.isoformat())
    graph=theme_graph(text,rid,symbol or title)
    if graph['edges']:db.put('theme',graph,symbol,record_id=rid+'theme',available_at=available.isoformat())
    if kind not in ('form4','13f'):
        task=TextTask(task=kind,text=text,source_reference=source_reference)
        with db.transaction() as s:
            if not s.get(Job,rid):s.add(Job(id=rid,kind='text',payload=task.model_dump(),due_at=available.isoformat()))
    from backend.intelligence.evidence_features import derive_document
    research=derive_document(db,rid)
    return {'id':rid,'status':'STORED','ai_status':'QUEUED_OR_DISABLED','deterministic':deterministic,'research':research}

def ingest_alpha_text(db,kind,data,symbol):
    if kind=='news':
        for article in data.get('feed',[]):
            text=(article.get('title','')+'\n'+article.get('summary','')).strip()
            published=article.get('time_published');published=datetime.strptime(published,'%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc) if published else None
            symbols=[x.get('ticker') for x in article.get('ticker_sentiment',[]) if x.get('ticker') in symbol.split(',')]
            primary=symbols[0] if symbols else symbol if ',' not in symbol else ''
            if text:store_document(db,text=text,kind='news',title=article.get('title','News'),source_reference=article.get('url') or 'alpha_vantage:news',symbol=primary,published_at=published,provider='alpha_vantage')
    elif kind=='transcript':
        entries=data.get('transcript',[])
        text='\n'.join((str(x.get('speaker') or '')+' ('+str(x.get('title') or '')+'): '+str(x.get('content') or '')) for x in entries) if isinstance(entries,list) else str(entries)
        quarter=str(data.get('quarter',''));period=None
        if len(quarter)==6 and quarter[:4].isdigit() and quarter[4]=='Q' and quarter[5] in '1234':
            year=int(quarter[:4]);month=int(quarter[5])*3;period=date(year,month,calendar.monthrange(year,month)[1])
        if text:store_document(db,text=text,kind='transcript',title=f'{symbol} earnings transcript',source_reference='alpha_vantage:transcript:'+symbol+':'+quarter,symbol=symbol,period_end=period,provider='alpha_vantage')
