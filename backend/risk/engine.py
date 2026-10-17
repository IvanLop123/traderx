"""Deterministic risk and paper accounting under one durable transaction."""
import json
import math
from datetime import datetime, timedelta
from sqlalchemy import select
from backend.schemas.contracts import now, uid, TradeCandidate, RiskAssessment, ApprovedOrder, RejectedOrder, ExecutionReport
from backend.storage.database import Record, Setting
from scripts.provider_common import ROOT
from backend.risk.config import load_limits

class PaperEngine:
    def __init__(self,db):
        self.db=db; self.limits=load_limits()
    def initial(self):
        cash=self.limits['initial_cash']
        return {'cash':cash,'initial_cash':cash,'positions':{},'realized_pnl':0.,'fees':0.,'equity':cash,'peak_equity':cash,'day_start_equity':cash,'day':now().date().isoformat(),'week':list(now().isocalendar()[:2]),'week_start_equity':cash,'kill_switch':True,'mode':'INTERNAL_PAPER'}
    def snapshot(self):
        return self.db.setting('portfolio',self.initial())
    def halt(self,halt=True):
        with self.db.transaction() as s:
            row=s.get(Setting,'portfolio'); state=dict(row.value) if row else self.initial()
            state['kill_switch']=halt; s.merge(Setting(key='portfolio',value=state))
            s.add(Record(kind='audit',symbol='',available_at=now().isoformat(),payload={'action':'halt' if halt else 'resume_internal_paper','timestamp':now().isoformat()}))
        return state
    def mark(self,quotes):
        with self.db.transaction() as s:
            row=s.get(Setting,'portfolio'); state=json.loads(json.dumps(row.value)) if row else self.initial()
            for symbol,p in state['positions'].items():
                if symbol in quotes:
                    try:price=float(quotes[symbol]['price'])
                    except (ValueError,TypeError,KeyError):price=float('nan')
                    if not math.isfinite(price) or price<=0:state['kill_switch']=True;state['integrity_warning']='INVALID_MARKET_MARK';continue
                    p['market_price']=price
            state['equity']=state['cash']+sum(p['quantity']*p['market_price'] for p in state['positions'].values())
            state['peak_equity']=max(state['peak_equity'],state['equity'])
            if state['day']!=now().date().isoformat():
                state['day']=now().date().isoformat(); state['day_start_equity']=state['equity']
            if state.get('week')!=list(now().isocalendar()[:2]):
                state['week']=list(now().isocalendar()[:2]);state['week_start_equity']=state['equity']
            if state['equity']<state.get('week_start_equity',state['equity'])*(1-self.limits['max_weekly_loss_fraction']):state['kill_switch']=True
            if state['equity']<state['day_start_equity']*(1-self.limits['max_daily_loss_fraction']) or state['equity']<state['peak_equity']*(1-self.limits['max_drawdown_fraction']): state['kill_switch']=True
            s.merge(Setting(key='portfolio',value=state))
        return state
    def _reasons(self,c,state,quote,provider_ok=True):
        t=now(); reasons=[]; l=self.limits; equity=state['equity']
        state_values=[state.get(k,0) for k in ('cash','equity','peak_equity','day_start_equity')]+[v for p in state['positions'].values() for k,v in p.items() if k in ('quantity','market_price','average_cost')]
        if any(not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 for v in state_values):return ['PORTFOLIO_STATE_INVALID']
        if state['kill_switch']: reasons.append('GLOBAL_KILL_SWITCH')
        if not provider_ok: reasons.append('PROVIDER_NOT_HEALTHY')
        if c.expires_at<=t or (t-c.created_at).total_seconds()>l['max_candidate_age_seconds']: reasons.append('CANDIDATE_EXPIRED')
        if c.created_at>t+timedelta(seconds=5): reasons.append('FUTURE_CANDIDATE')
        try:stamp=datetime.fromisoformat(quote.get('timestamp','1970-01-01T00:00:00+00:00').replace('Z','+00:00'))
        except (ValueError,TypeError,AttributeError):return reasons+['STALE_OR_INVALID_QUOTE']
        if stamp.tzinfo is None or (t-stamp).total_seconds()>l['max_quote_age_seconds'] or stamp>t+timedelta(seconds=5): reasons.append('STALE_OR_INVALID_QUOTE')
        try:
            price=float(quote.get('price',0)); bid=float(quote.get('bid',0)); ask=float(quote.get('ask',0)); volume=float(quote.get('volume',0))
        except (ValueError,TypeError):return reasons+['INVALID_MARKET']
        if not all(math.isfinite(v) for v in [price,bid,ask,volume,equity]):return reasons+['INVALID_MARKET']
        if min(price,bid,ask)<=0 or ask<bid: reasons.append('INVALID_MARKET')
        elif (ask-bid)/price*1e4>l['max_spread_bps']: reasons.append('SPREAD_LIMIT')
        if price and abs(c.entry_price/price-1)>.01: reasons.append('ENTRY_PRICE_CHANGED')
        if c.direction=='buy' and c.expected_edge<=0: reasons.append('NO_NET_EDGE')
        if c.asset.asset_class not in ('crypto','stock','etf'): reasons.append('INSTRUMENT_NOT_SUPPORTED_FOR_PAPER')
        if equity<=0: return reasons+['NONPOSITIVE_EQUITY']
        positions=state['positions']; held=positions.get(c.asset.symbol,{}).get('quantity',0)
        delta=c.quantity if c.direction=='buy' else -c.quantity
        if held+delta<0: reasons.append('SHORTING_DISABLED')
        if c.direction=='buy':
            if (held+c.quantity)*price>equity*l['max_position_fraction']: reasons.append('POSITION_CONCENTRATION')
            gross=sum(p['quantity']*p['market_price'] for p in positions.values())+c.quantity*price
            if gross>equity*l['max_gross_fraction']: reasons.append('GROSS_EXPOSURE')
            if gross>equity*l['max_net_fraction']:reasons.append('NET_EXPOSURE')
            exposure=sum(p['quantity']*p['market_price'] for p in positions.values() if p['asset_class']==c.asset.asset_class or {p['asset_class'],c.asset.asset_class}<={'stock','etf'})+c.quantity*price
            if exposure>equity*l['max_asset_class_fraction']: reasons.append('ASSET_CLASS_EXPOSURE')
            if c.quantity*ask*(1+(l['fee_bps']+l['slippage_bps'])/1e4)>state['cash']: reasons.append('INSUFFICIENT_CASH')
        if c.quantity>float(quote.get('volume',0))*l['max_participation']: reasons.append('LIQUIDITY_LIMIT')
        if equity<state['day_start_equity']*(1-l['max_daily_loss_fraction']): reasons.append('DAILY_LOSS_LIMIT')
        if equity<state['peak_equity']*(1-l['max_drawdown_fraction']): reasons.append('DRAWDOWN_LIMIT')
        if equity<state.get('week_start_equity',equity)*(1-l['max_weekly_loss_fraction']):reasons.append('WEEKLY_LOSS_LIMIT')
        if c.direction=='buy' and not reasons:
            from backend.risk.analytics import portfolio_risk
            stress=portfolio_risk(self.db,state,l,c)
            if any(v>l['max_sector_fraction'] for k,v in stress['sector_fractions'].items() if k not in ('CRYPTO','PERPETUAL','PREDICTION')):reasons.append('SECTOR_EXPOSURE')
            if not stress['covariance_available'] and l['require_covariance_for_entry']:reasons.append('COVARIANCE_UNAVAILABLE')
            if stress['annualized_volatility'] is not None and stress['annualized_volatility']>l['max_portfolio_annual_volatility']:reasons.append('PORTFOLIO_VOLATILITY_LIMIT')
            if any(g['gross_fraction']>l['max_correlated_group_fraction'] for g in stress['correlated_groups']):reasons.append('CORRELATED_EXPOSURE')
        return reasons
    def assess(self,c:TradeCandidate,quote,provider_ok=True):
        if not isinstance(c,TradeCandidate): raise TypeError('TradeCandidate required')
        with self.db.transaction() as s:
            existing=s.get(Record,c.id)
            if not existing or existing.kind!='candidate' or existing.payload!=c.model_dump(mode='json'): raise ValueError('Candidate must be persisted by research')
            state_row=s.get(Setting,'portfolio'); state=state_row.value if state_row else self.initial()
            reasons=self._reasons(c,state,quote,provider_ok)
            assessment=RiskAssessment(candidate_id=c.id,approved=not reasons,reasons=reasons,limits=self.limits)
            s.add(Record(id=assessment.id,kind='risk_assessment',symbol=c.asset.symbol,available_at=now().isoformat(),payload=assessment.model_dump(mode='json')))
            if reasons: return RejectedOrder(candidate_id=c.id,assessment_id=assessment.id,reasons=reasons)
            order=ApprovedOrder(candidate_id=c.id,assessment_id=assessment.id,asset=c.asset,side=c.direction,quantity=c.quantity,limit_price=c.entry_price*1.01 if c.direction=='buy' else c.entry_price*.99,expires_at=c.expires_at)
            s.add(Record(id=order.id,kind='approved_order',symbol=c.asset.symbol,available_at=now().isoformat(),payload=order.model_dump(mode='json')))
            return order
    def execute(self,order:ApprovedOrder,quote,provider_ok=True):
        if type(order) is not ApprovedOrder: raise TypeError('Execution accepts only ApprovedOrder')
        if order.venue!='internal_paper':raise ValueError('Order requires its approved execution venue')
        with self.db.transaction() as s:
            saved=s.get(Record,order.id)
            if not saved or saved.kind!='approved_order' or saved.payload!=order.model_dump(mode='json'): raise ValueError('No matching durable risk approval')
            prior=s.get(Record,'fill-'+order.id)
            if prior: return prior.payload
            a=s.get(Record,order.assessment_id)
            if not a or not a.payload.get('approved') or a.payload['candidate_id']!=order.candidate_id: raise ValueError('Risk approval invalid')
            c=TradeCandidate.model_validate(s.get(Record,order.candidate_id).payload)
            row=s.get(Setting,'portfolio'); state=json.loads(json.dumps(row.value)) if row else self.initial()
            reasons=self._reasons(c,state,quote,provider_ok)
            if order.expires_at<=now(): reasons.append('ORDER_EXPIRED')
            if reasons: raise ValueError(', '.join(reasons))
            # A candidate can fill only once, even if it was risk-assessed twice.
            used=s.get(Record,'executed-'+c.id)
            if used: raise ValueError('CANDIDATE_ALREADY_EXECUTED')
            l=self.limits; side=1 if order.side=='buy' else -1
            price=float(quote['ask' if side==1 else 'bid'])*(1+side*l['slippage_bps']/1e4)
            if (side==1 and price>order.limit_price) or (side==-1 and price<order.limit_price): raise ValueError('LIMIT_PRICE_NOT_REACHED')
            fill_reasons=self._reasons(c.model_copy(update={'entry_price':price}),state,{**quote,'price':price,'bid':price,'ask':price},provider_ok)
            if fill_reasons:raise ValueError(', '.join(fill_reasons))
            amount=price*order.quantity; fee=amount*l['fee_bps']/1e4
            state['cash']-=side*amount+fee; state['fees']+=fee
            p=state['positions'].get(order.asset.symbol,{'quantity':0,'average_cost':0,'market_price':price,'asset_class':order.asset.asset_class})
            if side==1: p['average_cost']=(p['average_cost']*p['quantity']+amount+fee)/max(1e-12,p['quantity']+order.quantity)
            else: state['realized_pnl']+=(price-p['average_cost'])*order.quantity-fee
            p['quantity']+=side*order.quantity; p['market_price']=float(quote['price']); state['positions'][order.asset.symbol]=p
            if abs(p['quantity'])<1e-12:state['positions'].pop(order.asset.symbol)
            state['equity']=state['cash']+sum(v['quantity']*v['market_price'] for v in state['positions'].values())
            s.merge(Setting(key='portfolio',value=state))
            report=ExecutionReport(order_id=order.id,status='filled',quantity=order.quantity,price=price,fee=fee).model_dump(mode='json')
            s.add(Record(id='fill-'+order.id,kind='fill',symbol=order.asset.symbol,available_at=now().isoformat(),payload=report))
            s.add(Record(id='executed-'+c.id,kind='audit',symbol=order.asset.symbol,available_at=now().isoformat(),payload={'order_id':order.id,'candidate_id':c.id}))
            return report
