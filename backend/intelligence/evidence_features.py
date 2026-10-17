"""Point-in-time derived evidence with versioned features and explicit expiry."""
import hashlib
import json
import math
from datetime import datetime,timedelta,timezone
from backend.schemas.contracts import AssetIdentifier,Feature,Signal,now
from backend.intelligence.transcripts import transcript_research
from backend.intelligence.documents import institution_changes

VERSION='document-evidence-v4'

def timestamp(value):
    if isinstance(value,datetime):result=value
    else:result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Evidence timestamps require a timezone')
    return result.astimezone(timezone.utc)

def known_documents(db,kind,symbol=None,as_of=None):
    cutoff=as_of or now()
    return [r for r in db.records('document',symbol,limit=5000) if r['payload']['kind']==kind and timestamp(r['available_at'])<=cutoff
            and (not r['payload'].get('published_at') or timestamp(r['payload']['published_at'])<=cutoff)]

def emit_features(db,symbol,metrics,evidence_ids,available_at,*,expires_at=None,prefix='',quality=None):
    if not symbol:return []
    asset=AssetIdentifier(symbol=symbol,asset_class='crypto' if symbol.endswith(('-USD','-USDT')) else 'stock')
    ids=[]
    for key,value in metrics.items():
        if value is not None and (not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value)):continue
        name=prefix+key;identity=json.dumps([VERSION,symbol,name,value,evidence_ids,available_at.isoformat()],sort_keys=True)
        fid=hashlib.sha256(identity.encode()).hexdigest()
        f=Feature(id=fid,asset=asset,name=name,value=value,as_of=available_at,available_at=available_at,expires_at=expires_at,
                  evidence_ids=evidence_ids,model=VERSION,quality=quality or {})
        db.put('feature',f,symbol,available_at=available_at.isoformat())
        if value is None:ids.append(fid);continue
        signal=Signal(id=fid+'s',asset=asset,type=name,value=value,direction='informational',confidence=0,horizon='research',
                      as_of=available_at,evidence_ids=evidence_ids,feature_ids=[fid],model=VERSION,freshness_seconds=0,
                      warnings=['Predictive value is unvalidated; this evidence does not authorize a trade.'])
        db.put('signal',signal,symbol,available_at=available_at.isoformat());ids.append(fid)
    return ids

def insider_snapshot(db,symbol,as_of=None):
    cutoff=as_of or now();docs=known_documents(db,'form4',symbol,cutoff);transactions={};unresolved=False
    for doc in docs:
        from backend.intelligence.documents import parse_form4,ownership_root
        if ownership_root(doc['payload']['text']).findtext('documentType')=='4/A':unresolved=True
        occurrences={}
        for t in parse_form4(doc['payload']['text']):
            if t.get('form')=='4/A':unresolved=True
            try:day=datetime.fromisoformat(t['date']).replace(tzinfo=timezone.utc)
            except (ValueError,KeyError):continue
            if day>cutoff or t.get('derivative'):continue
            owners=sorted(o.get('cik') or o.get('name') for o in t.get('owners',[]) if o.get('cik') or o.get('name'))
            identity=json.dumps([t.get('issuer_cik'),owners or [doc['payload'].get('hash') or doc['id']],t.get('security'),t['date'],t.get('code'),t.get('shares'),t.get('price'),t.get('ownership'),t.get('acquired_disposed')])
            occurrence=occurrences.get(identity,0);occurrences[identity]=occurrence+1
            key=hashlib.sha256((identity+str(occurrence)).encode()).hexdigest()
            if key not in transactions:transactions[key]={**t,'evidence_ids':[],'transaction_at':day.isoformat(),'owner_ids':owners}
            transactions[key]['evidence_ids'].append(doc['id'])
    values=list(transactions.values());windows={};metrics={}
    for days in (3,7,14,30,60):
        recent=[t for t in values if cutoff-timedelta(days=days)<=timestamp(t['transaction_at'])<=cutoff]
        buys=[t for t in recent if t.get('code')=='P'];sales=[t for t in recent if t.get('code')=='S']
        owners={o for t in buys for o in t['owner_ids']}
        buy_value=sum(t['value'] for t in buys if t.get('value') is not None);sell_value=sum(t['value'] for t in sales if t.get('value') is not None)
        windows[str(days)]={'purchase_count':len(buys),'sale_count':len(sales),'known_buyers':len(owners),'known_purchase_value':buy_value,'known_sale_value':sell_value,
                            'missing_transaction_values':sum(t.get('value') is None for t in recent),'cluster':len(owners)>=2}
        if docs and not unresolved:
            metrics.update({f'insider_purchase_count_{days}d':len(buys),f'insider_sale_count_{days}d':len(sales),f'insider_known_buyers_{days}d':len(owners),
                            f'insider_purchase_value_{days}d':buy_value,f'insider_sale_value_{days}d':sell_value})
            metrics.update({f'insider_officer_purchases_{days}d':sum(any(o.get('officer') for o in t.get('owners',[])) for t in buys),
                            f'insider_director_purchases_{days}d':sum(any(o.get('director') for o in t.get('owners',[])) for t in buys),
                            f'insider_repeat_buyers_{days}d':sum(sum(o in t['owner_ids'] for t in buys)>1 for o in owners),
                            f'insider_cluster_{days}d':int(len(owners)>=2)})
        elif unresolved:
            metrics.update({f'insider_{field}_{days}d':None for field in ('purchase_count','sale_count','known_buyers','purchase_value','sale_value')})
    return {'symbol':symbol,'as_of':cutoff.isoformat(),'status':'AMENDMENT_REVIEW_REQUIRED' if unresolved else 'AVAILABLE' if docs else 'NO_FILINGS',
            'windows':windows,'transactions':sorted(values,key=lambda t:t['transaction_at'],reverse=True),'metrics':metrics,'evidence_ids':[d['id'] for d in docs],
            'warnings':['Coverage is limited to collected filings, not a complete insider history.','P/S includes private transactions; personal capital is not proven.',
                        'An observed amendment blocks new numerical insider features until reconciled.' if unresolved else 'Derivative exercises and grants are excluded from purchase clusters.']}

