"""Causal, bounded event replay with explicit liquidity and instrument lifecycle.

Research ledger only: it has no execution-provider imports or external side effects.
"""
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime,timedelta
from typing import Literal
from pydantic import Field, AwareDatetime, model_validator
from backend.schemas.contracts import Contract
from backend.research.engine import ordered_bars,performance

class ReplayInstrument(Contract):
    symbol:str=Field(min_length=1,max_length=128)
    asset_class:Literal['stock','etf','crypto','option','perpetual','prediction']
    multiplier:float=Field(default=1,gt=0,le=100000)
    eligible_from:AwareDatetime
    eligible_until:AwareDatetime|None=None
    expiry:AwareDatetime|None=None
    underlying:str|None=None
    strike:float|None=Field(default=None,gt=0)
    option_type:Literal['call','put']|None=None
    settlement:Literal['cash','physical']='cash'
    @model_validator(mode='after')
    def terms(self):
        if self.asset_class in ('stock','etf','crypto') and self.multiplier!=1:raise ValueError('Cash instruments require unit multiplier')
        if self.eligible_until and self.eligible_until<=self.eligible_from:raise ValueError('Universe membership interval is invalid')
        if self.asset_class=='option' and (not self.expiry or not self.underlying or self.strike is None or not self.option_type):raise ValueError('Explicit option terms are required')
        if self.asset_class=='prediction' and not self.expiry:raise ValueError('Prediction contract resolution time required')
        if self.asset_class!='option' and self.settlement=='physical':raise ValueError('Physical exercise applies to options only')
        return self

class ReplayEvent(Contract):
    id:str=Field(min_length=1,max_length=128)
    symbol:str
    kind:Literal['quote','split','dividend','funding','borrow','settlement','exercise']
    event_at:AwareDatetime
    available_at:AwareDatetime
    source_reference:str=Field(min_length=1,max_length=1000)
    bid:float|None=Field(default=None,gt=0)
    ask:float|None=Field(default=None,gt=0)
    volume:float=Field(default=0,ge=0)
    value:float|None=None
    @model_validator(mode='after')
    def valid(self):
        if self.available_at<self.event_at:raise ValueError('Event cannot be known before it occurs')
        if self.kind=='quote' and (self.bid is None or self.ask is None or self.bid>self.ask):raise ValueError('A valid two-sided quote is required')
        if self.kind!='quote' and self.value is None:raise ValueError('Lifecycle amount or ratio required')
        if self.kind=='split' and self.value<=0:raise ValueError('Positive split ratio required')
        if self.kind in ('dividend','borrow','settlement','exercise') and self.value<0:raise ValueError('Negative lifecycle value')
        return self

class ReplayIntent(Contract):
    id:str=Field(min_length=1,max_length=128)
    symbol:str
    side:Literal['buy','sell']
    quantity:float=Field(gt=0)
    limit_price:float=Field(gt=0)
    decided_at:AwareDatetime
    evidence_available_at:AwareDatetime
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def causal(self):
        if self.evidence_available_at>self.decided_at:raise ValueError('Intent contains future evidence')
        if self.expires_at<=self.decided_at:raise ValueError('Intent already expired')
        return self

class ReplayRequest(Contract):
    instruments:list[ReplayInstrument]=Field(min_length=1,max_length=50)
    events:list[ReplayEvent]=Field(min_length=1,max_length=20000)
    intents:list[ReplayIntent]=Field(default_factory=list,max_length=5000)
    initial_cash:float=Field(default=100000,gt=0)
    fee_bps:float=Field(default=5,ge=0,le=1000)
    slippage_bps:float=Field(default=5,ge=0,le=1000)
    participation:float=Field(default=.01,gt=0,le=.1)
    latency_seconds:float=Field(default=1,gt=0,le=86400)
    max_quote_delay_seconds:float=Field(default=300,ge=0,le=86400)
    max_position_fraction:float=Field(default=.1,gt=0,le=1)
    max_gross_fraction:float=Field(default=.5,gt=0,le=1)
    corporate_action_policy:Literal['supplied_events','reviewed_no_actions']='supplied_events'

