from backend.intelligence.news import live_governance
"""Portfolio targets bound new experimental orders; existing risk remains authoritative."""
import numpy as np
import pandas as pd
from backend.schemas.contracts import now
from backend.research.features import stable_hash,market_frame
from backend.research.history import HistoryStore
from backend.research.alpha.math import optimize,shrink_covariance,LIMITS
from backend.research.alpha.registry import context
from backend.ensemble.engine import candidate

class Allocation:
    def __init__(self,db):self.db=db;self.cache={}
    def plan(self,snapshot,view,at=None):
        at=at or now();g=live_governance(self.db);assets=snapshot.get('assets',{});selected=[];held={p['symbol']:p['market_value']/max(view['equity'],1) for p in view['positions']}
        pending={}
        for o in view['orders']:
            if o['side']=='buy' and o['status'] in ('OPEN','PARTIALLY_FILLED'):pending[o['symbol']]=pending.get(o['symbol'],0)+(o['quantity']-o['filled_quantity'])*o['reserve_price']/max(view['equity'],1)
        for row in snapshot.get('rows',[]):
            r=candidate(context(row,g),assets.get(row['symbol'],{}),at=at)
            if r['ensemble']['action'] in ('BUY','HOLD') or row['symbol'] in held or row['symbol'] in pending:selected.append(r)
        selected=sorted(selected,key=lambda r:(r['symbol'] not in held and r['symbol'] not in pending,-(r.get('expected_edge') or -1)))[:20]
        if not selected:return {'status':'CASH','weights':{},'notionals':{},'reason':'No diversified positive-edge forecast','at':at.isoformat()}
        symbols=[r['symbol'] for r in selected];store=HistoryStore(self.db);series={};sources={}
        for symbol in symbols:
            m=store.manifest(symbol)
            if not m:return {'status':'NO ALLOCATION','notionals':{},'reason':'Missing covariance archive','at':at.isoformat()}
            sources[symbol]=m['id']
            if m['id'] not in self.cache:
                frame,_,_=market_frame(store.read(symbol));self.cache[m['id']]=pd.Series(frame.close.pct_change().to_numpy(),index=pd.to_datetime(frame.available_at,utc=True))
            series[symbol]=self.cache[m['id']]
        history=pd.DataFrame(series)
        try:cov,provenance=shrink_covariance(history,at)
        except ValueError:return {'status':'NO ALLOCATION','notionals':{},'reason':'Insufficient common covariance history','at':at.isoformat()}
        rows=[]
        for r in selected:
            a=assets.get(r['symbol'],{});rows.append({'symbol':r['symbol'],'edge':r.get('expected_edge') or 0,'confidence':max(0,2*((r.get('probability') or .5)-.5)),'cost':r.get('estimated_roundtrip_cost') or .02,'adv':a.get('eligibility',{}).get('mean_dollar_volume') or 0,'sector':a.get('sector') or 'unknown','asset_class':a.get('asset_class') or 'unknown'})
        today=at.date().isoformat();spent=sum(f['quantity']*f['price'] for f in view.get('fills',[]) if f['at'][:10]==today)/max(view['equity'],1);old=np.array([held.get(s,0)+pending.get(s,0) for s in symbols]);remaining=max(0,LIMITS['turnover']-spent-sum(pending.values()))
        plan=optimize('mean_variance',rows,cov,capital=view['equity'],previous=old,limits={'turnover':remaining},annualization=365,entry_only=True);weights=dict(zip(symbols,plan['weights']));notionals={s:max(0,weights[s]-held.get(s,0)-pending.get(s,0))*view['equity'] for s in symbols};plan.update(at=at.isoformat(),weights=weights,notionals=notionals,covariance=provenance,history_versions=sources,weight_epoch=g.get('weight_epoch'),account_id=view['id'],basis='Target portfolio subject to separate risk and delayed quote fills; existing holdings are not assumed sold',external_execution=False);plan['id']='aplan_'+stable_hash({k:v for k,v in plan.items() if k!='at'});self.db.put('alpha_allocation',plan,record_id=plan['id']);self.db.set_setting('alpha_allocation_latest',plan);return plan
