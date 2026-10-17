"""Disposable synthetic research acceptance. No live services, keys, trades or archives."""
import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from datetime import timedelta
import numpy as np
from backend.schemas.contracts import Bar,now
from backend.storage.database import Database,Base
from backend.research.autonomous.schema import Budget,ExperimentSpec,Feature
from backend.research.autonomous.service import AutonomousResearch
from backend.research.features import stable_hash


def demonstration():
    with tempfile.TemporaryDirectory(prefix='traderx-research-acceptance-') as folder:
        db=Database('sqlite:///'+folder+'/research.db');Base.metadata.create_all(db.engine)
        db.set_setting('alpha_governance',{'sentinel':'unchanged-production-policy'})
        db.set_setting('model_portfolio_policy',{'sentinel':'unchanged-risk-policy'})
        protected=stable_hash([db.setting('alpha_governance'),db.setting('model_portfolio_policy'),db.records('order')])
        rng=np.random.default_rng(184);n=1000;start=now()-timedelta(days=n+2);close=100*np.exp(np.cumsum(rng.normal(.0003,.01,n)))
        for i,c in enumerate(close):
            t=start+timedelta(days=i);o=float(close[max(0,i-1)])
            b=Bar(symbol='BTC-USD',provider='acceptance_fixture',timestamp=t,available_at=t+timedelta(days=1),observed_at=t+timedelta(days=1),open=o,high=max(o,c)*1.01,low=min(o,c)*.99,close=float(c),volume=float(rng.uniform(100000,200000)))
            db.put('bar',b,'BTC-USD')
        engine=AutonomousResearch(db,root=Path(folder)/'compute');engine.configure(Budget(paused=False,experiments_per_day=2))
        proposal=asyncio.run(engine.propose());one=engine.run_next()
        spec=ExperimentSpec(hypothesis='Short-lived dislocations may revert when observed trading volume supports low-cost execution.',economic_mechanism='Inventory imbalances may be temporary, so reversion conditioned on trailing liquidity could improve a long-cash strategy.',lineage='liquidity-reversion',universe=['BTC-USD'],asset_class='crypto',features=[Feature(name='bollinger_z'),Feature(name='volume_zscore')])
        registration=engine.register(spec);two=engine.run_next()
        rejected=False
        try:engine.register({**spec.model_dump(),'code':'enable_live_trading(); modify_risk_limits()'})
        except ValueError:rejected=True
        after=stable_hash([db.setting('alpha_governance'),db.setting('model_portfolio_policy'),db.records('order')])
        assert protected==after and rejected
        assert one['metrics'] and two['metrics'], [(r.get('status'),r.get('reasons')) for r in (one,two)]
        assert not list(engine.temporary.glob('run-*'))
        status=engine.status()
        output={'scope':'isolated synthetic acceptance; no market performance claim','experiments_executed':2,'proposal_status':proposal['status'],
                'results':[{'status':r['status'],'reasons':r['reasons'],'holdout':r['metrics']['holdout'],'resources':r['resources']} for r in (one,two)],
                'immutable_registrations':status['registered_total'],'malicious_spec_rejected':rejected,'production_state_hash_before':protected,'production_state_hash_after':after,
                'production_unchanged':protected==after,'orders_created':len(db.records('order')),'temporary_inputs_remaining':0,'storage':status['storage']}
        db.engine.dispose()
        return output

if __name__=='__main__':
    result=demonstration();path=Path('data/autonomous_acceptance/cycle.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('experiments_executed','proposal_status','production_unchanged','malicious_spec_rejected','orders_created','temporary_inputs_remaining')}))
    print('Results:',[r['status'] for r in result['results']])
