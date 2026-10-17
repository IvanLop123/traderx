"use client";
import { useEffect,useState } from "react";
import { api,money,number,pct } from "@/lib/api";
import { Panel } from "./Common";
type Data=Record<string,any>;
export function CopyReplay({act,onInspect}:{act:any;onInspect:(v:Data)=>void}){
  const [text,setText]=useState(''),[rows,setRows]=useState<Data[]>([]),[busy,setBusy]=useState(false);
  const load=()=>api('/records/copy_replay').then(setRows);
  useEffect(()=>{load().catch(()=>{});},[]);
  return <Panel title="Publication-delay replay" eyebrow="RESEARCH ONLY · NO WALLET MIRRORING">
    <p className="panel-note">Provide public fills with original, visible and ingested timestamps, plus a two-sided historical quote tape. The simulator includes analysis/execution delays, spread, liquidity, fees and supplied funding events. The exact input contract is in the local API reference and docs/COPYABILITY.md.</p>
    <label className="standalone">Authorized observation and market data (JSON)<textarea rows={5} value={text} onChange={e=>setText(e.target.value)} placeholder="Paste a CopyReplayRequest using your source observations"/></label>
    <button className="button secondary" disabled={busy||!text} onClick={async()=>{setBusy(true);try{const r=await act(()=>api('/traders/copy-replay',JSON.parse(text)),"Copy replay stored");if(r)onInspect(r);await load();}finally{setBusy(false);}}}>{busy?'Replaying…':'Run delay replay'}</button>
    <div className="table-scroll"><table><thead><tr><th>OBSERVATIONS</th><th>FILLS</th><th>REPLICATED PNL</th><th>COSTS</th><th>COPYABILITY</th><th/></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td>{number(r.payload.copyability.delay_stages.length,0)}</td><td>{r.payload.fills.length}</td><td>{money(r.payload.copyability.replicated_marked_pnl)}</td><td>{money(r.payload.total_cost)}</td><td>{pct(r.payload.copyability.score)}</td><td><button className="text-link" onClick={()=>onInspect(r)}>Evidence</button></td></tr>)}</tbody></table></div>
    <p className="panel-note">A missing score means the required positive original PnL or flat closing state is unavailable. Imported delays are scenario assumptions unless supported by observation records.</p>
  </Panel>
}
