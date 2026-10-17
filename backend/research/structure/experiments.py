"""Frozen, bounded signal-horizon/capacity diagnostics; no promotion or training reuse."""
import hashlib,json,platform
from pathlib import Path
import numpy as np
import pandas as pd
from backend.research.features import stable_hash,market_frame
from backend.research.advanced.models import block_test,by_adjust
from backend.research.advanced.lab import clean
from backend.research.history import HistoryStore
from backend.research.universe import ROOT
from backend.schemas.contracts import now

HORIZONS=[1,2,5,10,20]
SIGNALS={'momentum':'return_20','mean_reversion':'return_5','low_volatility':'realized_volatility'}
SIZES=[100,1000,10000,100000,1000000]

def capacity(frame,capital):
    """Illustrative square-root impact sensitivity, not calibrated capacity."""
    size=capital/max(len(frame),1);adv=frame.adv.to_numpy(float);vol=frame.realized_volatility.to_numpy(float)
    valid=(adv>0)&np.isfinite(adv)&np.isfinite(vol)
    if not valid.all():return {'capital':capital,'classification':'INSUFFICIENT EVIDENCE','net_return':None,'participation':None}
    participation=size/adv;impact=2*np.maximum(vol,0)*np.sqrt(participation)
    net=frame.gross_return.to_numpy()-frame.cost.to_numpy()-impact
    return {'capital':capital,'net_return':float(net.mean()),'impact_cost':float(impact.mean()),'participation':float(participation.max()),'classification':'INSUFFICIENT EVIDENCE','reason':'Historical executable spread, consolidated depth and calibrated impact unavailable; sensitivity only'}

def return_correlations(streams,minimum_dates=40):
    frame=pd.DataFrame(streams).sort_index();count=frame.notna().astype(int).T@frame.notna().astype(int)
    corr=frame.corr(min_periods=minimum_dates)
    return {'correlations':clean(corr.to_dict()),'paired_dates':count.to_dict(),'minimum_dates':minimum_dates,'basis':'Aligned nonoverlapping realized top-decile active returns after costs, relative to the same-date universe','qualification':'Retrospective diagnostics only; no independent-alpha certification'}

def compare(a,b):
    fields=sorted(set(a['identity'])|set(b['identity']));return {'a':a['id'],'b':b['id'],'changed':{k:{'a':a['identity'].get(k),'b':b['identity'].get(k)} for k in fields if a['identity'].get(k)!=b['identity'].get(k)},'a_results':a.get('results'),'b_results':b.get('results')}

