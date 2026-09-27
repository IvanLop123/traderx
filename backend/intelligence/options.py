"""Descriptive historical option-chain research. Never infers trade aggressors."""
import hashlib
import math
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from statistics import median
from backend.schemas.contracts import now

VERSION='option-chain-v1'

def numeric(row,key,*,required=False,signed=False):
    value=row.get(key)
    if value in (None,'','None','null','NA','N/A'):
        if required:raise ValueError('Missing '+key)
        return None
    value=float(value)
    if not math.isfinite(value) or (not signed and value<0):raise ValueError('Invalid '+key)
    return value

def option_chain_research(data,symbol):
    rows=data.get('data')
    if not isinstance(rows,list) or not rows:raise ValueError('No historical option contracts returned')
    contracts={};invalid=[]
    for index,row in enumerate(rows):
        try:
            if row.get('symbol')!=symbol:raise ValueError('Mismatched underlying symbol')
            day=date.fromisoformat(row['date']);expiration=date.fromisoformat(row['expiration'])
            if expiration<day:raise ValueError('Contract expired before observation')
            kind=row['type'].lower()
            if kind not in ('call','put'):raise ValueError('Unknown option type')
            strike=numeric(row,'strike',required=True)
            if not strike:raise ValueError('Strike must be positive')
            bid=numeric(row,'bid');ask=numeric(row,'ask');volume=numeric(row,'volume');oi=numeric(row,'open_interest')
            delta=numeric(row,'delta',signed=True);iv=numeric(row,'implied_volatility')
            if delta is not None and (abs(delta)>1 or (kind=='call' and delta<0) or (kind=='put' and delta>0)):raise ValueError('Invalid delta')
            if volume is not None and not volume.is_integer():raise ValueError('Fractional contract volume')
            if oi is not None and not oi.is_integer():raise ValueError('Fractional open interest')
            crossed=bid is not None and ask is not None and bid>ask
            quoted=bid is not None and ask is not None and 0<bid<=ask
            mid=(bid+ask)/2 if quoted else None
            identifier=str(row.get('contractID') or f'{symbol}:{expiration}:{kind}:{strike}')
            item={'contract_id':identifier,'symbol':symbol,'date':day.isoformat(),'expiration':expiration.isoformat(),'days_to_expiry':(expiration-day).days,
                  'type':kind,'strike':strike,'bid':bid,'ask':ask,'midpoint':mid,'spread_fraction':(ask-bid)/mid if quoted else None,
                  'quote_status':'TWO_SIDED' if quoted else 'CROSSED' if crossed else 'MISSING_OR_ZERO_BID',
                  'volume':volume,'open_interest':oi,'volume_to_oi':volume/oi if volume is not None and oi else None,
                  'implied_volatility':iv,'delta':delta,'gamma':numeric(row,'gamma'),'theta':numeric(row,'theta',signed=True),
                  'vega':numeric(row,'vega'),'rho':numeric(row,'rho',signed=True)}
            key=(day,expiration,kind,strike,identifier)
            if key in contracts and contracts[key]!=item:raise ValueError('Conflicting duplicate contract')
            contracts[key]=item
        except (ValueError,KeyError,TypeError,AttributeError) as e:invalid.append({'row':index,'reason':str(e)[:120]})
    rows=list(contracts.values())
    if not rows:raise ValueError('No valid option contracts to analyze')
    dates={r['date'] for r in rows}
    if len(dates)!=1:raise ValueError('Analyze one option-chain observation date at a time')
    day=next(iter(dates))
    if date.fromisoformat(day)>now().date():raise ValueError('Option observation is in the future')
    def totals(group):
        totals={}
        for kind in ('call','put'):
            side=[r for r in group if r['type']==kind]
            for field in ('volume','open_interest'):
                totals[kind+'_'+field]=sum(r[field] for r in side) if side and all(r[field] is not None for r in side) else None
        for field in ('volume','open_interest'):
            c=totals['call_'+field];p=totals['put_'+field]
            totals['put_call_'+field+'_ratio']=p/c if p is not None and c else None
        return totals
    buckets=defaultdict(list)
    for row in rows:buckets[row['expiration']].append(row)
    expirations=[]
    for expiration,group in sorted(buckets.items()):
        def closest(kind,target):
            candidates=[r for r in group if r['type']==kind and r['delta'] is not None and r['implied_volatility'] is not None and r['implied_volatility']>0 and r['quote_status']=='TWO_SIDED']
            candidate=min(candidates,key=lambda r:abs(abs(r['delta'])-target)) if candidates else None
            return candidate if candidate and abs(abs(candidate['delta'])-target)<=.10 else None
        call=closest('call',.25);put=closest('put',.25)
        near=[r for r in (closest('call',.5),closest('put',.5)) if r]
        spreads=[r['spread_fraction'] for r in group if r['spread_fraction'] is not None]
        expirations.append({'expiration':expiration,'days_to_expiry':group[0]['days_to_expiry'],'contracts':len(group),**totals(group),
                            'median_spread_fraction':median(spreads) if spreads else None,
                            'near_50_delta_iv':sum(r['implied_volatility'] for r in near)/len(near) if near else None,
                            'put_minus_call_25_delta_iv':put['implied_volatility']-call['implied_volatility'] if call and put else None,
                            'skew_contract_ids':[r['contract_id'] for r in (put,call) if r],
                            'term_contract_ids':[r['contract_id'] for r in near]})
    unusual=sorted([r for r in rows if r['volume_to_oi'] is not None and r['volume']>0],key=lambda r:r['volume_to_oi'],reverse=True)[:20]
    return {'method_version':VERSION,'symbol':symbol,'observation_date':day,'contract_count':len(rows),'rejected_rows':invalid,
            'status':'PARTIAL_DATA' if invalid else 'AVAILABLE','totals':totals(rows),'expirations':expirations,'activity_rankings':unusual,
            'quote_coverage':{'two_sided':sum(r['quote_status']=='TWO_SIDED' for r in rows),'crossed':sum(r['quote_status']=='CROSSED' for r in rows)},
            'contracts':sorted(rows,key=lambda r:(r['expiration'],r['strike'],r['type'])),
            'warnings':['Historical chain snapshots are not live executable quotes.',
                        'Volume/open interest does not establish new positions, buyer direction, unusual intent, or opening trades.',
                        'IV and Greeks are provider estimates. Skew uses nearest absolute delta within 0.10; missing comparisons remain unavailable.',
                        'No dollar notional or arbitrage claim: contract deliverables, synchronized underlying, fees, dividends and exercise terms are not established.']}

