"""Immutable alpha definitions and preregistered, disjoint evaluation epochs."""
from collections import defaultdict
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from backend.schemas.contracts import now
from backend.research.features import stable_hash
from backend.ensemble.engine import FAMILY_GROUPS
from backend.research.advanced.models import block_test
from backend.research.alpha.math import adaptive

STATES=('IDEA','HISTORICAL_RESEARCH','HOLDOUT','FORWARD_TESTING','SHADOW','QUALIFIED_SIMULATION','SUSPENDED','RETIRED')
POLICY={'version':'alpha-governance-v2','gate_evaluation':'Once per phase, first 60 nonoverlapping completed decision-date clusters; failed gate cannot be retried','forward_symbols':['AAPL','MSFT','NVDA','AMZN','GOOGL','META','SPY','QQQ','IWM','TLT','GLD','XOM','BTC-USD','ETH-USD','SOL-USD'],'minimum_dates':60,'minimum_calibration_dates':60,'max_brier':.25,'maximum_drawdown':.10,'minimum_net_lower_bound':0.,'maximum_feature_z':8.,'maximum_cost_ratio':2.,'degradation_dates':30,'reactivation_epochs':3,'release_delay_days':7,'minimum_adaptation_dates':60,'prior_fraction':.8,'maximum_weight_step':.02,'correlation_minimum_dates':40,'maximum_correlation':.8,'evaluation_lane':'even symbol SHA256; reserved from weight adaptation','adaptation_lane':'odd symbol SHA256; completed observations released after 7 days','policy_changes':'New immutable version and new evidence start; old receipts never transferred'}
DEFINITIONS={'momentum':'Continuation after positive trailing returns','trend_following':'Moving-average trend persistence','breakout':'Continuation beyond a previously observed range','relative_strength':'Strength relative to contemporaneous peers','cross_sectional_ranking':'Relative returns conditional on cross-sectional factor ranks','mean_reversion':'Reversal after an unusually large recent move','pairs_relative_value':'Relative-value spread convergence','volatility':'Return opportunity conditional on trailing volatility','macro_regime':'Return opportunity conditional on available macro/regime evidence','insider_event':'Return response to publication-available insider events','crypto_funding':'Funding/basis-related conditional returns','advanced_ml':'Nonlinear sequence forecast challenger; architectures are variants, not independent alphas'}

def implementation():
    root=Path(__file__).resolve().parents[3]
    files=list((root/'backend/research/alpha').glob('*.py'))+[root/n for n in ('backend/intelligence/news.py','backend/ensemble/engine.py','backend/ensemble/portfolio.py','backend/selection/risk.py','backend/research/forward.py','backend/product/paper.py')]
    return stable_hash({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)})
def lane(symbol):return 'evaluation' if int(hashlib.sha256(symbol.encode()).hexdigest()[:8],16)%2==0 else 'adaptation'
def context(row,governance,at=None):
    from backend.intelligence.news import attach
    row=attach(row,governance,at)
    if not governance.get("families"):return row
    age=(pd.Timestamp(at or now())-pd.Timestamp(governance.get('at','1970-01-01T00:00:00Z'))).total_seconds()
    stale=not 0<=age<=300
    votes=[]
    for vote in row.get('votes',[]):
        a=governance.get('families',{}).get(vote['family']);v=dict(vote);v['source_health']=vote.get('source_health',vote.get('health',[]));v['health']=list(v['source_health'])
        if not a or v.get('model_id') not in a.get('models',[]):v['health']=list(v.get('health',[]))+['Alpha version not registered']
        else:
            v.update(alpha_id=a['id'],alpha_state=a['state'],adaptive_multiplier=a.get('multiplier',1.))
            if a['state'] in ('IDEA','SUSPENDED','RETIRED'):v['health']=list(v.get('health',[]))+['Alpha '+a['state'].lower()]
        if stale:v['health'].append('Alpha governance unavailable or stale')
        votes.append(v)
    return {**row,'votes':votes,'strategy_return_dependence':governance.get('dependence') or row.get('strategy_return_dependence',{}),'alpha_context':{'version':governance.get('version'),'known_at':governance.get('at'),'weight_epoch':governance.get('weight_epoch'),'external_execution':False}}

