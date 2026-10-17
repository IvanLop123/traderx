"""Trade-level diagnostics; missing account returns remain explicitly unavailable."""
import math
from collections import defaultdict
import numpy as np

def trade_diagnostics(trades):
    groups=defaultdict(list);sizes=[];pnl=[];sides=[];holding=[];leverage=[];regimes=defaultdict(list)
    def numeric(value):
        try:x=float(value);return x if math.isfinite(x) else None
        except (ValueError,TypeError):return None
    for row in trades:
        value=numeric(row.get('pnl',row.get('closedPnl')))
        if value is None:continue
        symbol=row.get('symbol',row.get('coin')) or 'unknown';groups[symbol].append(value);pnl.append(value)
        size=numeric(row.get('notional'))
        if size is None:
            px=numeric(row.get('px'));qty=numeric(row.get('sz'));size=abs(px*qty) if px is not None and qty is not None else None
        sizes.append(abs(size) if size is not None else None)
        side=str(row.get('side','')).lower();sides.append(1 if side in ('b','buy') else -1 if side in ('a','sell','s') else 0)
        duration=numeric(row.get('holding_seconds'));lev=numeric(row.get('leverage'))
        if duration is not None and duration>=0:holding.append(duration)
        if lev is not None and lev>=0:leverage.append(lev)
        if row.get('regime'):regimes[str(row['regime'])].append(value)
    if not pnl:return {'status':'NO_FINITE_PNL'}
    known_sizes=[v for v in sizes if v is not None];a=np.array(pnl)
    increases=sum(pnl[i-1]<0 and sizes[i] is not None and sizes[i-1] is not None and sizes[i]>sizes[i-1]*1.5 for i in range(1,len(pnl)))
    return {'performance_by_asset':{k:{'trades':len(v),'realized_pnl':sum(v),'win_rate':sum(x>0 for x in v)/len(v)} for k,v in groups.items()},
        'asset_specialization':max(map(len,groups.values()))/len(pnl),'directional_fill_bias':sum(sides)/sum(v!=0 for v in sides) if any(sides) else None,
        'average_observed_holding_seconds':float(np.mean(holding)) if holding else None,'average_reported_leverage':float(np.mean(leverage)) if leverage else None,
        'observed_notional_turnover':sum(known_sizes) if known_sizes else None,'mean_observed_trade_notional':float(np.mean(known_sizes)) if known_sizes else None,
        'pnl_quantile_05':float(np.quantile(a,.05)),'worst_trade':float(a.min()),'size_increases_after_losses':increases,
        'rolling_20_trade_pnl':[{'ending_trade':i,'pnl':float(a[max(0,i-20):i].sum())} for i in range(1,len(a)+1)],
        'performance_by_reported_regime':{k:{'trades':len(v),'pnl':sum(v)} for k,v in regimes.items()},
        'sharpe':None,'sortino':None,'calmar':None,'trend_following':None,'mean_reversion':None,
        'unavailable_reason':'Account Sharpe/Sortino/Calmar require a complete cash-flow-adjusted equity series. Strategy style requires contemporaneous market context. Fill PnL alone cannot establish them.',
        'flags':(['tiny_sample'] if len(pnl)<30 else [])+(['size_escalation_after_losses'] if increases else [])+(['reported_high_leverage'] if leverage and max(leverage)>5 else []),
        'ordering':'As supplied; import rows in chronological order. Public wallet fills are sorted by provider timestamps. These are descriptive metrics, not skill certification.'}
