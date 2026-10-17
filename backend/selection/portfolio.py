"""Automatic local-only portfolio. Reuses the simulator with an isolated ledger namespace.

There are deliberately no brokerage adapters, external execution imports or order endpoints here.
"""
import asyncio,json,math
from collections import defaultdict,Counter
import numpy as np
import pandas as pd
from sqlalchemy import select,func
from backend.schemas.contracts import now
from backend.storage.database import Setting,Record
from backend.product.paper import ManualPaper,Ticket,Confirm,OPEN
from backend.product.market import ProductMarket
from backend.research.features import stable_hash
from backend.selection.policy import policy,policy_hash
from backend.intelligence.news import live_governance
from backend.research.alpha.registry import context
from backend.ensemble.engine import candidate as ensemble_candidate
from backend.selection.registry import SelectionRegistry
from backend.selection.opportunities import OpportunityEngine
from backend.selection.risk import size,exposure,exit_reason

from backend.qualification.integrity import paper_authorized

class ModelPaper(ManualPaper):
    account_key='model_paper_account'
    record_prefix='auto'
    source='model_paper'
    fill_limit=None
    account_description='Automatic model paper portfolio. Manual trades and scientific studies excluded.'
    def reset(self,request):raise ValueError('Automatic account reset is not exposed')
    def maximum_fill_notional(self,order,state,quote,at):
        p=policy(self.db);snapshot=self.db.setting('model_opportunities',{});row=next((r for r in snapshot.get('rows',[]) if r['symbol']==order['symbol']),None)
        if row:
            fresh=ensemble_candidate(context(row,live_governance(self.db),at),snapshot.get('assets',{}).get(order['symbol'],{}),at=at,qualified_only=True)
            if fresh['ensemble']['action']!='BUY':return 0.
            row={**row,'expected_edge':min(row['expected_edge'],fresh['expected_edge'])}
        if not row or row.get('ensemble',{}).get('action')!='BUY' or not row.get('trade_eligible') or row.get('health') or not row.get('feature_available_at'):return 0.
        if not 0<=(pd.Timestamp(at)-pd.Timestamp(row['feature_available_at'])).total_seconds()<=p.maximum_data_age_days*86400:return 0.
        for vote in row.get('votes',[]):
            if vote['weight']>0:
                artifact=self.db.get(vote['model_id'])
                if not artifact or stable_hash(artifact['payload'])!=vote['artifact_hash'] or paper_authorized(self.db,vote['model_id'],vote['artifact_hash']) is False:return 0.
        spread=(quote['ask']-quote['bid'])/((quote['ask']+quote['bid'])/2)
        cost=spread+2*(order['policy']['slippage_bps']+order['policy']['fee_bps'])/1e4
        row={**row,'expected_edge':row['expected_edge']+row['estimated_roundtrip_cost']-cost}
        if row['expected_edge']<=0:return 0.
        # Revalue the proposed fill using the fresh quote before enforcing risk caps.
        state=json.loads(json.dumps(state));state['marks'][order['symbol']]={'bid':quote['bid'],'timestamp':quote['timestamp']}
        positions=[{**v,'symbol':s,'market_value':v['quantity']*state['marks'].get(s,{}).get('bid',v['average_cost'])} for s,v in state['positions'].items() if v['quantity']>0]
        if any(s!=order['symbol'] and pos['quantity']>0 and (not state['marks'].get(s) or not 0<=(pd.Timestamp(at)-pd.Timestamp(state['marks'][s]['timestamp'])).total_seconds()<=120) for s,pos in state['positions'].items()):return 0.
        equity=state['cash']+sum(v['market_value'] for v in positions);orders=[o for o in state['orders'].values() if o['id']!=order['id']]
        reserve=sum((o['quantity']-o['filled_quantity'])*o['reserve_price']*(1+o['policy']['fee_bps']/1e4) for o in orders if o['side']=='buy' and o['status'] in OPEN)
        view={'equity':equity,'cash':state['cash'],'available_cash':max(0,state['cash']-reserve),'positions':positions,'orders':orders}
        links={}
        for o in state['orders'].values():
            d=self.db.get(o.get('model_decision_id',''))
            if d:links[o['symbol']]=d['payload'].get('groups',['unknown'])
        high=self.db.setting('model_portfolio_control',{}).get('high_water',state['initial_cash'])
        return size(row,view,snapshot.get('assets',{}),snapshot.get('correlation',{}),p,high,links,allow_existing=True)['notional']

    def process(self,symbol,q,at=None):
        p=policy(self.db);control=self.db.setting('model_portfolio_control',{});state=self.state()
        if state:
            for o in list(state['orders'].values()):
                if o['symbol']==symbol and o['side']=='buy' and o['status'] in OPEN:
                    if not p.enabled or control.get('entries_blocked',True) or o.get('model_policy_hash')!=policy_hash(p):self.cancel(o['id'])
        return super().process(symbol,q,at)

