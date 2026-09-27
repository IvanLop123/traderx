"""Local numerical finance. This module has no access to LLM providers."""
import math
import json
from scripts.provider_common import ROOT
RESEARCH=json.loads((ROOT/'config/research.json').read_text())
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq

def features(bars):
    df=pd.DataFrame(bars).sort_values('timestamp').drop_duplicates('timestamp',keep='last').reset_index(drop=True)
    c=df.close; v=df.volume; r=c.pct_change()
    result=pd.DataFrame(index=df.index)
    for n in [1,5,20,60,252]: result[f'return_{n}']=c.pct_change(n)
    annual=365 if 'symbol' in df and '-' in str(df.iloc[0].symbol) else 252
    result['realized_volatility']=r.rolling(20).std()*np.sqrt(annual)
    result['volume_zscore']=(v-v.rolling(20).mean())/v.rolling(20).std().replace(0,np.nan)
    result['relative_volume']=v/v.rolling(20).mean().replace(0,np.nan)
    result['vwap']=((df.high+df.low+c)/3*v).rolling(20).sum()/v.rolling(20).sum().replace(0,np.nan)
    result['vwap_distance']=c/result.vwap-1
    result['atr']=pd.concat([df.high-df.low,(df.high-c.shift()).abs(),(df.low-c.shift()).abs()],axis=1).max(axis=1).rolling(14).mean()
    result['gap_return']=df.open/c.shift()-1
    result['intraday_return']=c/df.open-1
    result['drawdown']=c/c.cummax()-1
    result['range_location']=(c-df.low.rolling(252,min_periods=20).min())/(df.high.rolling(252,min_periods=20).max()-df.low.rolling(252,min_periods=20).min()).replace(0,np.nan)
    delta=c.diff(); gain=delta.clip(lower=0).rolling(14).mean(); loss=-delta.clip(upper=0).rolling(14).mean()
    result['rsi']=100-100/(1+gain/loss.replace(0,np.nan))
    result.loc[(loss==0)&(gain>0),'rsi']=100
    result.loc[(loss==0)&(gain==0),'rsi']=50
    result['macd']=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    result['bollinger_z']=(c-c.rolling(20).mean())/c.rolling(20).std().replace(0,np.nan)
    result['acceleration']=result.return_5-result.return_5.shift(5)
    result['timestamp']=df.timestamp
    return result.replace([np.inf,-np.inf],np.nan)

def latest_features(bars):
    if len(bars)<21: return {'status':'INSUFFICIENT_HISTORY','bars':len(bars)}
    row=features(bars).iloc[-1]
    values={k:float(v) for k,v in row.items() if k!='timestamp' and pd.notna(v)}
    return {'status':'AVAILABLE','as_of':row['timestamp'],'values':values,'regime':regime(values),'method':'deterministic-v1'}

def regime(values):
    return {'trend':'uptrend' if values.get('return_20',0)>RESEARCH['trend_return_threshold'] else 'downtrend' if values.get('return_20',0)<-RESEARCH['trend_return_threshold'] else 'range',
            'volatility':'high' if values.get('realized_volatility',0)>RESEARCH['high_volatility_threshold'] else 'low',
            'scope':'Price and volatility only; macro regime unavailable until macro inputs exist'}

def black_scholes(spot,strike,years,rate,volatility,kind='call',dividend=0):
    if min(spot,strike,years,volatility)<=0: raise ValueError('Positive spot, strike, time and volatility required')
    d1=(math.log(spot/strike)+(rate-dividend+volatility**2/2)*years)/(volatility*math.sqrt(years)); d2=d1-volatility*math.sqrt(years)
    sign=1 if kind=='call' else -1
    discounted=math.exp(-dividend*years); discount=math.exp(-rate*years)
    price=sign*(spot*discounted*norm.cdf(sign*d1)-strike*discount*norm.cdf(sign*d2))
    theta=(-spot*discounted*norm.pdf(d1)*volatility/(2*math.sqrt(years))-sign*rate*strike*discount*norm.cdf(sign*d2)+sign*dividend*spot*discounted*norm.cdf(sign*d1))/365
    return {'price':float(price),'delta':float(sign*discounted*norm.cdf(sign*d1)),
            'gamma':float(discounted*norm.pdf(d1)/(spot*volatility*math.sqrt(years))),
            'vega':float(spot*discounted*norm.pdf(d1)*math.sqrt(years)/100),'theta':float(theta),
            'rho':float(sign*strike*years*discount*norm.cdf(sign*d2)/100),'assumption':'European exercise, constant volatility; not an executable quote'}

