"""Bounded, preregistered retrospective comparisons; no holdout recycling or promotion."""
import hashlib,json,platform
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import logsumexp
from sklearn.linear_model import Ridge,LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from backend.schemas.contracts import now
from backend.research.features import stable_hash,market_frame
from backend.research.history import HistoryStore
from backend.research.advanced.lab import clean,FEATURES
from backend.research.advanced.models import block_test,by_adjust
from backend.research.structure.experiments import return_correlations
from backend.research.alpha.math import METHODS,LIMITS,shrink_covariance,optimize,neutralize,factor_regression

PAIRS=[('XOM','CVX'),('KO','PEP'),('V','MA'),('GLD','IAU'),('MSFT','AAPL')]
SIGNALS={'momentum':('return_20',1),'trend_following':('ma20_to_ma60',1),'mean_reversion':('return_5',-1),'breakout':('breakout_20',1),'relative_strength':('relative_momentum',1),'volatility':('realized_volatility',-1)}

def performance(values):
    v=np.asarray(values,float);curve=np.cumprod(1+v)
    return {'return':block_test(v),'cumulative_return':float(curve[-1]-1) if len(v) else 0,'maximum_drawdown':float(max(1-curve/np.maximum.accumulate(np.r_[1.,curve])[1:])) if len(v) else 0,'observations':len(v)}

def pair_path(train,test):
    """Prior-only fixed and Kalman relationships; current observation updates the NEXT beta."""
    from statsmodels.tsa.stattools import coint,adfuller
    tr=np.log(train.dropna());te=np.log(test.dropna());x=np.column_stack([np.ones(len(tr)),tr.iloc[:,1]]);beta=np.linalg.lstsq(x,tr.iloc[:,0],rcond=None)[0];res=tr.iloc[:,0]-x@beta;scale=max(float(res.std()),1e-8);theta=beta.copy();cov=np.eye(2);out=[]
    for date,row in te.iterrows():
        v=np.array([1.,row.iloc[1]]);fixed=float((row.iloc[0]-v@beta-res.mean())/scale);err=float(row.iloc[0]-v@theta);dynamic=err/scale
        out.append({'date':str(date),'fixed_beta':float(beta[1]),'kalman_beta':float(theta[1]),'fixed_z':fixed,'kalman_z':dynamic})
        cov+=np.eye(2)*1e-5;k=cov@v/(.001+v@cov@v);theta+=k*err;cov-=np.outer(k,v)@cov
    return {'cointegration_p':float(coint(tr.iloc[:,0],tr.iloc[:,1],maxlag=5,autolag=None)[1]),'training_spread_adf_p':float(adfuller(res,maxlag=5,autolag=None)[1]),'path':out}

def volatility_path(train,test):
    """Every emitted forecast precedes the corresponding return; HMM only filters forward."""
    from arch import arch_model
    from hmmlearn.hmm import GaussianHMM
    tr=np.asarray(train,float);te=np.asarray(test,float)
    g=arch_model(tr*100,mean='Zero',vol='GARCH',p=1,q=1,rescale=False).fit(disp='off',show_warning=False);p=g.params;gv=float(g.conditional_volatility[-1]**2/10000);ew=float(np.var(tr));last=tr[-1];history=list(tr)
    h=GaussianHMM(2,covariance_type='diag',n_iter=100,random_state=41).fit((tr*100).reshape(-1,1));posterior=h.startprob_;var=h.covars_.reshape(-1);means=h.means_.reshape(-1)
    def update(value,posterior):
        prior=posterior@h.transmat_;logp=np.log(np.maximum(prior,1e-30))-.5*(np.log(2*np.pi*var)+(value*100-means)**2/var);return np.exp(logp-logsumexp(logp))
    for x in tr:posterior=update(x,posterior)
    out=[]
    for value in te:
        ew=.94*ew+.06*last**2;gv=p['omega']/10000+p['alpha[1]']*last**2+p['beta[1]']*gv;prior=posterior@h.transmat_
        out.append({'realized':float(np.mean(np.asarray(history[-20:])**2)),'ewma':float(ew),'garch':float(gv),'hmm':float(prior@(var+means**2)/10000),'deterministic_on':bool(np.sum(history[-20:])>0),'hmm_on':bool(prior@means>0)})
        posterior=update(value,posterior);history.append(value);last=value
    return out