def derive_options(db,record_id):
    record=db.get(record_id)
    if not record or record['kind']!='options':raise ValueError('Stored options chain not found')
    rid=hashlib.sha256((VERSION+record_id).encode()).hexdigest()
    if db.get(rid):return db.get(rid)['payload']
    p=record['payload']
    # Provider records retain symbol in the chain rows, not necessarily the envelope.
    symbol=p.get('symbol') or (p.get('data') or [{}])[0].get('symbol')
    if not symbol:raise ValueError('Underlying symbol is missing')
    result=option_chain_research(p,symbol);at=now()
    result.update(available_at=at.isoformat(),evidence_ids=[record_id],feature_ids=[])
    expires=datetime.combine(date.fromisoformat(result['observation_date'])+timedelta(days=2),datetime.min.time(),tzinfo=timezone.utc)
    if expires>at and result['status']=='AVAILABLE':
        from backend.intelligence.evidence_features import emit_features
        metrics={'options_'+k:v for k,v in result['totals'].items()}
        result['feature_ids']=emit_features(db,symbol,metrics,[record_id],at,expires_at=expires,
                                           quality={'kind':'options','observation_date':result['observation_date'],'predictive_validation':'unvalidated'})
    db.put('options_research',result,symbol,record_id=rid,available_at=at.isoformat())
    return result
