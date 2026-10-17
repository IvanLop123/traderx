"""Durable, fail-closed Alpaca paper submission and broker-owned accounting."""
import asyncio
import hashlib
import json
import math
from datetime import datetime,timedelta
from backend.schemas.contracts import now,TradeCandidate,RiskAssessment,ApprovedOrder,RejectedOrder
from backend.storage.database import Setting,Record
from backend.execution.providers import AlpacaPaperProvider

TERMINAL={'filled','canceled','expired','rejected','replaced','done_for_day'}

def finite(value):
    v=float(value)
    if not math.isfinite(v):raise ValueError('Nonfinite broker account value')
    return v

class PaperBroker:
    def __init__(self,db,paper,credentials,transport=None):
        self.db=db;self.paper=paper;self.provider=AlpacaPaperProvider(credentials,transport);self.lock=asyncio.Lock()
    def status(self):
        return {'venue':'alpaca_paper','configured':self.provider.configured(),'submission_enabled':self.provider.cfg.get('ALPACA_PAPER_EXECUTION_ENABLED')=='true',
                'global_halt':self.paper.snapshot()['kill_switch'],'snapshot':self.db.setting('alpaca_paper_snapshot'),
                'reconciliation':self.db.setting('alpaca_reconciliation',{'status':'NOT_CHECKED'}),'orders':self.orders(),
                'live_trading':False}
    def orders(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        with Session(self.db.engine) as s:return [r.value for r in s.scalars(select(Setting).where(Setting.key.like('broker_order_%')))]
    async def sync(self):
        async with self.lock:return await self._sync()
    async def _sync(self):
        try:
            account,positions,orders=await self.provider.snapshot()
            if not account.get('id'):raise ValueError('Broker account identity missing')
            equity=finite(account['equity']);cash=finite(account['cash']);last=finite(account['last_equity'])
            if equity<=0 or last<=0 or cash<0:raise ValueError('Unlevered positive-equity paper account required')
            previous=self.db.setting('alpaca_paper_snapshot',{})
            if previous.get('account_id')!=account['id']:previous={}
            mapped={}
            for p in positions:
                quantity=finite(p['qty']);price=finite(p['current_price']);cost=finite(p['avg_entry_price'])
                if quantity<0 or price<=0 or cost<0 or p.get('asset_class')!='us_equity':raise ValueError('Unsupported broker position; new submission blocked')
                mapped[p['symbol']]={'quantity':quantity,'market_price':price,'average_cost':cost,'asset_class':'stock'}
            state={'account_id':account['id'],'cash':cash,'equity':equity,'buying_power':finite(account['buying_power']),
                   'positions':mapped,'day_start_equity':last,'peak_equity':max(previous.get('peak_equity',equity),equity),
                   'pending_orders':orders,'kill_switch':self.paper.snapshot()['kill_switch'],'mode':'ALPACA_PAPER',
                   'account_blocked':bool(account.get('trading_blocked') or account.get('account_blocked') or account.get('status')!='ACTIVE'),
                   'as_of':now().isoformat(),'week':list(now().isocalendar()[:2]),
                   'week_start_equity':previous.get('week_start_equity',equity) if previous.get('week')==list(now().isocalendar()[:2]) else equity}
            discrepancies=[]
            for ledger in self.orders():
                if ledger['account_id']!=state['account_id']:
                    if ledger['status'] not in TERMINAL:discrepancies.append('ACCOUNT_CHANGED_WITH_UNRESOLVED_ORDER')
                    continue
                if ledger['status'] not in TERMINAL:
                    response=await self.provider.lookup(ledger['client_order_id'])
                    if response: self._record_response(ledger,response)
                    else:discrepancies.append('UNRESOLVED_ORDER:'+ledger['client_order_id'])
            known={o['client_order_id'] for o in self.orders() if o['account_id']==state['account_id']}
            state['external_open_orders']=sum(o.get('client_order_id') not in known for o in orders)
            # Compare broker equity against independently marked long/cash holdings.
            computed=cash+sum(p['quantity']*p['market_price'] for p in mapped.values())
            if abs(computed-equity)>max(2,equity*.002):discrepancies.append('ACCOUNT_EQUITY_MISMATCH')
            report={'status':'MISMATCH' if discrepancies else 'RECONCILED','issues':discrepancies,'checked_at':now().isoformat()}
            self.db.set_setting('alpaca_paper_snapshot',state);self.db.set_setting('alpaca_reconciliation',report)
            self.db.put('broker_snapshot',{'venue':'alpaca_paper','state':state,'reconciliation':report})
            if discrepancies:self.paper.halt(True)
            return self.status()
        except Exception:
            self.db.set_setting('alpaca_reconciliation',{'status':'UNAVAILABLE','checked_at':now().isoformat(),'issues':['Snapshot or order reconciliation failed; submissions blocked']})
            raise
    def risk_state(self,state):
        s=json.loads(json.dumps(state));s['kill_switch']=self.paper.snapshot()['kill_switch'];s['reserved_sells']={};issues=[]
        if s['account_blocked']:issues.append('BROKER_ACCOUNT_BLOCKED')
        if self.db.setting('alpaca_reconciliation',{}).get('status')!='RECONCILED':issues.append('BROKER_RECONCILIATION_REQUIRED')
        if (now()-datetime.fromisoformat(s['as_of'])).total_seconds()>30:issues.append('BROKER_SNAPSHOT_STALE')
        for order in s['pending_orders']:
            qty=finite(order['qty'])-finite(order.get('filled_qty',0))
            if qty<0:raise ValueError('Invalid outstanding broker quantity')
            symbol=order['symbol'];side=order['side']
            if side=='buy':
                price=finite(order.get('limit_price') or 0)
                if price<=0:issues.append('UNPRICED_PENDING_ORDER');continue
                p=s['positions'].setdefault(symbol,{'quantity':0,'market_price':price,'asset_class':'stock'})
                p['quantity']+=qty;p['market_price']=max(price,p['market_price']);s['cash']-=qty*price*1.002
            elif side=='sell':
                s['reserved_sells'][symbol]=s['reserved_sells'].get(symbol,0)+qty
                if s['reserved_sells'][symbol]>s['positions'].get(symbol,{}).get('quantity',0):issues.append('PENDING_SELL_EXCEEDS_HOLDINGS')
            else:issues.append('UNKNOWN_PENDING_ORDER_SIDE')
        return s,issues
    async def assess(self,candidate,quote,provider_ok=True):
        if type(candidate) is not TradeCandidate:raise TypeError('TradeCandidate required')
        await self.sync();state=self.db.setting('alpaca_paper_snapshot');state,issues=self.risk_state(state)
        reasons=self.paper._reasons(candidate,state,quote,provider_ok)+issues
        if candidate.direction=='sell' and candidate.quantity>state['positions'].get(candidate.asset.symbol,{}).get('quantity',0)-state['reserved_sells'].get(candidate.asset.symbol,0):reasons.append('SHARES_RESERVED_BY_PENDING_ORDER')
        if candidate.asset.asset_class not in ('stock','etf'):reasons.append('BROKER_INSTRUMENT_UNSUPPORTED')
        if not float(candidate.quantity).is_integer():reasons.append('WHOLE_SHARES_REQUIRED')
        with self.db.transaction() as s:
            saved=s.get(Record,candidate.id)
            if not saved or saved.kind!='candidate' or saved.payload!=candidate.model_dump(mode='json'):raise ValueError('Persisted research candidate required')
            a=RiskAssessment(candidate_id=candidate.id,approved=not reasons,reasons=reasons,limits={**self.paper.limits,'account_id':state['account_id'],'venue':'alpaca_paper'})
            s.add(Record(id=a.id,kind='risk_assessment',symbol=candidate.asset.symbol,available_at=now().isoformat(),payload=a.model_dump(mode='json')))
            if reasons:return RejectedOrder(candidate_id=candidate.id,assessment_id=a.id,reasons=reasons)
            o=ApprovedOrder(candidate_id=candidate.id,assessment_id=a.id,asset=candidate.asset,side=candidate.direction,quantity=candidate.quantity,
                            limit_price=candidate.entry_price*(1.01 if candidate.direction=='buy' else .99),expires_at=candidate.expires_at,venue='alpaca_paper')
            s.add(Record(id=o.id,kind='approved_order',symbol=o.asset.symbol,available_at=now().isoformat(),payload=o.model_dump(mode='json')))
            return o
    def _record_response(self,ledger,response):
        quantity=finite(response.get('filled_qty',0))
        if response.get('client_order_id')!=ledger['client_order_id'] or response.get('symbol')!=ledger['symbol'] or response.get('side')!=ledger['side']:
            self.paper.halt(True);raise ValueError('Broker order identity mismatch')
        if finite(response.get('qty',0))!=ledger['quantity'] or quantity<0 or quantity>ledger['quantity'] or (response.get('status')=='filled' and quantity!=ledger['quantity']):
            self.paper.halt(True);raise ValueError('Broker filled quantity mismatch')
        average=finite(response['filled_avg_price']) if response.get('filled_avg_price') else None
        if quantity and (average is None or average<=0):
            self.paper.halt(True);raise ValueError('Broker fill price invalid')
        rid=hashlib.sha256(json.dumps(response,sort_keys=True).encode()).hexdigest()
        with self.db.transaction() as session:
            row=session.get(Setting,'broker_order_'+ledger['client_order_id'])
            current=row.value if row else ledger
            # An older in-flight status response cannot undo a later fill or terminal state.
            if quantity<current.get('filled_quantity',0) or (current['status'] in TERMINAL and response['status'] not in TERMINAL):return current
            result={**current,'status':response['status'],'broker_order_id':response['id'],'filled_quantity':quantity,
                    'filled_average_price':average,'updated_at':now().isoformat(),'response':response}
            session.merge(Setting(key='broker_order_'+ledger['client_order_id'],value=result))
            if not session.get(Record,rid):session.add(Record(id=rid,kind='broker_order_event',symbol=ledger['symbol'],available_at=now().isoformat(),payload=result))
        return result
    async def execute(self,order,quote,provider_ok=True):
        if type(order) is not ApprovedOrder or order.venue!='alpaca_paper':raise TypeError('Alpaca paper ApprovedOrder required')
        self.provider.guard(True)
        async with self.lock:
            # Existing durable reservations always reconcile; a timed-out POST is never retried.
            cid='tx-'+hashlib.sha256(order.id.encode()).hexdigest()[:32]
            existing=self.db.setting('broker_order_'+cid)
            if existing:
                account=await self.provider.request('/v2/account')
                if account.get('id')!=existing['account_id']:raise ValueError('Paper account changed; original account required for reconciliation')
                response=await self.provider.lookup(cid)
                return self._record_response(existing,response) if response else {**existing,'detail':'Submission is unresolved. No replacement order was sent.'}
            await self._sync();state,issues=self.risk_state(self.db.setting('alpaca_paper_snapshot'))
            with self.db.transaction() as s:
                saved=s.get(Record,order.id);assessment=s.get(Record,order.assessment_id);candidate=s.get(Record,order.candidate_id)
                if not saved or saved.kind!='approved_order' or saved.payload!=order.model_dump(mode='json'):raise ValueError('Durable risk approval required')
                if not assessment or not assessment.payload['approved'] or assessment.payload['candidate_id']!=order.candidate_id or not candidate:raise ValueError('Risk approval invalid')
                if assessment.payload['limits'].get('account_id')!=state['account_id']:raise ValueError('Approval belongs to another paper account')
                c=TradeCandidate.model_validate(candidate.payload)
                halt=s.get(Setting,'portfolio');state['kill_switch']=halt.value['kill_switch'] if halt else True
                reasons=self.paper._reasons(c,state,quote,provider_ok)+issues
                if c.direction=='sell' and c.quantity>state['positions'].get(c.asset.symbol,{}).get('quantity',0)-state['reserved_sells'].get(c.asset.symbol,0):reasons.append('SHARES_RESERVED_BY_PENDING_ORDER')
                if order.side=='buy':
                    worst=max(order.limit_price,float(quote['ask']))
                    worst_candidate=c.model_copy(update={'entry_price':worst})
                    reasons+=self.paper._reasons(worst_candidate,state,{**quote,'price':worst,'bid':worst,'ask':worst},provider_ok)
                if order.expires_at<=now():reasons.append('ORDER_EXPIRED')
                if reasons:raise ValueError(', '.join(reasons))
                if s.get(Record,'executed-'+c.id):raise ValueError('Candidate already reserved or executed')
                ledger={'client_order_id':cid,'approval_id':order.id,'candidate_id':c.id,'account_id':state['account_id'],'venue':'alpaca_paper',
                        'symbol':order.asset.symbol,'side':order.side,'quantity':order.quantity,'status':'submitting','filled_quantity':0,'created_at':now().isoformat()}
                s.add(Setting(key='broker_order_'+cid,value=ledger))
                s.add(Record(id='executed-'+c.id,kind='audit',symbol=c.asset.symbol,available_at=now().isoformat(),payload={'action':'paper_broker_reserved','order_id':order.id,'client_order_id':cid}))
            try:
                if self.paper.snapshot()['kill_switch']:raise ValueError('GLOBAL_KILL_SWITCH')
                response=await self.provider.submit(order,cid)
                return self._record_response(ledger,response)
            except Exception:
                ledger={**ledger,'status':'uncertain','updated_at':now().isoformat(),'detail':'Reconcile the reserved client order ID; automatic resubmission is prohibited.'}
                self.db.set_setting('broker_order_'+cid,ledger)
                self.db.set_setting('alpaca_reconciliation',{'status':'MISMATCH','issues':['UNRESOLVED_SUBMISSION'],'checked_at':now().isoformat()})
                self.paper.halt(True)
                return ledger
    async def cancel(self,cid):
        async with self.lock:return await self._cancel(cid)
    async def _cancel(self,cid):
        ledger=self.db.setting('broker_order_'+cid)
        if not ledger or not ledger.get('broker_order_id'):raise ValueError('Known broker order required')
        current=await self.provider.request('/v2/account')
        if current.get('id')!=ledger['account_id']:raise ValueError('Paper account changed')
        if ledger['status'] in TERMINAL:return ledger
        await self.provider.cancel(ledger['broker_order_id'])
        # A cancellation request is not a cancellation confirmation.
        response=await self.provider.lookup(cid)
        return self._record_response(ledger,response) if response else ledger