class EventReplay:
    def __init__(self,request):
        self.r=request;self.instruments={i.symbol:i for i in request.instruments}
        if len(self.instruments)!=len(request.instruments):raise ValueError('Duplicate instrument')
        self.cash=request.initial_cash;self.positions={};self.quotes={};self.pending=[];self.orders={};self.fills=[];self.ledger=[];self.curve=[];self.settled=set();self.seen_events=set();self.halted=False
        self.cost=0.;self.last_event={}
    def equity(self):
        return self.cash+sum(p['quantity']*self.instruments[s].multiplier*p['mark'] for s,p in self.positions.items())
    def active(self,instrument,t):return instrument.eligible_from<=t and (not instrument.eligible_until or t<instrument.eligible_until) and (not instrument.expiry or t<instrument.expiry)
    def intent(self,intent):
        if intent.id in self.orders:raise ValueError('Duplicate intent ID')
        if intent.symbol not in self.instruments:raise ValueError('Unknown instrument')
        o={**intent.model_dump(mode='json'),'remaining':intent.quantity,'filled':0.,'status':'pending'};self.orders[intent.id]=o
        if not self.active(self.instruments[intent.symbol],intent.decided_at):o['status']='rejected_universe_or_expiry'
        else:self.pending.append((intent,o))
    def record(self,event,action,amount,**extra):
        self.ledger.append({'event_id':event.id,'timestamp':event.available_at.isoformat(),'symbol':event.symbol,'action':action,'cash_change':amount,'source_reference':event.source_reference,**extra})
    def market(self,event):
        i=self.instruments[event.symbol]
        # Late historical packets do not provide executable current liquidity.
        if (event.available_at-event.event_at).total_seconds()>self.r.max_quote_delay_seconds:return
        if event.event_at<=self.last_event.get(event.symbol,datetime.min.replace(tzinfo=event.event_at.tzinfo)):return
        if event.symbol in self.settled:return
        self.last_event[event.symbol]=event.event_at;self.quotes[event.symbol]=event
        mid=(event.bid+event.ask)/2
        if event.symbol in self.positions:self.positions[event.symbol]['mark']=mid
        liquidity=event.volume*self.r.participation
        for intent,o in self.pending:
            if o['remaining']<=0 or o['status'] not in ('pending','partially_filled') or intent.symbol!=event.symbol:continue
            if event.available_at>=intent.expires_at:o['status']='expired';continue
            if not self.active(i,event.available_at):o['status']='canceled_universe_or_expiry';continue
            ready=intent.decided_at+timedelta(seconds=self.r.latency_seconds)
            if event.event_at<ready or event.available_at<ready:continue
            side=1 if intent.side=='buy' else -1;price=(event.ask if side==1 else event.bid)*(1+side*self.r.slippage_bps/10000)
            if (side==1 and price>float(o['limit_price'])) or (side==-1 and price<float(o['limit_price'])):continue
            held=self.positions.get(i.symbol,{}).get('quantity',0);quantity=min(o['remaining'],liquidity)
            if side==1:
                if self.halted:continue
                equity=self.equity();gross=sum(p['quantity']*self.instruments[s].multiplier*p['mark'] for s,p in self.positions.items())
                # Full cash collateral, including perpetuals. No margin borrowing.
                quantity=min(quantity,max(0,self.cash)/(price*i.multiplier*(1+self.r.fee_bps/10000)),max(0,equity*self.r.max_position_fraction/(price*i.multiplier)-held),max(0,equity*self.r.max_gross_fraction-gross)/(price*i.multiplier))
            else:quantity=min(quantity,held)
            if i.asset_class in ('stock','etf','option','prediction'):quantity=math.floor(quantity+1e-10)
            if quantity<=1e-10:continue
            notional=quantity*price*i.multiplier;fee=notional*self.r.fee_bps/10000
            cash_change=-side*notional-fee;self.cash+=cash_change;self.cost+=fee+quantity*i.multiplier*abs(price-mid)
            p=self.positions.setdefault(i.symbol,{'quantity':0.,'mark':mid,'average_cost':0.})
            if side==1:p['average_cost']=(p['quantity']*p['average_cost']+quantity*price)/(p['quantity']+quantity)
            p['quantity']+=side*quantity;p['mark']=mid
            if abs(p['quantity'])<1e-10:self.positions.pop(i.symbol)
            liquidity-=quantity;o['remaining']-=quantity;o['filled']+=quantity;o['status']='filled' if o['remaining']<1e-10 else 'partially_filled'
            fill={'order_id':intent.id,'event_id':event.id,'symbol':i.symbol,'side':intent.side,'quantity':quantity,'price':price,'fee':fee,'decided_at':intent.decided_at.isoformat(),'timestamp':event.available_at.isoformat()}
            self.fills.append(fill);self.record(event,'fill',cash_change,order_id=intent.id,quantity=quantity,price=price)
    def lifecycle(self,e):
        i=self.instruments[e.symbol];p=self.positions.get(e.symbol);qty=p['quantity'] if p else 0;amount=0.
        # Accounting corrections cannot retroactively change fills or eligible holdings.
        if e.available_at!=e.event_at:raise ValueError('Lifecycle replay requires events available at their effective time')
        if e.kind=='split':
            if i.asset_class not in ('stock','etf'):raise ValueError('Split applies only to equities')
            if p:p['quantity']*=e.value;p['mark']/=e.value;p['average_cost']/=e.value
            for intent,o in self.pending:
                if intent.symbol==e.symbol and o['status'] in ('pending','partially_filled'):
                    o['remaining']*=e.value;o['quantity']*=e.value;o['filled']*=e.value;o['limit_price']/=e.value
        elif e.kind=='dividend':
            if i.asset_class not in ('stock','etf'):raise ValueError('Dividend applies only to equities')
            amount=qty*i.multiplier*e.value
        elif e.kind=='funding':
            if i.asset_class!='perpetual':raise ValueError('Funding applies only to perpetuals')
            if qty:
                if e.symbol not in self.quotes:raise ValueError('Funding requires a preceding mark')
                amount=-qty*i.multiplier*p['mark']*e.value
        elif e.kind=='borrow':
            # Explicit dollar charge, attached to an existing position. No inferred rates.
            if qty:amount=-e.value
        elif e.kind=='settlement':
            if i.asset_class!='prediction' or e.value>1:raise ValueError('Prediction settlement requires a payout in [0,1]')
            if e.event_at<i.expiry:raise ValueError('Settlement before resolution time')
            if e.symbol in self.settled:raise ValueError('Duplicate contract settlement')
            amount=qty*i.multiplier*e.value;self.positions.pop(e.symbol,None);self.settled.add(e.symbol)
        elif e.kind=='exercise':
            if i.asset_class!='option' or e.event_at<i.expiry:raise ValueError('Only explicit expiry exercise is supported')
            if e.symbol in self.settled:raise ValueError('Duplicate option exercise')
            intrinsic=max(0,e.value-i.strike) if i.option_type=='call' else max(0,i.strike-e.value)
            if i.settlement=='cash':amount=qty*i.multiplier*intrinsic
            elif qty and intrinsic>0:
                underlying=self.instruments.get(i.underlying)
                if underlying is None or underlying.asset_class not in ('stock','etf'):raise ValueError('Deliverable underlying required')
                units=qty*i.multiplier;under=self.positions.get(i.underlying)
                if i.option_type=='call':
                    amount=-units*i.strike
                    if self.cash+amount<0:raise ValueError('Physical exercise cannot be funded; supply a closing intent before expiry')
                    under=under or {'quantity':0.,'mark':e.value,'average_cost':0.}
                    under['average_cost']=(under['quantity']*under['average_cost']+units*i.strike)/(under['quantity']+units);under['quantity']+=units;under['mark']=e.value;self.positions[i.underlying]=under
                else:
                    if not under or under['quantity']<units:raise ValueError('Physical put exercise requires deliverable shares')
                    under['quantity']-=units;under['mark']=e.value;amount=units*i.strike
            self.positions.pop(e.symbol,None);self.settled.add(e.symbol)
        self.cash+=amount
        if self.cash<0:raise ValueError('Lifecycle charge exceeds free cash; explicit reduction or a supported margin policy is required')
        self.record(e,e.kind,amount,value=e.value)
    def event(self,e):
        if e.id in self.seen_events:raise ValueError('Duplicate event ID')
        if e.symbol not in self.instruments:raise ValueError('Unknown event instrument')
        self.seen_events.add(e.id)
        if e.kind=='quote':self.market(e)
        else:self.lifecycle(e)
        value=self.equity()
        if not math.isfinite(value) or value<=0:raise ValueError('Replay insolvent or invalid')
        if self.curve and self.curve[-1]['timestamp']==e.available_at.isoformat():self.curve[-1]['equity']=value
        else:self.curve.append({'timestamp':e.available_at.isoformat(),'equity':value})
    def run(self):
        # Lifecycle actions precede quotes; intents cannot fill on the same quote that caused them.
        timeline=[(e.available_at,0 if e.kind!='quote' else 1,e.id,e) for e in self.r.events]+[(o.decided_at,2,o.id,o) for o in self.r.intents]
        for _,_,_,item in sorted(timeline,key=lambda x:x[:3]):
            if isinstance(item,ReplayEvent):self.event(item)
            else:self.intent(item)
        end=max(e.available_at for e in self.r.events)
        for symbol,p in self.positions.items():
            if p['quantity'] and self.instruments[symbol].expiry and end>=self.instruments[symbol].expiry:raise ValueError('Expired position has no explicit exercise or settlement event')
        for _,o in self.pending:
            if o['status'] in ('pending','partially_filled') and datetime.fromisoformat(o['expires_at'])<=end:o['status']='expired'
        daily={}
        for row in self.curve:daily[row['timestamp'][:10]]=row['equity']
        annual=365 if all(i.asset_class in ('crypto','perpetual','prediction') for i in self.r.instruments) else 252
        return {'engine':'event_replay_v1','metrics':performance([self.r.initial_cash,*daily.values()],annual),'curve':self.curve,'fills':self.fills,'orders':list(self.orders.values()),'ledger':self.ledger,'positions':self.positions,'cash':self.cash,'total_cost':self.cost,'halted':self.halted,
                'dataset_hash':hashlib.sha256(self.r.model_dump_json().encode()).hexdigest(),'data_policy':'explicit_event_availability','corporate_action_policy':self.r.corporate_action_policy,
                'warnings':['Research ledger only. Long positions, full cash collateral; no leveraged liquidation or short option assignment.', 'Liquidity, slippage and latency are supplied assumptions, not calibrated market impact.','Corporate actions, membership dates and settlement values must be supplied from authorized point-in-time sources.','Open positions remain marked at the end; no cost-free terminal liquidation is invented.']}

