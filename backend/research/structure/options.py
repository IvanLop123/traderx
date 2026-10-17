"""Deterministic chain surfaces and comparable-tenor forward IV history."""
import math
from statistics import median
import numpy as np
from backend.intelligence.options import option_chain_research
from backend.intelligence.quant import black_scholes,implied_vol,parity

def surface(chain,symbol,history=(),underlying=None):
    r=option_chain_research(chain,symbol);day=r['observation_date'];terms=r['expirations'];spot=(underlying or {}).get('spot');rv=(underlying or {}).get('realized_volatility');rate=(underlying or {}).get('rate');dividend=(underlying or {}).get('dividend',0)
    # History uses one observation per date, same 20–40 DTE band; do not rank across all maturities.
    def reference(terms):
        ts=[t for t in terms if 20<=t['days_to_expiry']<=40 and t['near_50_delta_iv'] is not None]
        return min(ts,key=lambda t:abs(t['days_to_expiry']-30)) if ts else None
    ref=reference(terms);past={h['observation_date']:reference(h.get('expirations',[])) for h in history if h['observation_date']<day};past={d:v for d,v in past.items() if v};values=[v['near_50_delta_iv'] for d,v in sorted(past.items())[-252:]];iv=ref['near_50_delta_iv'] if ref else None
    latest=past[max(past)] if past else None;expected=lambda t:t['near_50_delta_iv']*math.sqrt(t['days_to_expiry']/365) if t and t['near_50_delta_iv'] and t['days_to_expiry']>0 else None
    r.update(surface=[{'strike':c['strike'],'expiration':c['expiration'],'type':c['type'],'iv':c['implied_volatility'],'quote_status':c['quote_status']} for c in r['contracts']],iv_history_days=len(values),iv_percentile=sum(x<=iv for x in values)/len(values) if iv is not None and len(values)>=60 else None,iv_rank=(iv-min(values))/(max(values)-min(values)) if iv is not None and len(values)>=60 and max(values)>min(values) else None,iv_rank_scope='Comparable 20–40 DTE near-50-delta proxy; 60 prior dates minimum, 252 maximum; not interpolated constant maturity',realized_minus_implied=rv-iv if rv is not None and iv is not None else None,skew_change=ref['put_minus_call_25_delta_iv']-latest['put_minus_call_25_delta_iv'] if ref and latest and ref['put_minus_call_25_delta_iv'] is not None and latest['put_minus_call_25_delta_iv'] is not None else None,expected_move_change=expected(ref)-expected(latest) if expected(ref) is not None and expected(latest) is not None else None,history_status='HISTORY_SUPPORTED' if len(values)>=60 else 'FORWARD_COLLECTED_ONLY / INSUFFICIENT COMPARABLE HISTORY',local_greeks=[],parity=[])
    for t in terms:t['expected_move_fraction']=expected(t);t['expected_move_dollars']=expected(t)*spot if spot and expected(t) else None
    # Local European approximation requires an explicitly dated, synchronized underlying.
    if underlying and underlying.get('observation_date')==day and spot and rate is not None:
        for c in r['contracts']:
            years=c['days_to_expiry']/365;vol=c['implied_volatility']
            if years<=0 or c['quote_status']!='TWO_SIDED':continue
            try:
                if not vol and dividend==0:vol=implied_vol(c['midpoint'],spot,c['strike'],years,rate,c['type'])
                if vol:r['local_greeks'].append({'contract_id':c['contract_id'],'iv':vol,**black_scholes(spot,c['strike'],years,rate,vol,c['type'],dividend)})
            except ValueError:continue
        if underlying.get('synchronized_quotes') and all(k in underlying for k in ('bid','ask','costs_per_share')):
            pairs={}
            for c in r['contracts']:pairs.setdefault((c['expiration'],c['strike']),{})[c['type']]=c
            for (expiry,strike),sides in pairs.items():
                if set(sides)!={'call','put'} or any(c['quote_status']!='TWO_SIDED' for c in sides.values()):continue
                c,p=sides['call'],sides['put'];years=c['days_to_expiry']/365
                if years<=0:continue
                r['parity'].append({'expiration':expiry,'strike':strike,**parity(underlying['bid'],underlying['ask'],c['bid'],c['ask'],p['bid'],p['ask'],strike,years,rate,underlying['costs_per_share'],dividend,american=underlying.get('exercise_style','american')=='american')})
    r['math_scope']='Deterministic; local Greeks are European approximations. American exercise/dividends/borrow can invalidate parity. No option orders.'
    return r
