"""Join optional evidence only after it was actually observed and processed."""
import pandas as pd
import numpy as np

def join_features_asof(bar_times,records):
    times=pd.DataFrame({'time':pd.to_datetime(bar_times,utc=True),'row':range(len(bar_times))}).sort_values('time')
    by_name={}
    for record in records:
        p=record['payload']; value=p.get('value')
        if value is not None and (not isinstance(value,(int,float)) or isinstance(value,bool) or not np.isfinite(value)):continue
        if value is None:value=np.nan
        available=max(pd.Timestamp(record['available_at']),pd.Timestamp(p['available_at']))
        by_name.setdefault(p['name'],[]).append({'time':available,'value':value,'expires_at':pd.Timestamp(p['expires_at']) if p.get('expires_at') else pd.NaT})
    result=pd.DataFrame(index=range(len(bar_times)))
    for name,rows in by_name.items():
        right=pd.DataFrame(rows).sort_values('time').drop_duplicates('time',keep='last')
        merged=pd.merge_asof(times,right,on='time',direction='backward').sort_values('row')
        expired=merged.expires_at.notna()&(merged.time>=pd.to_datetime(merged.expires_at,utc=True))
        merged.loc[expired,'value']=np.nan
        result[name]=merged.value.to_numpy()
    return result
