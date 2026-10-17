"""Explicit paper-broker actions; never a live venue route."""
from fastapi import APIRouter,HTTPException
from backend.schemas.contracts import TradeCandidate,ApprovedOrder

def execution_routes(db,broker):
    router=APIRouter(prefix='/api/v1/execution')
    def stored(rid,kind):
        row=db.get(rid)
        if not row or row['kind']!=kind:raise HTTPException(404,kind+' not found')
        return row['payload']
    def quote(symbol):
        rows=db.records('quote',symbol,limit=20)
        for row in rows:
            if row['payload'].get('provider')=='alpaca':
                q=row['payload'];healthy=db.setting('provider_alpaca',{}).get('status','').startswith('WORKING')
                return q,healthy
        raise HTTPException(409,'A fresh Alpaca quote is required')
    @router.get('/alpaca')
    def status():return broker.status()
    @router.post('/alpaca/sync')
    async def sync():return await broker.sync()
    @router.post('/alpaca/candidates/{rid}/assess')
    async def assess(rid:str):
        c=TradeCandidate.model_validate(stored(rid,'candidate'));q,healthy=quote(c.asset.symbol)
        return await broker.assess(c,q,healthy)
    @router.post('/alpaca/orders/{rid}/submit')
    async def submit(rid:str):
        order=ApprovedOrder.model_validate(stored(rid,'approved_order'));q,healthy=quote(order.asset.symbol)
        return await broker.execute(order,q,healthy)
    @router.post('/alpaca/orders/{client_id}/cancel')
    async def cancel(client_id:str):
        if not client_id.startswith('tx-') or len(client_id)!=35:raise HTTPException(422,'Invalid client order ID')
        return await broker.cancel(client_id)
    return router
