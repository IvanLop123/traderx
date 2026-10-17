"""Historical public-time Form 4 features; collection coverage is never assumed."""
from collections import Counter
import numpy as np
import pandas as pd

COLUMNS=['insider_purchase_count_30d','insider_purchase_dollars_30d','insider_open_market_confirmed_count_30d','insider_distinct_buyers_30d','insider_role_weighted_count_30d','insider_repeat_buyers_60d','insider_days_since_filing']
def historical_features(db,symbol,times):
    result=pd.DataFrame(np.nan,index=range(len(times)),columns=COLUMNS)
    coverage=db.setting('form4_coverage_'+symbol,{})
    if not coverage.get('complete_window') or not coverage.get('start'):return result
    start=pd.Timestamp(coverage['start'])+pd.Timedelta(days=61);end=pd.Timestamp(coverage['end']);filings=[r['payload'] for r in db.records('historical_form4',symbol,limit=20000)]
    events=[];amendments=[];publications=[]
    for f in filings:
        at=pd.Timestamp(f['published_at']);publications.append(at)
        if f['form']=='4/A':amendments.append(at);continue
        for t in f['transactions']:
            if f.get('cik') and str(t.get('issuer_cik','')).lstrip('0')!=str(f['cik']).lstrip('0'):continue
            notes=' '.join(t.get('footnotes',[])).lower()
            if t['code']!='P' or t['derivative'] or t['acquired_disposed']!='A' or not t.get('value') or 'private' in notes or t.get('planned_10b5_1'):continue
            owners=tuple(sorted(o['cik'] or o['name'] for o in t['owners']))
            events.append({'at':at,'value':t['value'],'owners':owners,'weight':max([2 if o['officer'] else 1.5 if o['director'] else 1 for o in t['owners']] or [1]),'confirmed':'open market' in notes or 'open-market' in notes,'filing':f['accession']})
    for i,ts in enumerate(pd.to_datetime(times,utc=True)):
        if not start<=ts<=end:continue
        # Unresolved amendments could change ownership transactions; suppress the entire lookback.
        if any(ts-pd.Timedelta(days=60)<a<=ts for a in amendments):continue
        window=[e for e in events if ts-pd.Timedelta(days=30)<e['at']<=ts];older=[e for e in events if ts-pd.Timedelta(days=60)<e['at']<=ts]
        people={p for e in window for p in e['owners']};buys=Counter(p for p in {p for e in older for p in e['owners']} for filing in {e['filing'] for e in older if p in e['owners']})
        past=[t for t in publications if t<=ts]
        result.iloc[i]=[len(window),sum(e['value'] for e in window),sum(e['confirmed'] for e in window),len(people),sum(e['weight'] for e in window),sum(c>=2 for c in buys.values()),(ts-max(past)).total_seconds()/86400 if past else np.nan]
    return result
