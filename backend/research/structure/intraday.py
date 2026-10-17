"""Bounded completed-bar research, explicit calendars and sampled microstructure."""
from datetime import timedelta
from typing import Literal
import math
import numpy as np
import pandas as pd
from pydantic import Field,AwareDatetime,model_validator
from backend.schemas.contracts import Contract,now
from backend.research.features import stable_hash
class Session(Contract):
    open:AwareDatetime
    close:AwareDatetime
    label:str
    segment:Literal['regular','overnight']='regular'
    @model_validator(mode='after')
    def ordered(self):
        if self.close<=self.open:raise ValueError('Invalid session interval')
        return self


class Bar(Contract):
    timestamp:AwareDatetime
    available_at:AwareDatetime
    open:float=Field(gt=0)
    high:float=Field(gt=0)
    low:float=Field(gt=0)
    close:float=Field(gt=0)
    volume:float=Field(ge=0)
    vwap:float|None=Field(default=None,gt=0)
    trades:int|None=Field(default=None,ge=0)
    @model_validator(mode='after')
    def valid(self):
        if self.low>min(self.open,self.close) or self.high<max(self.open,self.close) or self.low>self.high:raise ValueError('Invalid OHLC')
        return self
class Bars(Contract):
    symbol:str=Field(pattern=r'^[A-Z0-9.-]{1,30}$')
    asset_class:Literal['stock','etf','crypto']
    provider:str
    feed:str
    interval_seconds:Literal[60,300,900,3600]
    rows:list[Bar]=Field(min_length=1,max_length=50000)
    adjustment:Literal['raw']='raw'
    availability_policy:str='Completed interval plus publication delay; retrospective provider vintage'
    @model_validator(mode='after')
    def completed(self):
        seen=set()
        for r in self.rows:
            if r.timestamp in seen or r.available_at<r.timestamp+timedelta(seconds=self.interval_seconds) or r.available_at>now():raise ValueError('Duplicate, incomplete or future bar')
            seen.add(r.timestamp)
        if max(r.timestamp for r in self.rows)-min(r.timestamp for r in self.rows)>timedelta(days=31):raise ValueError('Intraday import exceeds 31 days')
        return self