class ModelPortfolio:
    def __init__(self,db,providers=None):
        self.db=db;self.providers=providers;self.market=ProductMarket(db);self.paper=ModelPaper(db,self.market);self.paper.initial_cash=policy(db).initial_cash;self.registry=SelectionRegistry(db);self.opportunities=OpportunityEngine(db);self.lock=asyncio.Lock()
    def alert(self,event,key,title,detail,severity='info'):
        day=now().date().isoformat();rid='auto_alert_'+stable_hash([event,key,day]);self.db.put('auto_alert',{'type':event,'title':title,'detail':detail,'severity':severity,'at':now().isoformat(),'channel':'in_app_only'},record_id=rid)
    def rebuild(self):
        p=policy(self.db);registry=self.registry.refresh()
        from backend.selection.review import review_registry
        review_registry(self.db,registry)
        assets=self.market.forecasts();view=self.paper.view();snapshot=self.opportunities.build(assets,registry,p,view)
        snapshot['policy_hash']=policy_hash(p);snapshot['registry_as_of']=registry['as_of'];snapshot['registry_digest']=stable_hash([(r['id'],r['artifact_hash'],r['eligibility']) for r in registry['rows']]);snapshot['assets']={a['symbol']:{k:a.get(k) for k in ['symbol','asset_class','sector','eligibility','price','price_at','market_cap_bucket','liquidity_bucket']} for a in assets}
        old=self.db.setting('model_opportunities',{});oldrows={r['symbol']:r for r in old.get('rows',[])}
        for row in snapshot['rows']:
            before=oldrows.get(row['symbol']);issues=row['health']+[reason for v in row['votes'] for reason in v['health']]
            if issues:self.alert('data_health',row['symbol'],row['symbol']+' data requires review',', '.join(sorted(set(issues))),'warning')
            if row['agreement']<.6 and len(row['research_groups'])>=2:self.alert('disagreement',row['symbol'],row['symbol']+' strategy disagreement','Independent group directions disagree; inspect the score breakdown.','warning')
            if before and before['feature_available_at']!=row['feature_available_at'] and before.get('expected_edge') is not None and row.get('expected_edge') is not None:
                scale=max(before.get('uncertainty') or .01,.01)
                if abs(row['expected_edge']-before['expected_edge'])>3*scale:
                    row['health'].append('Prediction distribution shift');row['trade_eligible']=False;row['would_trade']=False;self.alert('prediction_drift',row['symbol'],row['symbol']+' prediction shift','Change exceeds three prior residual-error units. New entries blocked.','warning')
        top=snapshot['rows'][0] if snapshot['rows'] else None
        if top and top['symbol']!=(old.get('rows') or [{}])[0].get('symbol'):self.alert('opportunity',top['symbol'],'New research leader: '+top['symbol'],top['score_basis'])
        old_registry=self.db.setting('selection_last_ids',[]);ids=[r['id'] for r in registry['rows']]
        if old_registry and set(ids)-set(old_registry):self.alert('training',stable_hash(sorted(set(ids)-set(old_registry))),'New model research available','New variants entered as challengers, with zero automatic execution weight.')
        self.db.set_setting('selection_last_ids',ids)
        for r in registry['rows']:
            if r['forward']['date_clusters']>=p.minimum_conditional_dates and (r['forward']['mean_net_return'] or 0)<0:self.alert('strategy_degradation',r['id'],'Strategy evidence weakened',r['family']+' has negative recent forward performance; shrinkage and minimum counts apply.','warning')
        from backend.qualification.integrity import implementation_hash
        snapshot['id']='auto_snapshot_'+stable_hash([implementation_hash(),snapshot['as_of'],snapshot['policy_hash'],snapshot['registry_digest'],[(r['symbol'],r['feature_available_at'],r['score'],r['health']) for r in snapshot['rows']],now().date().isoformat()])
        self.db.put('auto_snapshot',snapshot,record_id=snapshot['id']);self.db.set_setting('model_opportunities',snapshot);self.db.set_setting('model_portfolio_control',{**self.db.setting('model_portfolio_control',{}),'data_error':False});return snapshot
    def ordered_decisions(self):
        # Only actual order decisions carry position attribution. Avoid loading large no-trade snapshots.
        with self.db.engine.connect() as c:
            return list(c.execute(select(Record.payload).where(Record.kind=='auto_decision',Record.payload['order_id'].as_string().is_not(None)).order_by(Record.created_at)).scalars())
    def links(self):
        return {d['symbol']:d for d in self.ordered_decisions() if d.get('side')=='buy'}
    def mark_metrics(self):
        v=self.paper.view();old=self.db.setting('model_portfolio_control',{});high=max(old.get('high_water',v['initial_cash']),v['equity']);dd=max(0,1-v['equity']/high);p=policy(self.db)
        snapshot=self.db.setting('model_opportunities',{});age=(pd.Timestamp(now())-pd.Timestamp(snapshot.get('as_of',now().isoformat()))).total_seconds()
        stale_marks=sum(not x.get('mark_at') or not 0<=(pd.Timestamp(now())-pd.Timestamp(x['mark_at'])).total_seconds()<=120 or bool(x.get('corporate_action_review')) for x in v['positions'])
        blocked=bool(stale_marks) or old.get('data_error',False) or not p.enabled or dd>=p.maximum_drawdown or not snapshot or age>7200 or snapshot.get('policy_hash')!=policy_hash(p)
        if dd>=p.maximum_drawdown:self.alert('portfolio_risk','drawdown','Drawdown limit reached','New entries blocked; existing positions request risk exits.','warning')
        self.db.set_setting('model_portfolio_control',{'data_error':old.get('data_error',False),'high_water':high,'drawdown':dd,'entries_blocked':blocked,'stale_marks':stale_marks,'at':now().isoformat(),'policy_hash':policy_hash(p)})
        # One daily mark for metrics, updated without multiplying the independent sample count.
        day=now().date().isoformat();self.db.set_setting('auto_equity_'+day,{'at':now().isoformat(),'date':day,'equity':v['equity'],'cash':v['cash'],'exposure':(v['equity']-v['cash'])/max(v['equity'],1),'fees':v['fees'],'stale_marks':stale_marks})
        return v,high,blocked
    async def submit(self,decision,quote,ticket):
        rid=decision['id'];existing=self.db.get(rid)
        if existing:return existing['payload']
        try:
            preview=self.paper.preview(ticket,quote);preview={**preview,'id':'auto_preview_'+stable_hash(rid),'model_decision_id':rid,'model_policy_hash':decision['policy_hash'],'strategy_family':'+'.join(decision.get('groups',[])),'holding_rule':decision.get('exit_policy',{})}
            self.db.put('auto_preview',preview,decision['symbol'],record_id=preview['id'])
            order=self.paper.place(Confirm(preview_id=preview['id'],confirmation='PLACE PAPER ORDER'))
            # Policy and attribution are carried in the saved preview/order; confirmation is local simulation only.
            decision.update(order_id=order['id'],status='ORDERED')
        except ValueError as e:decision.update(status='NO_TRADE',reason=str(e))
        self.db.put('auto_decision',decision,decision['symbol'],record_id=rid);return decision
    async def cycle(self,rebuild=False):
        async with self.lock:
            p=policy(self.db);snapshot=self.db.setting('model_opportunities')
            if rebuild or not snapshot or (pd.Timestamp(now())-pd.Timestamp(snapshot['as_of'])).total_seconds()>3600:
                try:snapshot=await asyncio.to_thread(self.rebuild)
                except Exception:
                    self.db.set_setting('model_portfolio_control',{**self.db.setting('model_portfolio_control',{}),'entries_blocked':True,'data_error':True,'at':now().isoformat(),'reason':'Required research snapshot unavailable'})
                    self.alert('data_health','snapshot','Model portfolio data unavailable','New entries paused; other data collectors and manual trading continue.','warning')
                    # Still process protective exits/expiry with last snapshot, never new entries.
                    snapshot=self.db.setting('model_opportunities',{'rows':[],'assets':{},'correlation':{},'id':'unavailable','policy_hash':''})
            governance=live_governance(self.db)
            snapshot={**snapshot,'rows':[context(r,governance) for r in snapshot['rows']]}
            view,high,blocked=self.mark_metrics();assets=snapshot.get('assets',{});opps={r['symbol']:r for r in snapshot['rows']};links=self.links();group_links={s:d.get('groups',['unknown']) for s,d in links.items()}
            self.paper.actions();state=self.paper.state() or {'orders':{},'positions':{}};quote_symbols={o['symbol'] for o in state['orders'].values() if o['status'] in OPEN}|{s for s,pos in state['positions'].items() if pos['quantity']>0}
            for symbol in sorted(quote_symbols):
                try:q=await self.providers.forward_quote(symbol)
                except Exception:q={}
                self.paper.process(symbol,q)
                current=self.paper.view();position=next((x for x in current['positions'] if x['symbol']==symbol),None)
                if not position or any(o['symbol']==symbol and o['side']=='sell' and o['status'] in OPEN for o in current['orders']):continue
                entry=links.get(symbol);candidate=opps.get(symbol,{});sessions=self.db.setting('research_calendar',{}).get('sessions',[]);opened=pd.Timestamp(position['opened_at']);at=pd.Timestamp(now())
                count=int((at-opened).total_seconds()//86400) if assets.get(symbol,{}).get('asset_class')=='crypto' else sum(opened<pd.Timestamp(s['close'])<=at for s in sessions)
                extrema=self.db.setting('auto_extrema_'+symbol,{});bid=q.get('bid');old_high=extrema.get('high',bid or position['average_cost'])
                # Marks used for stops must satisfy the same fresh-quote and session checks as fills.
                from backend.research.forward import quote_check,ForwardPolicy
                valid=not quote_check(q,{'symbol':symbol,'decided_at':(now()-pd.Timedelta(seconds=60)).isoformat()},ForwardPolicy(),now(),sessions,assets.get(symbol,{}).get('asset_class','stock'))
                if not valid:continue
                same=extrema.get('opened_at')==position['opened_at'];extrema={'opened_at':position['opened_at'],'high':max(old_high,bid) if same else bid,'low':min(extrema.get('low',bid),bid) if same else bid};self.db.set_setting('auto_extrema_'+symbol,extrema)
                reason=exit_reason(position,{**candidate,'bid':bid,'high_bid':extrema['high'],'drawdown':max(0,1-current['equity']/high),'data_unreliable':bool(candidate.get('health')) or not candidate},p,count)
                from backend.ensemble.engine import decide
                from backend.ensemble.portfolio import trigger,ExitPolicy
                reason=reason or trigger(position,decide(candidate,assets.get(symbol,{}),held=True,qualified_only=True),q,extrema,ExitPolicy(),sessions,assets.get(symbol,{}).get('asset_class'),max(0,1-current['equity']/high),candidate.get('daily_volatility'))
                if reason:
                    for pending in current['orders']:
                        if pending['symbol']==symbol and pending['side']=='buy' and pending['status'] in OPEN:self.paper.cancel(pending['id'])
                    did='auto_decision_'+stable_hash([position['opened_at'],symbol,'sell',now().date().isoformat(),len(current['fills'])]);d={'id':did,'symbol':symbol,'side':'sell','at':now().isoformat(),'reason':reason,'policy_hash':policy_hash(p),'entry_decision_id':entry['id'] if entry else None,'snapshot_id':snapshot['id'],'groups':entry.get('groups',[]) if entry else [],'quote':q,'exit_policy':p.model_dump(),'position':position,'extrema':extrema}
                    await self.submit(d,q,Ticket(symbol=symbol,side='sell',quantity=position['quantity']))
            governance=live_governance(self.db)
            snapshot={**snapshot,'rows':[context(r,governance) for r in snapshot['rows']]}
            view,high,blocked=self.mark_metrics();quote_count=0
            for row in snapshot['rows']:
                from backend.ensemble.engine import candidate as ensemble_candidate
                row=ensemble_candidate(row,assets.get(row['symbol'],{}),qualified_only=True)
                await asyncio.sleep(0) # Yield between independent deterministic decisions.
                did='auto_decision_'+stable_hash([snapshot['id'],row['symbol'],'buy']);old=self.db.get(did)
                if old:continue
                if any(v.get('weight',0)>0 and paper_authorized(self.db,v['model_id'],v['artifact_hash']) is False for v in row.get('votes',[])):
                    row={**row,'trade_eligible':False,'health':[*row.get('health',[]),'Qualification suspended or expired']}
                risk=size(row,view,assets,snapshot.get('correlation',{}),p,high,group_links);d={'id':did,'symbol':row['symbol'],'side':'buy','at':now().isoformat(),'snapshot_id':snapshot['id'],'policy_hash':policy_hash(p),'candidate':row,'groups':row['groups'],'risk':risk,'exit_policy':p.model_dump(),'status':'NO_TRADE','reason':'; '.join(risk['reasons'])}
                if blocked or risk['notional']<=0:
                    if blocked:d['reason']='Portfolio entries paused; '+d['reason']
                    self.db.put('auto_decision',d,row['symbol'],record_id=did);continue
                if quote_count>=p.maximum_quote_requests_per_cycle:break
                quote_count+=1
                try:q=await self.providers.forward_quote(row['symbol'])
                except Exception:q={}
                from backend.research.forward import quote_check,ForwardPolicy
                reasons=quote_check(q,{'symbol':row['symbol'],'decided_at':(now()-pd.Timedelta(seconds=60)).isoformat()},ForwardPolicy(),now(),self.db.setting('research_calendar',{}).get('sessions',[]),row['asset_class'])
                d['quote']=q
                if reasons:d['reason']='; '.join(reasons);self.db.put('auto_decision',d,row['symbol'],record_id=did);continue
                spread=(q['ask']-q['bid'])/((q['ask']+q['bid'])/2);actual_cost=spread+2*(25 if row.get('liquidity_bucket')=='limited' or row['asset_class']=='stock' and row.get('market_cap_bucket') in ('small','unknown') else 5)/1e4+.001
                # Forecasts are already net of research costs; replace that estimate instead of double-counting.
                adjusted=row['expected_edge']+row['estimated_roundtrip_cost']-actual_cost;d['actual_estimated_cost']=actual_cost;d['quote_adjusted_edge']=adjusted
                if adjusted<=0:d['reason']='Fresh quote costs remove expected edge';self.db.put('auto_decision',d,row['symbol'],record_id=did);continue
                adjusted_candidate={**row,'expected_edge':adjusted};updated_risk=size(adjusted_candidate,view,assets,snapshot.get('correlation',{}),p,high,group_links);d['risk_after_quote']=updated_risk
                if updated_risk['notional']<=0:
                    d['reason']='Fresh quote sizing rejected';self.db.put('auto_decision',d,row['symbol'],record_id=did);continue
                await self.submit(d,q,Ticket(symbol=row['symbol'],side='buy',amount=min(risk['notional'],updated_risk['notional'])))
                view=self.paper.view();group_links[row['symbol']]=row['groups']
            self.reconcile();self.mark_metrics();self.db.set_setting('model_portfolio_worker',{'status':'RUNNING','last_cycle':now().isoformat(),'external_execution':False})
    def reconcile(self):
        view=self.paper.view();fills=view['fills'];decisions={d['order_id']:d for d in self.ordered_decisions()}
        for order in view['orders']:
            d=decisions.get(order['id'])
            if not d:continue
            if order['status'] in ('NO_FILL','EXPIRED','CANCELED'):
                self.db.put('auto_order_result',{'decision_id':d['id'],'order_id':order['id'],'status':order['status'],'filled_quantity':order['filled_quantity'],'at':now().isoformat()},order['symbol'],record_id='auto_order_result_'+stable_hash(order))
            if order['side']!='sell' or order['status']!='FILLED':continue
            entry=self.db.get(d.get('entry_decision_id',''));entry=entry['payload'] if entry else {};entries=[f for f in fills if f['order_id']==entry.get('order_id')];exit_ids={oid for oid,decision in decisions.items() if decision.get('side')=='sell' and decision.get('entry_decision_id')==entry.get('id')};exits=[f for f in fills if f['order_id'] in exit_ids]
            if not entries or not exits or any(p['symbol']==order['symbol'] for p in view['positions']):continue
            cost=sum(f['quantity']*f['price']+f['fee'] for f in entries);pnl=sum(f['realized_pnl'] for f in exits);c=entry.get('candidate',{});weights={v['family']:v['weight'] for v in c.get('votes',[]) if v['weight']>0};total=sum(weights.values())
            outcome={'entry_decision_id':entry.get('id'),'exit_decision_id':d['id'],'symbol':order['symbol'],'completed_at':now().isoformat(),'realized_pnl':pnl,'entry_cost':cost,'net_return':pnl/cost if cost else None,'model_ids':[v['model_id'] for v in c.get('votes',[]) if v['weight']>0],'regime':c.get('regime'),'liquidity_bucket':c.get('liquidity_bucket'),'family_attribution':{k:pnl*w/total for k,w in weights.items()} if total else {},'attribution_scope':'Performance allocation by recorded vote weight, not a causal contribution estimate','fees':sum(f['fee'] for f in entries+exits),'evidence_policy':'portfolio_evaluation_only; excluded from training','maximum_favorable_excursion':d.get('extrema',{}).get('high',0)/max(d.get('position',{}).get('average_cost',1),1e-9)-1,'maximum_adverse_excursion':d.get('extrema',{}).get('low',0)/max(d.get('position',{}).get('average_cost',1),1e-9)-1}
            self.db.put('auto_outcome',outcome,order['symbol'],record_id='auto_outcome_'+entry['id'])
    def status(self):
        v=self.paper.view();snapshot=self.db.setting('model_opportunities',{});links=self.links();assets=snapshot.get('assets',{});outcomes=[r['payload'] for r in self.db.records('auto_outcome',limit=100000)]
        with self.db.engine.connect() as c:
            from sqlalchemy import text
            equity=[r[0] for r in c.execute(select(Setting.value).where(Setting.key.like('auto_equity_%')).order_by(Setting.key))]
        decisions=[r['payload'] for r in self.db.records('auto_decision',limit=50)]
        with self.db.engine.connect() as c:
            status=Record.payload['status'].as_string();counts=dict(c.execute(select(status,func.count()).where(Record.kind=='auto_decision').group_by(status)).all())
        return {'account':v,'policy':policy(self.db).model_dump(),'control':self.db.setting('model_portfolio_control',{}),'worker':self.db.setting('model_portfolio_worker',{}),'exposure':exposure(v,assets,{s:d.get('groups',['unknown']) for s,d in links.items()}),'metrics':portfolio_metrics(equity,outcomes,v),'decisions':decisions[:50],'decision_counts':counts,'order_counts':dict(Counter(o['status'] for o in v['orders'])),'outcomes':outcomes[:100],'equity':equity,'incumbent':self.db.setting('selection_registry',{}).get('incumbent','cash'),'isolation':{'manual':True,'scientific_forward':True,'training':True,'external_execution':False}}

def portfolio_metrics(equity,outcomes,view):
    equity=[r if isinstance(r,dict) else json.loads(r) for r in equity];curve=pd.DataFrame(equity);rets=curve.equity.pct_change().dropna() if len(curve)>1 else pd.Series(dtype=float);consecutive=bool(len(curve)>1 and (pd.to_datetime(curve.date).diff().dropna()==pd.Timedelta(days=1)).all());valid=len(rets)>=60 and consecutive and not any(r.get('stale_marks',0) for r in equity);pnl=[o['realized_pnl'] for o in outcomes];returns=[o['net_return'] for o in outcomes if o.get('net_return') is not None];groups={}
    for key in ['regime','liquidity_bucket']:
        groups[key]={name:{'trades':len(rows),'realized_pnl':sum(o['realized_pnl'] for o in rows)} for name in {str(o.get(key,'unknown')) for o in outcomes} if (rows:=[o for o in outcomes if str(o.get(key,'unknown'))==name])}
    fam=defaultdict(lambda:{'trades':0,'allocated_pnl':0.})
    for o in outcomes:
        for name,value in o.get('family_attribution',{}).items():fam[name]['trades']+=1;fam[name]['allocated_pnl']+=value
    vol=float(rets.std(ddof=1)) if len(rets)>1 else None;negative=rets.clip(upper=0);down=float(np.sqrt(np.mean(negative**2))) if len(rets) else 0
    return {'net_return':view['total_pnl']/view['initial_cash'],'observed_days':len(equity),'daily_return_observations':len(rets),'completed_trades':len(outcomes),'annualized_volatility':vol*math.sqrt(365) if valid and vol else None,'sharpe_like':float(rets.mean()/vol*math.sqrt(365)) if valid and vol else None,'sortino_like':float(rets.mean()/down*math.sqrt(365)) if valid and down else None,'annualization_basis':'365 calendar-day marks; at least 60 returns, no stale marks; still exploratory','maximum_drawdown':float((1-curve.equity/curve.equity.cummax()).max()) if len(curve) else 0.,'turnover':sum(f['price']*f['quantity'] for f in view['fills'])/view['initial_cash'],'average_trade_return':float(np.mean(returns)) if returns else None,'wins':sum(p>0 for p in pnl),'losses':sum(p<0 for p in pnl),'flat':sum(p==0 for p in pnl),'return_quantiles':dict(zip(['min','median','max'],map(float,np.quantile(returns,[0,.5,1])))) if returns else None,'fees':view['fees'],'fee_drag':view['fees']/view['initial_cash'],'estimated_spread_slippage_drag':sum(f['quantity']*f['price']*(f['slippage_bps']+f['spread_bps']/2)/1e4 for f in view['fills'])/view['initial_cash'],'by':groups,'family_attribution':dict(fam),'warning':'Insufficient forward evidence; annualized ratios hidden below 60 daily returns. Empty/short samples are not profitable-performance evidence.' if not valid else 'Exploratory ratios; serial dependence and changing exposures limit inference.'}
