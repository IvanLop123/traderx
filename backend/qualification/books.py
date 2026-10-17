"""Isolated quote-driven comparison books; reused by live qualification and historical replay.

Only verified quotes fill. Historical candles may generate signals but never manufacture
quotes, depth or executions. Comparators are isolated counterfactual accounts.
"""
import math
from collections import Counter
from datetime import timedelta
import pandas as pd
from backend.schemas.contracts import now
from backend.product.paper import ManualPaper,Ticket,Confirm,OPEN
from backend.research.features import stable_hash
from backend.research.forward import ForwardPolicy,quote_check
from backend.selection.policy import PortfolioPolicy
from backend.selection.risk import size,exit_reason
from backend.selection.portfolio import portfolio_metrics

class StudyPaper(ManualPaper):
    source='qualification_paper'
    account_description='Preregistered qualification comparison; never Model Paper capital'
    fill_limit=None
    def __init__(self,db,market,identity,clock,candidate=False):
        super().__init__(db,market);self.record_prefix='q'+stable_hash(identity)[:16];self.account_key=self.record_prefix+'_account';self.clock=clock;self.candidate=candidate;self.context={}
    def maximum_fill_notional(self,order,state,quote,at):
        if not self.candidate:return super().maximum_fill_notional(order,state,quote,at)
        c=self.context.get(order['symbol']);p=self.risk_policy
        if not c or c.get('health') or not c.get('trade_eligible'):return 0.
        for vote in c.get('votes',[]):
            artifact=self.db.get(vote['model_id'])
            if vote.get('weight',0)>0 and (not artifact or stable_hash(artifact['payload'])!=vote.get('artifact_hash')):return 0.
        if not c.get('feature_available_at') or not 0<=(pd.Timestamp(at)-pd.Timestamp(c['feature_available_at'])).total_seconds()<=p.maximum_data_age_days*86400:return 0.
        positions=[{**v,'symbol':s,'market_value':v['quantity']*(quote['bid'] if s==order['symbol'] else state['marks'].get(s,{}).get('bid',v['average_cost']))} for s,v in state['positions'].items() if v['quantity']>0]
        if any(v['symbol']!=order['symbol'] and (not state['marks'].get(v['symbol']) or (pd.Timestamp(at)-pd.Timestamp(state['marks'][v['symbol']]['timestamp'])).total_seconds()>120) for v in positions):return 0.
        orders=[v for v in state['orders'].values() if v['id']!=order['id']];reserve=sum((o['quantity']-o['filled_quantity'])*o['reserve_price']*(1+o['policy']['fee_bps']/1e4) for o in orders if o['side']=='buy' and o['status'] in OPEN)
        view={'equity':state['cash']+sum(v['market_value'] for v in positions),'cash':state['cash'],'available_cash':max(0,state['cash']-reserve),'positions':positions,'orders':orders}
        spread=(quote['ask']-quote['bid'])/((quote['ask']+quote['bid'])/2);cost=spread+2*(order['policy']['fee_bps']+order['policy']['slippage_bps'])/1e4;c={**c,'expected_edge':c['expected_edge']+c['estimated_roundtrip_cost']-cost}
        return size(c,view,self.assets,self.correlations,p,self.high_water,self.links,allow_existing=True)['notional']

class FrozenMarket:
    def __init__(self,assets):self.assets=assets
    def lookup(self,symbol):return self.assets[symbol]

