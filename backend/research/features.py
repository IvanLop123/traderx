"""Causal feature families. No backward filling, guessed history, or LLM dependency."""
import hashlib
import json
import numpy as np
import pandas as pd
from backend.research.engine import ordered_bars
from backend.intelligence.quant import features
from backend.research.point_in_time import join_features_asof

VERSION='evidence-families-v5-history'
PEERS=['BTC-USD','ETH-USD','SOL-USD','AAPL','MSFT','NVDA']
MACRO=['FEDFUNDS','UNRATE','T10Y2Y','CPIAUCSL','INDPRO','M2SL','BAMLC0A0CM']
SOURCES={'price':'Coinbase / Alpaca completed OHLCV','technical':'Local OHLCV calculations','regime':'Past-only OHLCV state proxies',
 'cross_asset':'Coinbase / Alpaca backward-aligned completed bars','macro':'ALFRED archived initial releases; next New York midnight availability',
 'sec':'Observed SEC filings / deterministic extraction','text':'Observed deterministic or existing attributed text extraction',
 'crypto_structure':'Observed Hyperliquid funding and open interest',
 'energy':'EIA observed relevant series only; explicit asset mapping required'}

def family(name):
    if name.startswith(('insider_','institution_','filing_')):return 'sec'
    if name.startswith('macro_'):return 'macro'
    if name.startswith('energy_'):return 'energy'
    if name.startswith('crypto_'):return 'crypto_structure'
    return 'text'

def market_frame(bars):
    df=ordered_bars(bars);q=features(df.to_dict('records'));c=df.close;v=df.volume;r=c.pct_change(fill_method=None)
    out=pd.DataFrame(index=df.index);groups={}
    def add(group,name,value):out[name]=value;groups[name]=group
    for name in ['return_1','return_5','return_20']:add('price',name,q[name])
    add('price','log_return_1',np.log(c).diff())
    for name in ['realized_volatility','volume_zscore','vwap_distance','rsi','bollinger_z','gap_return','intraday_return','acceleration','range_location']:
        add('technical',name,q[name])
    add('technical','atr_fraction',q.atr/c)
    add('technical','macd_fraction',q.macd/c)
    add('technical','bollinger_width',4*c.rolling(20).std()/c.rolling(20).mean())
    add('technical','ma20_to_ma60',c.rolling(20).mean()/c.rolling(60).mean()-1)
    add('technical','volume_change_5',v.pct_change(5,fill_method=None))
    add('technical','signed_volume',np.sign(r)*v/v.rolling(20).mean())
    add('technical','drawdown_60',c/c.rolling(60).max()-1)
    add('technical','vol_of_vol',r.rolling(20).std().rolling(20).std())
    add('technical','trend_efficiency',c.diff(20).abs()/c.diff().abs().rolling(20).sum())
    prior_vol=r.rolling(20).std();reference=prior_vol.rolling(120,min_periods=30).median().shift(1)
    add('regime','regime_trend',np.where(q.return_20>.03,1,np.where(q.return_20<-.03,-1,0)))
    add('regime','regime_vol_ratio',prior_vol/reference.replace(0,np.nan))
    add('regime','liquidity_stress_proxy',r.abs()/(c*v).replace(0,np.nan)*1e8)
    return df,out.replace([np.inf,-np.inf],np.nan),groups

def backward(times,rows,tolerance):
    left=pd.DataFrame({'time':pd.to_datetime(times,utc=True),'row':range(len(times))}).sort_values('time')
    right=pd.DataFrame(rows).sort_values('time').drop_duplicates('time',keep='last')
    return pd.merge_asof(left,right,on='time',direction='backward',tolerance=pd.Timedelta(tolerance)).sort_values('row')

