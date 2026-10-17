"use client";
import { useEffect,useState } from "react";
import { api,pct,date } from "@/lib/api";
import { Panel,Badge } from "./Common";
type Data=Record<string,any>;
export function SemanticResearch({revision,onInspect}:{revision:Data[];onInspect:(r:Data)=>void}){
  const [rows,setRows]=useState<Data[]>([]),[status,setStatus]=useState("off");
  useEffect(()=>{Promise.all([api('/records/semantic_research'),api('/settings/ai')]).then(([r,s])=>{setRows(r);setStatus(s.current_provider)}).catch(()=>{});},[revision]);
  return <Panel title="Bottlenecks, relationships & disagreement" eyebrow="SOURCE-QUOTED SEMANTIC RESEARCH" action={<Badge>{status==='off'?'AI OFF':status.toUpperCase()}</Badge>}>
    {!rows.length&&<p className="panel-note">{status==='off'?'AI extraction is disabled. Deterministic document research continues.':'Analyze an imported narrative document to extract supported relationships, bottlenecks and answer assessments. Unsupported or absent items remain unavailable.'}</p>}
    {rows.map(r=><div key={r.id} className="module-result"><h3>{r.symbol||'Source research'} · {r.payload.period_end||date(r.available_at)}</h3>
      <p className="panel-note">{r.payload.provider} / {r.payload.model} · Evasiveness: {pct(r.payload.scores.management_evasiveness)} · Analyst skepticism: {pct(r.payload.scores.analyst_skepticism)} · Disagreement: {pct(r.payload.scores.management_analyst_disagreement)}</p>
      {r.payload.bottlenecks.map((b:Data,i:number)=><p key={i}><strong>{b.company}: {b.type}</strong> ({b.severity}) — {b.quote}{b.mitigation&&<span> Mitigation: {b.mitigation}</span>}</p>)}
      {r.payload.relationships.map((e:Data,i:number)=><p key={i}>{e.subject} → {e.relation.replaceAll('_',' ')} → {e.object}<br/><small>“{e.quote}”</small></p>)}
      {r.payload.contradictions.map((c:Data,i:number)=><p key={i}>“{c.first_quote}” / “{c.second_quote}” — {c.explanation}</p>)}
      <button className="text-link" onClick={()=>onInspect(r)}>Inspect quotes, scores and provenance</button>
    </div>)}
    <p className="panel-note">Semantic scores are subjective evidence, not calibrated predictions. Disagreement can relate to uncertainty or volatility; it does not automatically imply price direction. Historical snapshots preserve changes over time.</p>
  </Panel>
}