def institution_snapshot(current,previous=None):
    holdings={}
    for row in current['deterministic']:
        key=(row['cusip'],row.get('put_call') or '',row.get('class') or '',row.get('share_type') or 'SH')
        if key not in holdings:holdings[key]={**row,'shares':0,'reported_value':0}
        holdings[key]['shares']+=row['shares'];holdings[key]['reported_value']+=row['reported_value']
    rows=list(holdings.values());total=sum(r['reported_value'] for r in rows)
    weights=[r['reported_value']/total for r in rows] if total else []
    result={'entity_id':current.get('entity_id'),'period_end':current.get('period_end'),'position_count':len(rows),'source_line_count':len(current['deterministic']),'reported_value_total':total,
            'value_unit':current.get('value_unit','unknown'),'concentration_hhi':sum(w*w for w in weights),
            'holdings':[{**r,'portfolio_weight':r['reported_value']/total if total else None} for r in rows],
            'changes':institution_changes(previous['deterministic'],rows) if previous else [],
            'warnings':['13F describes delayed quarter-end holdings, not current trades.','Reported value units must be supplied; cross-fund dollar totals are not inferred.']}
    if current.get('value_unit') in ('dollars','thousands'):result['reported_value_usd']=total*(1000 if current['value_unit']=='thousands' else 1)
    return result

def derive_document(db,document_id):
    record=db.get(document_id)
    if not record or record['kind']!='document':raise ValueError('Document not found')
    p=record['payload'];kind=p['kind'];rid=hashlib.sha256((document_id+VERSION).encode()).hexdigest()
    if db.get(rid):return db.get(rid)['payload']
    at=now()
    if p.get('published_at') and timestamp(p['published_at'])>at:return {'status':'NOT_YET_PUBLISHED'}
    prior=None;prior_id=None
    if p.get('period_end') and (p.get('symbol') or p.get('entity_id')):
        candidates=[d for d in known_documents(db,kind,p.get('symbol') or None,at) if d['id']!=document_id and d['payload'].get('period_end') and d['payload']['period_end']<p['period_end']
                    and (kind!='13f' or (p.get('entity_id') and d['payload'].get('entity_id')==p['entity_id']))
                    and (not p.get('entity_id') or d['payload'].get('entity_id')==p['entity_id'])]
        candidates.sort(key=lambda d:(d['payload']['period_end'],d['available_at']),reverse=True)
        if candidates:prior=candidates[0]['payload'];prior_id=candidates[0]['id']
    evidence=[document_id]+([prior_id] if prior_id else []);metrics={};symbol=p.get('symbol','')
    if kind=='transcript':
        output=transcript_research(p['text'],transcript_research(prior['text']) if prior else None);metrics=output['metrics'];record_kind='transcript_research'
    elif kind=='13f':output=institution_snapshot(p,prior);record_kind='institution_research'
    elif kind=='form4':
        output=insider_snapshot(db,symbol,at) if symbol else {'status':'SYMBOL_REQUIRED','metrics':{}}
        metrics=output['metrics'];evidence=output.get('evidence_ids') or evidence;record_kind='insider_research'
    else:
        output={'method':VERSION,'narrative':p['deterministic']};record_kind='narrative_research'
        metrics={'narrative_hedge_fraction':p['deterministic']['hedge_fraction'],'narrative_bottleneck_mentions':len(p['deterministic']['bottlenecks'])}
    output.update(document_id=document_id,evidence_ids=evidence,previous_document_id=prior_id,available_at=at.isoformat(),method_version=VERSION,symbol=symbol,period_end=p.get('period_end'),entity_id=p.get('entity_id'))
    ttl={'form4':1,'news':3,'filing':120,'transcript':120}.get(kind,7)
    output['feature_ids']=emit_features(db,symbol,metrics,evidence,at,expires_at=at+timedelta(days=ttl),quality={'kind':kind,'coverage':'observed_documents_only','predictive_validation':'unvalidated'})
    db.put(record_kind,output,symbol,record_id=rid,available_at=at.isoformat())
    return output

