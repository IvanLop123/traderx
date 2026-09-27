"""Observable statistical features are evidence, not trading instructions."""
import hashlib
from datetime import datetime
from backend.schemas.contracts import AssetIdentifier, Feature, Signal, now

def persist_market_signals(db,symbol,feature_result,bar_records):
    if feature_result.get('status')!='AVAILABLE': return []
    values=feature_result['values']; asset=AssetIdentifier(symbol=symbol,asset_class='crypto' if '-' in symbol else 'stock')
    as_of=max(datetime.fromisoformat(r['payload']['available_at']) for r in bar_records)
    evidence=[r['id'] for r in bar_records]; ids=[]
    for name,horizon,direction in [('return_20','20 bars','bullish' if values.get('return_20',0)>0 else 'bearish'),('realized_volatility','20 bars','volatility')]:
        if name not in values: continue
        fid=hashlib.sha256(f'{symbol}:{name}:{as_of.isoformat()}:{values[name]}'.encode()).hexdigest()
        f=Feature(id=fid,asset=asset,name=name,value=values[name],as_of=as_of,available_at=now(),evidence_ids=evidence)
        db.put('feature',f,symbol)
        signal=Signal(id=fid+'s',asset=asset,type=name,value=values[name],direction=direction,
                      confidence=0,horizon=horizon,as_of=as_of,evidence_ids=evidence,feature_ids=[fid],model='deterministic-v1',
                      freshness_seconds=max(0,(now()-as_of).total_seconds()),warnings=['Predictive confidence uncalibrated; confidence=0 until validated.','Research signal, not a trade recommendation.'])
        db.put('signal',signal,symbol);ids.append(signal.id)
    return ids