class PortfolioReplayRequest(Contract):
    symbols:list[str]=Field(default_factory=lambda:['BTC-USD','ETH-USD','SOL-USD'],min_length=1,max_length=10)
    lookback:int=Field(default=20,ge=2,le=252)
    fee_bps:float=Field(default=5,ge=0,le=1000)
    slippage_bps:float=Field(default=5,ge=0,le=1000)
    spread_bps:float=Field(default=2,ge=0,le=1000)
    participation:float=Field(default=.01,gt=0,le=.1)
    strict_observed:bool=False
    equity_actions_reviewed:bool=False

def replay_portfolio(db,request):
    instruments=[];events=[];histories={}
    symbols=list(dict.fromkeys(request.symbols))
    for symbol in symbols:
        df=ordered_bars([r['payload'] for r in db.records('bar',symbol)])
        asset_class=str(df.iloc[0].get('asset_class','crypto' if '-' in symbol else 'stock'))
        if asset_class not in ('stock','etf','crypto'):raise ValueError('Daily momentum replay supports cash equities and spot crypto')
        if asset_class in ('stock','etf') and not request.equity_actions_reviewed:raise ValueError('Raw equity history requires corporate-action and universe review; use explicit events for splits/dividends')
        first=datetime.fromisoformat(str(df.iloc[0].available_at).replace('Z','+00:00'))
        instruments.append(ReplayInstrument(symbol=symbol,asset_class=asset_class,eligible_from=first));histories[symbol]=[]
        for idx,row in df.iterrows():
            t=datetime.fromisoformat(str(row.available_at).replace('Z','+00:00'));observed=datetime.fromisoformat(str(row.observed_at).replace('Z','+00:00'))
            # Strict mode excludes retrospective imports as executable historical snapshots.
            if request.strict_observed and observed>t+timedelta(minutes=5):continue
            mid=float(row.close);half=request.spread_bps/20000
            events.append(ReplayEvent(id=f'{symbol}-{idx}',symbol=symbol,kind='quote',event_at=t,available_at=t,bid=mid*(1-half),ask=mid*(1+half),volume=float(row.volume),source_reference='stored-daily-bar:'+symbol+':'+str(row.timestamp)))
    if not events:raise ValueError('No executable history under selected observation policy; collect forward observations or use retrospective research mode')
    r=ReplayRequest(instruments=instruments,events=events,fee_bps=request.fee_bps,slippage_bps=request.slippage_bps,participation=request.participation,corporate_action_policy='reviewed_no_actions')
    engine=EventReplay(r);generated=[]
    for e in sorted(events,key=lambda e:(e.available_at,e.symbol)):
        engine.event(e);prices=histories[e.symbol];prices.append((e.bid+e.ask)/2)
        if len(prices)<=request.lookback or len(prices)%5:continue
        if any(i.symbol==e.symbol and o['status'] in ('pending','partially_filled') for i,o in engine.pending):continue
        positive=prices[-1]>prices[-1-request.lookback];target=engine.equity()*min(.1,.5/len(symbols))/prices[-1] if positive else 0
        held=engine.positions.get(e.symbol,{}).get('quantity',0);delta=target-held
        if abs(delta)*prices[-1]<10:continue
        side='buy' if delta>0 else 'sell';quantity=abs(delta)
        if engine.instruments[e.symbol].asset_class in ('stock','etf'):quantity=math.floor(quantity)
        if quantity<=0:continue
        intent=ReplayIntent(id='momentum-'+e.id,symbol=e.symbol,side=side,quantity=quantity,limit_price=prices[-1]*(1.02 if side=='buy' else .98),decided_at=e.available_at,evidence_available_at=e.available_at,expires_at=e.available_at+timedelta(days=5))
        engine.intent(intent);generated.append(intent)
    # Replay the resulting causal intents from scratch to produce a reproducible artifact.
    r.intents=generated;result=EventReplay(r).run()
    result['input_record_id']=db.put('replay_input',r.model_dump(mode='json'))
    result['strategy']='multi_asset_lagged_momentum';result['parameters']=request.model_dump();result['symbols']=symbols
    result['data_policy']='strict_observed_daily_snapshots' if request.strict_observed else 'retrospective_daily_close_snapshots'
    result['warnings']+=['Daily close snapshots approximate executions at later closes. Daily volume is not actual queue liquidity.','This user-selected universe has survivorship bias. Missing assets are not silently replaced.','Signals use known closes; same-time cash contention uses stable symbol order. Equity action review is an assertion, not an automated corporate-action feed.']
    return result
