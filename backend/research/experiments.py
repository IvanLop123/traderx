"""Declared, versioned signal experiments with availability joins and sealed holdout."""
import hashlib
import json
from typing import Literal, Annotated
import numpy as np
import pandas as pd
from pydantic import Field,AwareDatetime,model_validator
from scipy.stats import spearmanr,false_discovery_control
from backend.schemas.contracts import Contract,now,uid
from backend.research.engine import ordered_bars,features,performance
from backend.research.point_in_time import join_features_asof
from backend.research.governance import block_bootstrap

class ExperimentDefinition(Contract):
    hypothesis:str=Field(min_length=5,max_length=2000)
    family:str=Field(default='declared_signals',min_length=1,max_length=60,pattern=r'^[a-zA-Z0-9_-]+$')
    universe:list[Annotated[str, Field(pattern=r'^[A-Z0-9.-]{1,30}$')]]=Field(min_length=1,max_length=20)
    population:Literal['all_observations','signal_above_threshold','signal_below_threshold']='all_observations'
    signal:str=Field(default='return_20',min_length=1,max_length=100,pattern=r'^[a-zA-Z0-9_.:-]+$')
    target:Literal['forward_return','excess_return','realized_volatility']='forward_return'
    horizon:int=Field(default=5,ge=1,le=60)
    threshold:float=0
    benchmark:Annotated[str, Field(pattern=r'^[A-Z0-9.-]{1,30}$')]|None=None
    start:AwareDatetime|None=None
    end:AwareDatetime|None=None
    training_end:AwareDatetime|None=None
    validation_end:AwareDatetime|None=None
    min_volume:float=Field(default=0,ge=0)
    regime:Literal['all','uptrend','downtrend','range']='all'
    fee_bps:float=Field(default=5,ge=0,le=1000)
    slippage_bps:float=Field(default=5,ge=0,le=1000)
    spread_bps:float=Field(default=2,ge=0,le=1000)
    strict_observed:bool=True
    @model_validator(mode='after')
    def validate_definition(self):
        if self.target=='excess_return' and not self.benchmark:raise ValueError('An explicit benchmark is required for excess return')
        if bool(self.training_end)!=bool(self.validation_end):raise ValueError('Supply both training and validation boundaries, or neither')
        if self.training_end and self.training_end>=self.validation_end:raise ValueError('Training must end before validation')
        if self.start and self.end and self.start>=self.end:raise ValueError('Invalid experiment period')
        if len(set(self.universe))!=len(self.universe):raise ValueError('Duplicate universe member')
        return self

def _rank(a,b):
    if len(a)<3 or np.std(a)==0 or np.std(b)==0:return None
    v=float(spearmanr(a,b).statistic);return v if np.isfinite(v) else None

def evaluate_rows(rows,horizon):
    if not rows:return {'status':'NO_ELIGIBLE_OBSERVATIONS','samples':0,'p_value':None}
    df=pd.DataFrame(rows).sort_values(['available_at','symbol']);selected=df[df.selected].copy();n=len(selected)
    if not n:return {'status':'NO_FILTER_MATCHES','samples':0,'eligible_rows':len(df),'p_value':None}
    r=selected.net_return.to_numpy();ic=_rank(selected.signal.to_numpy(),selected.target.to_numpy());pvalue=None
    # Shift each asset's target independently; never permute across assets or split periods.
    if n>=30 and ic is not None:
        rng=np.random.default_rng(1729);extreme=0
        for _ in range(499):
            shuffled=selected.target.copy()
            for _,group in selected.groupby('symbol'):
                values=group.target.to_numpy();shuffled.loc[group.index]=np.roll(values,int(rng.integers(1,len(values)))) if len(values)>1 else values
            null=_rank(selected.signal.to_numpy(),shuffled.to_numpy())
            extreme+=null is not None and abs(null)>=abs(ic)
        pvalue=(extreme+1)/500
    daily=selected.groupby('available_at').net_return.mean().to_numpy()
    curve=np.r_[1.,np.cumprod(1+daily)]
    stats=performance(curve,252/horizon)
    return {'status':'EXPLORATORY','samples':n,'eligible_rows':len(df),'coverage':n/len(df),'information_coefficient':ic,'p_value':pvalue,
            'mean_forward_return':float(selected.forward_return.mean()),'median_forward_return':float(selected.forward_return.median()),
            'mean_excess_return':float(selected.excess_return.mean()) if selected.excess_return.notna().all() else None,
            'hit_rate':float((r>0).mean()),'mean_realized_volatility':float(selected.realized_volatility.mean()),
            'mean_adverse_excursion':float(selected.adverse_excursion.mean()),'mean_favorable_excursion':float(selected.favorable_excursion.mean()),
            'mean_net_return_after_costs':float(r.mean()),'equal_weight_event_sleeve':stats,
            'estimated_round_trips':n,'median_participation_capacity_units':float(selected.capacity_units.median()),
            'mean_return_interval':block_bootstrap(daily,block_length=5),
            'by_asset':{str(k):{'samples':len(g),'mean_net_return':float(g.net_return.mean()),'ic':_rank(g.signal.to_numpy(),g.target.to_numpy())} for k,g in selected.groupby('symbol')},
            'by_regime':{str(k):{'samples':len(g),'mean_net_return':float(g.net_return.mean())} for k,g in selected.groupby('regime')},
            'by_subperiod':{str(k):{'samples':len(g),'mean_net_return':float(g.net_return.mean())} for k,g in selected.groupby(selected.available_at.str[:4])},
            'warnings':['Equal-weight event sleeves are a research diagnostic, not an executable multi-asset portfolio. Use event replay for actual cash/overlap constraints.',
                        'Nonoverlapping labels within each asset do not remove market-wide dependence. Shift-test and bootstrap inference assume sufficiently stable dependence.',
                        'Annualization uses a 252-session convention. Capacity uses 1% of prior completed volume in instrument units; market impact is not measured.']}

