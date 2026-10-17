"""Fixed block inference; no IID asset-row inflation or continuous p-value peeking."""
import numpy as np
import pandas as pd

def interval(values,alpha=.05,block=5,draws=4999):
    x=np.asarray(values,dtype=float);x=x[np.isfinite(x)];n=len(x)
    result={'n':n,'effective_blocks':n//block,'mean':float(x.mean()) if n else None,'lower':None,'upper':None,'method':f'circular {block}-observation block bootstrap; {draws} fixed-seed draws','weak_conclusion':n<60}
    if n>=max(10,block*2):
        rng=np.random.default_rng(7201);starts=rng.integers(0,n,(draws,int(np.ceil(n/block))));idx=((starts[:,:,None]+np.arange(block))%n).reshape(draws,-1)[:,:n];means=x[idx].mean(axis=1);result.update(lower=float(np.quantile(means,alpha/2)),upper=float(np.quantile(means,1-alpha/2)))
    return result

def nonoverlapping(rows):
    """One equal-weight cross-asset cluster per entry date; overlapping label spans purged."""
    groups={}
    for r in rows:groups.setdefault(str(r['decided_at'])[:10],[]).append(r)
    result=[];last_end=None
    for date,items in sorted(groups.items()):
        start=min(pd.Timestamp(r['decided_at']) for r in items);end=max(pd.Timestamp(r['completed_at']) for r in items)
        if last_end is not None and start<=last_end:continue
        result.append({'date':date,'started_at':start.isoformat(),'completed_at':end.isoformat(),'net_return':float(np.mean([r['net_return'] for r in items])),'rows':items});last_end=end
    return result
