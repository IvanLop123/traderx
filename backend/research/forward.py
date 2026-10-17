"""Isolated hypothetical forward ledger. This module has no broker execution dependency."""
from datetime import timedelta
import math,json,hashlib,asyncio
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import Field
from backend.schemas.contracts import Contract,now
from backend.storage.database import Record,Setting
from backend.research.features import stable_hash,build_frame
from backend.research.universe import load_universe,eligible_at
from backend.research.history import HistoryStore

class ForwardPolicy(Contract):
    initial_cash:float=Field(default=100000,gt=0,le=10000000)
    maximum_position_fraction:float=Field(default=.1,gt=0,le=.25)
    participation:float=Field(default=.05,gt=0,le=.1)
    fee_bps:float=Field(default=5,ge=0,le=100)
    slippage_bps:float=Field(default=5,ge=0,le=100)
    latency_seconds:int=Field(default=5,ge=1,le=3600)
    maximum_quote_age_seconds:int=Field(default=30,ge=1,le=120)
    entry_expiry_seconds:int=Field(default=3600,ge=30,le=86400)
    probability_threshold:float=Field(default=.55,ge=.5,le=.99)
    maximum_spread_bps:float=Field(default=50,gt=0,le=200)

class EnrollRequest(Contract):
    model_id:str
    symbol:str|None=None
    policy:ForwardPolicy=Field(default_factory=ForwardPolicy)

class ReleaseRequest(Contract):
    study_id:str
    minimum_age_days:int=Field(default=90,ge=90,le=3650)
    reason:str=Field(min_length=20,max_length=1000)

_CACHE={}
def study_prediction(db,model_id):
    """Reconstruct frozen local estimators from immutable JSON, never arbitrary pickle."""
    from backend.research.studies import fit_bundle,targets
    from threadpoolctl import threadpool_limits
    row=db.get(model_id)
    if row and row['kind']=='auto_model':
        from backend.research.autonomous.forward import prediction
        return prediction(db,model_id)
    if not row or row['kind']!='ml_study':raise ValueError('A frozen model comparison is required')
    model=row['payload'];w=model['selected'];h=w['horizon'];data=db.get('input-'+model_id)['payload'];fingerprint=stable_hash(data)
    if model_id not in _CACHE or _CACHE[model_id][0]!=fingerprint:
        d=pd.DataFrame(data['bars']);x=pd.DataFrame(data['matrix']['data'],columns=data['matrix']['columns']).astype(float)
        end=model['periods']['development_end_index'];fit_end=int(end*.8);fit=np.arange(60,fit_end-h-2);cal=np.arange(fit_end,end-h-2)
        req=model['request'];cost=2*(req['fee_bps']+req['slippage_bps']+req['spread_bps']/2)/1e4;y,labels,_=targets(d,h,cost)
        with threadpool_limits(limits=1):bundle=fit_bundle(x,y,labels[w['target']],fit,cal,data['groups'],w['families'],w['algorithm'],w['parameters'])
        if len(_CACHE)>=24:_CACHE.pop(next(iter(_CACHE)))
        _CACHE[model_id]=(fingerprint,bundle)
    bundle=_CACHE[model_id][1];d,x,groups,_=build_frame(db,model['symbol']);names=bundle[1];medians=bundle[2]
    missing=[n for n in names if n not in x or pd.isna(x.iloc[-1].get(n))]
    values=x.reindex(columns=names).iloc[[-1]].fillna(medians)
    with threadpool_limits(limits=1):expected,p=bundle[0]([0],override=values)
    return {'model_id':model_id,'model_hash':stable_hash(model),'symbol':model['symbol'],'features':{n:float(values.iloc[0][n]) for n in names},'imputed_features':missing,'feature_available_at':str(d.iloc[-1].available_at),'feature_families':model['feature_families'],'data_version':HistoryStore(db).manifest(model['symbol']),'entry_delay_bars':2,'prediction':float(expected[0]),'probability':float(p[0]),'probability_target':w['target'],'uncertainty':model['latest']['development_residual_std'],'horizon':h,'regime':{1:'uptrend',0:'range',-1:'downtrend'}.get(int(x.iloc[-1].regime_trend),'unknown')}

