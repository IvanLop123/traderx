import asyncio
from fastapi import APIRouter,HTTPException
from backend.research.autonomous.schema import Budget,ExperimentSpec,ReviewProposal,ReviewDecision

def routes(service):
    router=APIRouter(prefix='/api/v1/research/autonomous')
    def guarded(call,*args):
        try:return call(*args)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
    @router.get('')
    def status():return service.status()
    @router.put('/settings')
    def configure(budget:Budget):return guarded(service.configure,budget)
    @router.post('/register')
    def register(spec:ExperimentSpec):return guarded(service.register,spec)
    @router.post('/review')
    async def review():
        try:return await service.propose()
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
    @router.post('/run')
    async def run():return await asyncio.to_thread(service.run_next)
    @router.post('/code-proposals')
    def proposal(request:ReviewProposal):return guarded(service.code_proposal,request)
    @router.post('/code-proposals/{pid}/review')
    def review_code(pid:str,request:ReviewDecision):return guarded(service.review_code,pid,request)
    @router.post('/challengers/{mid}/forward')
    def enroll(mid:str):return guarded(service.enroll,mid)
    return router
