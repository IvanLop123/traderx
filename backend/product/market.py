"""Cached, deterministic product data. Scores are descriptions, never promotion."""
import time
import threading
import numpy as np
import pandas as pd
from backend.schemas.contracts import now
from backend.research.universe import load_universe,eligible_at
from backend.research.history import HistoryStore
from backend.research.features import market_frame,stable_hash

class ProductMarket:
    def __init__(self,db):self.db=db;self.cached=[];self.until=0;self.signature=None;self.lock=threading.RLock()
    def universe(self):
        with self.lock:return self._universe()
    def _universe(self):
        u=load_universe(self.db);signature=stable_hash(u.model_dump(mode='json'))
        if self.cached and time.monotonic()<self.until and self.signature==signature:return self.cached
        saved=self.db.setting('product_summary_cache',{})
        if saved.get('signature')==signature and time.time()-saved.get('at',0)<1800:
            self.cached=saved['rows'];self.until=time.monotonic()+300;self.signature=signature;return self.cached
        store=HistoryStore(self.db);rows=[];calendar=self.db.setting('research_calendar',{}).get('sessions',[])
        for i in u.instruments:
            try:
                raw=store.read(i.symbol,'raw');bars=store.read(i.symbol);d,x,_=market_frame(bars[-300:]) if len(bars)>65 else (None,None,None)
                expected=[v['date'] for v in calendar] if i.asset_class!='crypto' else pd.date_range(raw[0]['timestamp'],raw[-1]['timestamp'],freq='D').tolist() if raw else []
                e=eligible_at(i,raw,now(),u.filters_for(i),expected_sessions=expected)
                adv=e['mean_dollar_volume'];bucket='deep' if adv and adv>=100e6 else 'liquid' if adv and adv>=20e6 else 'limited'
                latest=x.iloc[-1] if x is not None else {};cap=i.market_cap;capbucket='unknown' if cap is None else 'mega' if cap>=200e9 else 'large' if cap>=10e9 else 'mid' if cap>=2e9 else 'small'
                rows.append({'symbol':i.symbol,'name':i.name or i.symbol,'asset_class':i.asset_class,'sector':i.sector or 'unclassified','market_cap_bucket':capbucket,'market_cap_known_at':str(i.market_cap_known_at) if i.market_cap_known_at else None,'liquidity_bucket':bucket,'eligibility':e,'price':raw[-1]['close'] if raw else None,'price_at':raw[-1]['timestamp'] if raw else None,'price_kind':'completed daily close','daily_move':float(d.close.pct_change().iloc[-1]) if d is not None else None,'volume':raw[-1]['volume'] if raw else None,'momentum':float(latest.get('return_20',0)),'regime':{1:'uptrend',-1:'downtrend',0:'range'}.get(int(latest.get('regime_trend',0))),'score':None,'model_prediction':None,'probability':None,'uncertainty':None,'strategy_family':'momentum','direction':'up' if latest.get('return_20',0)>0 else 'down','warnings':e['reasons']+(['Market capitalization history unavailable'] if cap is None else [])})
            except (ValueError,KeyError,IndexError):
                rows.append({'symbol':i.symbol,'name':i.name or i.symbol,'asset_class':i.asset_class,'eligibility':{'eligible':False,'reasons':['Historical data unavailable']},'warnings':['Historical data unavailable'],'liquidity_bucket':'unknown','market_cap_bucket':'unknown','regime':'unknown','score':None,'strategy_family':'unavailable'})
        eligible=[r for r in rows if r['eligibility']['eligible']]
        for r in eligible:r['score']=round(100*sum(v['momentum']<=r['momentum'] for v in eligible)/max(1,len(eligible)),1)
        models={}
        for record in self.db.records('ml_study',limit=1000):models.setdefault(record['symbol'],record['payload'])
        # Frozen study forecasts are identified as historical; they are not live calibrated promises.
        for r in rows:
            m=models.get(r['symbol']);r['model_status']='Research only; no promoted model'
            if m:r['model_version']=m.get('id');r['historical_model_summary']=m.get('latest');r['model_family']=m.get('selected',{}).get('algorithm')
        self.cached=rows;self.until=time.monotonic()+300;self.signature=signature;self.db.set_setting('product_summary_cache',{'signature':signature,'at':time.time(),'rows':rows});return rows
    def forecasts(self):
        by_symbol={}
        at=pd.Timestamp(now())
        for row in self.db.records('research_forecast',limit=3000):
            forecast=row['payload']
            if at-pd.Timedelta(days=4)<=pd.Timestamp(forecast['feature_available_at'])<=at:by_symbol.setdefault(row['symbol'],forecast)
        result=[]
        for original in self.universe():
            r=dict(original);forecast=by_symbol.get(r['symbol'])
            if forecast:
                r.update({k:forecast[k] for k in ['model_prediction','probability','uncertainty','strategy_family','model_id','feature_available_at','horizon']});r['forecast_status']=forecast['status'];r['model_direction']='positive after costs' if forecast['model_prediction']>0 else 'cash / nonpositive after costs'
            else:r['forecast_status']='Current forecast unavailable';r['model_direction']='unavailable'
            filing=self.db.setting('form4_coverage_'+r['symbol'],{})
            r['evidence_change']='Form 4 history available through '+filing.get('end','')[:10] if filing.get('downloaded') else 'No verified recent event change'
            result.append(r)
        return result
    def lookup(self,symbol):
        normalized=symbol.upper();normalized=normalized+'-USD' if normalized in ('BTC','ETH','SOL') else normalized
        row=next((r for r in self.universe() if r['symbol']==normalized),None)
        if not row:raise ValueError('Asset is not in the configured research universe')
        return row
    def asset(self,symbol):
        r=dict(self.lookup(symbol));symbol=r['symbol'];r=next(v for v in self.forecasts() if v['symbol']==symbol);bars=HistoryStore(self.db).read(symbol)
        r['bars']=bars[-252:];r['chart_basis']='Provider adjusted daily history' if r['asset_class']!='crypto' else 'Completed daily history'
        r['filings']=self.db.setting('form4_coverage_'+symbol,{})
        r['evidence']=[{'at':v['payload']['published_at'],'kind':'Insider filing','label':v['payload']['form']+' · '+v['payload']['accession']} for v in sorted(self.db.records('historical_form4',symbol,limit=10000),key=lambda v:v['payload']['published_at'],reverse=True)[:5]]
        r['macro']=[{'series':s,'status':'First-release history available' if self.db.records('macro_initial',s,limit=1) else 'Unavailable'} for s in ['FEDFUNDS','UNRATE','T10Y2Y']]
        r['warnings']=[*r.get('warnings',[]),'Score ranks trailing momentum; it is not a forecast or probability.','No model is promoted. Manual decisions do not enter model evaluation.']
        return r
