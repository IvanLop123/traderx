"use client";
import { Panel } from "./Common";
import { money,number,pct } from "@/lib/api";
type Data=Record<string,any>;
export function ObservationMetrics({page,rows,onInspect}:{page:string;rows:Data[];onInspect:(v:Data)=>void}){
  if(!['social','traders'].includes(page))return null;
  return <Panel title={page==='social'?'Observed social activity':'Observed trader performance'} eyebrow="DETERMINISTIC ANALYSIS">
    {!rows.length&&<p className="panel-note">No authorized observations yet. Fetch a configured source or import trades below.</p>}
    {rows.filter(r=>r.payload.metrics).slice(0,20).map(r=>{const m=r.payload.metrics;return <div key={r.id} className="module-result"><h3>{r.payload.query||r.payload.wallet||r.payload.source||'Observation'}</h3>
    <div className="metric-list">{(page==='social'?[['Observed posts',number(m.mentions,0)],['Unique authors',number(m.unique_authors,0)],['Posts in latest hour',number(m.mention_velocity_per_hour,0)],['Author concentration',pct(m.author_concentration)],['Duplicate text',pct(m.duplicate_text_fraction)],['Lexical disagreement',pct(m.lexical_disagreement)],['Engagement',number(m.engagement,0)],['Complete window posts',number(m.complete_window_mentions,0)],['Comparable history windows',number(m.history_windows,0)],['Mention z-score',number(m.historical_mention_zscore)],['Matched engagement / hour',number(m.engagement_velocity)],['Matched posts',number(m.engagement_matched_posts,0)]]:[['Observed fills',number(m.trade_count,0)],['Realized PnL',money(m.realized_pnl)],['Win rate',pct(m.win_rate)],['Profit factor',number(m.profit_factor)],['Drawdown dollars',money(m.max_drawdown_dollars)],['Worst trade',money(m.worst_trade)],['Largest win share',pct(m.largest_win_share)],['Cost-only copy estimate',money(m.copy_pnl_after_costs)]]).map(([k,v])=><div key={k}><span>{k}</span><strong>{v}</strong></div>)}</div>
    <p className="panel-note">{(m.warnings||[]).join(' ')}</p><button className="text-link" onClick={()=>onInspect(r)}>All metrics and source evidence</button></div>})}
  </Panel>
}