def quote_check(q,decision,policy,at,sessions,asset_class):
    reasons=[];t=pd.Timestamp(at)
    if q.get('halted'):return ['Security halted']
    try:
        qt=pd.Timestamp(q['timestamp']);seen=pd.Timestamp(q['observed_at'])
        numbers=[float(q[k]) for k in ('bid','ask','bid_size','ask_size')]
        if not all(math.isfinite(v) and v>0 for v in numbers) or numbers[1]<numbers[0]:return ['Invalid two-sided depth']
        if qt.tzinfo is None or seen.tzinfo is None:reasons.append('Missing quote timezone')
        elif qt>t or seen>t or (t-qt).total_seconds()>policy.maximum_quote_age_seconds or (t-seen).total_seconds()>policy.maximum_quote_age_seconds:reasons.append('Stale or future quote')
        if qt<max(pd.Timestamp(decision['decided_at'])+pd.Timedelta(seconds=policy.latency_seconds),pd.Timestamp(decision.get('entry_not_before') or decision['decided_at'])):reasons.append('Execution delay not elapsed')
        if q.get('depth_units')!='base_units':reasons.append('Displayed depth units unverified')
        if q['symbol']!=decision['symbol']:reasons.append('Wrong asset')
        spread=(numbers[1]-numbers[0])/((numbers[0]+numbers[1])/2)*10000
        if spread>policy.maximum_spread_bps:reasons.append('Spread outside limit')
        if asset_class!='crypto' and not any(pd.Timestamp(s['open'])<=qt<pd.Timestamp(s['close']) and pd.Timestamp(s['open'])<=t<pd.Timestamp(s['close']) for s in sessions):reasons.append('Market closed or calendar unavailable')
    except (KeyError,ValueError,TypeError):reasons.append('Quote or displayed depth unavailable')
    return reasons

