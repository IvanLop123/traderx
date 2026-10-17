"""Delayed next-open diagnostic exit comparison. Not an execution backtest.

The source has daily reference bars, not executable historical depth/spreads.
Every entry/exit charges the source's conservative round-trip cost and waits
until a later session open; it never assumes the observed close could fill.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from backend.research.advanced.models import block_test,by_adjust

RULES=['reversal','edge_loss','deterioration','fixed_horizon','volatility_stop','risk_limit','trailing','profit_taking']

def compare(full,train,cal_start,start,end,features,scaler):
    models=[]
    for ix in ([0,1],[2],[3,6]):
        m=Ridge(alpha=100).fit(scaler.transform(train[features])[:,ix],train.net_return);models.append((m,ix))
    histories=[]
    for symbol,g in full.groupby('symbol'):
        g=g.sort_values('date');g=g[(g.date>=pd.Timestamp(start,tz='UTC'))&(g.date<pd.Timestamp(end,tz='UTC'))].copy()
        if len(g)<50:continue
        valid=g[features].notna().all(axis=1)&g.eligible;mat=scaler.transform(g[features].fillna(train[features].median()));pred=np.column_stack([m.predict(mat[:,ix]) for m,ix in models]);g['edge']=pred.mean(axis=1);g['support']=(pred>0).sum(axis=1);g['unc']=float(train.net_return.std());g['usable']=valid
        histories.append(g)
    result={}
    for rule in RULES:
        trades=[];candidates=0
        for g in histories:
            g=g.reset_index(drop=True);i=0
            while i<len(g)-25:
                r=g.iloc[i]
                if not r.usable or r.support<2 or r.edge<=max(0,r.unc*.25):i+=1;continue
                candidates+=1
                # Panel labels deliberately use open[t+2]. Preserve that availability lag.
                enter=i+2;entry=float(g.iloc[enter].get('close',np.nan));open_price=g.iloc[enter].get('execution_open')
                if open_price is None or not np.isfinite(open_price) or open_price<=0:i+=1;continue
                entry=float(open_price);high=entry;chosen=min(enter+5,len(g)-2);reason='maximum_20_sessions'
                for j in range(enter,min(enter+20,len(g)-2)):
                    x=g.iloc[j];price=float(x.close);high=max(high,price);gain=price/entry-1
                    checks={'reversal':x.support==0,'edge_loss':x.edge<=0,'deterioration':not x.usable or x.support<2 or x.edge<x.unc*.25,'fixed_horizon':j-enter>=5,'volatility_stop':gain<=-2*max(x.realized_volatility,0),'risk_limit':gain<=-.05,'trailing':price/high-1<=-.05,'profit_taking':gain>=.1}
                    chosen=j+2
                    if checks[rule] or gain<=-.05:reason=rule if checks[rule] else 'protective_stop';break
                exit_price=g.iloc[chosen].execution_open
                if pd.notna(exit_price) and exit_price>0:trades.append({'date':str(r.date),'net_return':float(exit_price/entry-1-r.cost),'sessions':chosen-enter,'reason':reason,'cost':float(r.cost)})
                i=chosen+1
        clustered=pd.DataFrame(trades).groupby('date').net_return.mean().to_numpy() if trades else np.array([])
        result[rule]={'trades':len(trades),'eligible_entry_signals':candidates,'return':block_test(clustered),'mean_holding_sessions':float(np.mean([t['sessions'] for t in trades])) if trades else None,'mean_cost':float(np.mean([t['cost'] for t in trades])) if trades else None,'zero_trade_reason':None if trades else 'No sufficiently strong multi-family entry on these chronological forecasts','scope':'Delayed session-open research marks with conservative costs; absent depth/borrow means not an executable fill claim'}
    for r,q in zip(result.values(),by_adjust([v['return']['p'] for v in result.values()],111)):r['BY_q']=q
    return result
