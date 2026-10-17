"""Personal local simulator. Never imports a brokerage execution adapter.

Manual account records use distinct kinds and are never model training inputs.
The forward engine's quote validation is shared; books and accounting are not.
"""
import json,math
from datetime import timedelta
from typing import Literal
import pandas as pd
from pydantic import Field,model_validator
from sqlalchemy import select
from backend.schemas.contracts import Contract,now,uid
from backend.storage.database import Setting,Record
from backend.research.forward import ForwardPolicy,quote_check
from backend.research.features import stable_hash
from backend.research.universe import load_universe

OPEN={'OPEN','PARTIALLY_FILLED'}
def coin_floor(value):
    # Remove sub-micro-unit floating noise before flooring to eight decimal places.
    # This tolerance is far smaller than one permitted coin increment.
    return math.floor(round(value*1e8,6))/1e8
class Ticket(Contract):
    symbol:str=Field(pattern=r'^[A-Z0-9.-]{1,40}$')
    side:Literal['buy','sell']
    order_type:Literal['market','limit']='market'
    quantity:float|None=Field(default=None,gt=0,le=1e8)
    amount:float|None=Field(default=None,gt=0,le=1e7)
    limit_price:float|None=Field(default=None,gt=0,le=1e8)
    @model_validator(mode='after')
    def valid(self):
        if (self.quantity is None)==(self.amount is None):raise ValueError('Choose dollars or quantity')
        if self.order_type=='limit' and self.limit_price is None:raise ValueError('Enter a limit price')
        return self
class Confirm(Contract):
    preview_id:str
    confirmation:Literal['PLACE PAPER ORDER']
class Reset(Contract):
    starting_balance:float=Field(ge=100,le=10000000)
    confirmation:Literal['RESET MY PAPER ACCOUNT']
    account_id:str
class Watch(Contract):
    symbol:str
    saved:bool=True

def new_account(balance=10000):
    return {'id':uid(),'created_at':now().isoformat(),'initial_cash':balance,'cash':balance,'positions':{},'realized_pnl':0.,'fees':0.,'orders':{},'marks':{},'consumed':{},'daily_baseline':None,'applied_actions':[],'receivables':[],'review':{},'source':'manual_paper','execution':'local_simulation_only'}

def record(session,kind,payload,symbol='',rid=None):
    session.add(Record(id=rid or uid(),kind=kind,symbol=symbol,available_at=now().isoformat(),payload=payload))

