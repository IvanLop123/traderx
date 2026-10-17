"""Immutable, content-addressed historical series. Adjustment/feed never mixed."""
import hashlib,json,os
from pathlib import Path
import pandas as pd
from backend.schemas.contracts import Bar,now
from backend.research.universe import ROOT

class HistoryStore:
    def __init__(self,db,root=None):self.db=db;self.root=Path(root or ROOT/'data/history')
    def save(self,symbol,provider,rows,*,adjustment='raw',feed='',metadata=None):
        if adjustment not in ('raw','all','split'):raise ValueError('Unknown adjustment semantics')
        clean={}
        for row in rows:
            b=Bar.model_validate({k:v for k,v in row.items() if k in Bar.model_fields}).model_dump(mode='json')
            if b['symbol']!=symbol or b['provider']!=provider:raise ValueError('Mixed series identity')
            if pd.Timestamp(b['available_at'])>pd.Timestamp.now(tz='UTC'):continue
            if pd.Timestamp(b['available_at'])<pd.Timestamp(b['timestamp'])+pd.Timedelta(days=1):raise ValueError('Incomplete daily interval')
            if b['timestamp'] in clean and {k:v for k,v in clean[b['timestamp']].items() if k!='observed_at'}!={k:v for k,v in b.items() if k!='observed_at'}:raise ValueError('Conflicting duplicate bar')
            clean[b['timestamp']]=b
        values=[clean[k] for k in sorted(clean)]
        if not values:raise ValueError('No valid completed bars returned')
        identity={'symbol':symbol,'provider':provider,'adjustment':adjustment,'feed':feed,'bars':[{k:v for k,v in b.items() if k!='observed_at'} for b in values]}
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest();rid='history_'+digest
        self.root.mkdir(parents=True,exist_ok=True);path=self.root/(digest+'.parquet')
        if not path.exists():
            tmp=self.root/(digest+'.tmp');pd.DataFrame(values).to_parquet(tmp,index=False);os.replace(tmp,path)
        manifest={'id':rid,'hash':digest,'file_hash':hashlib.sha256(path.read_bytes()).hexdigest(),'symbol':symbol,'provider':provider,'adjustment':adjustment,'feed':feed,'count':len(values),'start':values[0]['timestamp'],'end':values[-1]['timestamp'],'observed_at':now().isoformat(),'semantics':'Retrospective provider vintage; adjusted values are not executable prices','metadata':metadata or {}}
        self.db.put('history_series',manifest,symbol,record_id=rid)
        # Explicit pointer is essential: a repeat fetch may resolve to an older immutable record.
        self.db.set_setting('history_'+symbol+'_'+adjustment,{'id':rid})
        return manifest
    def manifest(self,symbol,adjustment=None):
        adjustment=adjustment or ('raw' if symbol.endswith('-USD') else 'all')
        pointer=self.db.setting('history_'+symbol+'_'+adjustment)
        return self.db.get(pointer['id'])['payload'] if pointer else None
    def read(self,symbol,adjustment=None):
        m=self.manifest(symbol,adjustment)
        if not m:return []
        path=self.root/(m['hash']+'.parquet')
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=m['file_hash']:raise ValueError('Historical series missing or checksum changed')
        return [{**r,'adjustment':m['adjustment'],'feed':m['feed']} for r in pd.read_parquet(path).to_dict('records')]

def research_bars(db,symbol):
    archived=HistoryStore(db).read(symbol)
    # Never append raw live bars to an adjusted archive. Refresh the same vintage as a unit.
    return archived or [r['payload'] for r in db.records('bar',symbol,limit=20000)]

def total_return(previous_close,current_close,*,split_ratio=1.,cash_dividend=0.):
    """Dividend per post-split share. One old share becomes split_ratio shares."""
    if min(previous_close,current_close,split_ratio)<=0 or cash_dividend<0:raise ValueError('Invalid corporate action')
    return split_ratio*(current_close+cash_dividend)/previous_close-1
