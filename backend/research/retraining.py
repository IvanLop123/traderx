"""Scheduled local forecasting experiments. Never activates a model or creates orders."""
import hashlib
import json
from datetime import datetime, timedelta
from pydantic import Field
from backend.schemas.contracts import Contract, now, uid
from backend.storage.database import Setting, Record
from backend.research.engine import ordered_bars, train_fusion


class TrainingSchedule(Contract):
    enabled: bool = False
    symbols: list[str] = Field(default_factory=lambda: ['BTC-USD', 'ETH-USD', 'SOL-USD'], min_length=1, max_length=10)
    interval_days: int = Field(default=7, ge=1, le=90)
    minimum_new_bars: int = Field(default=7, ge=1, le=90)
    horizon: int = Field(default=5, ge=1, le=20)
    compare_models: bool = True

    @classmethod
    def validate_symbols(cls, settings):
        import re
        if len(set(settings.symbols)) != len(settings.symbols) or any(not re.fullmatch(r'[A-Z0-9_.-]{1,30}', s) for s in settings.symbols):
            raise ValueError('Use unique uppercase asset symbols')
        return settings


class Retrainer:
    def __init__(self, db):
        self.db = db

    def settings(self):
        return TrainingSchedule.validate_symbols(TrainingSchedule.model_validate(self.db.setting('training_schedule', {})))

    def configure(self, settings):
        TrainingSchedule.validate_symbols(settings)
        self.db.set_setting('training_schedule', settings.model_dump())
        self.db.put('audit', {'action': 'training_schedule_changed', 'settings': settings.model_dump()})
        return self.status()

    def status(self):
        return {'settings': self.settings().model_dump(), 'worker': self.db.setting('training_worker', {'status': 'NOT_STARTED'}),
                'runs': self.db.records('training_run', limit=20),
                'scope': 'Local statistical predictors only. New research versions require separate prospective validation and explicit promotion. No language-model fine-tuning or automatic trading.'}

    def cycle(self):
        settings = self.settings()
        if not settings.enabled:
            self.db.set_setting('training_worker', {'status': 'DISABLED', 'checked_at': now().isoformat()})
            return []
        token = uid()
        # A durable global lease prevents parallel workers from fitting the same batch.
        with self.db.transaction() as session:
            lease = session.get(Setting, 'training_lease')
            if lease and lease.value['until'] > now().isoformat():
                return []
            session.merge(Setting(key='training_lease', value={'token': token, 'until': (now()+timedelta(hours=1)).isoformat()}))
        results = []
        try:
            for symbol in settings.symbols:
                # A stop requested during a fit takes effect before the next asset.
                if not self.settings().enabled:
                    break
                result = self.train_if_due(symbol, settings, token)
                results.append({'symbol': symbol, **result})
            self.db.set_setting('training_worker', {'status': 'WORKING', 'checked_at': now().isoformat(), 'outcomes': results})
            return results
        finally:
            with self.db.transaction() as session:
                lease = session.get(Setting, 'training_lease')
                if lease and lease.value['token'] == token:
                    session.delete(lease)

    def train_if_due(self, symbol, settings, lease_token):
        key = 'training_last_'+hashlib.sha256((symbol+str(settings.horizon)).encode()).hexdigest()[:32]
        previous = self.db.setting(key, {})
        history = [r['payload'] for r in self.db.records('bar', symbol) if datetime.fromisoformat(r['payload']['available_at']) <= now() and datetime.fromisoformat(r['payload']['observed_at']) <= now()]
        saved_model=self.db.get('scheduled-model-'+previous.get('input_hash','')) if previous else None
        successful_at=previous.get('succeeded_at') or (saved_model['payload'].get('trained_at') if saved_model else None)
        summary={'last_training_at':previous.get('attempted_at'),'last_successful_training_at':successful_at,
                 'last_data_update':max((r['observed_at'] for r in history),default=None),
                 'new_observations':len({r['timestamp'] for r in history if r['timestamp']>previous.get('last_timestamp','')})}
        if previous.get('attempted_at') and now()-datetime.fromisoformat(previous['attempted_at']) < timedelta(days=settings.interval_days):
            return {'status': 'WAITING_FOR_SCHEDULE',**summary,'next_eligible_at':(datetime.fromisoformat(previous['attempted_at'])+timedelta(days=settings.interval_days)).isoformat()}
        try:
            df = ordered_bars(history)
            if len(df) < 250:
                return {'status': 'WAITING_FOR_HISTORY', 'completed_bars': len(df),**summary}
            if previous.get('last_timestamp'):
                new_bars = int((df.timestamp > previous['last_timestamp']).sum())
                if new_bars < settings.minimum_new_bars:
                    return {'status': 'WAITING_FOR_NEW_BARS', 'new_bars': new_bars,**summary}
            if now()-datetime.fromisoformat(str(df.iloc[-1].available_at)) > timedelta(days=4):
                return {'status': 'STALE_HISTORY',**summary}
            features = self.db.records('feature', symbol)
            # Observation metadata may change on download; identify actual input values too.
            fingerprint = hashlib.sha256(json.dumps({'version':'scheduled-v3','bars': [{k:v for k,v in r.items() if k not in ('observed_at','id')} for r in df.to_dict('records')], 'features': features, 'horizon': settings.horizon}, sort_keys=True).encode()).hexdigest()
            attempt = {'attempted_at': now().isoformat(), 'last_timestamp': str(df.iloc[-1].timestamp), 'input_hash': fingerprint}
            self.db.set_setting(key, attempt)
            result = train_fusion(df.to_dict('records'), settings.horizon, features)
            result['training_origin'] = 'scheduled_local_retraining'
            result['schedule'] = settings.model_dump()
            model_id = 'scheduled-model-'+fingerprint
            with self.db.transaction() as session:
                lease = session.get(Setting, 'training_lease')
                if not lease or lease.value['token'] != lease_token or lease.value['until'] <= now().isoformat():
                    return {'status': 'LEASE_EXPIRED',**summary}
                if not session.get(Record, model_id):
                    session.add(Record(id=model_id, kind='model', symbol=symbol, available_at=now().isoformat(), payload=result))
            outcome = {'status': 'RESEARCH_VERSION_SAVED', 'model_id': model_id, 'historical_eligible': result['research_candidate_eligible'],
                       'trained_at': result['trained_at'], 'input_hash': fingerprint, 'activation': 'research_only',**summary,
                       'data_range':{'start':str(df.iloc[0].timestamp),'end':str(df.iloc[-1].timestamp),'bars':len(df)},
                       'feature_count':len(result['features']),'excluded_features':result['insufficient_historical_coverage'],
                       'validation':result['research_candidate_gates'],'model_type':result['model']}
            self.db.set_setting(key,{**attempt,'succeeded_at':result['trained_at']})
            if settings.compare_models and len(df)>=400:
                from backend.research.studies import Studies,StudyRequest
                try:
                    study=Studies(self.db).run(StudyRequest(symbol=symbol))
                    outcome['comparison_study_id']=study['id'];outcome['comparison_status']=study['holdout']['status']
                except Exception:outcome['comparison_status']='COMPARISON_FAILED_BASELINE_PRESERVED'
        except ValueError:
            outcome = {'status': 'INSUFFICIENT_OR_INVALID_DATA',**summary}
        except Exception:
            outcome = {'status': 'TRAINING_FAILED',**summary}
        self.db.put('training_run', outcome, symbol)
        return outcome