def refresh_evidence(db):
    """Recover unfinished derivations and refresh rolling windows without any inference."""
    at=now();documents=db.records('document',limit=5000,as_of=at);failures=[];symbols=set()
    for doc in documents:
        try:derive_document(db,doc['id'])
        except Exception:failures.append(doc['id'])
        if doc['payload']['kind']=='form4' and doc['symbol']:symbols.add(doc['symbol'])
    for symbol in symbols:
        try:snapshot=insider_snapshot(db,symbol,at)
        except Exception:
            failures.append('insider:'+symbol)
            continue
        key=hashlib.sha256(json.dumps([VERSION,symbol,at.date().isoformat(),sorted(snapshot['evidence_ids'])]).encode()).hexdigest()
        if db.get(key):continue
        snapshot['feature_ids']=emit_features(db,symbol,snapshot['metrics'],snapshot['evidence_ids'],at,expires_at=at+timedelta(days=1),
                                            quality={'kind':'form4','coverage':'observed_documents_only','predictive_validation':'unvalidated'})
        snapshot['method_version']=VERSION
        db.put('insider_research',snapshot,symbol,record_id=key,available_at=at.isoformat())
    status={'status':'DEGRADED' if failures else 'WORKING','last_cycle':at.isoformat(),'documents_checked':len(documents),'failures':failures}
    db.set_setting('evidence_worker',status)
    return status

def institutional_consensus(db,period_end=None):
    """Compare only identified managers reporting the same quarter; never guess tickers."""
    docs=known_documents(db,'13f')
    eligible=[d for d in docs if d['payload'].get('entity_id') and d['payload'].get('period_end')]
    periods=sorted({d['payload']['period_end'] for d in eligible},reverse=True)
    period=period_end or (periods[0] if periods else None)
    managers={}
    for doc in sorted(eligible,key=lambda d:d['available_at']):
        if doc['payload']['period_end']==period:managers[doc['payload']['entity_id']]=doc
    consensus={};evidence=[];comparison_count=0
    def key(row):return (row['cusip'],row.get('class') or '',row.get('put_call') or '',row.get('share_type') or 'SH')
    for manager,doc in managers.items():
        p=doc['payload'];earlier=[d for d in eligible if d['payload']['entity_id']==manager and d['payload']['period_end']<period]
        earlier.sort(key=lambda d:(d['payload']['period_end'],d['available_at']),reverse=True)
        previous=earlier[0]['payload'] if earlier else None
        snapshot=institution_snapshot(p,previous);evidence.append(doc['id'])
        if earlier:evidence.append(earlier[0]['id']);comparison_count+=1
        changes={key(c):c['shares_change'] for c in snapshot['changes']}
        for holding in snapshot['holdings']:
            k=key(holding)
            if k not in consensus:consensus[k]={'cusip':k[0],'class':k[1],'put_call':k[2],'share_type':k[3],'issuer':holding['issuer'],'holders':[]}
            consensus[k]['holders'].append({'entity_id':manager,'portfolio_weight':holding['portfolio_weight'],'shares':holding['shares'],
                                            'shares_change':changes.get(k),'document_id':doc['id']})
    rows=[]
    for row in consensus.values():
        holders=row['holders'];weights=[h['portfolio_weight'] for h in holders if h['portfolio_weight'] is not None]
        row.update(manager_count=len(holders),observed_manager_fraction=len(holders)/len(managers),
                   mean_reported_portfolio_weight=sum(weights)/len(weights) if weights else None,
                   managers_adding=sum(h['shares_change'] is not None and h['shares_change']>0 for h in holders),
                   managers_reducing=sum(h['shares_change'] is not None and h['shares_change']<0 for h in holders))
        rows.append(row)
    rows.sort(key=lambda r:(-r['manager_count'],r['cusip'],r['put_call']))
    return {'status':'AVAILABLE' if managers else 'NO_COMPARABLE_FILINGS','period_end':period,'available_periods':periods,
            'manager_count':len(managers),'managers_with_prior_period':comparison_count,'excluded_unidentified_documents':len(docs)-len(eligible),
            'holdings':rows,'evidence_ids':sorted(set(evidence)),'as_of':now().isoformat(),'method_version':VERSION,
            'warnings':['Consensus describes collected managers in one reporting period; it is not market-wide ownership or free-float crowding.',
                        'No CUSIP-to-ticker mapping is guessed. Positions with different classes, option sides or share units remain separate.',
                        'Add/reduce counts cover current holders with an available prior filing; fully exited positions are shown in individual filing changes.',
                        'The latest imported snapshot for a manager and period is used. Verify that amendments are complete restatements before importing.']}