def run(db):
    root=Path(__file__).resolve().parents[3];panel=sorted((root/'data/strategy_panels').glob('*.parquet'))[-1];source=db.get(db.setting('structure_experiment_latest',''))
    if not source:raise ValueError('Completed market-structure experiment required')
    reference=source['payload'];artifact=root/reference['artifacts']['features_targets'];identity={'version':'alpha-lab-v1','code_hash':stable_hash({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}),'panel_hash':hashlib.sha256(panel.read_bytes()).hexdigest(),'source_experiment':reference['id'],'source_features_hash':hashlib.sha256(artifact.read_bytes()).hexdigest(),'dates':['2022-01-01','2025-01-01'],'fit_label_end_before':'2022-01-01','features':FEATURES,'signals':SIGNALS,'pairs':PAIRS,'portfolio_methods':METHODS,'constraints':LIMITS,'seed':41,'maximum_fit_rows':18000,'pair_roundtrip_per_leg':.002,'annual_borrow_scenario':.03,'regime_sizing_one_way_cost':.001,'promotion_eligible':False,'basis':'Previously inspected history; no untouched OOS claim','python':platform.python_version()}
    rid='alpha_research_'+stable_hash(identity);old=db.get(rid)
    if old:db.set_setting('alpha_research_result',old['payload']);return old['payload']
    db.put('alpha_research_plan',{'id':rid,'at':now().isoformat(),'identity':identity},record_id=rid+'_plan');full=pd.read_parquet(panel);full=full[full.asset_class.isin(['stock','etf'])].copy();z=pd.read_parquet(artifact);extras=[c for c in set(FEATURES)|{v[0] for v in SIGNALS.values()} if c not in z.columns];z=z.merge(full[['symbol','date']+extras],on=['symbol','date'],validate='one_to_one');z=z[z.target_5.notna()&(z.end_5<pd.Timestamp('2025-01-01',tz='UTC'))];train=full[(full.label_end<pd.Timestamp('2022-01-01',tz='UTC'))&full.eligible&full.net_return.notna()].dropna(subset=FEATURES);train=train.iloc[np.linspace(0,len(train)-1,min(18000,len(train)),dtype=int)]
    scaler=StandardScaler().fit(train[FEATURES]);xx=scaler.transform(train[FEATURES]);model=Ridge(alpha=100).fit(xx,train.net_return);classifier=LogisticRegression(C=.01,max_iter=300).fit(xx,train.net_return>0);z=z.dropna(subset=FEATURES);z['prediction']=model.predict(scaler.transform(z[FEATURES]));z['confidence']=classifier.predict_proba(scaler.transform(z[FEATURES]))[:,1];returns=full.pivot_table(index='date',columns='symbol',values='return_1').sort_index();prices=full.pivot_table(index='date',columns='symbol',values='close').sort_index();market=returns['SPY'];beta=returns.rolling(120,min_periods=60).cov(market).div(market.rolling(120,min_periods=60).var(),axis=0).shift(1)
    grid=[];end=None
    for date,g in z.groupby('date',sort=True):
        if end is None or date>end:grid.append(date);end=g.end_5.max()
    streams={k:{} for k in SIGNALS};neutral_streams={k:{} for k in SIGNALS};factor_rows={};ic={k:[] for k in SIGNALS};neutral_ic={k:[] for k in SIGNALS};allocations={m:[] for m in METHODS};skipped=0
    with threadpool_limits(limits=2):
        for date in grid:
            g=z[z.date==date].copy();g['beta']=g.symbol.map(beta.loc[date] if date in beta.index else {});g=g.dropna(subset=['beta'])
            if len(g)<30:continue
            market_label=g[g.symbol=='SPY'].target_5
            if market_label.empty:continue
            universe=g.target_5.mean();mom=g.sort_values('return_20');factor_rows[str(date)]={'market':float(market_label.iloc[0]),'momentum_proxy':float(mom.tail(max(1,len(g)//10)).target_5.mean()-mom.head(max(1,len(g)//10)).target_5.mean())}
            for family,(feature,sign) in SIGNALS.items():
                raw=g[feature]*sign;factors=g[['beta','momentum_rank','volatility_rank','liquidity_rank']];res=neutralize(raw,factors);top=g.assign(score=raw).sort_values(['score','symbol']).tail(max(1,len(g)//10));ntop=g.assign(score=res).dropna(subset=['score']).sort_values(['score','symbol']).tail(max(1,len(g)//10));streams[family][str(date)]=float((top.target_5-top.cost).mean()-universe);neutral_streams[family][str(date)]=float((ntop.target_5-ntop.cost).mean()-universe)
                if raw.nunique()>1:ic[family].append(float(raw.corr(g.target_5,method='spearman')))
                if np.isfinite(res).all() and np.std(res)>1e-12:neutral_ic[family].append(float(pd.Series(res,index=g.index).corr(g.target_5,method='spearman')))
            top=g[(g.prediction>0)&(g.confidence>=.55)].sort_values(['prediction','symbol']).tail(12);assets=[{'symbol':r.symbol,'edge':r.prediction,'confidence':r.confidence,'cost':r.cost,'adv':r.adv,'sector':'unknown','asset_class':r.asset_class} for r in top.itertuples()]
            try:cov,provenance=shrink_covariance(returns.reindex(columns=top.symbol),date)
            except ValueError:cov=np.zeros((0,0));assets=[];top=top.iloc[:0];skipped+=1
            for method in METHODS:
                # Fresh nonoverlapping sleeves: budget both entry and exit turnover and costs.
                out=optimize(method,assets,cov,limits={'turnover':LIMITS['turnover']/2,'cost':LIMITS['cost']/2});w=np.array(out['weights']);net=float(w@(top.target_5-top.cost).to_numpy()) if len(w) else 0.
                allocations[method].append({'date':str(date),'net':net,'gross_exposure':out.get('gross',0),'turnover':2*sum(w),'cost':float(w@top.cost.to_numpy()) if len(w) else 0,'constraints':out})
    factors=pd.DataFrame.from_dict(factor_rows,orient='index');factor_results={k:{'raw':factor_regression(pd.Series(v),factors),'neutralized':factor_regression(pd.Series(neutral_streams[k]),factors),'rank_ic':block_test(ic[k]),'neutral_rank_ic':block_test(neutral_ic[k])} for k,v in streams.items()};store=HistoryStore(db);pair_results=[];rawopens={}
    for symbol in sorted({s for pair in PAIRS for s in pair}|{'SPY'}):
        bars=store.read(symbol)
        if bars:
            f,_,_=market_frame(bars);rawopens[symbol]=pd.Series(f.open.to_numpy(),index=pd.to_datetime(f.available_at,utc=True).dt.ceil('D'))
    for a,b in PAIRS:
        if a not in prices or b not in prices or a not in rawopens or b not in rawopens:continue
        history=prices[[a,b]].dropna();trainp=history[history.index<pd.Timestamp('2022-01-01',tz='UTC')].tail(1000);test=history[(history.index>=pd.Timestamp('2022-01-01',tz='UTC'))&(history.index<pd.Timestamp('2025-01-01',tz='UTC'))]
        if len(trainp)<252 or len(test)<100:continue
        path=pair_path(trainp,test);opens=pd.concat([rawopens[a].rename(a),rawopens[b].rename(b)],axis=1).reindex(test.index);future=opens.shift(-3)/opens.shift(-2)-1;pnl={m:[] for m in ('fixed','kalman')}
        for i,item in enumerate(path['path']):
            if i%4 or i>=len(test)-3:continue
            ret=future.iloc[i]
            if not np.isfinite(ret).all():continue
            for method in pnl:
                hedge=item[method+'_beta'];signal=item[method+'_z'];side=-np.sign(signal) if abs(signal)>1 else 0;legs=np.array([side,-side*hedge])/max(1,1+abs(hedge));gross=legs@ret.to_numpy();cost=np.abs(legs).sum()*.002+np.abs(np.minimum(legs,0)).sum()*.03/252;pnl[method].append(float(gross-cost))
        pair_results.append({'pair':[a,b],'training_end':str(trainp.index.max()),'test_start':str(test.index.min()),'cointegration_p':path['cointegration_p'],'training_spread_adf_p':path['training_spread_adf_p'],'fixed':performance(pnl['fixed']),'kalman':performance(pnl['kalman']),'eligible_from_training':False,'execution_status':'Conditional research scenario only: short borrow availability, synchronized depth and two-leg fills unverified','path_hash':stable_hash(path['path'])})
    for p,q in zip(pair_results,by_adjust([x['cointegration_p'] for x in pair_results])):p.update(training_BY_q=q,eligible_from_training=q<.05)
    r=np.log(prices.SPY.dropna()).diff().dropna();tr=r[r.index<pd.Timestamp('2022-01-01',tz='UTC')];te=r[(r.index>=pd.Timestamp('2022-01-01',tz='UTC'))&(r.index<pd.Timestamp('2025-01-01',tz='UTC'))];vp=volatility_path(tr.to_numpy(),te.to_numpy());volatility={};regime={};o=rawopens['SPY'].reindex(te.index);forward=(o.shift(-2)/o.shift(-1)-1).to_numpy();valid=np.isfinite(forward);truth=te.to_numpy()**2
    # Forecast at t uses observations strictly before t, enters delayed actual open[t+1], exits open[t+2].
    for method in ('realized','ewma','garch','hmm'):
        variance=np.array([v[method] for v in vp]);weights=np.minimum(1,.10/np.sqrt(np.maximum(variance,1e-12)*252));cost=np.abs(np.diff(np.r_[0,weights]))*.001;net=weights[valid]*forward[valid]-cost[valid];net[-1]-=weights[valid][-1]*.001
        volatility[method]={'variance_mse':float(np.mean((truth-variance)**2)),'qlike':float(np.mean(np.log(np.maximum(variance,1e-12))+truth/np.maximum(variance,1e-12))),'sizing':performance(net),'mean_weight':float(weights.mean()),'forecast_path_hash':stable_hash(variance.tolist())}
    base=np.minimum(1,.10/np.sqrt(np.maximum([v['realized'] for v in vp],1e-12)*252))
    for name,gate in [('always',np.ones(len(vp))),('deterministic_trend',np.array([v['deterministic_on'] for v in vp])),('hmm_expected_return',np.array([v['hmm_on'] for v in vp]))]:
        weights=base*gate;cost=np.abs(np.diff(np.r_[0,weights]))*.001;net=weights[valid]*forward[valid]-cost[valid];net[-1]-=weights[valid][-1]*.001;regime[name]=performance(net)
    decay={}
    for family,(feature,sign) in SIGNALS.items():
        decay[family]=[]
        for horizon in (1,2,5,10,20):
            vals=[];ics=[];costs=[];turn=[];last=None;previous=set()
            eligible=z[z['target_'+str(horizon)].notna()&(z['end_'+str(horizon)]<pd.Timestamp('2025-01-01',tz='UTC'))]
            for date,g in eligible.groupby('date',sort=True):
                if last is not None and date<=last:continue
                last=g['end_'+str(horizon)].max();g=g.dropna(subset=[feature])
                if len(g)<30 or g[feature].nunique()<2:continue
                sig=g[feature]*sign;target=g['target_'+str(horizon)];ics.append(float(sig.corr(target,method='spearman')));top=g.assign(score=sig).sort_values(['score','symbol']).tail(max(1,len(g)//10));vals.append(float((top['target_'+str(horizon)]-top.cost).mean()-target.mean()));costs.append(float(top.cost.mean()));selected=set(top.symbol);turn.append(1-len(previous&selected)/len(selected));previous=selected
            decay[family].append({'family':family,'horizon_sessions':horizon,'rank_ic':block_test(ics),'active_return':block_test(vals),'cost_drag':float(np.mean(costs)) if costs else None,'turnover':float(np.mean(turn)) if turn else None,'status':'Reference rank hypothesis; no automatic horizon selection'})
    dr=[v for values in decay.values() for v in values];qs=by_adjust([v['rank_ic']['p'] for v in dr]+[v['active_return']['p'] for v in dr],100)
    for i,v in enumerate(dr):v['rank_ic_BY_q']=qs[i];v['active_return_BY_q']=qs[i+len(dr)]
    portfolio={m:{**performance([r['net'] for r in rows]),'average_exposure':float(np.mean([r['gross_exposure'] for r in rows])),'total_turnover':float(sum(r['turnover'] for r in rows)),'total_cost_drag':float(sum(r['cost'] for r in rows)),'infeasible_or_cash':sum(r['constraints']['status']!='FEASIBLE' for r in rows)} for m,rows in allocations.items()};tests=[v['rank_ic'] for v in factor_results.values()]+[v['return'] for v in portfolio.values()]+[v['return'] for v in regime.values()]
    for v,q in zip(tests,by_adjust([v['p'] for v in tests],100)):v['BY_q_100_declared']=q
    folder=root/'data/alpha_phase';folder.mkdir(exist_ok=True);out=folder/(rid+'_paths.json');out.write_text(json.dumps(clean({'alpha_returns':streams,'neutral_returns':neutral_streams,'allocations':allocations,'volatility':vp}),sort_keys=True));result=clean({'id':rid,'at':now().isoformat(),'identity':identity,'decay':decay,'alpha_correlations':return_correlations({k:pd.Series(v) for k,v in streams.items()}),'factors':factor_results,'factor_missing':{'size':'Historical market-cap/shares unavailable; liquidity is not size','value':'Point-in-time book-to-market/valuation unavailable','sector':'Historical classifications unavailable; current sector tags used only for present risk caps'},'pairs':pair_results,'volatility':volatility,'regime':regime,'portfolio':portfolio,'covariance_unavailable_dates':skipped,'adaptive_vs_fixed':{'status':'WAITING FOR UNTOUCHED FORWARD EVALUATION','observations':0,'historical_winner_not_deployed':True},'artifact':str(out.relative_to(root)),'artifact_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'genuine_oos_improvement':False,'limitations':['Historical universe survivorship and adjusted-price labels remain limitations','Unknown historical sectors share one conservative exposure cap; no sector-neutral claim','Pair returns are conditional borrow/execution scenarios, not deployable results','One-way 10bp volatility/regime sizing costs are assumptions, not verified fills','No new deep architectures or previously held-out scientific outcomes used','All periods previously inspected; no qualified strategy or profitability claim']});db.put('alpha_research_result',result,record_id=rid);db.set_setting('alpha_research_result',result);return result