def observations(db,aid,phase=None,purpose=None,as_of=None):
    rows=[]
    for record in db.records('alpha_outcome',limit=None):
        o=record['payload']
        if o['alpha_id']!=aid or (phase and o['phase']!=phase) or (purpose and o['lane']!=purpose):continue
        if as_of and pd.Timestamp(o['completed_at'])>pd.Timestamp(as_of):continue
        rows.append(o)
    return rows

def independent(rows):
    # One cross-sectional cluster per decision day; no overlapping holding intervals.
    groups=defaultdict(list)
    for x in rows:groups[x['decision_at'][:10]].append(x)
    result=[];last=None
    for day,items in sorted(groups.items()):
        start=min(pd.Timestamp(x['decision_at']) for x in items);end=max(pd.Timestamp(x['completed_at']) for x in items)
        if last is not None and start<=last:continue
        result.append({'date':day,'end':end.isoformat(),'net':float(np.mean([x.get('strategy_return',x['net_return']) for x in items])),'brier':float(np.mean([(x['probability']-(x['net_return']>0))**2 for x in items])),'items':items});last=end
    return result

def metrics(rows):
    clusters=independent(rows);values=[x['net'] for x in clusters];curve=np.cumprod(1+np.asarray(values));ics=[]
    for c in clusters:
        day_ics=[]
        for cls in sorted({x['asset_class'] for x in c['items']}):
            z=pd.DataFrame([x for x in c['items'] if x['asset_class']==cls])
            if len(z)>=5 and z.prediction.nunique()>1 and z.net_return.nunique()>1:day_ics.append(float(z.prediction.corr(z.net_return,method='spearman')))
        if day_ics:ics.append(float(np.mean(day_ics)))
    return {'dates':len(clusters),'observations':len(rows),'net_return':block_test(values),'rank_ic':block_test(ics),'hit_rate':float(np.mean(np.asarray(values)>0)) if values else None,'brier':float(np.mean([x['brier'] for x in clusters])) if clusters else None,'maximum_drawdown':float(max(1-curve/np.maximum.accumulate(np.r_[1.,curve])[1:])) if len(curve) else None}

