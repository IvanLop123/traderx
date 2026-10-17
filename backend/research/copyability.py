"""Publication-aware replication research using the same causal cash ledger."""
from datetime import timedelta
from typing import Literal
from pydantic import Field,AwareDatetime,model_validator
from backend.schemas.contracts import Contract
from backend.research.replay import ReplayRequest,ReplayIntent,EventReplay

class PublicFill(Contract):
    id:str=Field(min_length=1,max_length=100)
    symbol:str
    side:Literal['buy','sell']
    quantity:float=Field(gt=0)
    price:float=Field(gt=0)
    fill_at:AwareDatetime
    public_at:AwareDatetime
    ingested_at:AwareDatetime
    source_reference:str=Field(min_length=1,max_length=1000)
    @model_validator(mode='after')
    def chronology(self):
        if self.fill_at>self.public_at or self.public_at>self.ingested_at:raise ValueError('Fill, public visibility and ingestion must be chronological')
        return self

class CopyReplayRequest(Contract):
    fills:list[PublicFill]=Field(min_length=1,max_length=5000)
    market:ReplayRequest
    analysis_seconds:float=Field(default=1,ge=0,le=86400)
    expiry_seconds:float=Field(default=300,gt=0,le=604800)
    limit_tolerance_bps:float=Field(default=25,ge=0,lt=10000)
    original_realized_pnl:float|None=None
    @model_validator(mode='after')
    def no_overrides(self):
        if self.market.intents:raise ValueError('Copy replay derives intents from public observations; market.intents must be empty')
        if len({f.id for f in self.fills})!=len(self.fills):raise ValueError('Duplicate public fill ID')
        return self

def replay_copyability(request):
    intents=[];stages=[];delay=request.market.latency_seconds
    for fill in request.fills:
        decision=fill.ingested_at+timedelta(seconds=request.analysis_seconds)
        intents.append(ReplayIntent(id=fill.id,symbol=fill.symbol,side=fill.side,quantity=fill.quantity,
            limit_price=fill.price*(1+(1 if fill.side=='buy' else -1)*request.limit_tolerance_bps/10000),
            decided_at=decision,evidence_available_at=fill.ingested_at,expires_at=decision+timedelta(seconds=request.expiry_seconds)))
        stages.append({'fill_id':fill.id,'source_reference':fill.source_reference,'public_delay_seconds':(fill.public_at-fill.fill_at).total_seconds(),
            'ingestion_delay_seconds':(fill.ingested_at-fill.public_at).total_seconds(),'analysis_seconds':request.analysis_seconds,'execution_delay_seconds':delay,
            'earliest_execution_at':(decision+timedelta(seconds=delay)).isoformat()})
    market=request.market.model_copy(update={'intents':intents});result=EventReplay(market).run()
    last=result['curve'][-1]['equity'] if result['curve'] else market.initial_cash
    pnl=last-market.initial_cash;original=request.original_realized_pnl
    # Open positions cannot be compared to an original realized-only account total.
    flat=not any(p.get('quantity',0)>1e-10 for p in result.get('positions',{}).values())
    score=max(0,min(1,pnl/original)) if flat and original is not None and original>0 else None
    return {**result,'copyability':{'score':score,'replicated_marked_pnl':pnl,'original_realized_pnl':original,'flat_at_end':flat,'delay_stages':stages,
        'warnings':['Visibility timestamps must come from observation evidence; assumed publication delays are scenarios, not measured copyability.',
                    'Long/full-cash replay does not replicate short or leveraged positions. Missing events, partial source history and survivorship remain limitations.',
                    'Score is capped replicated PnL / user-supplied positive original PnL, only when flat. Compare equal periods, sizing and cash flows before interpreting. No wallet is automatically mirrored.']}}
