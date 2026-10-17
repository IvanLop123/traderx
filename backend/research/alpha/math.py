"""Deterministic portfolio and factor calculations, with explicit missing-data gates."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf
from backend.research.advanced.models import block_test

METHODS=('equal','edge','inverse_volatility','volatility_target','risk_parity','confidence','mean_variance')
LIMITS={'asset':.10,'sector':.30,'asset_class':.60,'gross':.80,'cluster':.25,'correlation':.70,'adv_fraction':.0001,'turnover':.40,'annual_volatility':.10,'cost':.003}

def shrink_covariance(returns,at,minimum=60):
    """Complete common observations only; never turn missing returns into zero."""
    x=returns.loc[returns.index<pd.Timestamp(at)].tail(252).replace([np.inf,-np.inf],np.nan).dropna()
    if len(x)<minimum or x.shape[1]<1:raise ValueError('At least 60 common prior return dates required')
    fit=LedoitWolf().fit(x.to_numpy())
    return fit.covariance_,{'observations':len(x),'end':str(x.index.max()),'shrinkage':float(fit.shrinkage_),'columns':list(x.columns)}

def neutralize(signal,factors):
    y=np.asarray(signal,float);x=np.asarray(factors,float)
    if x.ndim==1:x=x[:,None]
    valid=np.isfinite(y)&np.isfinite(x).all(axis=1);out=np.full(len(y),np.nan)
    if valid.sum()<max(10,x.shape[1]+3):return out
    z=np.column_stack([np.ones(valid.sum()),x[valid]]);out[valid]=y[valid]-z@np.linalg.lstsq(z,y[valid],rcond=None)[0]
    return out

def factor_regression(strategy,factors,minimum=40):
    z=pd.concat([strategy.rename('strategy'),factors],axis=1).dropna()
    if len(z)<minimum:return {'status':'INSUFFICIENT EVIDENCE','observations':len(z)}
    x=np.column_stack([np.ones(len(z)),z[factors.columns]]);y=z.strategy.to_numpy();b=np.linalg.lstsq(x,y,rcond=None)[0];res=y-x@b
    return {'status':'RETROSPECTIVE DESCRIPTIVE','observations':len(z),'exposures':dict(zip(factors.columns,map(float,b[1:]))),'intercept':float(b[0]),'r_squared':float(1-np.var(res)/max(np.var(y),1e-12)),'residual_mean':float(res.mean()),'intercept_uncertainty':'Not a novel-alpha significance claim; factor selection and multiple testing remain relevant'}

def adaptive(prior,history,previous=None,minimum=60,max_change=.02,recent_fraction=.20):
    """Long-run prior >=80%; at most 2 percentage-point change per evidence epoch."""
    keys=sorted(prior);p=np.array([max(0,prior[k]) for k in keys],float)
    if not len(keys) or p.sum()==0:return {},{'status':'NO PRIOR'}
    p/=p.sum();prev=np.array([(previous or {}).get(k,p[i]) for i,k in enumerate(keys)],float)
    if not np.isfinite(prev).all() or prev.sum()<=0:prev=p.copy()
    prev/=prev.sum();scores=[];usable=True;counts={}
    for k in keys:
        v=np.asarray(history.get(k,[]),float);v=v[np.isfinite(v)];counts[k]=len(v)
        if len(v)<minimum:usable=False
        # Shrink the recent 60-window mean toward a zero-skill prior. Bounded score.
        tail=v[-60:];skill=(float(tail.mean())/(float(tail.std())+1e-6)*len(v)/(len(v)+240)) if len(tail) else 0
        scores.append(np.clip(skill,-.5,.5))
    target=p.copy()
    if usable:
        tilt=p*np.exp(scores);tilt/=tilt.sum();target=(1-recent_fraction)*p+recent_fraction*tilt
    # Convex step preserves sum=1 and every coordinate's change bound.
    delta=target-prev;step=min(1,max_change/max(np.max(np.abs(delta)),1e-12));w=prev+step*delta
    return dict(zip(keys,map(float,w))),{'status':'BOUNDED ADAPTATION' if usable else 'FIXED PRIOR — INSUFFICIENT FORWARD DATES','counts':counts,'prior_fraction':1-recent_fraction,'maximum_step':max_change}

def optimize(method,assets,cov,capital=10000,previous=None,limits=None,annualization=252,entry_only=False):
    if method not in METHODS:raise ValueError('Unknown portfolio method')
    p={**LIMITS,**(limits or {})};n=len(assets);old=np.asarray(previous if previous is not None else np.zeros(n),float);zero=np.zeros(n)
    def rejected(why):return {'weights':zero.tolist(),'status':'NO ALLOCATION','reasons':[why],'cash_weight':1.,'external_execution':False}
    if not n:return rejected('No eligible positive-edge forecasts')
    c=np.asarray(cov,float)
    if c.shape!=(n,n) or not np.isfinite(c).all() or not np.allclose(c,c.T) or np.linalg.eigvalsh(c).min()<-1e-10:return rejected('Invalid covariance')
    edge=np.asarray([a.get('edge',np.nan) for a in assets]);vol=np.sqrt(np.maximum(np.diag(c),1e-12));cost=np.asarray([a.get('cost',np.nan) for a in assets]);adv=np.asarray([a.get('adv',0) for a in assets]);confidence=np.asarray([a.get('confidence',0) for a in assets]);
    if capital<=0 or not np.isfinite(np.r_[edge,cost,adv,confidence,old]).all() or np.any(cost<0) or np.any(old<0):return rejected('Invalid risk inputs')
    caps=np.minimum(p['asset'],np.maximum(adv,0)*p['adv_fraction']/capital);caps=np.where((edge>0)&(confidence>0)&(cost<=np.maximum(edge,0)),caps,0)
    lower=old.copy() if entry_only else zero
    if np.any(lower>caps+1e-10):return rejected('Existing exposure requires separate exits before new allocation')
    corr=c/np.outer(vol,vol);groups=[]
    for field in ('sector','asset_class'):
        for name in sorted({a.get(field) or 'unknown' for a in assets}):groups.append((np.array([(a.get(field) or 'unknown')==name for a in assets]),p[field],field+':'+name))
    # Connected components, not pair counts: transitive high-correlation clusters share a cap.
    unseen=set(range(n))
    while unseen:
        todo=[min(unseen)];cluster=set()
        while todo:
            i=todo.pop()
            if i in cluster:continue
            cluster.add(i);unseen.discard(i);todo += [j for j in list(unseen) if abs(corr[i,j])>=p['correlation']]
        groups.append((np.array([i in cluster for i in range(n)]),p['cluster'],'correlation_cluster'))
    if method=='equal':raw=np.ones(n)
    elif method=='edge':raw=np.maximum(edge,0)
    elif method in ('inverse_volatility','volatility_target'):raw=1/vol
    elif method=='confidence':raw=np.clip(confidence,0,1)*np.maximum(edge,0)/vol
    elif method=='risk_parity':
        raw=1/vol;raw/=raw.sum()
        for _ in range(100):
            rc=raw*(c@raw);target=max(raw@c@raw,1e-12)/n;raw*=np.sqrt(target/np.maximum(rc,1e-12));raw/=raw.sum()
    else:raw=np.maximum(edge,0)/vol
    desired=raw/max(raw.sum(),1e-12)*p['gross']
    if method=='volatility_target':desired*=min(1,p['annual_volatility']/max(np.sqrt(annualization*(desired@c@desired)),1e-12))
    desired=np.minimum(desired,caps)
    def margins(w):
        return np.r_[p['gross']-w.sum(),p['turnover']-np.abs(w-old).sum(),p['annual_volatility']**2-annualization*(w@c@w),p['cost']-np.abs(w-old)@cost,[cap-w[mask].sum() for mask,cap,_ in groups]]
    def objective(w):
        if method=='mean_variance':return float(5*annualization*(w@c@w)-w@edge+np.abs(w-old)@cost)
        return float(np.sum((w-desired)**2)+.01*np.abs(w-old)@cost)
    start=np.minimum(caps,np.maximum(old,0));res=minimize(objective,start,method='SLSQP',bounds=list(zip(lower,caps)),constraints=[{'type':'ineq','fun':margins}],options={'maxiter':300,'ftol':1e-12})
    w=np.maximum(0,res.x)
    if not res.success or np.any(w>caps+1e-7) or np.any(w<lower-1e-7) or margins(w).min()<-1e-7:return rejected('Constraints infeasible or optimizer failed; no new orders, existing exposure needs separate exits')
    return {'weights':w.tolist(),'status':'FEASIBLE','method':method,'cash_weight':float(1-w.sum()),'gross':float(w.sum()),'turnover':float(np.abs(w-old).sum()),'estimated_cost_drag':float(np.abs(w-old)@cost),'annual_volatility':float(np.sqrt(max(0,w@c@w)*annualization)),'maximum_weight':float(w.max()),'groups':[{'name':name,'weight':float(w[mask].sum()),'cap':cap} for mask,cap,name in groups],'limits':p,'external_execution':False}

def attribution(pnl,fees,family_weights,alpha_ids,symbol,regime,sector,sizing):
    weights={k:max(0,float(v)) for k,v in family_weights.items()};total=sum(weights.values());weights={k:v/total for k,v in weights.items()} if total else {'unattributed':1.}
    return {'alpha':{alpha_ids.get(k,k):v*pnl for k,v in weights.items()},'family':{k:v*pnl for k,v in weights.items()},'asset':{symbol:pnl},'regime':{regime or 'unknown':pnl},'sector':{sector or 'unknown':pnl},'sizing_decision':{sizing:pnl},'costs':{'fees':fees,'gross_before_fees':pnl+fees,'net':pnl},'scope':'Each dimension separately reconciles to net P&L; dimensions must not be summed. Entry-weight allocation is descriptive, not causal. Slippage is embedded in fills.'}
