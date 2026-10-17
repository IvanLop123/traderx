"""Historical event replay of recorded as-of snapshots and actual quotes, in a disposable book."""
from collections import Counter
import pandas as pd
from backend.storage.database import Database,Base
from backend.selection.policy import PortfolioPolicy
from backend.selection.opportunities import score_opportunity
from backend.selection.risk import size
from backend.qualification.books import ComparisonBook
from backend.qualification.policy import QualificationCriteria
from backend.research.features import stable_hash
from backend.schemas.contracts import now

def replay(db,limit=50):
    sources=sorted(db.records('auto_snapshot',limit=None),key=lambda r:r['available_at'])[-max(1,min(limit,100)):]
    if not sources:raise ValueError('No saved point-in-time snapshots available')
    isolated=Database('sqlite://');Base.metadata.create_all(isolated.engine)
    isolated.set_setting('research_calendar',db.setting('research_calendar',{}))
    first=pd.Timestamp(sources[0]['available_at']);last=pd.Timestamp(now());policy=PortfolioPolicy(**db.setting('model_portfolio_policy',{}))
    quotes=[r for r in db.records('qualification_quote',limit=None) if first<=pd.Timestamp(r['payload']['observed_at'])<=last]
    identity=stable_hash([[(r['id'],r['available_at']) for r in sources],[r['id'] for r in quotes],policy.model_dump(),'replay-v2'])
    old=db.get('qreplay_'+identity)
    if old:return old['payload']
    definition={'id':'replay_'+identity,'registered_at':(first-pd.Timedelta(days=36500)).isoformat(),'risk_policy':policy.model_dump(),'criteria':QualificationCriteria().model_dump(),'universe':sorted({row['symbol'] for r in sources for row in r['payload']['rows']}),'incumbent_ids':[]}
    book=ComparisonBook(isolated,definition,'candidate',scope='historical');snapshot=None;contexts={};traces=[];snapshots=0;copied=set()
    events=sorted([(pd.Timestamp(r['available_at']),0,r) for r in sources]+[(pd.Timestamp(r['payload']['observed_at']),1,r) for r in quotes],key=lambda x:(x[0],x[1]))
    for at,kind,record in events:
        if kind==0:
            snapshot=record['payload'];contexts={};snapshots+=1;asof_view=book.paper.view()
            for original in snapshot['rows']:
                date=original.get('feature_available_at')
                if not date or pd.Timestamp(date)>at:
                    traces.append({'snapshot_id':record['id'],'at':at.isoformat(),'symbol':original['symbol'],'feature_available_at':date,'prediction':None,'score':None,'risk':{'notional':0.,'reasons':['Required feature timestamp unavailable or after replay timestamp']},'status':'DATA_UNAVAILABLE'})
                    continue
                votes=original.get('votes',[])
                for vote in votes:
                    if vote['model_id'] not in copied:
                        artifact=db.get(vote['model_id'])
                        if artifact:isolated.put(artifact['kind'],artifact['payload'],record_id=vote['model_id'])
                        copied.add(vote['model_id'])
                # Replay the weights/availability recorded then, never today's fitted model or approval.
                row=pd.Series({'date':date,'cost':original.get('estimated_roundtrip_cost'),'realized_volatility':original.get('daily_volatility')})
                asset={**snapshot['assets'].get(original['symbol'],{}),**{k:original.get(k) for k in ['symbol','asset_class','sector','regime','liquidity_bucket','market_cap_bucket']}}
                c=score_opportunity(asset,row,votes,original.get('health',[]),policy,snapshot.get('correlation',{}));contexts[c['symbol']]=c
                risk=size(c,asof_view,snapshot['assets'],snapshot.get('correlation',{}),policy,policy.initial_cash)
                traces.append({'snapshot_id':record['id'],'at':at.isoformat(),'symbol':c['symbol'],'feature_available_at':date,'model_ids':[v['model_id'] for v in votes],'prediction':c['expected_edge'],'probability':c['probability'],'score':c['score'],'risk':risk,'status':'NO_TRADE' if not risk['notional'] else 'AWAITING_RECORDED_QUOTE','execution':'No close or midpoint substituted for a quote'})
        if snapshot is None:continue
        q={}
        if kind==1:
            quote=record['payload']['quote'];symbol=record['symbol']
            # Corporate-action event replay is not inferred from today's adjusted candles.
            if snapshot['assets'].get(symbol,{}).get('asset_class')=='crypto':q[symbol]=quote
        book.step(at.to_pydatetime(),q,contexts,snapshot['assets'],snapshot.get('correlation',{}))
    view=book.paper.view();result={'id':'qreplay_'+identity,'at':now().isoformat(),'scope':'historical_debug_only','snapshots':snapshots,'recorded_quotes':len(quotes),'trace_count':len(traces),'statuses':dict(Counter(t['status'] for t in traces)),'orders':len(view['orders']),'fills':len(view['fills']),'completed_outcomes':len(isolated.records('qualification_outcome',limit=None)),'net_pnl':view['equity']-policy.initial_cash,'ending_cash':view['cash'],'traces':traces,'orders_detail':view['orders'],'fills_detail':view['fills'],'limitations':['Only snapshots and quotes actually recorded as available are replayed. Earlier daily bars cannot reconstruct executable prices.','Equity/ETF fills require a future historical corporate-action event adapter; they remain unavailable in this debug replay.','No learning, no qualification evidence, no mutation of any live paper book. Synthetic end-to-end fill/exit validation is confined to automated tests.']}
    isolated.engine.dispose();db.put('qualification_replay',result,record_id=result['id']);db.set_setting('qualification_replay',result);return result
