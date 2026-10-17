"use client";
import { useEffect, useState } from "react";
import { api, date } from "@/lib/api";
import { Panel, Badge } from "./Common";
type Data = Record<string, any>;
export function TrainingSchedule({act}:{act:any}) {
  const [data,setData]=useState<Data|null>(null);
  const [settings,setSettings]=useState<Data|null>(null);
  const [symbols,setSymbols]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const receive=(r:Data)=>{setData(r);setSettings(r.settings);setSymbols(r.settings.symbols.join(", "));};
  useEffect(()=>{api("/settings/training").then(receive).catch(e=>setError(e.message));},[]);
  const action=async(check:boolean)=>{
    setBusy(true);
    const r=await act(()=>check?api("/models/check-training",{}):api("/settings/training",{...settings,symbols:symbols.split(",").map(s=>s.trim().toUpperCase()).filter(Boolean)},"PUT"),check?"Training schedule checked":"Training schedule saved");
    if(r)receive(r);setBusy(false);
  };
  return <Panel title="Learn from new market history" eyebrow="LOCAL PREDICTORS · NO API COST">
    {error&&<p role="alert">{error}</p>}
    {settings&&data&&<><p className="panel-note">Create a new statistical forecasting model when enough new daily bars have arrived. Each version is tested against simple benchmarks and saved for review. Existing forward studies continue. Language-model weights are not trained here.</p>
    <label className="check"><input type="checkbox" checked={settings.enabled} onChange={e=>setSettings({...settings,enabled:e.target.checked})}/> Enable scheduled local retraining</label>
    <label className="check"><input type="checkbox" checked={settings.compare_models} onChange={e=>setSettings({...settings,compare_models:e.target.checked})}/> Compare model families when retraining is due</label>
    <div className="form-grid cols4"><label>Assets (comma-separated)<input value={symbols} onChange={e=>setSymbols(e.target.value)}/></label>
    {([["interval_days","Minimum days between runs",90],["minimum_new_bars","Minimum new daily bars",90],["horizon","Prediction horizon (bars)",20]] as [string,string,number][]).map(([key,label,max])=><label key={key}>{label}<input type="number" min="1" max={max} value={settings[key]} onChange={e=>setSettings({...settings,[key]:+e.target.value})}/></label>)}</div>
    <div className="actions"><button className="button primary" disabled={busy} onClick={()=>action(false)}>Save training schedule</button><button className="button secondary" disabled={busy} onClick={()=>action(true)}>Check saved schedule now</button><Badge>{data.worker.status}</Badge></div>
    <p className="panel-note">Checked hourly while TraderX is running. A saved schedule defaults to weekly runs after seven new bars. No automatic model promotion or order submission.</p>
    {(data.worker.outcomes||[]).map((r:Data)=><p key={r.symbol} className="panel-note">{r.symbol}: {r.status.replaceAll("_"," ").toLowerCase()} · {r.new_observations??"—"} new observations · next eligible {date(r.next_eligible_at)}</p>)}
    {data.runs.length>0&&<div className="table-scroll"><table><thead><tr><th>ASSET</th><th>LAST RUN</th><th>RESULT</th><th>HISTORICAL GATES</th></tr></thead><tbody>{data.runs.slice(0,10).map((r:Data)=><tr key={r.id}><td>{r.symbol}</td><td>{date(r.created_at)}</td><td>{r.payload.status.replaceAll("_"," ")}</td><td>{r.payload.historical_eligible===true?"Passed":r.payload.historical_eligible===false?"Not passed":"—"}</td></tr>)}</tbody></table></div>}</>}
  </Panel>;
}