def derive(bars:Bars,sessions):
    rows=sorted(bars.rows,key=lambda b:b.timestamp);parsed=[Session.model_validate(s) for s in sessions];groups={};outside=0
    for b in rows:
        if bars.asset_class=='crypto':key=b.timestamp.date().isoformat();opened=pd.Timestamp(key,tz='UTC');segment='24/7'
        else:
            s=next((s for s in parsed if s.open<=b.timestamp and b.timestamp+timedelta(seconds=bars.interval_seconds)<=s.close),None)
            if not s:outside+=1;continue
            key=s.label;opened=s.open;segment=s.segment
        groups.setdefault(key,[]).append((b,int((b.timestamp-opened).total_seconds()//60),segment))
    history={};out=[];previous=None
    for label,items in sorted(groups.items()):
        first=items[0][0];last=items[-1][0];vol=sum(b.volume for b,_,_ in items);vwap=sum(b.vwap*b.volume for b,_,_ in items)/vol if vol and all(b.vwap for b,_,_ in items) else None
        expected=[]
        if previous and bars.asset_class!='crypto':
            prior_session=next((s for s in parsed if s.open<=previous.timestamp<s.close),None);current_session=next((s for s in parsed if s.label==label),None)
            if not prior_session or not current_session or any(prior_session.close<s.close<current_session.open for s in parsed):previous=None
        for b,minute,_ in items:
            h=history.get(minute,[])
            if len(h)>=5:expected.append(sum(h[-20:])/len(h[-20:]))
        complete_open=items[0][1]==0;opening=[b for b,m,_ in items if m<30];opening_complete=complete_open and len(opening)*bars.interval_seconds==1800
        c=np.array([b.close for b,_,_ in items]);returns=np.diff(np.log(c));gap=first.open/previous.close-1 if previous and complete_open else None
        out.append({'session':label,'available_at':last.available_at.isoformat(),'bars':len(items),'segment':items[0][2],'intraday_momentum':last.close/first.open-1,'previous_close_to_open':gap,'open_to_close':last.close/first.open-1 if complete_open else None,'overnight_return':gap if bars.asset_class!='crypto' else None,'opening_range_high':max(b.high for b in opening) if opening_complete else None,'opening_range_low':min(b.low for b in opening) if opening_complete else None,'vwap_distance':last.close/vwap-1 if vwap else None,'realized_intraday_volatility':float(np.sqrt(np.sum(returns**2))) if len(returns)>1 else None,'relative_time_of_day_volume':vol/sum(expected) if len(expected)==len(items) and sum(expected)>0 else None,'high_low_location':(last.close-min(b.low for b,_,_ in items))/(max(b.high for b,_,_ in items)-min(b.low for b,_,_ in items)) if max(b.high for b,_,_ in items)>min(b.low for b,_,_ in items) else None,'gap_basis':'Previous observed session close; missing sessions/open/close prevent a verified overnight label','volume_scope':bars.feed,'historical_status':'Historical bar diagnostics; not a validated trading strategy'})
        # Only a verified closing bar can be the next session's previous close.
        session=next((s for s in parsed if s.label==label),None)
        previous=last if bars.asset_class=='crypto' or session and last.timestamp+timedelta(seconds=bars.interval_seconds)==session.close else None
        for b,m,_ in items:history.setdefault(m,[]).append(b.volume)
    return {'symbol':bars.symbol,'interval_seconds':bars.interval_seconds,'sessions':out,'out_of_session_bars':outside,'gaps_filled':False,'calendar':'24/7 UTC' if bars.asset_class=='crypto' else 'Explicit dated exchange sessions; no weekday approximation','source':bars.provider,'feed':bars.feed}

def microstructure(quotes,books=(),trades=(),at=None):
    at=pd.Timestamp(at or now());qs=[]
    for q in quotes:
        try:
            t=pd.Timestamp(q['timestamp']);bid=float(q['bid']);ask=float(q['ask'])
            if not math.isfinite(bid+ask) or not 0<bid<=ask or t>at:continue
            qs.append({**q,'t':t,'mid':(bid+ask)/2,'spread':(ask-bid)/((bid+ask)/2)})
        except (ValueError,KeyError,TypeError):continue
    qs=sorted({q['t']:q for q in qs}.values(),key=lambda q:q['t']);latest=qs[-1] if qs else None;depth=None;imbalance=None;impact=None;book_at=None
    valid=[b for b in books if pd.Timestamp(b['timestamp'])<=at]
    if valid:
        book=max(valid,key=lambda b:b['timestamp']);bids=book.get('bids',[]);asks=book.get('asks',[])
        if bids and asks and max(p for p,v in bids)<min(p for p,v in asks) and all(math.isfinite(p+v) and p>0 and v>=0 for p,v in bids+asks):
            b=sum(p*v for p,v in bids);a=sum(p*v for p,v in asks);depth={'bid_notional':b,'ask_notional':a,'levels':min(len(bids),len(asks))};imbalance=(b-a)/(b+a) if b+a else None;book_at=book['timestamp'];target=1000;remaining=target;qty=0;spent=0
            for price,size in sorted(asks):
                take=min(remaining,price*size);spent+=take;qty+=take/price;remaining-=take
            impact=spent/qty/min(p for p,v in asks)-1 if remaining<1e-8 and qty else None
    duration=(qs[-1]['t']-qs[0]['t']).total_seconds() if len(qs)>1 else 0
    ts={str(t.get('trade_id',stable_hash(t))):t for t in trades if t.get('timestamp') and (not qs or qs[0]['t']<=pd.Timestamp(t['timestamp'])<=at)}
    return {'status':'AVAILABLE' if latest else 'UNAVAILABLE','spread_bps':latest['spread']*10000 if latest else None,'quote_staleness_seconds':(at-latest['t']).total_seconds() if latest else None,'sampled_quote_updates_per_second':(len(qs)-1)/duration if duration else None,'sampled_trade_count':len(ts),'sampled_trades_per_second':len(ts)/duration if duration and ts else None,'depth':depth,'notional_imbalance':imbalance,'buy_1000_depth_impact_proxy':impact,'book_at':book_at,'book_staleness_seconds':(at-pd.Timestamp(book_at)).total_seconds() if book_at else None,'scope':'FORWARD COLLECTED ONLY — sampled quotes/books; not complete order-book or trade-event history','price_impact_scope':'Displayed-depth walk only; no queue, cancellation or hidden-liquidity model'}