class ForwardStudies:
    def __init__(self,db):self.db=db
    def studies(self):
        with Session(self.db.engine) as s:return [r.value for r in s.scalars(select(Setting).where(Setting.key.like('forward_state_%')))]
    def enroll(self,request):
        model=self.db.get(request.model_id)
        if not model or model['kind'] not in ('ml_study','strategy_model','auto_model'):raise ValueError('Select a saved frozen research model')
        if model['kind']=='auto_model':
            result=self.db.get(model['payload']['registration_id']+'-result')
            if not result or result['payload']['status']!='CHALLENGER':raise ValueError('Historical challenger gates required')
            from backend.research.autonomous.schema import ExperimentSpec
            spec=ExperimentSpec.model_validate(model['payload']['spec'])
            frozen=ForwardPolicy(fee_bps=spec.fee_bps,slippage_bps=spec.slippage_bps,participation=spec.maximum_participation,maximum_position_fraction=min(.25,spec.hypothetical_notional/100000))
            if request.policy.model_dump()!=frozen.model_dump():raise ValueError('Use the frozen challenger forward policy')
        symbol=request.symbol if model['kind']=='strategy_model' else model['payload']['symbol']
        if not symbol:raise ValueError('Select an asset for the pooled strategy model')
        instrument=next((i for i in load_universe(self.db).instruments if i.symbol==symbol),None)
        if instrument and instrument.asset_class=='stock' and (instrument.market_cap is None or instrument.market_cap<2e9):
            request.policy=request.policy.model_copy(update={'slippage_bps':max(25,request.policy.slippage_bps),'participation':min(.02,request.policy.participation)})
        if model['kind']=='strategy_model':
            instrument=next((i for i in load_universe(self.db).instruments if i.symbol==symbol),None)
            if not instrument or instrument.asset_class!=model['payload']['asset_class']:raise ValueError('Model asset class does not match selected asset')
        if symbol not in {i.symbol for i in load_universe(self.db).instruments}:raise ValueError('Asset is not in configured research universe')
        sid=stable_hash([request.model_id,request.policy.model_dump(),*([symbol] if model['kind']=='strategy_model' else [])])[:32];key='forward_state_'+sid
        with self.db.transaction() as s:
            existing=s.get(Setting,key)
            if existing:return existing.value
            active=list(s.scalars(select(Setting).where(Setting.key.like('forward_state_%'))))
            if sum(x.value['state']=='collecting' for x in active)>=500:raise ValueError('At most 500 simultaneous studies')
            state={'id':sid,'model_id':request.model_id,'model_hash':stable_hash(model['payload']),'symbol':symbol,'families':model['payload'].get('feature_families') or [model['payload']['family']],'started_at':now().isoformat(),'state':'collecting','cash':request.policy.initial_cash,'policy':request.policy.model_dump(),'pending':None,'last_feature_time':None,'completed':0,'realized_pnl':0.,'evidence_policy':'quarantined_evaluation','corporate_action_review':False}
            s.add(Setting(key=key,value=state))
        self.db.put('forward_enrollment',state,state['symbol']);return state
    def retire(self,sid):
        with self.db.transaction() as s:
            row=s.get(Setting,'forward_state_'+sid)
            if not row:raise ValueError('Unknown forward study')
            if row.value.get('pending'):raise ValueError('Resolve the existing hypothetical position before retirement')
            row.value={**row.value,'state':'retired','retired_at':now().isoformat()}
        return row.value
    def decide(self,sid,prediction,at=None,eligibility=None):
        at=at or now();key='forward_state_'+sid
        with self.db.transaction() as session:
            row=session.get(Setting,key)
            if not row or row.value['state']!='collecting':return
            state=dict(row.value);policy=ForwardPolicy(**state['policy'])
            if state['pending'] or state['last_feature_time']==prediction['feature_available_at']:return
            if prediction['symbol']!=state['symbol'] or prediction['model_id']!=state['model_id'] or prediction['model_hash']!=state['model_hash']:raise ValueError('Model identity changed')
            if not pd.Timestamp(state['started_at'])<=pd.Timestamp(prediction['feature_available_at'])<=pd.Timestamp(at):return
            if not all(math.isfinite(float(v)) for v in [prediction['prediction'],prediction['probability'],prediction['uncertainty'],*prediction['features'].values()]):raise ValueError('Nonfinite prediction')
            if not 0<=prediction['probability']<=1 or prediction['uncertainty']<0:raise ValueError('Invalid uncertainty or probability')
            reasons=[];cost=2*(policy.fee_bps+policy.slippage_bps)/10000
            if prediction['probability']<=.5:reasons.append('Weak probability')
            elif prediction['probability']<=policy.probability_threshold:reasons.append('Probability below policy threshold')
            if prediction['prediction']<=cost:reasons.append('Expected return after estimated costs is nonpositive')
            if prediction.get('imputed_features'):reasons.append('Missing current features')
            if not eligibility or not eligibility.get('eligible'):reasons.extend((eligibility or {}).get('reasons') or ['Insufficient eligibility data'])
            if state.get('corporate_action_review'):reasons.append('Corporate action requires position review')
            entry_not_before=at
            if prediction.get('entry_delay_bars')==2:
                if state['symbol'].endswith('-USD'):entry_not_before=max(at,(pd.Timestamp(prediction['feature_available_at'])+pd.Timedelta(days=1)).to_pydatetime())
                else:
                    sessions=self.db.setting('research_calendar',{}).get('sessions',[])
                    future=[v for v in sessions if pd.Timestamp(v['open'])>=pd.Timestamp(prediction['feature_available_at'])]
                    if len(future)>=2:entry_not_before=max(at,pd.Timestamp(future[1]['open']).to_pydatetime())
                    else:reasons.append('Future trading session calendar unavailable')
            intended=min(state['cash'],policy.initial_cash*policy.maximum_position_fraction)
            if eligibility and eligibility.get('mean_dollar_volume') is not None:intended=min(intended,eligibility['mean_dollar_volume']*.0001)
            if intended<=0:reasons.append('No available hypothetical cash')
            did='forward_decision_'+stable_hash([sid,prediction['feature_available_at']]);status='CASH' if reasons else 'PENDING'
            payload={**prediction,'id':did,'study_id':sid,'decided_at':at.isoformat(),'entry_not_before':entry_not_before.isoformat(),'decision':status,'decision_result':'NO_TRADE' if reasons else 'PENDING_EXECUTION','reasons':reasons or ['Positive estimated edge and sufficient probability; actual spread checked at fill'],'intended_entry':{'side':'none' if reasons else 'buy','notional':0. if reasons else intended,'price_rule':'fresh ask plus adverse slippage; never a close or midpoint'},'position_size':{'maximum_notional':0. if reasons else intended},'exit_rule':{'type':'elapsed_calendar_days' if state['symbol'].endswith('-USD') else 'completed_trading_sessions','horizon':prediction['horizon'],'price_rule':'fresh bid less adverse slippage'},'eligibility':eligibility,'strategy_family':prediction.get('strategy_family','+'.join(state['families'])),'asset_class':prediction.get('asset_class','crypto' if state['symbol'].endswith('-USD') else 'stock'),'liquidity_bucket':prediction.get('liquidity_bucket','unknown'),'market_cap_bucket':prediction.get('market_cap_bucket','unknown'),'policy':state['policy'],'evidence_policy':'quarantined_evaluation'}
            session.add(Record(id=did,kind='forward_decision',symbol=state['symbol'],available_at=at.isoformat(),payload=payload))
            state['last_feature_time']=prediction['feature_available_at']
            state['pending']={'decision_id':did,'budget':intended,'spent':0.,'quantity':0.,'entry_quantity':0.,'entry_cost':0.,'exit_proceeds':0.,'status':'cash' if reasons else 'entry','expires_at':(entry_not_before+timedelta(seconds=policy.entry_expiry_seconds)).isoformat(),'first_fill_at':None,'last_quote':None,'last_quote_at':None,'mfe':None,'mae':None,'marks':0,'exit_at':None,'cash_reference_bid':None}
            row.value=state
        return payload
    def process_quote(self,sid,q,at=None):
        at=at or now();sessions=self.db.setting('research_calendar',{}).get('sessions',[]);key='forward_state_'+sid
        with self.db.transaction() as session:
            row=session.get(Setting,key)
            if not row or not row.value.get('pending'):return
            state=json.loads(json.dumps(row.value));position=state['pending'];decision=session.get(Record,position['decision_id']).payload;policy=ForwardPolicy(**state['policy']);asset_class='crypto' if state['symbol'].endswith('-USD') else 'stock'
            def save_event(kind,payload,identity):session.add(Record(id=kind+'_'+stable_hash(identity),kind=kind,symbol=state['symbol'],available_at=at.isoformat(),payload=payload))
            def finish(status):
                outcome={'study_id':sid,'decision_id':decision['id'],'model_id':state['model_id'],'symbol':state['symbol'],'families':state['families'],'regime':decision['regime'],'strategy_family':decision.get('strategy_family','+'.join(state['families'])),'asset_class':decision.get('asset_class','unknown'),'liquidity_bucket':decision.get('liquidity_bucket','unknown'),'market_cap_bucket':decision.get('market_cap_bucket','unknown'),'status':status,'execution_result':'NO_FILL' if status=='UNFILLED' else 'NO_TRADE' if status=='CASH_EVALUATED' else 'COMPLETED','cash_price_change':(position.get('last_bid',0)/position['cash_reference_bid']-1) if position.get('cash_reference_bid') else None,'completed_at':at.isoformat(),'dividends':position.get('dividends',0),'realized_pnl':position['exit_proceeds']+position.get('dividends',0)-position['entry_cost'],'entry_cost':position['entry_cost'],'exit_proceeds':position['exit_proceeds'],'filled_quantity':position['entry_quantity'],'maximum_favorable_excursion':position['mfe'],'maximum_adverse_excursion':position['mae'],'observed_marks':position['marks'],'excursion_scope':'Observed bid quotes only; intrapoll extrema unknown','evidence_policy':'quarantined_evaluation'}
                save_event('forward_outcome',outcome,decision['id']);state['completed']+=1;state['realized_pnl']+=outcome['realized_pnl'];state['pending']=None
            if position['status']=='entry' and pd.Timestamp(at)>=pd.Timestamp(position['expires_at']):
                if not position['quantity']:finish('UNFILLED');row.value=state;return
                position['status']='holding'
            if state.get('corporate_action_review'):state['last_status']='Corporate action review required';row.value=state;return
            errors=quote_check(q,decision,policy,at,sessions,asset_class)
            if errors:state['last_status']='; '.join(errors);row.value=state;return
            qid=stable_hash([q['symbol'],q['timestamp'],q['bid'],q['ask'],q['bid_size'],q['ask_size']])
            if qid==position['last_quote'] or (position['last_quote_at'] and pd.Timestamp(q['timestamp'])<=pd.Timestamp(position['last_quote_at'])):return
            position['last_quote']=qid;position['last_quote_at']=q['timestamp'];fee=policy.fee_bps/10000;slip=policy.slippage_bps/10000
            # An entry is rejected when the actual spread consumes the predicted net edge.
            actual_cost=2*(policy.fee_bps+policy.slippage_bps)/10000+(q['ask']-q['bid'])/q['ask']
            if position['status']=='entry' and decision['prediction']<=actual_cost:state['last_status']='Observed spread consumes expected edge';row.value=state;return
            if position['status']=='cash':
                position['cash_reference_bid']=position['cash_reference_bid'] or q['bid'];position['last_bid']=q['bid'];position['marks']+=1
                if not position['exit_at']:
                    if asset_class=='crypto':position['exit_at']=(at+timedelta(days=decision['horizon'])).isoformat()
                    else:
                        future=[v for v in sessions if pd.Timestamp(v['open'])>pd.Timestamp(at)]
                        if len(future)>=decision['horizon']:position['exit_at']=future[decision['horizon']-1]['open']
                save_event('forward_mark',{'study_id':sid,'decision_id':decision['id'],'at':at.isoformat(),'quote_timestamp':q['timestamp'],'bid':q['bid'],'ask':q['ask'],'quantity':0,'regime':decision['regime']},[sid,qid])
                if position['exit_at'] and pd.Timestamp(at)>=pd.Timestamp(position['exit_at']):finish('CASH_EVALUATED')
                state['last_status']='Cash decision; collecting subsequent prices';row.value=state;return
            if position['exit_at'] and pd.Timestamp(at)>=pd.Timestamp(position['exit_at']):position['status']='exit'
            side='buy' if position['status']=='entry' else 'sell' if position['status']=='exit' else None
            if side:
                price=q['ask']*(1+slip) if side=='buy' else q['bid']*(1-slip)
                available=q['ask_size' if side=='buy' else 'bid_size']*policy.participation
                wanted=min((position['budget']-position['spent'])/(price*(1+fee)),state['cash']/(price*(1+fee))) if side=='buy' else position['quantity']
                quantity=max(0,min(available,wanted));quantity=math.floor(quantity) if asset_class=='stock' else quantity
                if quantity>1e-10:
                    charge=quantity*price*fee
                    if side=='buy':
                        cost=quantity*price+charge;state['cash']-=cost;position['spent']+=cost;position['entry_cost']+=cost;position['quantity']+=quantity;position['entry_quantity']+=quantity
                        if not position['first_fill_at']:
                            position['first_fill_at']=at.isoformat()
                            if asset_class=='crypto':position['exit_at']=(at+timedelta(days=decision['horizon'])).isoformat()
                            else:
                                future=[s for s in sessions if pd.Timestamp(s['open'])>pd.Timestamp(at)]
                                if len(future)>=decision['horizon']:position['exit_at']=future[decision['horizon']-1]['open']
                                else:state['corporate_action_review']=True;state['last_status']='Future session schedule unavailable'
                        if position['budget']-position['spent']<price*(1+fee):position['status']='holding'
                    else:
                        proceeds=quantity*price-charge;state['cash']+=proceeds;position['exit_proceeds']+=proceeds;position['quantity']=max(0,position['quantity']-quantity)
                    save_event('forward_fill',{'study_id':sid,'decision_id':decision['id'],'model_id':state['model_id'],'side':side,'quantity':quantity,'price':price,'fee':charge,'quote':q,'at':at.isoformat(),'partial':quantity+1e-10<wanted,'liquidity_assumption':'At most configured fraction of displayed base-unit depth; polling is not an exchange queue'},[sid,qid,side])
            if position['entry_quantity']:
                average=position['entry_cost']/position['entry_quantity'];excursion=q['bid']/average-1
                position['mfe']=max(position['mfe'] if position['mfe'] is not None else excursion,excursion);position['mae']=min(position['mae'] if position['mae'] is not None else excursion,excursion);position['marks']+=1
                position['marked_value']=position['quantity']*q['bid']*(1-fee-slip)
                save_event('forward_mark',{'study_id':sid,'decision_id':decision['id'],'at':at.isoformat(),'quote_timestamp':q['timestamp'],'bid':q['bid'],'ask':q['ask'],'quantity':position['quantity'],'liquidation_value':position['marked_value'],'regime':decision['regime']},[sid,qid])
            if position['status']=='exit' and position['quantity']<1e-10:finish('COMPLETED')
            state['last_status']='Collecting fresh executable observations';row.value=state
    def apply_corporate_actions(self,sid,at=None):
        """Supported stock distributions only; unknown lifecycle changes halt the book."""
        from zoneinfo import ZoneInfo
        at=at or now()
        with self.db.transaction() as session:
            row=session.get(Setting,'forward_state_'+sid)
            if not row:return
            state=json.loads(json.dumps(row.value));position=state.get('pending')
            for receivable in state.get('receivables',[]):
                if not receivable['paid'] and pd.Timestamp(receivable['payable_at'])<=pd.Timestamp(at):
                    state['cash']+=receivable['amount'];receivable['paid']=True
            if not position or not position.get('first_fill_at') or state['symbol'].endswith('-USD'):row.value=state;return
            entry=pd.Timestamp(position['first_fill_at']);applied=set(state.get('applied_actions',[]))
            actions=list(session.scalars(select(Record).where(Record.kind=='corporate_action',Record.symbol==state['symbol'])))
            actions.sort(key=lambda r:(r.payload['data'].get('ex_date') or r.payload['data'].get('effective_date') or '',0 if r.payload['action_type'] in ('forward_splits','reverse_splits') else 1,r.id))
            for action in actions:
                if action.id in applied:continue
                data=action.payload['data'];kind=action.payload['action_type'];effective=data.get('ex_date') or data.get('effective_date')
                if not effective:state['corporate_action_review']=True;continue
                effective_at=pd.Timestamp(effective).tz_localize('America/New_York')
                if not entry<effective_at<=pd.Timestamp(at):continue
                if kind in ('forward_splits','reverse_splits'):
                    ratio=float(data['new_rate'])/float(data['old_rate'])
                    if not math.isfinite(ratio) or ratio<=0:raise ValueError('Invalid provider split ratio')
                    position['quantity']*=ratio;position['entry_quantity']*=ratio
                    if abs(position['quantity']-round(position['quantity']))>1e-8:
                        state['corporate_action_review']=True;state['last_status']='Split produced fractional entitlement; cash-in-lieu data required'
                elif kind=='cash_dividends':
                    amount=float(data.get('rate',0))*position['quantity'];payable=data.get('payable_date')
                    if not payable or not math.isfinite(amount) or amount<0:state['corporate_action_review']=True;continue
                    position['dividends']=position.get('dividends',0)+amount
                    paid=pd.Timestamp(payable).tz_localize('America/New_York')<=pd.Timestamp(at)
                    if paid:state['cash']+=amount
                    state.setdefault('receivables',[]).append({'action_id':action.id,'amount':amount,'payable_at':pd.Timestamp(payable).tz_localize('America/New_York').isoformat(),'paid':bool(paid)})
                else:
                    state['corporate_action_review']=True;state['last_status']='Unsupported corporate lifecycle event; fills paused for review';continue
                applied.add(action.id)
                event={'study_id':sid,'decision_id':position['decision_id'],'action_id':action.id,'action_type':kind,'effective_at':effective_at.isoformat(),'processed_at':at.isoformat(),'source_observed_at':action.payload['observed_at'],'quantity_after':position['quantity']}
                session.add(Record(id='forward_action_'+stable_hash([sid,action.id]),kind='forward_action',symbol=state['symbol'],available_at=at.isoformat(),payload=event))
            state['applied_actions']=sorted(applied);row.value=state

    def release(self,request):
        state=self.db.setting('forward_state_'+request.study_id)
        if not state or state['state']!='retired':raise ValueError('Retire the entire evaluation cohort before releasing it to training')
        cutoff=now()-timedelta(days=request.minimum_age_days)
        completed=[r for r in self.db.records('forward_outcome',state['symbol'],limit=100000) if r['payload']['study_id']==request.study_id and r['payload']['status'] in ('COMPLETED','CASH_EVALUATED')]
        if not completed or any(pd.Timestamp(r['payload']['completed_at'])>pd.Timestamp(cutoff) for r in completed):raise ValueError('Every completed observation must satisfy the minimum 90-day quarantine')
        ids=sorted(r['id'] for r in completed);rid='forward_release_'+stable_hash([request.study_id,ids]);payload={'id':rid,'study_id':request.study_id,'outcome_ids':ids,'reason':request.reason,'released_at':now().isoformat(),'training_available_after':now().isoformat(),'evaluation_eligible':False,'automatic_training':False}
        existing=self.db.get(rid)
        if existing:return existing['payload']
        self.db.put('forward_training_release',payload,state['symbol'],record_id=rid)
        self.db.set_setting('forward_state_'+request.study_id,{**state,'evidence_policy':'released_for_future_training_only'});return payload
    def view(self):
        states=self.studies();evaluation={s['id']:s['evidence_policy']=='quarantined_evaluation' for s in states};decisions=[{**r['payload'],'evaluation_eligible':evaluation.get(r['payload']['study_id'],False)} for r in self.db.records('forward_decision',limit=1000)];outcomes=[{**r['payload'],'evaluation_eligible':evaluation.get(r['payload']['study_id'],False)} for r in self.db.records('forward_outcome',limit=100000)];attribution={}
        for field in ['model_id','symbol','regime','families','strategy_family','asset_class','liquidity_bucket','market_cap_bucket']:
            groups={}
            for o in outcomes:
                if not o['evaluation_eligible']:continue
                for label in o[field] if field=='families' else [o.get(field,'unknown')]:
                    g=groups.setdefault(label,{'trades':0,'unfilled':0,'pnl':0.})
                    if o['status']=='COMPLETED':g['trades']+=1;g['pnl']+=o['realized_pnl']
                    elif o['status']=='UNFILLED':g['unfilled']+=1
                    else:g['cash_decisions']=g.get('cash_decisions',0)+1
            attribution[field]=groups
        return {'studies':states,'decisions':decisions,'outcomes':outcomes[:1000],'fills':[r['payload'] for r in self.db.records('forward_fill',limit=1000)],'attribution':attribution,'warning':'Hypothetical independent model books. Attributions overlap across feature families and are not causal effects. Forward evidence is quarantined; no external orders.'}
    async def cycle(self,providers):
        states=[s for s in self.studies() if s['state']=='collecting'];cursor=self.db.setting('forward_cursor',{}).get('offset',0)
        batch=(states[cursor:]+states[:cursor])[:24]
        self.db.set_setting('forward_cursor',{'offset':(cursor+len(batch))%max(1,len(states))})
        for state in batch:
            try:
                self.apply_corporate_actions(state['id'])
                if not state['pending']:
                    manifest=HistoryStore(self.db).manifest(state['symbol'])
                    if manifest and pd.Timestamp(manifest['end'])+pd.Timedelta(days=1)<=max(pd.Timestamp(state['started_at']),pd.Timestamp(state.get('last_feature_time') or state['started_at'])):continue
                    model=self.db.get(state['model_id'])
                    if model['kind']=='strategy_model':
                        from backend.research.strategies import strategy_prediction
                        pred=await asyncio.to_thread(strategy_prediction,self.db,state['model_id'],state['symbol'])
                    else:pred=await asyncio.to_thread(study_prediction,self.db,state['model_id'])
                    u=load_universe(self.db);instrument=next(i for i in u.instruments if i.symbol==state['symbol']);raw=HistoryStore(self.db).read(state['symbol'],'raw');calendar=self.db.setting('research_calendar',{}).get('sessions',[])
                    expected=[s['date'] for s in calendar] if instrument.asset_class!='crypto' else pd.date_range(raw[0]['timestamp'],raw[-1]['timestamp'],freq='D').tolist() if raw else []
                    eligibility=eligible_at(instrument,raw,now(),u.filters_for(instrument),expected_sessions=expected,strict_membership=False)
                    self.decide(state['id'],pred,eligibility=eligibility)
                current=self.db.setting('forward_state_'+state['id'])
                if current.get('pending'):
                    self.apply_corporate_actions(state['id'])
                    quote=await providers.forward_quote(state['symbol']);self.process_quote(state['id'],quote)
            except Exception:
                self.process_quote(state['id'],{})
                current=self.db.setting('forward_state_'+state['id']);self.db.set_setting('forward_state_'+state['id'],{**current,'last_status':'Data or model unavailable; no fabricated decision or fill','last_attempt':now().isoformat()})
