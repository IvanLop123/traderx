"""Predeclared bounded sizing/exit diagnostics. Historical daily opens are price proxies, not fills."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from backend.schemas.contracts import now
from backend.research.history import HistoryStore
from backend.research.features import stable_hash
from backend.selection.policy import policy,policy_hash
from backend.selection.risk import exit_reason

SYMBOLS=['AAPL','MSFT','NVDA','JPM','JNJ','XOM','WMT','CAT','NEE','PLTR','FIX','STRL','HIMS','CALM','SPY','QQQ','IWM','MDY','XBI','URA','XLE','GLD','BTC-USD','ETH-USD']
EXITS=['fixed_horizon','signal_reversal','score_decay','risk_stop','volatility_stop','profit_target','trailing']

def simulate(series,p,start,end):
    """Transparent momentum reference isolates sizing/exit effects, not evidence for model promotion.

    Signals/stops use the last fully available bar; transactions use a later daily open
    plus adverse costs. No high/low touch or midpoint is treated as executable.
    """
    by_day={};prepared={}
    for symbol,bars in series.items():
        d=pd.DataFrame(bars).sort_values('timestamp').reset_index(drop=True);d['time']=pd.to_datetime(d.timestamp,utc=True);d['known']=pd.to_datetime(d.available_at,utc=True);d['ret20']=d.close.pct_change(20);d['vol']=d.close.pct_change().rolling(20).std();d['adv']=(d.close*d.volume).rolling(20).mean();prepared[symbol]=d
        for i,row in d.iterrows():
            if start<=row.time<end and i>65:by_day.setdefault(row.time.normalize(),[]).append((symbol,i))
    cash=10000.;positions={};marks={};high=10000.;curve=[];completed=[];costs=0.;turnover=0.;decisions=0;exposure=[]
    for day,items in sorted(by_day.items()):
        for symbol,i in sorted(items):
            d=prepared[symbol];bar=d.iloc[i];known=d.iloc[:i];known=known[known.known<=bar.time]
            if known.empty:continue
            prev=known.iloc[-1];price=float(bar.open);marks[symbol]=price;equity=cash+sum(v['quantity']*marks.get(s,v['price']) for s,v in positions.items());high=max(high,equity);dd=1-equity/high;cost=.0055 if not symbol.endswith('-USD') and symbol not in ['SPY','QQQ','IWM','MDY','XBI','URA','XLE','GLD'] else .0011
            if symbol in positions:
                pos=positions[symbol];count=i-pos['entry_index'];pos['high']=max(pos['high'],float(prev.close));reason=exit_reason({'average_cost':pos['price']},{'bid':float(prev.close),'high_bid':pos['high'],'daily_volatility':float(prev.vol),'expected_edge':float(prev.ret20),'score':70 if prev.ret20>0 else 20,'drawdown':dd},p,count)
                if reason:
                    proceeds=pos['quantity']*price*(1-cost);cash+=proceeds;paid=pos['quantity']*price*cost;costs+=paid;turnover+=pos['quantity']*price;completed.append({'symbol':symbol,'return':proceeds/pos['spent']-1,'pnl':proceeds-pos['spent'],'exit':reason,'date':str(day),'regime':'uptrend' if prev.ret20>0 else 'downtrend'});del positions[symbol]
                continue
            decisions+=1
            if prev.ret20<=0 or prev.vol<=0 or prev.adv<1e6 or prev.close<5 or dd>=p.maximum_drawdown:continue
            if len(positions)>=p.maximum_positions:continue
            confidence=min(.5,max(0,float(prev.ret20))/(float(prev.vol)*np.sqrt(20)+1e-9));annual=float(prev.vol)*np.sqrt(365 if symbol.endswith('-USD') else 252)
            weight=p.maximum_position*confidence if p.sizing=='confidence_capped' else min(p.maximum_position,p.annual_volatility_target/max(annual,.01)/p.maximum_positions)*np.sqrt(confidence)
            current=sum(v['quantity']*marks.get(s,v['price']) for s,v in positions.items());budget=min(cash,max(0,equity*p.maximum_gross_exposure-current),equity*weight,float(prev.adv)*p.maximum_adv_fraction)
            qty=budget/(price*(1+cost));qty=np.floor(qty) if not symbol.endswith('-USD') else np.floor(qty*1e8)/1e8
            if qty<=0:continue
            spent=qty*price*(1+cost);cash-=spent;costs+=qty*price*cost;turnover+=qty*price;positions[symbol]={'quantity':qty,'price':price*(1+cost),'spent':spent,'entry_index':i,'high':price}
        equity=cash+sum(v['quantity']*marks.get(s,v['price']) for s,v in positions.items());curve.append({'date':str(day),'equity':equity});exposure.append((equity-cash)/equity if equity else 0)
    values=np.array([10000]+[c['equity'] for c in curve]);ret=values[1:]/values[:-1]-1
    return {'net_marked_return':float(values[-1]/10000-1),'maximum_drawdown':float(np.max(1-values/np.maximum.accumulate(values))),'dates':len(curve),'entry_decisions':decisions,'completed_trades':len(completed),'open_positions':len(positions),'mean_trade_return':float(np.mean([t['return'] for t in completed])) if completed else None,'wins':sum(t['pnl']>0 for t in completed),'losses':sum(t['pnl']<0 for t in completed),'turnover':turnover/10000,'cost_drag':costs/10000,'mean_exposure':float(np.mean(exposure)) if exposure else 0,'annualized_metrics':None,'by_regime':{g:{'trades':len(z),'pnl':sum(t['pnl'] for t in z)} for g in ['uptrend','downtrend'] if (z:=[t for t in completed if t['regime']==g])},'curve':curve,'scope':'Daily-open research proxy; fixed 24-asset reference, no quote/depth/queue data. Does not replace automatic-portfolio hard risk or establish executable historical profit.'}

def run_policy_research(db):
    p=policy(db);store=HistoryStore(db);series={s:store.read(s) for s in SYMBOLS if store.manifest(s)};identity={s:store.manifest(s)['id'] for s in series}
    definition={'version':'bounded-portfolio-policies-v1','created_at':now().isoformat(),'assets':list(series),'data_ids':identity,'sizing':['volatility_targeted','confidence_capped'],'exit_policies':EXITS,'policy':p.model_dump(),'signal':'fixed 20-session positive momentum reference; not a promoted model','folds':[['2020-01-01','2022-01-01'],['2022-01-01','2024-01-01'],['2024-01-01','2025-04-16']],'holdout':['2025-04-16','2026-10-10'],'holdout_scope':'Previously inspected historical dates; diagnostic, not independent prospective evidence','selection':'No deployed selection; fixed_horizon and volatility_targeted remain conservative defaults'}
    rid='policy_research_'+stable_hash({k:v for k,v in definition.items() if k!='created_at'});old=db.get(rid)
    if old:return old['payload']
    db.put('portfolio_policy_definition',definition,record_id=rid+'_definition');definition=db.get(rid+'_definition')['payload'];results=[]
    for sizing in definition['sizing']:
        for exit_policy in EXITS:
            pp=p.model_copy(update={'sizing':sizing,'exit_policy':exit_policy});folds=[]
            for start,end in definition['folds']:
                result=simulate(series,pp,pd.Timestamp(start,tz='UTC'),pd.Timestamp(end,tz='UTC'));folds.append({k:v for k,v in result.items() if k!='curve'})
            hold=simulate(series,pp,pd.Timestamp(definition['holdout'][0],tz='UTC'),pd.Timestamp(definition['holdout'][1],tz='UTC'))
            results.append({'sizing':sizing,'exit_policy':exit_policy,'walk_forward_folds':folds,'holdout':hold})
    result={'id':rid,'definition':definition,'results':results,'promotion_eligible':False,'warning':'Reference-policy diagnostics only. Existing retrospective membership and adjusted vintages remain biased; no live strategy selection or profitability claim follows.'};result=json.loads(json.dumps(result,default=lambda v:v.item()));db.put('portfolio_policy_research',result,record_id=rid);db.set_setting('portfolio_policy_research',result);return result