class ComparisonBook:
    def __init__(self,db,definition,arm,scope='forward'):
        self.db=db;self.definition=definition;self.arm=arm;self.scope=scope;self.at=now();self.assets={};self.market=FrozenMarket(self.assets)
        self.id=stable_hash([definition['id'],arm,scope]);self.paper=StudyPaper(db,self.market,self.id,lambda:self.at,candidate=arm in ('candidate','incumbent'));self.p=PortfolioPolicy(**definition['risk_policy']);self.paper.initial_cash=self.p.initial_cash
        self.state_key='qbook_'+self.id[:32]
    def step(self,at,quotes,contexts,assets,correlations):
        self.at=at;self.assets.update(assets);state=self.db.setting(self.state_key,{'high_water':self.p.initial_cash,'last_features':{},'entries':{},'links':{},'extrema':{},'seen':[]});view=self.paper.view();state['high_water']=max(state['high_water'],view['equity']);self.paper.context=contexts;self.paper.risk_policy=self.p;self.paper.assets=self.assets;self.paper.correlations=correlations;self.paper.high_water=state['high_water'];self.paper.links=state['links']
        if self.scope=='forward':self.paper.actions()
        for symbol,q in quotes.items():self.paper.process(symbol,q,at)
        view=self.paper.view();sessions=self.db.setting('research_calendar',{}).get('sessions',[])
        for position in view['positions']:
            symbol=position['symbol'];q=quotes.get(symbol);c=contexts.get(symbol,{});asset=assets.get(symbol,{})
            if not q or quote_check(q,{'symbol':symbol,'decided_at':(at-timedelta(seconds=60)).isoformat()},ForwardPolicy(),at,sessions,asset.get('asset_class','stock')):continue
            if any(o['symbol']==symbol and o['side']=='sell' and o['status'] in OPEN for o in view['orders']):continue
            extrema=state['extrema'].get(symbol,{'high':q['bid'],'low':q['bid'],'opened_at':position['opened_at']})
            if extrema['opened_at']!=position['opened_at']:extrema={'high':q['bid'],'low':q['bid'],'opened_at':position['opened_at']}
            extrema.update(high=max(extrema['high'],q['bid']),low=min(extrema['low'],q['bid']));state['extrema'][symbol]=extrema
            count=int((pd.Timestamp(at)-pd.Timestamp(position['opened_at'])).total_seconds()//86400) if asset.get('asset_class')=='crypto' else sum(pd.Timestamp(position['opened_at'])<pd.Timestamp(s['close'])<=pd.Timestamp(at) for s in sessions)
            reason=exit_reason(position,{**c,'bid':q['bid'],'high_bid':extrema['high'],'data_unreliable':bool(c.get('health')) or not c,'drawdown':max(0,1-view['equity']/state['high_water'])},self.p,count) if self.arm in ('candidate','incumbent') else ('horizon' if self.arm in ('momentum','mean_reversion') and count>=self.p.horizon_sessions else None)
            if reason:
                for o in view['orders']:
                    if o['symbol']==symbol and o['side']=='buy' and o['status'] in OPEN:self.paper.cancel(o['id'])
                self.order(symbol,'sell',None,position['quantity'],q,c,reason,state)
        view=self.paper.view()
        for symbol,c in sorted(contexts.items(),key=lambda kv:(-kv[1].get('research_score',0),kv[0])):
            if self.arm=='cash' or self.arm=='incumbent' and not self.definition.get('incumbent_ids'):break
            if symbol not in self.definition['universe'] or symbol not in quotes:continue
            feature=c.get('feature_available_at')
            if not feature or pd.Timestamp(feature)<pd.Timestamp(self.definition['registered_at']) or pd.Timestamp(feature)>pd.Timestamp(at):continue
            if state['last_features'].get(symbol)==feature:continue
            asset=assets[symbol];held={p['symbol'] for p in view['positions']}|{o['symbol'] for o in view['orders'] if o['status'] in OPEN}
            if symbol in held:continue
            if self.arm in ('buy_hold','equal_weight') and symbol in state['seen']:continue
            if self.arm=='buy_hold' and symbol!=self.definition['buy_hold_symbol']:continue
            q=quotes[symbol];reasons=quote_check(q,{'symbol':symbol,'decided_at':(at-timedelta(seconds=60)).isoformat()},ForwardPolicy(),at,sessions,asset['asset_class'])
            if reasons:continue # A later valid quote may retry the same feature; no fake fills.
            state['last_features'][symbol]=feature
            if self.arm in ('candidate','incumbent'):
                spread=(q['ask']-q['bid'])/((q['ask']+q['bid'])/2);cost=spread+(60 if asset['asset_class']=='stock' or asset.get('liquidity_bucket')=='limited' else 20)/1e4
                c={**c,'expected_edge':(c.get('expected_edge') or 0)+(c.get('estimated_roundtrip_cost') or 0)-cost};risk=size(c,view,assets,correlations,self.p,state['high_water'],state['links']);amount=risk['notional'];reason='; '.join(risk['reasons'])
            else:
                signal=self.arm in ('buy_hold','equal_weight') or self.arm=='momentum' and c.get('return_20',0)>0 or self.arm=='mean_reversion' and c.get('rsi',100)<30
                amount=min(view['available_cash'],self.p.initial_cash/(len(self.definition['universe']) if self.arm=='equal_weight' else 1 if self.arm=='buy_hold' else self.p.maximum_positions)) if signal else 0.;amount=min(amount,(asset.get('eligibility',{}).get('mean_dollar_volume') or 0)*self.p.maximum_adv_fraction);reason='Frozen benchmark allocation' if signal else 'Benchmark stays in cash';risk={'notional':amount}
            rid='qdecision_'+stable_hash([self.id,symbol,feature,'buy']);payload={'id':rid,'definition_id':self.definition['id'],'book_id':self.id,'arm':self.arm,'scope':self.scope,'symbol':symbol,'at':at.isoformat(),'feature_available_at':feature,'candidate':c,'risk':risk,'reason':reason,'status':'NO_TRADE','side':'buy','evidence_policy':'historical_debug_only' if self.scope!='forward' else 'quarantined_evaluation'}
            if amount>0 and asset.get('eligibility',{}).get('eligible'):
                order=self.order(symbol,'buy',amount,None,q,c,reason,state)
                if order:payload.update(status='ORDERED',order_id=order['id'])
                else:payload['reason']=state.get('last_order_error','Simulator rejected order')
            self.db.put('qualification_decision',payload,symbol,record_id=rid);view=self.paper.view()
        self.reconcile(state,at);view=self.paper.view();state['high_water']=max(state['high_water'],view['equity']);state['drawdown']=max(0,1-view['equity']/state['high_water']);self.db.set_setting(self.state_key,state)
        # Valid observed bid marks only. Closed-session marks may be carried for UI but cannot count as new independent price evidence.
        fresh=all(not p.get('corporate_action_review') and p.get('mark_at') and 0<=(pd.Timestamp(at)-pd.Timestamp(p['mark_at'])).total_seconds()<=self.definition['criteria']['maximum_mark_age_minutes']*60 for p in view['positions'])
        mark={'book_id':self.id,'definition_id':self.definition['id'],'arm':self.arm,'scope':self.scope,'at':at.isoformat(),'date':at.date().isoformat(),'equity':view['equity'],'cash':view['cash'],'fees':view['fees'],'fresh':fresh,'exposure':(view['equity']-view['cash'])/view['equity'],'concentration':sum(p['allocation']**2 for p in view['positions']),'regime':(Counter(c.get('regime','unknown') for c in contexts.values()).most_common(1) or [('unknown',0)])[0][0],'turnover':sum(f['quantity']*f['price'] for f in view['fills'])/self.p.initial_cash}
        key='qmark_'+stable_hash([self.id,mark['date']])[:32];previous=self.db.setting(key)
        # Keep the last valid observed session valuation instead of replacing it with overnight stale marks.
        if fresh or not previous or not previous.get('fresh'):self.db.set_setting(key,mark)
        return view
    def order(self,symbol,side,amount,quantity,q,c,reason,state):
        try:
            preview=self.paper.preview(Ticket(symbol=symbol,side=side,amount=amount,quantity=quantity),q);order=self.paper.place(Confirm(preview_id=preview['id'],confirmation='PLACE PAPER ORDER'))
            if side=='buy':state['entries'][symbol]={'order_id':order['id'],'candidate':c,'at':self.at.isoformat(),'reason':reason};state['links'][symbol]=c.get('groups') or ['benchmark'];state['seen']=list(set(state['seen']+[symbol]))
            return order
        except ValueError as exc:
            state['last_order_error']=str(exc);return None
    def reconcile(self,state,at):
        view=self.paper.view();held={p['symbol'] for p in view['positions']};fills=view['fills']
        for symbol,entry in list(state['entries'].items()):
            if symbol in held or any(o['symbol']==symbol and o['status'] in OPEN for o in view['orders']):continue
            buys=[f for f in fills if f['order_id']==entry['order_id']];sells=[f for f in fills if f['symbol']==symbol and f['side']=='sell' and f['at']>=entry['at']]
            if not buys or not sells:continue
            cost=sum(f['quantity']*f['price']+f['fee'] for f in buys);pnl=sum(f['realized_pnl'] for f in sells);c=entry['candidate']
            outcome={'book_id':self.id,'definition_id':self.definition['id'],'arm':self.arm,'scope':self.scope,'symbol':symbol,'decided_at':entry['at'],'completed_at':at.isoformat(),'maximum_favorable_excursion':state['extrema'].get(symbol,{}).get('high',cost/sum(f['quantity'] for f in buys))/(cost/sum(f['quantity'] for f in buys))-1,'maximum_adverse_excursion':state['extrema'].get(symbol,{}).get('low',cost/sum(f['quantity'] for f in buys))/(cost/sum(f['quantity'] for f in buys))-1,'excursion_scope':'Observed bid quotes only; between-poll extremes unavailable','net_return':pnl/cost,'realized_pnl':pnl,'entry_cost':cost,'probability':c.get('probability'),'regime':c.get('regime'),'liquidity_bucket':c.get('liquidity_bucket'),'model_ids':[v['model_id'] for v in c.get('votes',[]) if v.get('weight',0)>0],'evidence_policy':'quarantined_evaluation' if self.scope=='forward' else 'historical_debug_only'}
            self.db.put('qualification_outcome',outcome,symbol,record_id='qoutcome_'+stable_hash(entry['order_id']));del state['entries'][symbol]
