from backend.intelligence.news import live_governance
"""Experimental ledger and explicit, position-bound manual exit consent.

Only ManualPaper's local fill simulator is reachable. No broker APIs are imported.
All outcomes are evaluation-only and never forwarded to training/qualification.
"""
import asyncio
import json
from datetime import timedelta
from typing import Literal
import pandas as pd
from pydantic import Field
from backend.schemas.contracts import Contract,now
from backend.product.paper import ManualPaper,Ticket,Confirm,OPEN
from backend.product.market import ProductMarket
from backend.research.features import stable_hash
from backend.research.forward import quote_check,ForwardPolicy
from backend.selection.policy import policy
from backend.selection.risk import size
from backend.ensemble.engine import candidate,decide,VERSION
from backend.research.alpha.registry import context
from backend.research.alpha.allocation import Allocation
from backend.research.alpha.math import attribution

class ExitPolicy(Contract):
    rule:Literal['never','regime_incompatibility','ensemble','reversal','edge_loss','deterioration','fixed_horizon','volatility_stop','risk_limit','trailing','profit_taking']='ensemble'
    horizon:int=Field(default=5,ge=1,le=60)
    volatility_multiple:float=Field(default=2,gt=0,le=10)
    stop:float=Field(default=.05,gt=0,le=.5)
    trailing:float=Field(default=.05,gt=0,le=.5)
    profit:float=Field(default=.1,gt=0,le=1)
class Consent(Contract):
    symbol:str
    account_id:str
    opened_at:str
    enabled:bool=False
    policy:ExitPolicy=Field(default_factory=ExitPolicy)
class Pause(Contract):
    paused:bool