class AlphaRegistry:
    def __init__(self,db):self.db=db
    def register(self,snapshot,at=None):
        at=(at or now()).isoformat();by=defaultdict(dict)
        for r in snapshot.get('rows',[]):
            for v in r.get('votes',[]):by[v['family']][v['model_id']]=v
        universe=sorted(snapshot.get('assets',{}));active={};impl=implementation()
        for family,definition in DEFINITIONS.items():
            variants=by[family];features=sorted({f for v in variants.values() for f in v.get('features',{})});horizons=sorted({v.get('horizon',5) for v in variants.values()})
            identity={'family':family,'definition':definition,'models':{k:v.get('artifact_hash') for k,v in sorted(variants.items())},'features':features,'horizons':horizons,'universe':universe,'regimes':['all; conditional validation required'],'implementation':impl,'policy':POLICY,'version':1}
            aid='alpha_'+stable_hash(identity);old=self.db.get(aid)
            if not old:
                self.db.put('alpha_definition',{'id':aid,'identity':identity,'registered_at':at,'policy_hash':stable_hash(POLICY),'historical_references':{k:v.get('historical_reliability',{}) for k,v in variants.items()},'historical_status':'Previously inspected development, never a new untouched holdout'},record_id=aid)
                self.db.set_setting('ast_'+aid[6:38],{'state':'IDEA','since':at,'phase_started_at':at,'healthy_epochs':0})
                if variants:
                    self.transition(aid,'HISTORICAL_RESEARCH','Existing implemented model and historical research',at)
                    self.transition(aid,'HOLDOUT','Frozen prospective evaluation lane begins now; prior outcomes excluded',at)
            active[family]=aid
        previous=self.db.setting('alpha_active',{})
        for family,aid in previous.items():
            if active.get(family)!=aid and self.state(aid)['state']!='RETIRED':self.transition(aid,'RETIRED','Superseded definition retained; no evidence transfers',at)
        self.db.set_setting('alpha_active',active);return active
    def state(self,aid):return self.db.setting('ast_'+aid[6:38],{'state':'IDEA'})
    def transition(self,aid,target,reason,at=None,receipt=None):
        if target not in STATES:raise ValueError('Unknown alpha state')
        at=at or now().isoformat();old=self.state(aid);current=old['state'];allowed={'IDEA':['HISTORICAL_RESEARCH','RETIRED'],'HISTORICAL_RESEARCH':['HOLDOUT','RETIRED'],'HOLDOUT':['FORWARD_TESTING','SUSPENDED','RETIRED'],'FORWARD_TESTING':['SHADOW','SUSPENDED','RETIRED'],'SHADOW':['QUALIFIED_SIMULATION','SUSPENDED','RETIRED'],'QUALIFIED_SIMULATION':['SUSPENDED','RETIRED'],'SUSPENDED':[old.get('resume_state','HOLDOUT'),'RETIRED'],'RETIRED':[]}
        if target not in allowed[current]:raise ValueError('Illegal alpha lifecycle transition')
        if target in ('FORWARD_TESTING','SHADOW','QUALIFIED_SIMULATION') and current!='SUSPENDED':
            proof=self.db.get(receipt or '')
            if not proof or proof['kind']!='alpha_gate' or proof['payload'].get('alpha_id')!=aid or proof['payload'].get('phase')!=current or not proof['payload'].get('passed'):raise ValueError('Frozen internal gate receipt required')
            definition=self.db.get(aid)['payload'];gate=proof['payload']
            if gate.get('policy_hash')!=definition['policy_hash'] or not old['phase_started_at']<=gate.get('at','')<=at:raise ValueError('Gate does not match frozen policy or phase')
            evidence=[self.db.get(oid) for oid in gate.get('outcomes',[])]
            if not evidence or any(not x or x['kind']!='alpha_outcome' or x['payload'].get('alpha_id')!=aid or x['payload'].get('phase')!=current or x['payload'].get('lane')!='evaluation' or x['payload']['decision_at']<old['phase_started_at'] or x['payload']['completed_at']>at for x in evidence):raise ValueError('Gate evidence is not an independent phase cohort')
            if receipt!='agate_'+stable_hash([aid,current,old['phase_started_at']]) or len(independent([x['payload'] for x in evidence]))!=definition['identity']['policy']['minimum_dates']:raise ValueError('Gate must be the single frozen phase decision')
            if not gate_pass(metrics([x['payload'] for x in evidence]),definition['identity']['policy']):raise ValueError('Recomputed frozen gate failed')
        if current=='SUSPENDED' and target!='RETIRED' and old.get('healthy_epochs',0)<POLICY['reactivation_epochs']:raise ValueError('Three new healthy feature epochs required')
        event={'alpha_id':aid,'from':current,'to':target,'reason':reason,'at':at,'receipt':receipt};self.db.put('alpha_transition',event,record_id='atr_'+stable_hash(event))
        value={**old,'state':target,'since':at,'healthy_epochs':0}
        if target=='SUSPENDED':value['resume_state']=current
        elif current!='SUSPENDED':value['phase_started_at']=at
        self.db.set_setting('ast_'+aid[6:38],value)
    def cycle(self,snapshot,at=None):
        at=at or now();active=self.register(snapshot,at);rows=defaultdict(list)
        for r in snapshot.get('rows',[]):
            for v in r.get('votes',[]):rows[v['family']].append((r,v))
        families={};histories={};priors={};fingerprint=[];released_all=[]
        for family,aid in active.items():
            d=self.db.get(aid)['payload'];state=self.state(aid);pairs=rows[family];epoch=max((r.get('feature_available_at') or '' for r,v in pairs),default='missing')
            healthy=any(not r.get('health') and not v.get('source_health',v.get('health')) and (v.get('maximum_feature_z') or 0)<=POLICY['maximum_feature_z'] for r,v in pairs)
            # Quantitative drift is observed only from completed forward records, never forecasts of outcomes.
            outcomes=observations(self.db,aid,as_of=at);m=metrics([o for o in outcomes if o['lane']=='evaluation']);recent=metrics([x for c in independent([o for o in outcomes if o['lane']=='evaluation'])[-30:] for x in c['items']]);reasons=[]
            if pairs and not healthy:reasons.append('Required data/feature health unreliable')
            if recent['dates']>=POLICY['degradation_dates']:
                if recent['net_return']['upper'] is not None and recent['net_return']['upper']<0:reasons.append('Negative net-return upper confidence bound')
                if recent['brier'] is not None and recent['brier']>.30:reasons.append('Calibration drift above frozen Brier threshold')
                if recent['rank_ic']['clusters']>=30 and recent['rank_ic']['upper'] is not None and recent['rank_ic']['upper']<0:reasons.append('IC deterioration')
                for reg in {o.get('regime') for o in outcomes}:
                    rm=metrics([o for o in outcomes if o.get('regime')==reg and o['lane']=='evaluation'])
                    if rm['dates']>=30 and rm['net_return']['upper'] is not None and rm['net_return']['upper']<0:reasons.append('Regime breakdown: '+str(reg))
                if any(o.get('cost_ratio',0)>POLICY['maximum_cost_ratio'] for c in independent(outcomes)[-3:] for o in c['items']):reasons.append('Execution cost drag exceeds frozen ratio')
            if state['state'] not in ('IDEA','RETIRED','SUSPENDED') and reasons:self.transition(aid,'SUSPENDED','; '.join(reasons),at.isoformat());state=self.state(aid)
            if state['state']=='SUSPENDED' and epoch!=state.get('health_epoch'):
                state.update(health_epoch=epoch,healthy_epochs=state.get('healthy_epochs',0)+1 if healthy and not reasons else 0);self.db.set_setting('ast_'+aid[6:38],state)
                if state['healthy_epochs']>=POLICY['reactivation_epochs']:self.transition(aid,state['resume_state'],'Three independent healthy feature epochs; frozen policy unchanged',at.isoformat());state=self.state(aid)
            phase=state['state']
            if phase in ('HOLDOUT','FORWARD_TESTING','SHADOW'):
                eligible=[o for o in outcomes if o['phase']==phase and o['lane']=='evaluation' and o['decision_at']>=state['phase_started_at']]
                # Freeze a single decision at the preregistered sample size; no repeated significance hunting.
                cs=independent(eligible);gid='agate_'+stable_hash([aid,phase,state['phase_started_at']])
                if len(cs)>=d['identity']['policy']['minimum_dates'] and not self.db.get(gid):
                    first=cs[:d['identity']['policy']['minimum_dates']];evidence=[o for c in first for o in c['items']];mm=metrics(evidence);passed=gate_pass(mm,d['identity']['policy'])
                    gate={'alpha_id':aid,'phase':phase,'policy_hash':d['policy_hash'],'passed':passed,'metrics':mm,'at':at.isoformat(),'outcomes':[x['id'] for x in evidence]};self.db.put('alpha_gate',gate,record_id=gid)
                    if passed:self.transition(aid,{'HOLDOUT':'FORWARD_TESTING','FORWARD_TESTING':'SHADOW','SHADOW':'QUALIFIED_SIMULATION'}[phase],'Frozen independent evaluation gate passed',at.isoformat(),gid);state=self.state(aid)
            released=[o for o in outcomes if o['lane']=='adaptation' and pd.Timestamp(o['completed_at'])+pd.Timedelta(days=POLICY['release_delay_days'])<=pd.Timestamp(at)];clusters=independent(released);histories[family]=[c['net'] for c in clusters];fingerprint += [o['id'] for o in released];released_all.extend(released)
            # Equal long-run prior until genuinely validated long-run evidence exists; no retrospective winner tilt.
            if pairs and state['state'] not in ('IDEA','SUSPENDED','RETIRED'):priors[family]=1.
            families[family]={'id':aid,'state':state['state'],'models':list(d['identity']['models']),'horizons':d['identity']['horizons'],'forward':m,'monitoring':{'health':healthy,'reasons':reasons,'recent':recent,'regime_performance':{reg:metrics([o for o in outcomes if o.get('regime')==reg]) for reg in sorted({o.get('regime') or 'unknown' for o in outcomes})}},'multiplier':1.}
        previous=self.db.setting('alpha_governance',{});epoch=stable_hash([active,sorted(fingerprint),sorted(priors)])
        if previous.get('weight_epoch')==epoch:weights=previous.get('weights',{});adapt=previous.get('adaptive',{})
        else:
            weights,adapt=adaptive(priors,histories,previous.get('weights'),minimum=POLICY['minimum_adaptation_dates']);self.db.put('alpha_weights',{'at':at.isoformat(),'epoch':epoch,'weights':weights,'fixed':{k:1/len(priors) for k in priors},'released_outcome_ids':sorted(fingerprint),'policy':POLICY,'diagnostics':adapt},record_id='aw_'+epoch)
        for k,f in families.items():f['multiplier']=weights.get(k,0)*len(priors) if priors else 0.
        dependence=forward_dependence(released_all,at)
        value={'dependence':dependence,'version':implementation(),'at':at.isoformat(),'families':families,'weights':weights,'weight_epoch':epoch,'adaptive':adapt,'external_execution':False};self.db.set_setting('alpha_governance',value);return value
    def status(self):
        g=self.db.setting('alpha_governance',{});rows=[];decay=self.db.get(self.db.setting('structure_experiment_latest',''));decay=(decay or {}).get('payload',{});research=self.db.setting('alpha_research_result',{})
        for family,aid in self.db.setting('alpha_active',{}).items():
            d=self.db.get(aid)['payload'];f=g.get('families',{}).get(family,{});mapped='low_volatility' if family=='volatility' else family
            rows.append({**d,**f,'family':family,'state':self.state(aid)['state'],'decay_reference':research.get('decay',{}).get(family) or [r for r in decay.get('results',[]) if r['family']==mapped],'horizon_classification':'multi-day fitted model' if d['identity']['horizons']==[5] else 'unavailable','holding_period_policy':'Use the registered forecast horizon; diagnostics never auto-select a winner','hit_rate':f.get('forward',{}).get('hit_rate'),'calibration':f.get('forward',{}).get('brier'),'maximum_drawdown':f.get('forward',{}).get('maximum_drawdown'),'rank_ic':f.get('forward',{}).get('rank_ic'),'historical_reference_metrics':research.get('decay',{}).get(family,[]),'transaction_cost_drag':None,'turnover':None,'capacity':'INSUFFICIENT EVIDENCE','missing':['Historical hit rate/turnover not unified across exact artifacts','Size/value and dated sector histories unavailable'],'correlation':research.get('alpha_correlations',{}),'historical_range':research.get('identity',{}).get('dates')})
        return {'alphas':rows,'distinct_families':len(rows),'independence_groups':len({FAMILY_GROUPS[k] for k in self.db.setting('alpha_active',{})}),'governance':g,'states':{s:sum(r['state']==s for r in rows) for s in STATES},'research':research,'policy':POLICY,'external_execution':False}