def build_frame(db,symbol,bars=None):
    from backend.research.history import research_bars
    bars=bars or research_bars(db,symbol)
    cutoff=pd.Timestamp.now(tz='UTC')
    bars=[r for r in bars if max(pd.Timestamp(r['available_at']),pd.Timestamp(r['observed_at']))<=cutoff]
    df,x,groups=market_frame(bars);times=df.available_at;coverage_notes={};peer_momentum=[]
    for peer in PEERS:
        if peer==symbol:continue
        history=[r for r in research_bars(db,peer) if max(pd.Timestamp(r['available_at']),pd.Timestamp(r['observed_at']))<=cutoff]
        if len(history)<65:continue
        p,pf,_=market_frame(history)
        rows=[{'time':pd.Timestamp(t),'close':close,'momentum':m,'vol':v,'source_time':pd.Timestamp(t)} for t,close,m,v in zip(p.available_at,p.close,pf.return_20,pf.realized_volatility)]
        aligned=backward(times,rows,'4 days');label=peer.replace('-','_')
        peer_momentum.append(aligned.momentum)
        peer_returns=aligned.close.pct_change(fill_method=None)
        # Daily alignment is an as-of relation, not a same-row join across calendars.
        for name,value in {
            'relative_momentum':x.return_20-aligned.momentum,
            'correlation_20':x.return_1.rolling(20).corr(peer_returns),
            'correlation_change':x.return_1.rolling(20).corr(peer_returns)-x.return_1.rolling(60).corr(peer_returns),
            'relative_vol':x.realized_volatility/aligned.vol.replace(0,np.nan),
        }.items():x['cross_'+label+'_'+name]=value;groups['cross_'+label+'_'+name]='cross_asset'
    if peer_momentum:
        peers=pd.concat(peer_momentum,axis=1)
        x['peer_risk_breadth']=peers.gt(0).where(peers.notna()).mean(axis=1).where(peers.notna().sum(axis=1)>=2)
        groups['peer_risk_breadth']='regime'
    # Initial releases are an explicitly reconstructed public vintage history.
    # We never use the latest-vintage macro snapshots as historical predictors.
    for series in MACRO:
        records=db.records('macro_initial',series,limit=1)
        if not records:continue
        rows=[]
        for o in records[0]['payload']['observations']:
            try:
                value=float(o['value']);release=pd.Timestamp(o['realtime_start'])
                if not np.isfinite(value) or release.date()<pd.Timestamp(o['date']).date():continue
                at=(release+pd.Timedelta(days=1)).tz_localize('America/New_York').tz_convert('UTC')
                rows.append({'time':at,'value':value,'observation':o['date']})
            except (ValueError,KeyError,TypeError):continue
        if not rows:continue
        # At each release, choose the most recent economic observation; late old releases cannot replace it.
        rows.sort(key=lambda r:(r['time'],r['observation']));latest='';filtered=[]
        for row in rows:
            if row['observation']>=latest:filtered.append(row);latest=row['observation']
        aligned=backward(times,filtered,'100 days')
        name='macro_'+series;x[name]=aligned.value;groups[name]='macro'
        x[name+'_change20']=aligned.value.diff(20);groups[name+'_change20']='macro'
    ext=join_features_asof(times,db.records('feature',symbol))
    for name in ext:
        if name not in x:x[name]=ext[name];groups[name]=family(name)
    from backend.research.filings import historical_features
    historical=historical_features(db,symbol,times)
    for name in historical:
        if historical[name].notna().any():x[name]=historical[name];groups[name]='sec'
    # Observed funding history is usable from observation time onward, never before download.
    base=symbol.split('-')[0]
    if symbol.endswith('-USD'):
        archived=db.records('funding_history',base,limit=1)
        if archived:
            funding_rows=[{'time':pd.Timestamp(r['time'],unit='ms',tz='UTC')+pd.Timedelta(hours=1),'funding_paid':float(r['fundingRate']),'funding_premium':float(r['premium'])} for r in archived[0]['payload']['rows']]
            if funding_rows:
                aligned=backward(times,funding_rows,'2 hours')
                for field in ('funding_paid','funding_premium'):x['crypto_'+field]=aligned[field];groups['crypto_'+field]='crypto_structure'
        rows=[]
        for r in db.records('crypto',base):
            p=r['payload']
            if p.get('provider')!='hyperliquid':continue
            rows.append({'time':max(pd.Timestamp(r['available_at']),pd.Timestamp(p['observed_at'])),
                         'funding':p.get('funding'),'open_interest':p.get('open_interest'),
                         'basis':p.get('mark_price',0)/p.get('oracle_price',1)-1 if p.get('oracle_price') else None})
        if rows:
            aligned=backward(times,rows,'2 days')
            for field in ['funding','open_interest','basis']:x['crypto_'+field]=aligned[field];groups['crypto_'+field]='crypto_structure'
    for name in SOURCES:
        if name not in groups.values():coverage_notes[name]='No defensible aligned numerical history collected or no explicit asset mapping'
    coverage_notes['energy']='EIA history lacks verified publication vintages; energy/utility mappings are research candidates only'
    coverage_notes['sec']='Historical Form 4 only within fully retrieved public-time windows, with 60-day warmup/amendment exclusion; no guessed 13F CUSIP mapping.'
    x=x.replace([np.inf,-np.inf],np.nan).astype(float)
    return df,x,groups,coverage_notes

def select_features(x,groups,indices,allowed):
    """All coverage, median and redundancy choices fit strictly on training rows."""
    chosen=[];excluded={};medians={};train=x.iloc[indices]
    for name in x:
        if groups[name] not in allowed:excluded[name]='Family not included in this ablation';continue
        if train[name].notna().mean()<.8:excluded[name]='Less than 80% training coverage';continue
        if train[name].nunique()<2:excluded[name]='Constant in training';continue
        if chosen and train[chosen].corrwith(train[name]).abs().fillna(0).max()>.98:
            excluded[name]='More than 98% correlated with an earlier training feature';continue
        chosen.append(name);medians[name]=float(train[name].median())
    if not chosen:raise ValueError('No features meet training-only coverage requirements')
    return chosen,medians,excluded

def stable_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