def trigger(position,e,quote,extrema,policy,sessions,asset_class,drawdown=0,volatility=None,at=None):
    at=pd.Timestamp(at or now());opened=pd.Timestamp(position['opened_at']);age=int((at-opened).total_seconds()//86400) if asset_class=='crypto' else sum(opened<pd.Timestamp(s['close'])<=at for s in sessions)
    gain=quote['bid']/position['average_cost']-1;rule=policy.rule
    if rule=='never':return None
    checks={'regime_incompatibility':e.get('regime_compatible') is False,'reversal':e['action']=='SELL','edge_loss':e['edge'] is not None and e['edge']<=0,'deterioration':e['action'] in ('NO TRADE','INSUFFICIENT EVIDENCE'),'fixed_horizon':age>=(e.get('horizon_sessions',policy.horizon) if rule=='ensemble' else policy.horizon),'volatility_stop':bool(volatility and volatility>0 and gain<=-policy.volatility_multiple*volatility),'risk_limit':drawdown>=.1 or gain<=-policy.stop,'trailing':quote['bid']/max(quote['bid'],extrema['high'])-1<=-policy.trailing,'profit_taking':gain>=policy.profit}
    selected=['risk_limit','reversal','edge_loss','regime_incompatibility','deterioration','fixed_horizon','volatility_stop'] if rule=='ensemble' else [rule]
    return next((r for r in selected if checks[r]),None)

def state_view(state,order,quote):
    state=json.loads(json.dumps(state));state['marks'][order['symbol']]={'bid':quote['bid'],'timestamp':quote['timestamp']}
    positions=[{**p,'symbol':s,'market_value':p['quantity']*state['marks'].get(s,{}).get('bid',p['average_cost'])} for s,p in state['positions'].items() if p['quantity']>0]
    orders=[o for o in state['orders'].values() if o['id']!=order['id']];reserve=sum((o['quantity']-o['filled_quantity'])*o['reserve_price']*(1+o['policy']['fee_bps']/1e4) for o in orders if o['side']=='buy' and o['status'] in OPEN)
    return {'equity':state['cash']+sum(p['market_value'] for p in positions),'available_cash':max(0,state['cash']-reserve),'cash':state['cash'],'positions':positions,'orders':orders}

class ShadowPaper(ManualPaper):
    account_key='ensemble_shadow_account'
    record_prefix='shadow'
    source='experimental_ensemble_shadow'
    fill_limit=None
    account_description='EXPERIMENTAL — NOT VALIDATED. Local simulation; never scientific training evidence.'
    def reset(self,request):raise ValueError('Shadow account reset is not exposed')
    def maximum_fill_notional(self,order,state,quote,at):
        if self.db.setting('ensemble_shadow_paused',False) or (self.db.setting('alpha_required',False) and not self.db.setting('alpha_governance',{})):return 0
        snap=self.db.setting('model_opportunities',{});asset=snap.get('assets',{}).get(order['symbol'],{});raw=next((r for r in snap.get('rows',[]) if r['symbol']==order['symbol']),{})
        if not raw:return 0
        raw=context(raw,live_governance(self.db),at);r=candidate(raw,asset,at=at)
        if r['ensemble']['id']!=order.get('ensemble_id'):return 0
        spread=(quote['ask']-quote['bid'])/((quote['ask']+quote['bid'])/2);cost=spread+2*(order['policy']['slippage_bps']+order['policy']['fee_bps'])/1e4
        if r['expected_edge'] is None:return 0
        r['expected_edge']+=raw.get('estimated_roundtrip_cost',0)-cost
        if r['expected_edge']<max(0,r['uncertainty']*.25):return 0
        for s,p in state['positions'].items():
            if s!=order['symbol'] and p['quantity']>0:
                t=state['marks'].get(s,{}).get('timestamp')
                if not t or not 0<=(pd.Timestamp(at)-pd.Timestamp(t)).total_seconds()<=120:return 0
        links=self.db.setting('shadow_links',{});view=state_view(state,order,quote)
        allowed=size(r,view,snap.get('assets',{}),snap.get('correlation',{}),policy(self.db).model_copy(update={'minimum_score':0}),self.db.setting('shadow_high_water',self.initial_cash),{s:d['groups'] for s,d in links.items()},allow_existing=True,require_qualified=False)['notional']
        allocation=order.get('evidence',{}).get('allocation')
        if self.db.setting('alpha_governance',{}):
            if not allocation or (pd.Timestamp(at)-pd.Timestamp(allocation['at'])).total_seconds()>120:return 0
            allowed=min(allowed,allocation.get('notionals',{}).get(order['symbol'],0))
        return allowed
    def process(self,symbol,q,at=None):
        snap=self.db.setting('model_opportunities',{});raw=next((r for r in snap.get('rows',[]) if r['symbol']==symbol),{});e=decide(context(raw,live_governance(self.db)),snap.get('assets',{}).get(symbol,{}),at=at)
        for o in (self.state() or {}).get('orders',{}).values():
            if o['symbol']==symbol and o['side']=='buy' and o['status'] in OPEN and (self.db.setting('ensemble_shadow_paused',False) or e['action']!='BUY' or e['id']!=o.get('ensemble_id')):self.cancel(o['id'])
        return super().process(symbol,q,at)

class ShadowPortfolio:
    def __init__(self,db,providers,market=None):
        self.db=db;self.providers=providers;self.market=market or ProductMarket(db);self.paper=ShadowPaper(db,self.market);self.lock=asyncio.Lock();self.allocator=Allocation(db)
    def submit(self,ticket,q,decision):
        rid=decision['id'];previous=self.db.get(rid)
        if previous:return previous['payload']
        try:
            preview=self.paper.preview(ticket,q);preview.update(id='shadow_preview_'+stable_hash(rid),ensemble_id=decision['ensemble']['id'],evidence=decision,holding_rule=decision['exit_policy'],strategy_family='+'.join(decision['groups']))
            self.db.put('shadow_preview',preview,ticket.symbol,record_id=preview['id']);order=self.paper.place(Confirm(preview_id=preview['id'],confirmation='PLACE PAPER ORDER'));decision.update(order_id=order['id'],status='ORDERED')
        except ValueError as ex:decision.update(status='NO_TRADE',reason=str(ex))
        self.db.put('shadow_decision',decision,ticket.symbol,record_id=rid);return decision
    async def cycle(self):
        async with self.lock:
            snap=self.db.setting('model_opportunities',{});governance=live_governance(self.db);rows={r['symbol']:context(r,governance) for r in snap.get('rows',[])};assets=snap.get('assets',{});sessions=self.db.setting('research_calendar',{}).get('sessions',[]);links=self.db.setting('shadow_links',{});p=policy(self.db).model_copy(update={'minimum_score':0});xp=ExitPolicy();self.paper.actions()
            view=self.paper.view();high=max(self.db.setting('shadow_high_water',view['initial_cash']),view['equity']);self.db.set_setting('shadow_high_water',high)
            held={p['symbol'] for p in view['positions']}|{o['symbol'] for o in view['orders'] if o['status'] in OPEN}
            for symbol in sorted(held):
                try:q=await self.providers.forward_quote(symbol)
                except Exception:q={}
                self.paper.process(symbol,q);view=self.paper.view();pos=next((p for p in view['positions'] if p['symbol']==symbol),None)
                if not pos:continue
                valid=not quote_check(q,{'symbol':symbol,'decided_at':(now()-timedelta(seconds=60)).isoformat()},ForwardPolicy(),now(),sessions,assets.get(symbol,{}).get('asset_class','stock'))
                if not valid:continue
                e=decide(rows.get(symbol,{}),assets.get(symbol,{}),held=True,at=now());key='shadow_extrema_'+stable_hash([view['id'],symbol,pos['opened_at']])[:30];old=self.db.setting(key,{});ext={'high':max(old.get('high',q['bid']),q['bid']),'low':min(old.get('low',q['bid']),q['bid'])};self.db.set_setting(key,ext)
                obs={'symbol':symbol,'at':now().isoformat(),'position':pos,'quote':q,'ensemble':e,'extrema':ext,'evidence_policy':'experimental_evaluation_only'}
                self.db.put('shadow_observation',obs,symbol,record_id='shadow_observation_'+stable_hash([key,q['timestamp'],e['id']]))
                why=trigger(pos,e,q,ext,xp,sessions,assets.get(symbol,{}).get('asset_class'),max(0,1-view['equity']/high),rows.get(symbol,{}).get('daily_volatility'))
                if why and not any(o['symbol']==symbol and o['side']=='sell' and o['status'] in OPEN for o in view['orders']):
                    for o in view['orders']:
                        if o['symbol']==symbol and o['side']=='buy' and o['status'] in OPEN:self.paper.cancel(o['id'])
                    entry=links.get(symbol,{});d={'id':'shadow_decision_'+stable_hash([key,'exit',e['id'],len(view['fills'])]),'side':'sell','symbol':symbol,'at':now().isoformat(),'reason':why,'ensemble':e,'entry_id':entry.get('id'),'groups':entry.get('groups',[]),'features':rows.get(symbol,{}).get('votes',[]),'position':pos,'quote':q,'extrema':ext,'exit_policy':xp.model_dump(),'evidence_policy':'experimental_evaluation_only'}
                    self.submit(Ticket(symbol=symbol,side='sell',quantity=pos['quantity']),q,d)
            view=self.paper.view();blocked=self.db.setting('ensemble_shadow_paused',False) or (self.db.setting('alpha_required',False) and not self.db.setting('alpha_governance',{})) or any(not pos.get('mark_at') or not 0<=(pd.Timestamp(now())-pd.Timestamp(pos['mark_at'])).total_seconds()<=120 or pos.get('corporate_action_review') for pos in view['positions'])
            allocation=await asyncio.to_thread(self.allocator.plan,snap,view) if governance else None
            quote_count=0
            for symbol,raw in rows.items():
                await asyncio.sleep(0) # Let UI and quote ingestion run between independent assets.
                r=candidate(raw,assets.get(symbol,{}),at=now());e=r['ensemble'];did='shadow_decision_'+stable_hash([view['id'],symbol,e['id'],'entry'])
                if self.db.get(did):continue
                if blocked and e['action']=='BUY':continue
                if e['action']!='BUY' or blocked:
                    reason='Entries paused or held marks stale' if blocked else '; '.join(e['reasons']) or e['action']
                    self.db.put('shadow_decision',{'id':did,'symbol':symbol,'side':'cash','at':now().isoformat(),'status':'NO_TRADE','reason':reason,'ensemble':e,'features':raw.get('votes',[]),'feature_available_at':raw.get('feature_available_at'),'regime':raw.get('regime'),'groups':r['groups'],'exit_policy':xp.model_dump(),'evidence_policy':'experimental_evaluation_only'},symbol,record_id=did)
                    continue
                risk=size(r,view,assets,snap.get('correlation',{}),p,high,{s:d['groups'] for s,d in links.items()},require_qualified=False)
                if allocation is not None:risk['notional']=min(risk['notional'],allocation.get('notionals',{}).get(symbol,0))
                if risk['notional']<=0:continue
                if quote_count>=p.maximum_quote_requests_per_cycle:break
                quote_count+=1
                try:q=await self.providers.forward_quote(symbol)
                except Exception:q={}
                d={'id':did,'side':'buy','symbol':symbol,'at':now().isoformat(),'reason':'Diversified ensemble BUY subject to simulator checks','ensemble':e,'features':raw.get('votes',[]),'feature_available_at':raw.get('feature_available_at'),'regime':raw.get('regime'),'risk':risk,'allocation':allocation,'sector':assets.get(symbol,{}).get('sector') or 'unknown','groups':r['groups'],'quote':q,'exit_policy':xp.model_dump(),'evidence_policy':'experimental_evaluation_only'}
                d=self.submit(Ticket(symbol=symbol,side='buy',amount=risk['notional']),q,d)
                if d.get('order_id'):links[symbol]=d;self.db.set_setting('shadow_links',links)
                view=self.paper.view()
            self.reconcile();self.db.set_setting('ensemble_shadow_worker',{'status':'PAUSED_ENTRIES' if self.db.setting('ensemble_shadow_paused',False) else 'RUNNING','at':now().isoformat(),'external_execution':False})
    def reconcile(self):
        v=self.paper.view()
        if not v['orders']:return
        from sqlalchemy import select
        from backend.storage.database import Record
        order_ids=[o['id'] for o in v['orders']]
        with self.db.engine.connect() as c:
            records=c.execute(select(Record.payload).where(Record.kind=='shadow_decision',Record.payload['order_id'].as_string().in_(order_ids))).scalars()
            decisions={r['order_id']:r for r in records}
        held={p['symbol'] for p in v['positions']}
        for o in v['orders']:
            d=decisions.get(o['id'])
            if not d or d['side']!='sell' or o['symbol'] in held or o['status'] not in ('FILLED','EXPIRED','CANCELED','NO_FILL') or not o['filled_quantity']:continue
            er=self.db.get(d.get('entry_id',''));entry=er['payload'] if er else {}
            if not entry or self.db.get('shadow_outcome_'+stable_hash(entry['id'])):continue
            sells={oid for oid,x in decisions.items() if x.get('entry_id')==entry['id']};exits=[f for f in v['fills'] if f['order_id'] in sells];buys=[f for f in v['fills'] if f['order_id']==entry['order_id']];pnl=sum(f['realized_pnl'] for f in exits);cost=sum(f['quantity']*f['price']+f['fee'] for f in buys);basis=d['position']['average_cost'];ext=d['extrema']
            outcome={'entry_id':entry['id'],'symbol':o['symbol'],'completed_at':now().isoformat(),'entry_ensemble':entry['ensemble']['id'],'model_ids':[m for f in entry['ensemble']['families'] for m in f['model_ids']],'exit_reason':d['reason'],'realized_pnl':pnl,'net_return':pnl/cost if cost else None,'fees':sum(f['fee'] for f in buys+exits),'regime':entry.get('regime'),'family_attribution':{k:w*pnl for k,w in entry['ensemble']['family_weights'].items()},'maximum_favorable_excursion':max(0.,ext['high']/basis-1),'maximum_adverse_excursion':min(0.,ext['low']/basis-1),'excursion_scope':'Observed executable bid samples only; intrapoll extremes unknown','evidence_policy':'experimental_evaluation_only; never training or qualification','attribution_scope':'Allocation by entry weight, not causal alpha attribution'}
            outcome['attribution']=attribution(pnl,outcome['fees'],entry['ensemble']['family_weights'],{x['family']:x['alpha_id'] for x in entry['ensemble'].get('alpha_sources',[])},o['symbol'],entry.get('regime'),entry.get('sector'),(entry.get('allocation') or {}).get('id','legacy_risk_sizing'))
            self.db.put('ensemble_shadow_outcome',outcome,o['symbol'],record_id='shadow_outcome_'+stable_hash(entry['id']))
    def status(self):
        outcomes=[r['payload'] for kind in ('ensemble_shadow_outcome','shadow_outcome') for r in self.db.records(kind,limit=1000) if r['payload'].get('entry_id') and r['payload'].get('evidence_policy','').startswith('experimental_evaluation_only')];v=self.paper.view();by={}
        for o in outcomes:
            for k,x in o['family_attribution'].items():by[k]=by.get(k,0)+x
        return {'account':v,'label':'EXPERIMENTAL — NOT VALIDATED','paused':self.db.setting('ensemble_shadow_paused',False),'worker':self.db.setting('ensemble_shadow_worker',{}),'outcomes':outcomes,'family_attribution':by,'decisions':[r['payload'] for r in self.db.records('shadow_decision',limit=50)],'exit_policy':ExitPolicy().model_dump(),'isolation':{'manual':True,'scientific':True,'qualified':True,'training':True,'external_execution':False}}

class ManualExits:
    def __init__(self,db,paper):self.db=db;self.paper=paper
    def key(self,account,symbol,opened):return 'manual_exit_'+stable_hash([account,symbol,opened])[:32]
    def consent(self,request):
        v=self.paper.view();pos=next((p for p in v['positions'] if p['symbol']==request.symbol and p['opened_at']==request.opened_at),None)
        if not pos or v['id']!=request.account_id:raise ValueError('Position changed; review current holdings')
        value={**request.model_dump(),'enabled':request.enabled and request.policy.rule!='never','at':now().isoformat(),'scope':'local simulated exits only'};key=self.key(v['id'],pos['symbol'],pos['opened_at']);self.db.set_setting(key,value);self.db.put('manual_exit_consent',value,pos['symbol'])
        if not value['enabled']:
            automatic={r['payload']['order_id'] for r in self.db.records('manual_automatic_exit',pos['symbol'],limit=None)}
            for order in v['orders']:
                if order['id'] in automatic and order['status'] in OPEN:self.paper.cancel(order['id'])
        return value
    def status(self):
        v=self.paper.view();return {p['symbol']:self.db.setting(self.key(v['id'],p['symbol'],p['opened_at']),{'enabled':False,'policy':ExitPolicy().model_dump()}) for p in v['positions']}
    async def cycle(self,providers):
        snap=self.db.setting('model_opportunities',{});rows={r['symbol']:r for r in snap.get('rows',[])};sessions=self.db.setting('research_calendar',{}).get('sessions',[])
        for p in self.paper.view()['positions']:
            v=self.paper.view();key=self.key(v['id'],p['symbol'],p['opened_at']);consent=self.db.setting(key,{})
            if not consent.get('enabled') or any(o['symbol']==p['symbol'] and o['side']=='sell' and o['status'] in OPEN for o in v['orders']):continue
            try:q=await providers.forward_quote(p['symbol'])
            except Exception:continue
            asset=snap.get('assets',{}).get(p['symbol'],{});raw=rows.get(p['symbol'],{});e=decide(raw,asset,held=True,at=now())
            if quote_check(q,{'symbol':p['symbol'],'decided_at':(now()-timedelta(seconds=60)).isoformat()},ForwardPolicy(),now(),sessions,asset.get('asset_class','stock')):continue
            old=self.db.setting(key+'_ext',{});ext={'high':max(old.get('high',q['bid']),q['bid']),'low':min(old.get('low',q['bid']),q['bid'])};self.db.set_setting(key+'_ext',ext)
            why=trigger(p,e,q,ext,ExitPolicy(**consent['policy']),sessions,asset.get('asset_class'),volatility=raw.get('daily_volatility'))
            if not why:continue
            for o in v['orders']:
                if o['symbol']==p['symbol'] and o['side']=='buy' and o['status'] in OPEN:self.paper.cancel(o['id'])
            # Re-read consent immediately before creating the local order.
            if not self.db.setting(key,{}).get('enabled'):continue
            try:
                preview=self.paper.preview(Ticket(symbol=p['symbol'],side='sell',quantity=p['quantity']),q);preview['evidence']={'ensemble':e,'features':raw.get('votes',[]),'consent':consent,'exit_reason':why};preview['holding_rule']=consent['policy'];self.db.put('manual_preview',preview,p['symbol'],record_id=preview['id']);order=self.paper.place(Confirm(preview_id=preview['id'],confirmation='PLACE PAPER ORDER'));self.db.put('manual_automatic_exit',{'order_id':order['id'],'reason':why,'ensemble':e,'consent':consent},p['symbol'])
            except ValueError:continue