def forward_dependence(rows,at):
    streams={};ends=[]
    for model in sorted({m for o in rows for m in o.get('model_ids',[]) if len(o.get('model_ids',[]))==1}):
        eligible=[o for o in rows if o.get('horizon',5)==5 and o.get('model_ids')==[model] and o.get('lane')=='adaptation' and pd.Timestamp(o['completed_at'])+pd.Timedelta(days=POLICY['release_delay_days'])<=pd.Timestamp(at)]
        cs=independent(eligible);streams[model]={c['date']:(c['net'],c['end']) for c in cs};ends.extend(c['end'] for c in cs)
    frame=pd.DataFrame(streams);pairs=[]
    for i,a in enumerate(frame.columns):
        for b in frame.columns[i+1:]:
            common=sorted(set(streams[a])&set(streams[b]));paired=[];last=None
            for date in common:
                if last is not None and pd.Timestamp(date,tz='UTC')<=last:continue
                paired.append([streams[a][date][0],streams[b][date][0]]);last=max(pd.Timestamp(streams[a][date][1]),pd.Timestamp(streams[b][date][1]))
            z=pd.DataFrame(paired,columns=[a,b])
            if len(z)>=40 and z[a].std()>0 and z[b].std()>0:pairs.append({'model_a':a,'model_b':b,'return_correlation':float(z[a].corr(z[b])),'nonoverlapping_dates':len(z)})
    return {'horizon_sessions':5,'known_at':at.isoformat(),'end_at':max(ends) if ends else None,'pairs':pairs,'status':'AVAILABLE' if pairs else 'INSUFFICIENT FORWARD EVIDENCE','basis':'Mature released adaptation lane only; exact model IDs; evaluation lane excluded'} if pairs else {}

def gate_pass(m,p):
    return bool(m['dates']>=p['minimum_dates'] and m['net_return']['lower'] is not None and m['net_return']['lower']>p['minimum_net_lower_bound'] and m['net_return']['p']<.05/(len(DEFINITIONS)*3) and m['brier'] is not None and m['brier']<=p['max_brier'] and m['maximum_drawdown'] is not None and m['maximum_drawdown']<=p['maximum_drawdown'])
