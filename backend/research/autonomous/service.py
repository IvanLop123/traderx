"""Research-only orchestration. Immutable ledger, finite leases, no order/promotion tools."""
import asyncio, hashlib, json, re
from datetime import timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control
from sqlalchemy import select,func,cast,String
from sqlalchemy.orm import Session
from backend.schemas.contracts import now, uid
from backend.storage.database import Record, Setting
from backend.research.features import stable_hash
from backend.research.history import HistoryStore
from backend.research.universe import load_universe
from backend.qualification.policy import QualificationCriteria
from backend.research.autonomous.schema import Budget, ExperimentSpec, Feature, FEATURES, ReviewProposal
from backend.research.autonomous.isolation import execute, clean_abandoned
from backend.research.autonomous.numerics import classify

ROOT=Path(__file__).resolve().parents[3]
KEY='autonomous_research'
AUTO_KINDS=('auto_registration','auto_result','auto_model','auto_forward_link','auto_proposal','auto_code_proposal','auto_code_review','auto_execution')

def implementation_hash():
    paths=list(Path(__file__).parent.glob('*.py'))+[ROOT/'backend/research/features.py',ROOT/'backend/research/studies.py',ROOT/'backend/research/point_in_time.py',ROOT/'backend/research/engine.py',ROOT/'backend/intelligence/quant.py',ROOT/'backend/qualification/statistics.py',ROOT/'backend/qualification/policy.py',ROOT/'backend/research/forward.py',ROOT/'requirements.lock.txt']
    return stable_hash({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})

def novelty(spec,previous):
    families={FEATURES[f.name] for f in spec.features};scores=[]
    for row in previous:
        old=row['spec'];other={FEATURES[f['name']] for f in old['features']}
        overlap=len(families&other)/max(1,len(families|other));universe=len(set(spec.universe)&set(old['universe']))/len(set(spec.universe)|set(old['universe']))
        words=lambda s:set(re.findall('[a-z]{4,}',s.lower()))
        a=words(spec.economic_mechanism);b=words(old['economic_mechanism']);economic=len(a&b)/max(1,len(a|b))
        score=.5*overlap+.2*universe+.15*(spec.target==old['target'])+.1*(spec.model_family==old['model_family'])+.05*economic
        scores.append({'id':row['id'],'similarity':round(score,4),'lineage':row['lineage'],'family_overlap':overlap})
    match=max(scores,key=lambda r:r['similarity']) if scores else None
    return {'novelty':round(1-match['similarity'],4) if match else 1.,'nearest':match,'redundant':bool(match and match['similarity']>=.94)}

