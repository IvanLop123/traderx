import asyncio
from fastapi import APIRouter
from backend.product.market import ProductMarket
from backend.product.paper import ManualPaper,Ticket,Confirm,Reset,Watch
from backend.storage.database import Setting
from backend.product.cockpit import Cockpit,ResearchTicket,Idea

def product_routes(db,providers):
    router=APIRouter(prefix='/api/v1/product');market=ProductMarket(db);paper=ManualPaper(db,market);universe_task=None;cockpit=Cockpit(db,paper)
    @router.get('/cockpit')
    def decision_board():return cockpit.board()
    @router.get('/cockpit/{symbol}')
    def decision_asset(symbol:str):return cockpit.asset(symbol)
    @router.get('/journal')
    def journal():return cockpit.journal()
    @router.put('/ideas')
    def idea(request:Idea):return cockpit.idea(request)
    @router.get('/universe')
    async def universe():
        nonlocal universe_task
        if universe_task is None or universe_task.done():universe_task=asyncio.create_task(asyncio.to_thread(market.forecasts))
        try:return await asyncio.wait_for(asyncio.shield(universe_task),timeout=2)
        except asyncio.TimeoutError:
            saved=db.setting('product_summary_cache',{})
            if not saved.get('rows'):return []
            return [{**v,'forecast_status':'Refreshing current forecasts','model_prediction':None,'probability':None,'uncertainty':None,'evidence_change':'Refreshing data; displayed history may be old','warnings':[*v.get('warnings',[]),'Refreshing data; execution eligibility is rechecked at preview']} for v in saved['rows']]
    @router.get('/assets/{symbol}')
    async def asset(symbol:str):
        result=await asyncio.to_thread(market.asset,symbol)
        try:result['quote']=await providers.forward_quote(result['symbol'])
        except Exception:result['quote']=None
        result['position']=next((p for p in paper.view()['positions'] if p['symbol']==result['symbol']),None)
        return result
    @router.get('/portfolio')
    def portfolio():return paper.view()
    @router.post('/preview')
    async def preview(ticket:ResearchTicket):
        await asyncio.to_thread(market.lookup,ticket.symbol)
        try:q=await providers.forward_quote(ticket.symbol)
        except Exception:q={}
        return cockpit.save_context(paper.preview(Ticket(**ticket.model_dump(exclude={'journal'})),q),ticket.journal)
    @router.post('/orders')
    def place(request:Confirm):return paper.place(request)
    @router.post('/orders/{oid}/cancel')
    def cancel(oid:str):return paper.cancel(oid)
    @router.post('/account/reset')
    def reset(request:Reset):return paper.reset(request)
    @router.get('/watchlist')
    def watchlist():return db.setting('personal_watchlist',{'symbols':[]})
    @router.put('/watchlist')
    def watch(request:Watch):
        symbol=market.lookup(request.symbol)['symbol']
        with db.transaction() as session:
            row=session.get(Setting,'personal_watchlist');symbols=set(row.value['symbols']) if row else set()
            if request.saved:symbols.add(symbol)
            else:symbols.discard(symbol)
            if len(symbols)>500:raise ValueError('Watchlist is limited to 500 assets')
            value={'symbols':sorted(symbols)}
            if row:row.value=value
            else:session.add(Setting(key='personal_watchlist',value=value))
        return value
    @router.get('/strategy-models')
    def strategy_models():return [{k:r['payload'][k] for k in ['id','family','asset_class','fitted_at','horizon']} for r in db.records('strategy_model',limit=200)]
    @router.get('/strategies')
    def strategies():
        ptr=db.setting('strategy_latest');return db.get(ptr['id'])['payload'] if ptr else None
    return router,paper
