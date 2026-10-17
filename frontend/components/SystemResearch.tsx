"use client";
import {useEffect,useState} from "react";
import {api,date} from "@/lib/api";
import {Panel,Badge} from "./Common";
type D=Record<string,any>;
export function SystemResearch(){
 const [data,setData]=useState<D|null>(null),[error,setError]=useState('');useEffect(()=>{api('/system/research').then(setData).catch(e=>setError(e.message))},[]);
 return <Panel title="Data coverage & workers" eyebrow="COLLECTION IS NOT MODEL ELIGIBILITY">{error&&<p className="panel-note">{error}</p>}{!data?<p className="panel-note">Loading worker status…</p>:<><div className="table-scroll"><table><thead><tr><th>Asset</th><th>Daily bars</th><th>History starts</th><th>Latest completed bar</th></tr></thead><tbody>{data.coverage.map((r:D)=><tr key={r.symbol}><td>{r.symbol}</td><td>{r.bars}</td><td>{r.start.slice(0,10)}</td><td>{date(r.end)}</td></tr>)}</tbody></table></div><p className="panel-note">Archived macro first-release series: {data.macro_initial_series.join(', ')||'Not available'}. Downloaded market history may contain revisions; current watchlists are not historical universe archives.</p><details><summary>Worker schedules and training decisions</summary><p>Training: <Badge>{data.training.worker.status}</Badge> · {date(data.training.worker.checked_at)}</p>{(data.training.worker.outcomes||[]).map((r:D)=><p key={r.symbol}>{r.symbol}: {r.status.replaceAll('_',' ')} · new observations: {r.new_observations??'—'} · next eligible: {date(r.next_eligible_at)}</p>)}{Object.entries(data.ingestion).map(([name,r]:[string,any])=><p key={name}>{name}: {r.status||'Not started'} · last attempt {date(r.last_attempt)}</p>)}</details></>}</Panel>
}