class ExperimentLab:
    def __init__(self,db):self.db=db
    def dataset(self,definition):
        d=definition;result=[];coverage={};benchmark=None
        if d.benchmark:
            b=ordered_bars([r['payload'] for r in self.db.records('bar',d.benchmark)])
            benchmark={pd.Timestamp(r.timestamp).normalize():r for _,r in b.iterrows()}
        for symbol in d.universe:
            data=ordered_bars([r['payload'] for r in self.db.records('bar',symbol)])
            data=data[pd.to_datetime(data.available_at,utc=True)<=pd.Timestamp(now())].reset_index(drop=True)
            matrix=features(data.to_dict('records'));external=join_features_asof(data.available_at,self.db.records('feature',symbol))
            if d.signal in matrix:signal=matrix[d.signal]
            elif d.signal in external:signal=external[d.signal]
            else:coverage[symbol]={'rows':len(data),'usable':0,'reason':'SIGNAL_NOT_OBSERVED'};continue
            used=0;next_entry=0
            for i in range(len(data)-d.horizon-1):
                if i<next_entry or not pd.notna(signal.iloc[i]):continue
                decision=data.iloc[i];entry=data.iloc[i+1];exit_row=data.iloc[i+d.horizon]
                available=pd.Timestamp(decision.available_at)
                if d.strict_observed:available=max(available,pd.to_datetime(data.observed_at.iloc[:i+1],utc=True).max())
                if available>pd.Timestamp(entry.timestamp):continue
                if d.start and available<pd.Timestamp(d.start) or d.end and pd.Timestamp(exit_row.available_at)>pd.Timestamp(d.end):continue
                price=float(entry.open);last=float(exit_row.close);window=data.iloc[i+1:i+d.horizon+1]
                if price<=0:continue
                ret=last/price-1;excess=None
                if benchmark:
                    first=benchmark.get(pd.Timestamp(entry.timestamp).normalize());final=benchmark.get(pd.Timestamp(exit_row.timestamp).normalize())
                    # Benchmark is a target, measured over the identical open-to-close window.
                    if first is not None and final is not None and float(first.open)>0:
                        excess=ret-(float(final.close)/float(first.open)-1)
                vol=float(np.sqrt(np.sum(np.diff(np.log(np.r_[price,window.close.to_numpy()]))**2)))
                target=ret if d.target=='forward_return' else excess if d.target=='excess_return' else vol
                if target is None:continue
                trend=float(matrix.return_20.iloc[i]) if pd.notna(matrix.return_20.iloc[i]) else 0
                regime='uptrend' if trend>.03 else 'downtrend' if trend<-.03 else 'range'
                selected=(d.population=='all_observations' or (d.population=='signal_above_threshold' and signal.iloc[i]>d.threshold) or (d.population=='signal_below_threshold' and signal.iloc[i]<d.threshold)) and float(decision.volume)>=d.min_volume and (d.regime=='all' or d.regime==regime)
                cost=(2*d.fee_bps+2*d.slippage_bps+d.spread_bps)/10000
                result.append({'symbol':symbol,'available_at':available.isoformat(),'label_end':str(exit_row.available_at),'signal':float(signal.iloc[i]),'target':target,'forward_return':ret,'excess_return':excess,'realized_volatility':vol,'net_return':ret-cost,'adverse_excursion':float(window.low.min())/price-1,'favorable_excursion':float(window.high.max())/price-1,'capacity_units':float(decision.volume)*.01,'regime':regime,'selected':bool(selected)})
                used+=1;next_entry=i+d.horizon
            coverage[symbol]={'rows':len(data),'usable':used}
        return sorted(result,key=lambda r:(r['available_at'],r['symbol'])),coverage
    def run(self,d):
        rid=uid();self.db.put('experiment_definition',{'id':rid,'definition':d.model_dump(mode='json'),'registered_at':now().isoformat()},record_id=rid)
        try:
            rows,coverage=self.dataset(d)
            times=sorted(set(r['available_at'] for r in rows))
            if len(times)<30:raise ValueError('At least 30 nonoverlapping eligible observation dates required; missing source history is not imputed')
            train_end=pd.Timestamp(d.training_end) if d.training_end else pd.Timestamp(times[int(len(times)*.6)])
            val_end=pd.Timestamp(d.validation_end) if d.validation_end else pd.Timestamp(times[int(len(times)*.8)])
            train=[r for r in rows if pd.Timestamp(r['label_end'])<train_end]
            validation=[r for r in rows if pd.Timestamp(r['available_at'])>=train_end and pd.Timestamp(r['label_end'])<val_end]
            holdout=[r for r in rows if pd.Timestamp(r['available_at'])>=val_end]
            if min(len(train),len(validation),len(holdout))<5:raise ValueError('Chronological split has insufficient rows after label purge')
            dataset_hash=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
            self.db.set_setting('experiment_'+rid,{'definition_id':rid,'holdout':holdout,'released':False})
            result={'definition_id':rid,'definition':d.model_dump(mode='json'),'dataset_hash':dataset_hash,'coverage':coverage,'training':evaluate_rows(train,d.horizon),'validation':evaluate_rows(validation,d.horizon),
                    'holdout':{'status':'SEALED','samples':len(holdout)},'split':{'training_end':train_end.isoformat(),'validation_end':val_end.isoformat(),'purged':len(rows)-len(train)-len(validation)-len(holdout)},
                    'status':'RESEARCH_ONLY','warning':'Universe and equity corporate actions must be reviewed. Retrospective market bars are labeled explicitly; evidence features always use actual observed availability.'}
            self.db.put('experiment_study',result,','.join(d.universe)[:50],record_id='study-'+rid);return result
        except Exception as exc:
            self.db.put('experiment_failure',{'definition_id':rid,'reason':str(exc)[:300]});raise
    def release(self,rid):
        state=self.db.setting('experiment_'+rid);row=self.db.get('study-'+rid)
        if not state or not row:raise ValueError('Experiment not found')
        existing=self.db.get('holdout-'+rid)
        if existing:return existing['payload']
        d=row['payload']['definition'];result={'definition_id':rid,'family':d['family'],'dataset_hash':row['payload']['dataset_hash'],'released_at':now().isoformat(),'holdout':evaluate_rows(state['holdout'],d['horizon']),'warning':'This holdout is now inspected. Further choices based on it require fresh prospective validation.'}
        self.db.put('experiment_holdout',result,record_id='holdout-'+rid);return result
    def families(self):
        from sqlalchemy import select,func
        from sqlalchemy.orm import Session
        from backend.storage.database import Record
        # Count all registered attempts, including failed or selectively unreleased trials.
        with Session(self.db.engine) as session:
            definitions=session.scalars(select(Record).where(Record.kind=='experiment_definition')).all()
            released=session.scalars(select(Record).where(Record.kind=='experiment_holdout')).all()
            failed=session.scalar(select(func.count()).select_from(Record).where(Record.kind=='experiment_failure'))
            by_id={r.payload['definition_id']:r.payload for r in released};families={}
            for row in definitions:
                p=by_id.get(row.id,{});family=row.payload['definition']['family']
                families.setdefault(family,[]).append({'definition_id':row.id,'dataset_hash':p.get('dataset_hash'),'p_value':p.get('holdout',{}).get('p_value'),'released':bool(p)})
            for items in families.values():
                adjusted=false_discovery_control([x['p_value'] if x['p_value'] is not None else 1. for x in items],method='by')
                for row,value in zip(items,adjusted):row['adjusted_p_value']=float(value) if row['p_value'] is not None else None
            return {'registered_trials':len(definitions),'failed_trials':failed,'released_holdouts':len(released),'families':families,'warning':'Declared-family BY correction counts every registered trial including failures, repeats and unreleased holdouts (missing p-values count as 1). It cannot account for unrecorded experiments outside this application.'}