def run(db,panel_path=None):
    path=Path(panel_path) if panel_path else sorted((ROOT/'data/strategy_panels').glob('*.parquet'))[-1]
    store=HistoryStore(db);p=pd.read_parquet(path);p=p[p.asset_class.isin(['stock','etf'])].copy();symbols=sorted(p.symbol.unique());manifests=[store.manifest(s) for s in symbols];manifests=[m for m in manifests if m]
    import importlib.metadata as md
    identity={'version':'horizon-capacity-v1','code_version':hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('intraday.py').read_bytes()+(ROOT/'backend/research/advanced/models.py').read_bytes()+(ROOT/'backend/research/features.py').read_bytes()).hexdigest(),'dataset_snapshot':hashlib.sha256(path.read_bytes()).hexdigest(),'history_versions':{m['symbol']:{'id':m['id'],'sha256':m['file_hash']} for m in manifests},'universe':symbols,'features':SIGNALS,'model_version':'Predeclared momentum / reversal / low volatility ranks; no fitted model','dates':['2022-01-01','2025-01-01'],'target':'Delayed open[t+2] to open[t+2+h], same asset sessions; research prices, not assumed executable fills','horizons':HORIZONS,'hyperparameters':{'entry_delay_bars':2,'minimum_cross_section':30,'long_quantile':.9,'impact_coefficient':1,'capital_sizes':SIZES},'seed':41,'costs':'Source-panel conservative roundtrip costs plus two-sided vol*sqrt(order/ADV) capacity sensitivity','packages':{k:md.version(k) for k in ('numpy','pandas','scipy','scikit-learn')},'python':platform.python_version(),'status':'Previously inspected historical periods; not untouched OOS','promotion_eligible':False}
    rid='structure_exp_'+stable_hash(identity);existing=db.get(rid)
    if existing:db.set_setting('structure_experiment_latest',rid);return existing['payload']
    db.put('structure_experiment_plan',{'id':rid,'identity':identity,'registered_at':now().isoformat()},record_id=rid+'_plan')
    p['execution_open']=np.nan
    for s,g in p.groupby('symbol'):
        bars=store.read(s)
        if not bars:continue
        f,_,_=market_frame(bars);mapping=dict(zip(pd.to_datetime(f.available_at,utc=True).dt.ceil('D'),f.open));p.loc[g.index,'execution_open']=g.date.map(mapping)
    p=p.sort_values(['symbol','date']);group=p.groupby('symbol');entry=group.execution_open.shift(-2)
    targets=[]
    for h in HORIZONS:
        p['target_'+str(h)]=group.execution_open.shift(-h-2)/entry-1;p['end_'+str(h)]=group.date.shift(-h-2);targets.extend(['target_'+str(h),'end_'+str(h)])
    p=p[(p.date>=pd.Timestamp('2022-01-01',tz='UTC'))&(p.date<pd.Timestamp('2025-01-01',tz='UTC'))&p.eligible].copy()
    folder=ROOT/'data/structure_experiments';folder.mkdir(exist_ok=True,parents=True);artifact=folder/(rid+'.parquet');cols=['symbol','date','asset_class','regime','liquidity_bucket','adv','cost']+list(SIGNALS.values())+targets;p[cols].to_parquet(artifact,index=False)
    results=[];streams={};diagnostic_rows=[];families=list(SIGNALS)
    dates=sorted(p.date.unique())
    for h in HORIZONS:
        # Common fixed grid for each horizon; holding windows never overlap.
        valid=p[p['target_'+str(h)].notna() & (p['end_'+str(h)]<pd.Timestamp('2025-01-01',tz='UTC'))];grid=[];last=None
        for date,g in valid.groupby('date'):
            if last is None or date>last:grid.append(date);last=g['end_'+str(h)].max()
        z=valid[valid.date.isin(grid)].copy();z['gross_return']=z['target_'+str(h)];z['net_return']=z.gross_return-z.cost
        for family,feature in SIGNALS.items():
            ic=[];net=[];active=[];deciles=[];turnover=[];caps={n:[] for n in SIZES};prior=set();by_regime={};perdate={};cost=[]
            for d,g in z.groupby('date'):
                g=g[g[feature].notna()&g.adv.notna()&g.cost.notna()].copy()
                if len(g)<30:continue
                g['signal']=g[feature]*(1 if family=='momentum' else -1)
                if g.signal.nunique()<2:continue
                ic.append(float(g.signal.corr(g.gross_return,method='spearman')));g=g.sort_values(['signal','symbol']);top=g.tail(max(1,len(g)//10));r=float(top.net_return.mean());universe=float(g.gross_return.mean());net.append(r);active.append(r-universe);perdate[str(d)]=r-universe;cost.append(float(top.cost.mean()));selected=set(top.symbol);turnover.append(1-len(prior&selected)/max(len(selected),1));prior=selected
                parts=np.array_split(np.arange(len(g)),10);deciles.append([float(g.iloc[q].net_return.mean()) for q in parts]);dominant=str(g.regime.mode().iloc[0]);by_regime.setdefault(dominant,[]).append(r-universe)
                for size in SIZES:caps[size].append(capacity(top,size))
                diagnostic_rows.append({'date':str(d),'family':family,'horizon':h,'net_return':r,'active_return':r-universe,'symbols':sorted(selected)})
            if h==5:streams[family]=pd.Series(perdate,dtype=float)
            curve=np.cumprod(1+np.array(net));row={'family':family,'horizon_sessions':h,'rank_ic':block_test(ic),'net_top_decile':block_test(net),'active_return':block_test(active),'decile_net_returns':np.mean(deciles,axis=0).tolist() if deciles else [],'turnover':float(np.mean(turnover)) if turnover else None,'cost_drag':float(np.mean(cost)) if cost else None,'maximum_drawdown':float(np.max(1-curve/np.maximum.accumulate(np.r_[1,curve])[1:])) if len(curve) else None,'regimes':{k:block_test(v) for k,v in by_regime.items()},'capacity':[{'capital':size,'mean_net_return':float(np.mean([v['net_return'] for v in values if v['net_return'] is not None])) if any(v['net_return'] is not None for v in values) else None,'max_participation':max((v['participation'] for v in values if v['participation'] is not None),default=None),'classification':'INSUFFICIENT EVIDENCE'} for size,values in caps.items()]};results.append(row)
    # Both IC and active-return families are declared; reserve all 30 tests.
    q=by_adjust([r['rank_ic']['p'] for r in results]+[r['active_return']['p'] for r in results],len(families)*len(HORIZONS)*2)
    for i,r in enumerate(results):r['rank_ic_BY_q']=q[i];r['active_return_BY_q']=q[i+len(results)]
    output=folder/(rid+'_returns.json');output.write_text(json.dumps(diagnostic_rows,sort_keys=True))
    result=clean({'id':rid,'at':now().isoformat(),'identity':identity,'results':results,'strategy_return_correlations':return_correlations(streams),'artifacts':{'features_targets':str(artifact.relative_to(ROOT)),'features_targets_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'returns':str(output.relative_to(ROOT)),'returns_sha256':hashlib.sha256(output.read_bytes()).hexdigest()},'genuine_oos_improvement':False,'limitations':['Daily next-bar equals one trading session; intraday next-bar validation awaits sufficient observations.','Current-member universe still has survivorship bias; delisting returns incomplete.','Adjusted provider opens are research labels only; cannot justify executable fills.','Five-session return streams aligned by decision date, not forecast correlations.','Capacity is a stress scenario with uncalibrated impact and incomplete feed volume; no capacity class is certified.','No test-selected horizon or family is automatically deployed.','No manual, shadow or prospective holdout evidence used.','No significance claim or improvement from revisiting previously inspected periods.']})
    db.put('structure_experiment',result,record_id=rid);db.set_setting('structure_experiment_latest',rid);return result
