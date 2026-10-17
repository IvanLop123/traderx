"""Explicit model lifecycle and prospective evaluation; no automatic trading."""
import hashlib
import json
import numpy as np
import pandas as pd
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.storage.database import Setting
from backend.schemas.contracts import now
from backend.research.engine import ordered_bars,infer_registered

class ModelRegistry:
    def __init__(self,db):self.db=db
    def key(self,rid):return 'model_watch_'+hashlib.sha256(rid.encode()).hexdigest()[:32]
    def model(self,rid):
        row=self.db.get(rid)
        if not row or row['kind']!='model' or not row['payload'].get('artifact'):raise ValueError('Stored portable model required')
        return row['payload']
    def watches(self):
        with Session(self.db.engine) as session:return [r.value for r in session.scalars(select(Setting).where(Setting.key.like('model_watch_%')))]
    def start(self,rid):
        model=self.model(rid)
        row=next((r for r in self.db.records('model') if r['id']==rid),None)
        if not row:raise ValueError('Model unavailable')
        with self.db.transaction() as session:
            saved=session.get(Setting,self.key(rid))
            if saved and saved.value['state']!='retired':return saved.value
            # One current forward study per asset. Starting a version never copies prior observations.
            watches=list(session.scalars(select(Setting).where(Setting.key.like('model_watch_%'))))
            if sum(w.value['state']!='retired' for w in watches)>=10:raise ValueError('At most ten simultaneous forward studies')
            for watch in watches:
                if watch.value['symbol']==row['symbol'] and watch.value['state']!='retired':watch.value={**watch.value,'state':'retired','retired_at':now().isoformat()}
            state={'model_id':rid,'symbol':row['symbol'],'state':'shadow','started_at':now().isoformat(),'artifact_hash':hashlib.sha256(json.dumps(model['artifact'],sort_keys=True).encode()).hexdigest()}
            session.merge(Setting(key=self.key(rid),value=state))
        self.db.put('model_lifecycle',state,row['symbol']);return state
    def metrics(self,rid):
        labels=[r['payload'] for r in self.db.records('shadow_outcome') if r['payload']['model_id']==rid]
        forecasts=[r['payload'] for r in self.db.records('shadow_prediction') if r['payload']['model_id']==rid]
        n=len(labels);ret=np.array([r['actual_return'] for r in labels]);expected=np.array([r['expected_return'] for r in labels]);prob=np.array([r['probability_positive'] for r in labels])
        mse=float(np.mean((expected-ret)**2)) if n else None;zero=float(np.mean(ret**2)) if n else None;brier=float(np.mean((prob-(ret>0))**2)) if n else None
        return {'outcomes':n,'pending':len(forecasts)-n,'return_mse':mse,'zero_return_mse':zero,'brier':brier,'coin_flip_brier':.25,
                'forward_gates':{'at_least_30_nonoverlapping_outcomes':n>=30,'return_beats_zero':n>0 and mse<zero,'direction_beats_coin_flip':n>0 and brier<.25},
                'scope':'Prospective nonoverlapping model forecasts, not executed strategy P&L. Revisions after an outcome is stored do not rewrite that outcome.'}
    def promote(self,rid):
        model=self.model(rid);state=self.db.setting(self.key(rid))
        if not state or state['state'] not in ('shadow','paper_candidate'):raise ValueError('Start a prospective shadow study first')
        m=self.metrics(rid)
        if not model.get('research_candidate_eligible') or not all(m['forward_gates'].values()):raise ValueError('Historical and prospective benchmark gates must all pass; no model is promoted by complexity alone')
        state={**state,'state':'paper_candidate','promoted_at':now().isoformat(),'promotion_metrics':m};self.db.set_setting(self.key(rid),state);self.db.put('model_lifecycle',state,state['symbol']);return state
    def retire(self,rid):
        state=self.db.setting(self.key(rid))
        if not state:raise ValueError('No forward study for this model')
        state={**state,'state':'retired','retired_at':now().isoformat()};self.db.set_setting(self.key(rid),state);self.db.put('model_lifecycle',state,state['symbol']);return state
    def eligible(self,rid):
        state=self.db.setting(self.key(rid));model=self.model(rid)
        return bool(state and state['state']=='paper_candidate' and model.get('research_candidate_eligible') and all(self.metrics(rid)['forward_gates'].values()))
    def status(self):
        rows=self.db.records('model',limit=20)
        return [{'id':r['id'],'symbol':r['symbol'],'trained_at':r['payload'].get('trained_at'),'historical_eligible':r['payload'].get('research_candidate_eligible',False),
                 'lifecycle':self.db.setting(self.key(r['id']),{'state':'research'}),'forward':self.metrics(r['id'])} for r in rows]
    def refresh(self):
        for watch in self.watches():
            if watch['state']=='retired':continue
            rid=watch['model_id'];symbol=watch['symbol'];model=self.model(rid)
            try:
                if hashlib.sha256(json.dumps(model['artifact'],sort_keys=True).encode()).hexdigest()!=watch['artifact_hash']:raise ValueError('Model artifact changed')
                df=ordered_bars([r['payload'] for r in self.db.records('bar',symbol)])
                # Never treat a future-dated observation as currently available.
                df=df[(pd.to_datetime(df.available_at,utc=True)<=pd.Timestamp(now()))&(pd.to_datetime(df.observed_at,utc=True)<=pd.Timestamp(now()))]
                if len(df)<65:continue
                predictions=[r['payload'] for r in self.db.records('shadow_prediction',symbol) if r['payload']['model_id']==rid]
                for pred in predictions:
                    if self.db.get('outcome-'+pred['id']):continue
                    later=df[pd.to_datetime(df.available_at,utc=True)>pd.Timestamp(pred['base_available_at'])]
                    horizon=model['hyperparameters']['horizon']
                    if len(later)<horizon:continue
                    target=later.iloc[horizon-1]
                    if pd.Timestamp(target.available_at)<=pd.Timestamp(pred['decided_at']):raise ValueError('Prospective label would precede prediction')
                    actual=float(target.close)/pred['base_close']-1
                    payload={**pred,'actual_return':actual,'target_timestamp':str(target.timestamp),'observed_at':now().isoformat()}
                    self.db.put('shadow_outcome',payload,symbol,record_id='outcome-'+pred['id'])
                # Wait for the previous horizon to finish: overlapping outcomes are not counted as independent observations.
                if any(not self.db.get('outcome-'+p['id']) for p in predictions):continue
                last=df.iloc[-1];as_of=str(last.available_at)
                if pd.Timestamp(as_of)<pd.Timestamp(watch['started_at']):continue
                prediction_id=hashlib.sha256((rid+as_of).encode()).hexdigest()
                if self.db.get(prediction_id):continue
                output=infer_registered(model,df.to_dict('records'),self.db.records('feature',symbol))
                payload={'id':prediction_id,'model_id':rid,'symbol':symbol,'base_timestamp':str(last.timestamp),'base_available_at':as_of,'base_close':float(last.close),'decided_at':now().isoformat(),**output}
                self.db.put('shadow_prediction',payload,symbol,record_id=prediction_id)
                current=self.db.setting(self.key(rid),watch)
                if current['state']=='paper_candidate' and not self.eligible(rid):current={**current,'state':'shadow','demoted_at':now().isoformat(),'reason':'Prospective benchmark gate no longer passes'};self.db.put('model_lifecycle',current,symbol)
                self.db.set_setting(self.key(rid),{**current,'monitor_status':'WORKING','checked_at':now().isoformat()})
            except Exception:
                current=self.db.setting(self.key(rid),watch)
                self.db.set_setting(self.key(rid),{**current,'state':'shadow','monitor_status':'DEGRADED','checked_at':now().isoformat()})