class ManualPaper:
    account_key="manual_paper"
    record_prefix="manual"
    source="manual_paper"
    account_description="Manual paper trades only. Model forward studies are separate."
    initial_cash=10000
    fill_limit=1000
    def clock(self):return now()
    def kind(self,name):return self.record_prefix+"_"+name
    def new_account(self,balance=None):return {**new_account(self.initial_cash if balance is None else balance),"created_at":self.clock().isoformat(),"source":self.source}
    def __init__(self,db,market):self.db=db;self.market=market
    def maximum_fill_notional(self,order,state,quote,at):return float("inf")
    def state(self):return self.db.setting(self.account_key)
    def reserve(self,state,excluding=None):
        cash=0.;quantity={}
        for o in state['orders'].values():
            if o['status'] not in OPEN or o['id']==excluding:continue
            left=o['quantity']-o['filled_quantity']
            if o['side']=='buy':cash+=left*o['reserve_price']*(1+o['policy']['fee_bps']/1e4)
            else:quantity[o['symbol']]=quantity.get(o['symbol'],0)+left
        return cash,quantity
    def view(self):
        s=self.state() or {**self.new_account(),'id':'uninitialized'};reserved,_=self.reserve(s);positions=[];equity=s['cash'];unrealized=0
        for symbol,p in s['positions'].items():
            if p['quantity']<=1e-10:continue
            mark=s['marks'].get(symbol);price=mark['bid'] if mark else p['average_cost'];value=p['quantity']*price;gain=value-p['quantity']*p['average_cost'];equity+=value;unrealized+=gain
            positions.append({**p,'symbol':symbol,'market_price':price,'market_value':value,'unrealized_pnl':gain,'mark_at':mark['timestamp'] if mark else None,'mark_status':'observed bid; may be stale' if mark else 'cost fallback; quote unavailable','corporate_action_review':s['review'].get(symbol)})
        equity+=sum(v['amount'] for v in s['receivables'] if not v['paid'])
        for p in positions:p['allocation']=p['market_value']/equity if equity else 0
        baseline=s['daily_baseline'];day_pnl=equity-baseline['equity'] if baseline and baseline['date']==self.clock().date().isoformat() else None
        return {'id':s['id'],'initial_cash':s['initial_cash'],'cash':s['cash'],'available_cash':max(0,s['cash']-reserved),'reserved_cash':reserved,'equity':equity,'realized_pnl':s['realized_pnl'],'unrealized_pnl':unrealized,'total_pnl':equity-s['initial_cash'],'day_pnl':day_pnl,'day_basis':'Since first observed valuation of current UTC day; unavailable before observation','fees':s['fees'],'positions':positions,'orders':sorted(s['orders'].values(),key=lambda v:v['created_at'],reverse=True),'fills':[r['payload'] for r in self.db.records(self.kind("fill"),limit=self.fill_limit) if r['payload']['account_id']==s['id']],'source':self.account_description,'starting_balance_default':self.initial_cash}
    def preview(self,ticket,q):
        asset=self.market.lookup(ticket.symbol);s=self.state() or {**self.new_account(),'id':'uninitialized'};symbol=asset['symbol'];e=asset['eligibility']
        if ticket.side=='buy' and not e['eligible']:raise ValueError('Asset is not research eligible: '+', '.join(e['reasons']))
        if s['review'].get(symbol):raise ValueError('Corporate action review required before trading this asset')
        conservative=asset['liquidity_bucket']=='limited' or asset['market_cap_bucket'] in ('small','unknown') and asset['asset_class']=='stock'
        policy=ForwardPolicy(slippage_bps=25 if conservative else 5,participation=.02 if conservative else .05).model_dump()
        price=q.get('ask' if ticket.side=='buy' else 'bid') if q else None
        base=ticket.limit_price if ticket.order_type=='limit' else price
        if not base or not math.isfinite(base) or base<=0:raise ValueError('A two-sided quote is required to estimate a market order. Try a limit order or retry during market hours.')
        estimated=base*(1+policy['slippage_bps']/1e4*(1 if ticket.side=='buy' else -1)) if ticket.order_type=='market' else base
        quantity=ticket.quantity if ticket.quantity is not None else ticket.amount/(estimated*(1+policy['fee_bps']/1e4) if ticket.side=='buy' else estimated)
        if asset['asset_class']!='crypto':quantity=math.floor(quantity)
        else:quantity=coin_floor(quantity)
        if quantity<=0:raise ValueError('Amount is too small for one share or the minimum coin increment')
        if asset['asset_class']!='crypto' and ticket.quantity and ticket.quantity!=quantity:raise ValueError('Whole shares are required for stock and ETF simulation')
        reserved,reserved_quantity=self.reserve(s);cost=quantity*estimated;fee=cost*policy['fee_bps']/1e4;available=s['cash']-reserved
        if ticket.side=='buy' and cost+fee>available+1e-8:raise ValueError('Insufficient available paper cash after open-order reservations')
        position=s['positions'].get(symbol,{}).get('quantity',0)-reserved_quantity.get(symbol,0)
        if ticket.side=='sell' and quantity>position+1e-10:raise ValueError('Sell quantity exceeds unreserved paper holdings. Short selling is not supported.')
        if cost>(e.get('mean_dollar_volume') or 0)*.0001:raise ValueError('Order exceeds conservative 0.01% average daily dollar-volume limit')
        at=self.clock();spread=(q['ask']-q['bid'])/((q['ask']+q['bid'])/2)*10000 if q and q.get('ask') and q.get('bid') else None
        reasons=quote_check(q or {},{'symbol':symbol,'decided_at':(at-timedelta(seconds=60)).isoformat()},ForwardPolicy(**policy),at,self.db.setting('research_calendar',{}).get('sessions',[]),asset['asset_class'])
        value={'id':uid(),'account_id':s['id'],'created_at':at.isoformat(),'expires_at':(at+timedelta(seconds=60)).isoformat(),'symbol':symbol,'asset_class':asset['asset_class'],'side':ticket.side,'order_type':ticket.order_type,'limit_price':ticket.limit_price,'quantity':quantity,'estimated_price':estimated,'estimated_fee':fee,'estimated_total':cost+fee if ticket.side=='buy' else cost-fee,'available_cash':max(0,available),'quoted_bid':q.get('bid') if q else None,'quoted_ask':q.get('ask') if q else None,'quote_at':q.get('timestamp') if q else None,'spread_bps':spread,'policy':policy,'eligibility':e,'liquidity_bucket':asset['liquidity_bucket'],'market_cap_bucket':asset['market_cap_bucket'],'warnings':reasons+['Local simulation only. A preview is not a fill. Five-second minimum delay.','Limit orders expire after 24 hours; market attempts after 60 seconds.'],'source':self.source,'strategy_family':'manual','evidence':{'score':asset.get('score'),'regime':asset.get('regime'),'model_prediction':asset.get('model_prediction'),'probability':asset.get('probability'),'uncertainty':asset.get('uncertainty'),'as_of':asset.get('price_at')}}
        self.db.put(self.kind("preview"),value,symbol,record_id=value['id']);return value
    def place(self,request):
        with self.db.transaction() as session:
            p=session.get(Record,request.preview_id)
            if not p or p.kind!=self.kind("preview"):raise ValueError('Preview not found')
            preview=p.payload;key=self.kind('order')+'_'+request.preview_id
            old=session.get(Record,key)
            if old:return old.payload
            if pd.Timestamp(preview['expires_at'])<pd.Timestamp(self.clock()):raise ValueError('Preview expired. Review a fresh estimate.')
            row=session.get(Setting,self.account_key);s=json.loads(json.dumps(row.value)) if row else self.new_account()
            if preview['account_id']!=('uninitialized' if not row else s['id']):raise ValueError('Paper account changed; request a new preview')
            reserved,quantities=self.reserve(s);q=preview['quantity'];symbol=preview['symbol']
            if preview['side']=='buy' and preview['estimated_total']>s['cash']-reserved+1e-8:raise ValueError('Paper buying power changed; review again')
            if preview['side']=='sell' and q>s['positions'].get(symbol,{}).get('quantity',0)-quantities.get(symbol,0)+1e-10:raise ValueError('Available holdings changed; review again')
            at=self.clock();order={**preview,'id':key,'account_id':s['id'],'preview_id':preview['id'],'created_at':at.isoformat(),'expires_at':(at+timedelta(seconds=60 if preview['order_type']=='market' else 86400)).isoformat(),'status':'OPEN','filled_quantity':0.,'filled_value':0.,'fees':0.,'reserve_price':preview['estimated_price'],'last_status':'Waiting for a fresh quote after execution delay','holding_rule':preview.get('holding_rule','Manual exit only')}
            s['orders'][key]=order;record(session,self.kind("order"),order,symbol,key)
            if row:row.value=s
            else:session.add(Setting(key=self.account_key,value=s))
            return order
    def cancel(self,oid):
        with self.db.transaction() as session:
            row=session.get(Setting,self.account_key);s=json.loads(json.dumps(row.value)) if row else None;o=s and s['orders'].get(oid)
            if not o or o['status'] not in OPEN:raise ValueError('Order is no longer open')
            o['status']='CANCELED';o['last_status']='Unfilled remainder canceled by you';record(session,self.kind("order_event"),{'order_id':oid,'account_id':s['id'],'status':'CANCELED','at':self.clock().isoformat()},o['symbol']);row.value=s;return o
    def reset(self,request):
        with self.db.transaction() as session:
            row=session.get(Setting,self.account_key);state=row.value if row else None
            if request.account_id!=(state['id'] if state else 'uninitialized'):raise ValueError('Account changed; reload before reset')
            if state:record(session,self.kind("account_archive"),{'account':state,'archived_at':self.clock().isoformat(),'reason':'Explicit user reset'})
            s=self.new_account(request.starting_balance)
            if row:row.value=s
            else:session.add(Setting(key=self.account_key,value=s))
        return self.view()
    def process(self,symbol,q,at=None):
        at=at or self.clock();sessions=self.db.setting('research_calendar',{}).get('sessions',[])
        instrument=next((i for i in load_universe(self.db).instruments if i.symbol==symbol),None)
        with self.db.transaction() as session:
            row=session.get(Setting,self.account_key)
            if not row:return
            s=json.loads(json.dumps(row.value));orders=sorted(s['orders'].values(),key=lambda o:o['created_at']);valid_mark=not quote_check(q or {},{'symbol':symbol,'decided_at':(at-timedelta(seconds=60)).isoformat()},ForwardPolicy(),at,sessions,'crypto' if symbol.endswith('-USD') else 'stock')
            if valid_mark:s['marks'][symbol]={'bid':q['bid'],'ask':q['ask'],'timestamp':q['timestamp']}
            for o in orders:
                if o['symbol']!=symbol or o['status'] not in OPEN:continue
                if pd.Timestamp(at)>=pd.Timestamp(o['expires_at']):
                    o['status']='EXPIRED' if o['filled_quantity'] else 'NO_FILL';o['last_status']='Expired without filling remaining quantity';record(session,self.kind("order_event"),{'order_id':o['id'],'account_id':s['id'],'status':o['status'],'at':at.isoformat()},symbol);continue
                policy=ForwardPolicy(**o['policy']);errors=quote_check(q or {},{'symbol':symbol,'decided_at':o['created_at']},policy,at,sessions,o['asset_class'])
                if s['review'].get(symbol):errors.append('Corporate action requires review')
                if instrument is None:errors.append('Security no longer in configured universe')
                elif instrument.halted or not instrument.active:errors.append('Security halted or inactive')
                if errors:o['last_status']='; '.join(errors);continue
                last=s['consumed'].get(symbol,{})
                if last.get('timestamp') and pd.Timestamp(q['timestamp'])<=pd.Timestamp(last['timestamp']):continue
                spread=(q['ask']-q['bid'])/((q['ask']+q['bid'])/2)*1e4;price=q['ask']*(1+policy.slippage_bps/1e4) if o['side']=='buy' else q['bid']*(1-policy.slippage_bps/1e4)
                if o['order_type']=='limit' and ((o['side']=='buy' and price>o['limit_price']) or (o['side']=='sell' and price<o['limit_price'])):o['last_status']='Waiting for limit price after slippage';continue
                reserved,quantities=self.reserve(s,o['id']);wanted=o['quantity']-o['filled_quantity'];depth=q['ask_size' if o['side']=='buy' else 'bid_size']*policy.participation
                qty=min(wanted,depth,o['eligibility']['mean_dollar_volume']*.0001/price)
                if o['side']=='buy':qty=min(qty,max(0,s['cash']-reserved)/(price*(1+policy.fee_bps/1e4)),self.maximum_fill_notional(o,s,q,at)/(price*(1+policy.fee_bps/1e4)))
                else:qty=min(qty,max(0,s['positions'].get(symbol,{}).get('quantity',0)-quantities.get(symbol,0)))
                qty=math.floor(qty) if o['asset_class']!='crypto' else coin_floor(qty)
                if qty<=0:o['last_status']='INSUFFICIENT_LIQUIDITY or buying power';continue
                fee=qty*price*policy.fee_bps/1e4;position=s['positions'].setdefault(symbol,{'quantity':0.,'average_cost':0.,'realized_pnl':0.,'opened_at':at.isoformat()});pnl=0.
                if o['side']=='buy':
                    if position['quantity']<=1e-10:position['opened_at']=at.isoformat()
                    position['average_cost']=(position['quantity']*position['average_cost']+qty*price+fee)/(position['quantity']+qty);position['quantity']=round(position['quantity']+qty,8);s['cash']-=qty*price+fee
                else:
                    pnl=qty*(price-position['average_cost'])-fee;position['quantity']=max(0,round(position['quantity']-qty,8));position['realized_pnl']+=pnl;s['realized_pnl']+=pnl;s['cash']+=qty*price-fee
                s['fees']+=fee;o['fees']+=fee;o['filled_quantity']+=qty;o['filled_value']+=qty*price;o['average_fill_price']=o['filled_value']/o['filled_quantity'];o['status']='FILLED' if o['quantity']-o['filled_quantity']<1e-8 else 'PARTIALLY_FILLED';o['last_status']='Simulated against fresh displayed depth';s['consumed'][symbol]={'timestamp':q['timestamp']}
                record(session,self.kind("fill"),{'account_id':s['id'],'order_id':o['id'],'symbol':symbol,'side':o['side'],'quantity':qty,'price':price,'fee':fee,'spread_bps':spread,'slippage_bps':policy.slippage_bps,'quote':q,'at':at.isoformat(),'realized_pnl':pnl,'source':self.source},symbol)
            equity=s['cash']+sum(p['quantity']*s['marks'].get(sym,{}).get('bid',p['average_cost']) for sym,p in s['positions'].items())+sum(v['amount'] for v in s['receivables'] if not v['paid'])
            if not s['daily_baseline'] or s['daily_baseline']['date']!=at.date().isoformat():s['daily_baseline']={'date':at.date().isoformat(),'equity':equity,'observed_at':at.isoformat()}
            row.value=s
    def actions(self):
        s=self.state()
        if not s:return
        with self.db.transaction() as session:
            row=session.get(Setting,self.account_key);s=json.loads(json.dumps(row.value));t=pd.Timestamp(self.clock())
            for v in s['receivables']:
                if not v['paid'] and pd.Timestamp(v['payable_at'])<=t:s['cash']+=v['amount'];v['paid']=True
            for symbol,p in s['positions'].items():
                if symbol.endswith('-USD'):continue
                actions=list(session.scalars(select(Record).where(Record.kind=='corporate_action',Record.symbol==symbol)))
                actions.sort(key=lambda r:(r.payload['data'].get('ex_date') or r.payload['data'].get('effective_date') or '',0 if r.payload['action_type'] in ('forward_splits','reverse_splits') else 1))
                for a in actions:
                    if a.id in s['applied_actions']:continue
                    data=a.payload['data'];effective=data.get('ex_date') or data.get('effective_date');kind=a.payload['action_type']
                    if not effective:continue
                    effective=pd.Timestamp(effective).tz_localize('America/New_York')
                    if not pd.Timestamp(p['opened_at'])<effective<=t:continue
                    if kind in ('forward_splits','reverse_splits'):
                        ratio=float(data['new_rate'])/float(data['old_rate'])
                        if not math.isfinite(ratio) or ratio<=0:s['review'][symbol]='Invalid split ratio';continue
                        # Late lifecycle data cannot safely rebase trades already made after the ex date.
                        later=[f for f in session.scalars(select(Record).where(Record.kind==self.kind("fill"),Record.symbol==symbol)) if f.payload['account_id']==s['id'] and pd.Timestamp(f.payload['at'])>=effective]
                        if later:s['review'][symbol]='Late split information overlaps newer fills; accounting review required';continue
                        p['quantity']*=ratio;p['average_cost']/=ratio
                        mark=s['marks'].get(symbol)
                        if mark and pd.Timestamp(mark['timestamp'])<effective:
                            mark['bid']/=ratio;mark['ask']/=ratio;mark['basis']='split-adjusted prior quote; not a new execution quote'
                        if abs(p['quantity']-round(p['quantity']))>1e-8:s['review'][symbol]='Fractional split entitlement requires verified cash-in-lieu data'
                    elif kind=='cash_dividends' and data.get('payable_date'):
                        entitled=p['quantity']
                        for fill in session.scalars(select(Record).where(Record.kind==self.kind("fill"),Record.symbol==symbol)):
                            f=fill.payload
                            if f['account_id']==s['id'] and pd.Timestamp(f['at'])>=effective:entitled+=f['quantity']*(1 if f['side']=='sell' else -1)
                        if entitled<0:s['review'][symbol]='Dividend entitlement requires review';continue
                        amount=entitled*float(data.get('rate',0))
                        if not math.isfinite(amount) or amount<0:s['review'][symbol]='Invalid dividend amount';continue
                        s['receivables'].append({'amount':amount,'paid':False,'payable_at':pd.Timestamp(data['payable_date']).tz_localize('America/New_York').isoformat(),'action_id':a.id});s['realized_pnl']+=amount;p['realized_pnl']+=amount
                    else:s['review'][symbol]='Unsupported corporate lifecycle event; simulation paused';continue
                    for o in s['orders'].values():
                        if o['symbol']==symbol and o['status'] in OPEN:o['status']='CANCELED';o['last_status']='Corporate action changed order terms; review a new ticket'
                    s['applied_actions'].append(a.id);record(session,self.kind("action"),{'account_id':s['id'],'action_id':a.id,'symbol':symbol,'effective_at':effective.isoformat(),'observed_at':self.clock().isoformat()},symbol)
            row.value=s
    async def cycle(self,providers):
        self.actions();s=self.state()
        if not s:return
        symbols={o['symbol'] for o in s['orders'].values() if o['status'] in OPEN}|{sym for sym,p in s['positions'].items() if p['quantity']>0}
        for symbol in sorted(symbols):
            try:q=await providers.forward_quote(symbol)
            except Exception:q={}
            self.process(symbol,q)
