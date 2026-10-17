import asyncio

async def reconcile_paper_broker(broker,stop):
    while not stop.is_set():
        enabled=broker.provider.cfg.get('ALPACA_PAPER_EXECUTION_ENABLED')=='true'
        pending=any(o['status'] not in ('filled','canceled','expired','rejected','replaced','done_for_day') for o in broker.orders())
        if broker.provider.configured() and (enabled or pending):
            try:await broker.sync()
            except Exception:pass  # sync persists the failure and blocks new submission.
        try:await asyncio.wait_for(stop.wait(),timeout=30)
        except asyncio.TimeoutError:pass
