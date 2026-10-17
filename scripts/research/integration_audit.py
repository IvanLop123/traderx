"""Explicit, bounded re-evaluation; read production inputs, write audit receipts only."""
import sys,json,hashlib,signal,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from backend.storage.database import Database,Base
from backend.research.advanced import lab
from backend.research.advanced.models import block_test
from backend.ensemble.engine import decide,VERSION

class ResearchOnly:
    """Keep all registrations/results in an isolated database, never production state."""
    def __init__(self,source,target):self.source=source;self.target=target
    def get(self,rid):return self.target.get(rid) if rid.startswith('advanced_') else self.source.get(rid)
    def setting(self,key,default=None):return self.source.setting(key,default)
    def put(self,*args,**kwargs):return self.target.put(*args,**kwargs)
    def set_setting(self,*args,**kwargs):return self.target.set_setting(*args,**kwargs)

def main():
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('Audit wall budget exceeded')));signal.alarm(900)
    root=Path(__file__).resolve().parents[2];out=root/'data/integration_audit';out.mkdir(exist_ok=True)
    source=Database();previous=source.setting('advanced_research_result',{});wanted=previous['identity']['panel_sha256']
    path=next(p for p in (root/'data/strategy_panels').glob('*.parquet') if hashlib.sha256(p.read_bytes()).hexdigest()==wanted)
    captured=[];original=lab.evaluate
    def capture(frame,pred,cal,cpred):
        result=original(frame,pred,cal,cpred);captured.append((frame,pred,cal,cpred));return result
    lab.evaluate=capture
    with tempfile.TemporaryDirectory(prefix='traderx-audit-') as directory:
        target=Database('sqlite:///'+directory+'/research.db');Base.metadata.create_all(target.engine)
        result=lab.run(ResearchOnly(source,target),path);target.engine.dispose()
    lab.evaluate=original
    (out/'comparable-models.json').write_text(json.dumps(result,indent=2))
    comparisons=[];offset=0
    for fold in result['folds']:
        records=dict(zip(fold['results'],captured[offset:offset+len(fold['results'])]));offset+=len(records)
        frame=records['momentum'][0];family={};names=['momentum','mean_reversion','volatility']
        for name in names:
            _,pred,cal,cpred=records[name];labels=(cal.net_return>0).astype(int)
            if labels.nunique()==2 and np.std(cpred)>1e-12:
                clf=LogisticRegression(C=1,max_iter=300).fit((cpred*100).reshape(-1,1),labels);prob=clf.predict_proba((pred*100).reshape(-1,1))[:,1]
            else:prob=np.full(len(pred),float(labels.mean()))
            family[name]={'pred':pred,'prob':prob,'unc':float(np.std(cal.net_return-cpred)), 'history':{'mse':float(np.mean((cal.net_return-cpred)**2)),'zero_mse':float(np.mean(cal.net_return**2)),'nonoverlapping_date_clusters':cal.date.nunique()}}
        comparisons.append({'fold':fold['fold'],'rows':len(frame),'assets':int(frame.symbol.nunique()),'modes':{}})
        for mode in ('equal','fixed','dynamic'):
            predictions=[];returns=[];actions=[]
            for j,row in enumerate(frame.itertuples()):
                votes=[{'family':name,'model_id':name,'horizon':5,'prediction_after_cost':float(family[name]['pred'][j]),'probability':float(family[name]['prob'][j]),'uncertainty':family[name]['unc'],'historical_reliability':family[name]['history'],'health':[],'eligible':False} for name in names]
                decision=decide({'symbol':row.symbol,'feature_available_at':row.date.isoformat(),'votes':votes,'health':[]}, {'eligibility':{'eligible':True}},at=row.date.to_pydatetime(),mode=mode)
                predictions.append(decision['edge']);actions.append(decision['action']);returns.append(row.net_return if decision['action']=='BUY' else 0.)
            daily=pd.Series(returns,index=frame.date).groupby(level=0).mean()
            comparisons[-1]['modes'][mode]={'mse':float(np.mean((frame.net_return-np.array(predictions))**2)),'after_cost_return':block_test(daily),'buy_rows':actions.count('BUY'),'cash_rows':len(actions)-actions.count('BUY')}
        best=min(names,key=lambda name:family[name]['history']['mse']);mask=(family[best]['pred']>0)&(family[best]['prob']>=.55)
        comparisons[-1]['calibration_selected_individual']={'family':best,'selection':'Calibration-only MSE; not test winner','after_cost_return':block_test(pd.Series(np.where(mask,frame.net_return,0.),index=frame.date).groupby(level=0).mean())}
        comparisons[-1]['momentum_baseline']=block_test(frame.net_return.where(frame.return_20>0,0.).groupby(frame.date).mean())
        comparisons[-1]['equal_asset_after_cost_benchmark']=block_test(frame.groupby('date').net_return.mean())
        comparisons[-1]['cash_benchmark']=0.
        print('Canonical ensemble audited',fold['fold'],flush=True)
    payload={'version':VERSION,'folds':comparisons,'scope':'Exact runtime decision function on the three comparable price families from the existing advanced protocol. Not a reconstruction of all current family artifacts, portfolio fills or prospective performance.','sample_policy':'Same dated eligible test rows as the model comparison; calibration precedes test; inspected retrospective periods; no model promotion','production_writes':False,'selected_runtime_mode':'equal','reason':'No independent forward evidence establishing a complex-weighting advantage'}
    (out/'canonical-ensemble.json').write_text(json.dumps(payload,indent=2))
    print('Audit results saved; production models unchanged',flush=True)
if __name__=='__main__':main()
