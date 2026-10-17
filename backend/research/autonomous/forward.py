"""Frozen safe-JSON challenger adapter for the existing scientific forward ledger."""
import pandas as pd
from backend.research.features import stable_hash
from backend.research.autonomous.schema import ExperimentSpec
from backend.research.autonomous.numerics import frames,predict
from backend.research.autonomous.service import AutonomousResearch,implementation_hash

def prediction(db,model_id):
    row=db.get(model_id)
    if not row or row['kind']!='auto_model':raise ValueError('Unknown challenger')
    m=row['payload']
    if m['implementation_hash']!=implementation_hash():raise ValueError('Frozen research implementation changed')
    spec=ExperimentSpec.model_validate(m['spec']);snapshot,_=AutonomousResearch(db).snapshot(spec)
    df,x=frames(spec,snapshot)[m['symbol']];artifact=m['artifact'];values=x.iloc[[-1]]
    if any(pd.isna(values.iloc[0][n]) for n in artifact['features']):raise ValueError('Missing current challenger evidence')
    expected,probability=predict(artifact,values)
    regime='uptrend' if df.close.pct_change(20).iloc[-1]>.03 else 'downtrend' if df.close.pct_change(20).iloc[-1]<-.03 else 'range'
    dollar=float((df.close*df.volume).tail(20).mean())
    if (spec.regime!='all' and spec.regime!=regime) or df.close.iloc[-1]<spec.minimum_price or dollar<spec.minimum_dollar_volume or spec.hypothetical_notional>dollar*spec.maximum_participation:
        expected[0]=0.;probability[0]=0.
    return {'model_id':model_id,'model_hash':stable_hash(m),'symbol':m['symbol'],'features':{n:float(values.iloc[0][n]) for n in artifact['features']},
            'feature_available_at':str(df.available_at.iloc[-1]),'feature_families':m['feature_families'],'data_version':{'dataset_hash':stable_hash(snapshot)},'entry_delay_bars':2,
            'prediction':float(expected[0]),'probability':float(probability[0]),'probability_target':spec.target,'uncertainty':artifact['uncertainty'],'horizon':spec.horizon,
            'regime':regime}