def implied_vol(price,spot,strike,years,rate,kind='call'):
    return brentq(lambda vol:black_scholes(spot,strike,years,rate,vol,kind)['price']-price,0.00001,5)

def parity(spot_bid,spot_ask,call_bid,call_ask,put_bid,put_ask,strike,years,rate,costs=0,dividend=0,american=False):
    bond=strike*math.exp(-rate*years); carry=math.exp(-dividend*years)
    theoretical=(call_bid+call_ask-put_bid-put_ask)/2-((spot_bid+spot_ask)/2*carry-bond)
    sell_synthetic=call_bid-put_ask-spot_ask*carry+bond-costs
    buy_synthetic=spot_bid*carry-bond-call_ask+put_bid-costs
    return {'theoretical_deviation':theoretical,'executable_upper_bound':max(sell_synthetic,buy_synthetic),
            'implied_forward':strike+((call_bid+call_ask-put_bid-put_ask)/2)*math.exp(rate*years),
            'warning':'Not certified arbitrage: verify borrow, dividends, synchronized quotes and execution'+('; American early exercise invalidates simple equality' if american else '')}

def trader_metrics(trades,latency_bps=5,fee_bps=5,slippage_bps=5):
    pnl=np.array([float(t.get('pnl',t.get('closedPnl',0))) for t in trades]); n=len(pnl)
    if not n:return {'status':'NO_TRADES'}
    wins=pnl[pnl>0]; losses=pnl[pnl<0]
    notionals=np.array([abs(float(t.get('notional',float(t.get('px',0))*float(t.get('sz',0))))) for t in trades])
    copy_pnl=pnl-notionals*(latency_bps+fee_bps+slippage_bps)/1e4
    cumulative=np.r_[0,np.cumsum(pnl)]; drawdown=cumulative-np.maximum.accumulate(cumulative)
    return {'trade_count':n,'realized_pnl':float(pnl.sum()),'win_rate':float((pnl>0).mean()),'expectancy':float(pnl.mean()),
            'profit_factor':float(wins.sum()/-losses.sum()) if len(losses) else None,'max_drawdown_dollars':float(drawdown.min()),
            'largest_win_share':float(wins.max()/wins.sum()) if len(wins) else None,'copy_pnl_after_costs':float(copy_pnl.sum()),
            'copyability_score':float(np.clip(copy_pnl.sum()/pnl.sum(),0,1)) if pnl.sum()>0 else 0,
            'warnings':['Partial public fill history; not account returns.','Tiny sample' if n<30 else 'Survivorship bias not resolved',
                        'Copyability is a cost sensitivity estimate, not measured latency replay.']}

def social_metrics(posts):
    n=len(posts)
    if not n:return {'status':'NO_POSTS'}
    authors=pd.Series([p.get('author_id','unknown') for p in posts]).value_counts(normalize=True)
    text=[p.get('text','').lower() for p in posts]
    bullish=sum(any(w in t.split() for w in ('bullish','buy','growth')) for t in text)
    bearish=sum(any(w in t.split() for w in ('bearish','sell','decline')) for t in text)
    return {'mentions':n,'unique_authors':len(authors),'author_concentration':float((authors**2).sum()),
            'bullish_keyword_fraction':bullish/n,'bearish_keyword_fraction':bearish/n,
            'lexical_disagreement':2*min(bullish,bearish)/n,'engagement':sum(sum(p.get('public_metrics',{}).values()) for p in posts),
            'warning':'Lexical counts, not semantic inference or a bot verdict.'}