class AutonomousResearch:
    def __init__(self,db,llm=None,root=None):
        self.db=db;self.llm=llm;self.root=Path(root or ROOT/'data/autonomous_research');self.temporary=self.root/'temporary';self.stopping=False
    def budget(self):return Budget.model_validate(self.db.setting(KEY,{}).get('budget',{}))
    def configure(self,budget):
        with self.db.transaction() as session:
            row=session.get(Setting,KEY);value=dict(row.value if row else {})
            value['budget']=budget.model_dump();session.merge(Setting(key=KEY,value=value))
        return self.status()
    def registrations(self):return [r['payload'] for r in self.db.records('auto_registration',limit=2000)]
    def file_usage(self):
        files=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()) if self.root.exists() else 0
        proposals=ROOT/'research/proposals'
        quarantine=sum(p.stat().st_size for p in proposals.glob('auto-*/*') if p.is_file() and not p.is_symlink()) if proposals.exists() else 0
        return files,quarantine
    def disk_usage(self):
        with Session(self.db.engine) as session:
            logical=session.scalar(select(func.coalesce(func.sum(func.length(cast(Record.payload,String))),0)).where(Record.kind.in_(AUTO_KINDS)))
        files,quarantine=self.file_usage()
        return {'ledger_bytes':logical,'file_bytes':files,'quarantine_bytes':quarantine,'total_bytes':logical+files+quarantine,'measurement':'Logical research payload/file bytes; shared database page/WAL overhead excluded'}
    def status(self):
        state=self.db.setting(KEY,{});regs=self.registrations();outcomes={r['payload']['registration_id']:r['payload'] for r in self.db.records('auto_result',limit=2000)}
        rows=[];ps=[]
        for r in regs:
            result=outcomes.get(r['id'],{});p=result.get('p_value');ps.append(float(p) if p is not None else 1.)
            summary={**r,'dataset':{k:r['dataset'][k] for k in ('dataset_hash','holdout_start','created_at','policy')}}
            rows.append({'registration':summary,'result':result,'status':result.get('status','RUNNING' if state.get('active')==r['id'] else 'PREREGISTERED')})
        for row,p in zip(rows,false_discovery_control(ps,method='by') if ps else []):row['adjusted_p_value_by']=float(p)
        studies=self.db.records('auto_forward_link',limit=500)
        return {'budget':self.budget().model_dump(),'storage':self.disk_usage(),'experiments':rows[:50],
                'registered_total':len(regs),'proposals':[r['payload'] for r in self.db.records('auto_proposal',limit=20)],
                'code_proposals':[{'id':r['id'],**r['payload'],'review':(self.db.get(r['id']+'-review') or {}).get('payload')} for r in self.db.records('auto_code_proposal',limit=20)],
                'forward_studies':[r['payload'] for r in studies],'qualified_discoveries':[],
                'running':state.get('active'),'last_review':state.get('last_review'),'last_observation':state.get('observation'),
                'multiple_testing':'Permanent attempt index alpha/(n*(n+1)); two tests and trial count included. BY is descriptive across all attempts, missing p=1. Approximate dependent-data inference is not a guarantee.',
                'production':'Immutable: no ensemble writes, promotion API, broker credentials or execution tools. Challenger research only.',
                'qualification':'Existing frozen qualification criteria apply. No autonomous production promotion; prospective benchmark comparison and explicit reviewed model registration remain required.'}
    def _capacity(self,session,budget,*,registration=False):
        rows=list(session.scalars(select(Record).where(Record.kind=='auto_registration')))
        if len(rows)>=budget.maximum_registrations:raise ValueError('Permanent ledger registration limit reached')
        count=session.scalar(select(func.count()).select_from(Record).where(Record.kind.in_(AUTO_KINDS)))
        if count>=budget.maximum_registrations*8:raise ValueError('Permanent ledger entry limit reached')
        logical=session.scalar(select(func.coalesce(func.sum(func.length(cast(Record.payload,String))),0)).where(Record.kind.in_(AUTO_KINDS)))
        if logical+sum(self.file_usage())+2*1024**2>budget.storage_mb*1024**2:raise ValueError('Research storage budget reached')
        if registration and sum(r.created_at[:10]==now().date().isoformat() for r in rows)>=budget.experiments_per_day:raise ValueError('Daily experiment budget reached')
        return rows
    def snapshot(self,spec):
        assets={};refs={};times=[];universe=load_universe(self.db)
        for symbol in spec.universe:
            instrument=next((i for i in universe.instruments if i.symbol==symbol),None)
            if not instrument or instrument.asset_class!=spec.asset_class:raise ValueError('Universe/asset class mismatch')
            store=HistoryStore(self.db);manifest=store.manifest(symbol)
            if manifest:
                rows=store.read(symbol)[-spec.training_window:];reference={'history_id':manifest['id'],'file_hash':manifest['file_hash'],'tail':spec.training_window}
            else:
                records=self.db.records('bar',symbol,limit=spec.training_window);rows=[r['payload'] for r in records];reference={'bar_ids':[r['id'] for r in records]}
            cutoff=now().isoformat();rows=[r for r in rows if max(r['available_at'],r['observed_at'])<=cutoff]
            rows=sorted(rows,key=lambda r:r['timestamp'])
            if len(rows)<400:raise ValueError('insufficient_data')
            features=self.db.records('feature',symbol,limit=1500)
            assets[symbol]={'bars':rows,'features':features};reference.update(feature_ids=[r['id'] for r in features],digest=stable_hash(assets[symbol]))
            refs[symbol]=reference;times+=list(r['timestamp'] for r in rows)
        news=[r for r in self.db.records('news_event',limit=1000) if any(s in spec.universe for s in r['payload']['symbols'])]
        dates=sorted(set(times));holdout=dates[int(len(dates)*.8)]
        snapshot={'assets':assets,'news':[r['payload'] for r in news],'holdout_start':holdout}
        references={'assets':refs,'news_ids':[r['id'] for r in news],'holdout_start':holdout,'dataset_hash':stable_hash(snapshot),'created_at':now().isoformat(),'universe':universe.model_dump(mode='json'),
                    'policy':'Retrospective market vintages; actual receipt time for external evidence; no fabricated historical news'}
        # Save only the selected universe metadata, never the full 500-asset roster per attempt.
        references['universe']['instruments']=[i for i in references['universe']['instruments'] if i['symbol'] in spec.universe]
        return snapshot,references
    def restore(self,registration):
        spec=ExperimentSpec.model_validate(registration['spec']);ref=registration['dataset'];assets={}
        for symbol,r in ref['assets'].items():
            if 'history_id' in r:
                manifest=self.db.get(r['history_id'])['payload'];path=ROOT/'data/history'/(manifest['hash']+'.parquet')
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=r['file_hash']:raise ValueError('Frozen dataset changed')
                rows=[{**v,'adjustment':manifest['adjustment'],'feed':manifest['feed']} for v in pd.read_parquet(path).to_dict('records')][-r['tail']:]
            else:rows=[self.db.get(i)['payload'] for i in r['bar_ids']]
            rows=sorted([v for v in rows if max(v['available_at'],v['observed_at'])<=ref['created_at']],key=lambda v:v['timestamp'])
            features=[]
            for rid in r['feature_ids']:
                item=self.db.get(rid)
                if not item:raise ValueError('Frozen evidence unavailable')
                # get() omits record available_at; use the stored column, not a guessed publication time.
                with Session(self.db.engine) as session:
                    row=session.get(Record,rid);features.append({'id':rid,'kind':row.kind,'symbol':row.symbol,'created_at':row.created_at,'available_at':row.available_at,'payload':row.payload})
            assets[symbol]={'bars':rows,'features':features}
            if stable_hash(assets[symbol])!=r['digest']:raise ValueError('Frozen dataset changed')
        snapshot={'assets':assets,'news':[self.db.get(i)['payload'] for i in ref['news_ids']],'holdout_start':ref['holdout_start']}
        if stable_hash(snapshot)!=ref['dataset_hash']:raise ValueError('Frozen dataset changed')
        return snapshot
    def register(self,spec,source=None):
        spec=ExperimentSpec.model_validate(spec);budget=self.budget()
        if len(spec.trials)>budget.maximum_trials:raise ValueError('Hyperparameter budget exceeded')
        snapshot,refs=self.snapshot(spec);prior=self.registrations();novel=novelty(spec,prior)
        # Lineage is inferred from economic feature family, even if the proposer renames it.
        lineage=(novel['nearest']['lineage'] if novel['nearest'] and novel['nearest']['similarity']>=.8 else 'lineage_'+stable_hash([sorted({FEATURES[f.name] for f in spec.features}),spec.target,spec.asset_class])[:20])
        pid='auto-'+uid();payload=spec.model_dump(mode='json')
        with self.db.transaction() as session:
            old=self._capacity(session,budget,registration=True)
            # Recheck novelty inside the writer lock to avoid simultaneous duplicate registrations.
            novel=novelty(spec,[r.payload for r in old])
            if novel['redundant']:raise ValueError('Redundant hypothesis; new wording or small parameter changes are not independent discovery')
            n=len(old)+1;alpha=spec.success.familywise_alpha/(n*(n+1)*len(spec.trials)*2)
            reg={'id':pid,'spec':payload,'lineage':lineage,'dataset':refs,'registered_at':now().isoformat(),'attempt':n,'alpha_threshold':alpha,'novelty':novel,
                 'implementation_hash':implementation_hash(),'source':source or {'provider':'deterministic_template'},'qualification':QualificationCriteria().model_dump(),
                 'immutable':True,'evaluation_metrics':['net_return','excess_return','drawdown','brier','return_mse','regime_stability'],'production_eligible':False}
            session.add(Record(id=pid,kind='auto_registration',symbol=','.join(spec.universe),available_at=now().isoformat(),payload=reg))
            session.add(Record(id=pid+'-declared',kind='experiment_definition',symbol=','.join(spec.universe),available_at=now().isoformat(),payload={'id':pid+'-declared','definition':{**payload,'family':lineage},'registered_at':reg['registered_at'],'autonomous_registration':pid}))
        return reg
    def _finish(self,reg,outcome):
        existing=self.db.get(reg['id']+'-result')
        if existing:return existing['payload']
        if len(json.dumps(outcome).encode())>200000:outcome={'status':'REJECTED','reason':'compact_result_budget'}
        result=outcome.get('result');reasons=[]
        if result:
            reasons=classify(result,ExperimentSpec.model_validate(reg['spec']),reg['alpha_threshold'])
            sketch=result['holdout']['signal_sketch']
            for old in self.db.records('auto_result',limit=2000):
                other=old['payload'].get('metrics',{}).get('holdout',{}).get('signal_sketch',{});common=sorted(set(sketch)&set(other))
                if len(common)>=20:
                    a=np.array([sketch[k] for k in common]);b=np.array([other[k] for k in common])
                    if np.std(a)>0 and np.std(b)>0 and abs(np.corrcoef(a,b)[0,1])>.95:reasons.append('redundant_alpha');break
        else:reasons=[outcome.get('reason','worker_failed')]
        status='REJECTED' if reasons else 'CHALLENGER';models=[]
        if status=='CHALLENGER':
            for symbol,artifact in result['artifacts'].items():
                mid='amodel_'+stable_hash([reg['id'],symbol])[:48]
                model={'id':mid,'registration_id':reg['id'],'symbol':symbol,'spec':reg['spec'],'artifact':artifact,'feature_families':result['feature_families'],'implementation_hash':reg['implementation_hash'],'production_eligible':False,'state':'CHALLENGER'}
                self.db.put('auto_model',model,symbol,record_id=mid);models.append(mid)
        metrics={k:v for k,v in (result or {}).items() if k!='artifacts'}
        payload={'registration_id':reg['id'],'status':status,'reasons':sorted(set(reasons)),'metrics':metrics,'model_ids':models,'p_value':max(float(result['holdout'][k]['p_value']) if result['holdout'][k]['p_value'] is not None else 1. for k in ('return_inference','excess_inference')) if result else None,
                 'completed_at':now().isoformat(),'resources':outcome.get('resources',{}),'production_eligible':False}
        self.db.put('auto_result',payload,record_id=reg['id']+'-result')
        if status=='REJECTED':self.db.put('experiment_failure',{'definition_id':reg['id']+'-declared','reason':'; '.join(reasons)},record_id=reg['id']+'-failure')
        # Share the existing experiment ledger and family correction views.
        self.db.put('experiment_holdout',{'definition_id':reg['id']+'-declared','family':reg['lineage'],'dataset_hash':reg['dataset']['dataset_hash'],'holdout':{'p_value':payload['p_value']},'autonomous_registration':reg['id']},record_id=reg['id']+'-holdout')
        return payload
    def run_next(self):
        token=uid();budget=self.budget();reg=None
        with self.db.transaction() as session:
            state=session.get(Setting,KEY);value=dict(state.value if state else {})
            if Budget.model_validate(value.get('budget',{})).paused:return {'status':'PAUSED'}
            if value.get('lease_until','')>now().isoformat():return {'status':'BUSY'}
            if value.get('active'):
                abandoned=session.get(Record,value['active'])
                if abandoned and not session.get(Record,value['active']+'-result'):
                    session.add(Record(id=value['active']+'-result',kind='auto_result',available_at=now().isoformat(),payload={'registration_id':value['active'],'status':'REJECTED','reasons':['interrupted_not_retried'],'p_value':None,'production_eligible':False}))
            for row in session.scalars(select(Record).where(Record.kind=='auto_registration').order_by(Record.created_at)):
                if not session.get(Record,row.id+'-result'):reg=row.payload;break
            if not reg:return {'status':'IDLE'}
            executions=list(session.scalars(select(Record).where(Record.kind=='auto_execution',Record.created_at>=now().date().isoformat())))
            if len(executions)>=budget.experiments_per_day:return {'status':'DAILY_BUDGET'}
            if self.disk_usage()['total_bytes']+2*1024**2>budget.storage_mb*1024**2:return {'status':'STORAGE_BUDGET'}
            session.add(Record(id=reg['id']+'-execution',kind='auto_execution',available_at=now().isoformat(),payload={'registration_id':reg['id'],'started_at':now().isoformat(),'budget':budget.model_dump()}))
            value.update(active=reg['id'],lease=token,lease_until=(now()+timedelta(seconds=budget.wall_seconds+120)).isoformat());session.merge(Setting(key=KEY,value=value))
        try:
            clean_abandoned(self.temporary,older_than=budget.wall_seconds+120)
            if reg['implementation_hash']!=implementation_hash():outcome={'status':'REJECTED','reason':'implementation_changed_reregister_required'}
            else:
                try:snapshot=self.restore(reg)
                except (ValueError,TypeError,KeyError,OSError):outcome={'status':'REJECTED','reason':'frozen_dataset_unavailable_or_changed'}
                else:outcome=execute(reg['spec'],snapshot,budget.model_dump(),self.temporary,lambda:self.stopping or self.budget().paused)
            try:return self._finish(reg,outcome)
            except (ValueError,KeyError,TypeError):return self._finish(reg,{'status':'REJECTED','reason':'invalid_worker_result'})
        finally:
            with self.db.transaction() as session:
                state=session.get(Setting,KEY);value=dict(state.value)
                if value.get('lease')==token:
                    for key in ('active','lease','lease_until'):value.pop(key,None)
                    state.value=value
    def observe(self):
        completed=self.db.records('forward_outcome',limit=10);failed=self.db.records('auto_result',limit=10);news=self.db.records('news_event',limit=10)
        manifests=[]
        for symbol in ('BTC-USD','ETH-USD','AAPL','MSFT','NVDA'):
            m=HistoryStore(self.db).manifest(symbol)
            if m:manifests.append({'symbol':symbol,'id':m['id'],'count':m['count']})
        governance=self.db.setting('alpha_governance',{});diagnostics=self.db.setting('qualification_diagnostics',{}).get('current',{})
        alpha_summary={k:{field:v.get(field) for field in ('state','weight','health') if field in v} for k,v in governance.get('families',{}).items() if isinstance(v,dict)}
        gates=[{k:g.get(k) for k in ('gate','count','fraction')} for g in diagnostics.get('gates',[]) if g.get('count')]
        return {'alpha_states':alpha_summary,'dependence':governance.get('dependence',{}),'gates':gates,'history':manifests,'forward_ids':[r['id'] for r in completed],
                'failure_reasons':sorted({reason for r in failed for reason in r['payload'].get('reasons',[])}),
                'news_ids':[r['id'] for r in news], 'news_categories':sorted({c for r in news for c in r['payload'].get('categories',[])})}
    async def propose(self):
        budget=self.budget()
        if budget.paused:return {'status':'PAUSED'}
        observation=await asyncio.to_thread(self.observe);fingerprint=stable_hash(observation)
        with self.db.transaction() as session:
            self._capacity(session,budget)
            row=session.get(Setting,KEY);state=dict(row.value if row else {})
            recent=self.db.records('auto_proposal',limit=10)
            if any(r['payload'].get('observation_hash')==fingerprint for r in recent):return {'status':'NO_NEW_OBSERVATIONS'}
            if state.get('last_review') and pd.Timestamp(now())-pd.Timestamp(state['last_review'])<pd.Timedelta(hours=budget.review_interval_hours):return {'status':'REVIEW_INTERVAL'}
            state.update(last_review=now().isoformat(),observation=observation);session.merge(Setting(key=KEY,value=state))
        prior=self.registrations();used={tuple(sorted(f['name'] for f in r['spec']['features'])) for r in prior}
        options=[(['return_20','regime_vol_ratio'],'trend_vs_volatility','Momentum may persist when volatility is stable because gradual information diffusion can dominate temporary risk shocks.'),
                 (['bollinger_z','volume_zscore'],'reversion_vs_liquidity','Short-term dislocations may revert only when trading activity provides sufficient liquidity to cover execution costs.'),
                 (['news_negative','return_5'],'news_first_sessions','Recently observed adverse events may weaken otherwise positive momentum during the first available trading sessions.'),
                 (['return_20','cross_sectional_momentum'],'relative_momentum','Relative momentum may distinguish common market exposure from asset-specific persistence among contemporaneous peers.')]
        choice=next((x for x in options if tuple(sorted(x[0])) not in used),None)
        if not choice:return {'status':'NO_DISTINCT_SUPPORTED_HYPOTHESIS'}
        names,lineage,rationale=choice
        universe=['BTC-USD','ETH-USD'] if 'cross_sectional_momentum' in names else ['BTC-USD']
        spec=ExperimentSpec(hypothesis=rationale,economic_mechanism=rationale,lineage=lineage,universe=universe,asset_class='crypto',features=[Feature(name=n) for n in names],target='relative_return' if len(universe)>1 else 'after_cost_return')
        source={'provider':'deterministic_template','observation_hash':fingerprint,'reason':'New evidence or coverage; previous failures constrain template selection. This is an observation-driven question, not a validated conclusion.'}
        # Optional language models see narrative research text, never raw bars/PnL/risk calculations.
        if budget.director!='off' and self.llm:
            from backend.llm.providers import TextTask
            settings=self.llm.settings();provider='local' if budget.director=='local' else 'openai'
            if settings.provider!='off' and (provider=='local' and settings.provider in ('local','hybrid') or provider=='openai' and settings.provider in ('openai','hybrid')):
                text='Research question: '+rationale+'\nPrevious rejection categories: '+', '.join(observation['failure_reasons'])+'\nObserved event categories: '+', '.join(observation['news_categories'])
                response=await self.llm._analyze(TextTask(task='research_hypothesis',text=text,source_reference='autonomous:'+fingerprint),settings.model_copy(update={'provider':provider,'escalation':False}))
                candidate=response.get('analysis',{}).get('hypothesis')
                if candidate:
                    try:spec=ExperimentSpec.model_validate(candidate);source={**source,**{k:response.get(k) for k in ('provider','model','run_id','prompt_version')}}
                    except ValueError:
                        source['provider_rejection']='Invalid proposal; deterministic fallback'
                        proposal=ReviewProposal(rationale='The narrative provider proposed an operation outside the supported experiment schema. It requires implementation review.',proposed_patch=json.dumps(candidate),tests='A reviewer must add leakage, budget and isolation tests before any implementation is accepted.',required_data='Verify actual timestamped source availability before extending the supported feature whitelist.',experiment_design='Treat the proposed hypothesis as unvalidated. Freeze a new specification, costs, lineage and holdout boundaries before evaluation.')
                        source['review_proposal']=self.code_proposal(proposal)['id']
                else:source['provider_status']=response['status']
        result={'observation_hash':fingerprint,'observation':observation,'spec':spec.model_dump(mode='json'),'source':source,'created_at':now().isoformat()}
        if self.budget().paused:return {'status':'PAUSED'}
        try:reg=await asyncio.to_thread(self.register,spec,source);result.update(status='PREREGISTERED',registration_id=reg['id'])
        except ValueError as e:result.update(status='REJECTED',reason=str(e))
        self.db.put('auto_proposal',result);return result
    def code_proposal(self,request):
        request=ReviewProposal.model_validate(request);budget=self.budget()
        with self.db.transaction() as session:self._capacity(session,budget)
        rid='auto-'+uid();path=ROOT/'research/proposals'/rid;path.mkdir(parents=True)
        # Non-executable text only; approval never invokes an interpreter or applies a patch.
        try:
            for name,value in {'RATIONALE.md':request.rationale,'proposed.patch.txt':request.proposed_patch,'TESTS.md':request.tests,'DATA.md':request.required_data,'EXPERIMENT.md':request.experiment_design}.items():(path/name).write_text('REQUIRES REVIEW\n\n'+value+'\n')
            self.db.put('auto_code_proposal',{'status':'REQUIRES_REVIEW','rationale':request.rationale,'path':'research/proposals/'+rid,'created_at':now().isoformat(),'executable':False},record_id=rid)
        except Exception:
            import shutil
            shutil.rmtree(path);raise
        return {'id':rid,'status':'REQUIRES_REVIEW'}
    def review_code(self,rid,request):
        row=self.db.get(rid)
        if not row or row['kind']!='auto_code_proposal':raise ValueError('Unknown implementation proposal')
        self.db.put('auto_code_review',{'proposal_id':rid,**request.model_dump(),'at':now().isoformat(),'executed':False},record_id=rid+'-review')
        return self.db.get(rid+'-review')['payload']
    def enroll(self,mid):
        from backend.research.forward import ForwardStudies,EnrollRequest,ForwardPolicy
        row=self.db.get(mid)
        if not row or row['kind']!='auto_model':raise ValueError('Select a governed challenger')
        result=self.db.get(row['payload']['registration_id']+'-result')
        if not result or result['payload']['status']!='CHALLENGER':raise ValueError('Historical gates did not pass')
        spec=ExperimentSpec.model_validate(row['payload']['spec'])
        policy=ForwardPolicy(fee_bps=spec.fee_bps,slippage_bps=spec.slippage_bps,participation=spec.maximum_participation,maximum_position_fraction=min(.25,spec.hypothetical_notional/100000))
        study=ForwardStudies(self.db).enroll(EnrollRequest(model_id=mid,policy=policy))
        self.db.put('auto_forward_link',{'model_id':mid,'study_id':study['id'],'status':'FORWARD_TESTING','qualification':QualificationCriteria().model_dump(),'production_eligible':False},record_id=mid+'-forward')
        return study
    async def run(self,stop):
        while not stop.is_set():
            try:
                if not self.budget().paused:
                    await self.propose();await asyncio.to_thread(self.run_next)
            except asyncio.CancelledError:
                self.stopping=True
                raise
            except Exception:
                # Fixed safe message, never arbitrary provider/credential exception text.
                self.db.set_setting('autonomous_research_health',{'status':'PAUSED_OR_RETRY','at':now().isoformat()})
            try:await asyncio.wait_for(stop.wait(),timeout=60)
            except TimeoutError:pass
