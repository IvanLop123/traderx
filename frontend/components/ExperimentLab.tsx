"use client";
import { useCallback, useEffect, useState } from "react";
import { api, number, pct } from "@/lib/api";
import { Panel, Badge } from "./Common";
type Data=Record<string,any>;
export function ExperimentLab({act,onInspect}:{act:any;onInspect:(v:Data)=>void}) {
  const [hypothesis,setHypothesis]=useState("Does prior 20-day momentum predict the next five days?");
  const [universe,setUniverse]=useState("BTC-USD, ETH-USD, SOL-USD");
  const [signal,setSignal]=useState("return_20"),[family,setFamily]=useState("momentum_research");
  const [target,setTarget]=useState("forward_return"),[benchmark,setBenchmark]=useState("BTC-USD");
  const [population,setPopulation]=useState("all_observations"),[threshold,setThreshold]=useState(0);
  const [horizon,setHorizon]=useState(5),[strict,setStrict]=useState(true),[cost,setCost]=useState(5);
  const [studies,setStudies]=useState<Data[]>([]),[counts,setCounts]=useState<Data|null>(null),[busy,setBusy]=useState(false);
  const [released,setReleased]=useState<Record<string,Data>>({});
  const load=useCallback(async()=>{const [s,c,r]=await Promise.all([api('/records/experiment_study'),api('/research/experiments/families'),api('/records/experiment_holdout')]);setStudies(s);setCounts(c);setReleased(Object.fromEntries(r.map((x:Data)=>[x.payload.definition_id,x.payload])));},[]);
  useEffect(()=>{load().catch(()=>{});},[load]);
  async function run(){setBusy(true);try{await act(()=>api('/research/experiments',{hypothesis,family,universe:universe.split(',').map(s=>s.trim().toUpperCase()).filter(Boolean),signal,target,benchmark:target==='excess_return'?benchmark:null,population,threshold,horizon,strict_observed:strict,fee_bps:cost,slippage_bps:cost}),"Experiment stored; holdout remains sealed");await load();}finally{setBusy(false);}}
  async function reveal(id:string){setBusy(true);try{await act(()=>api('/research/experiments/'+id+'/holdout',{}),"Holdout revealed and recorded");await load();}finally{setBusy(false);}}
  return <><Panel title="Declare a signal experiment" eyebrow="VERSIONED HYPOTHESES · LOCAL COMPUTE">
    <label className="standalone">Hypothesis<input value={hypothesis} onChange={e=>setHypothesis(e.target.value)}/></label>
    <div className="form-grid cols4">
      <label>Assets (comma separated)<input value={universe} onChange={e=>setUniverse(e.target.value)}/></label>
      <label>Experiment family<input value={family} onChange={e=>setFamily(e.target.value)}/></label>
      <label>Signal feature<input list="experiment-signals" value={signal} onChange={e=>setSignal(e.target.value)}/><datalist id="experiment-signals">{['return_5','return_20','realized_volatility','volume_zscore','relative_volume','rsi','vwap_distance'].map(x=><option key={x} value={x}/>)}</datalist></label>
      <label>Target<select value={target} onChange={e=>setTarget(e.target.value)}><option value="forward_return">Forward return</option><option value="excess_return">Return above benchmark</option><option value="realized_volatility">Future volatility</option></select></label>
      {target==='excess_return'&&<label>Benchmark<input value={benchmark} onChange={e=>setBenchmark(e.target.value.toUpperCase())}/></label>}
      <label>Observation filter<select value={population} onChange={e=>setPopulation(e.target.value)}><option value="all_observations">All observations</option><option value="signal_above_threshold">Signal above threshold</option><option value="signal_below_threshold">Signal below threshold</option></select></label>
      <label>Threshold<input type="number" step="any" value={threshold} onChange={e=>setThreshold(+e.target.value)}/></label>
      <label>Horizon (daily bars)<input type="number" min={1} max={60} value={horizon} onChange={e=>setHorizon(+e.target.value)}/></label>
      <label>Fee and slippage, each (bps)<input type="number" min={0} max={1000} value={cost} onChange={e=>setCost(+e.target.value)}/></label>
    </div>
    <label className="check"><input type="checkbox" checked={strict} onChange={e=>setStrict(e.target.checked)}/> Require history actually observed before each decision</label>
    <p className="panel-note">Newly downloaded history cannot satisfy strict historical observation. Uncheck for explicitly retrospective market research. Evidence features always retain their observed availability. Missing evidence is never invented. Training / validation / holdout use chronological 60 / 20 / 20 boundaries with label purging.</p>
    <button className="button primary" disabled={busy||hypothesis.length<5} onClick={run}>{busy?'Working…':'Register and evaluate'}</button>
  </Panel>
  <Panel title="Registered experiments" action={<Badge>{counts?.registered_trials??0} TRIALS</Badge>}>
    <p className="panel-note">{counts?.failed_trials??0} unsuccessful attempts · {counts?.released_holdouts??0} revealed holdouts. Revealing a holdout permanently marks it inspected. Further tuning requires fresh forward data.</p>
    {!studies.length&&<p className="panel-note">No declared experiments yet.</p>}
    {studies.map(({payload:p,id})=>{const release=released[p.definition_id];const adjustment=counts?.families?.[p.definition.family]?.find((x:Data)=>x.definition_id===p.definition_id);return <div key={id} className="module-result">
      <h3>{p.definition.hypothesis}</h3><p className="panel-note">{p.definition.universe.join(', ')} · {p.definition.signal} · {p.definition.horizon}-bar horizon · {p.definition.strict_observed?'Observed history':'Retrospective history'}</p>
      <div className="table-scroll"><table><thead><tr><th>PERIOD</th><th>OBSERVATIONS</th><th>RANK CORRELATION</th><th>NET EVENT RETURN</th><th>HIT RATE</th></tr></thead><tbody>{[['Training',p.training],['Validation',p.validation],['Holdout',release?.holdout]].map(([name,r]:any)=><tr key={name}><td>{name}</td><td>{r?.samples??'Sealed'}</td><td>{number(r?.information_coefficient,3)}</td><td>{pct(r?.mean_net_return_after_costs)}</td><td>{pct(r?.hit_rate)}</td></tr>)}</tbody></table></div>
      <p className="panel-note">Family-adjusted holdout p-value: {number(adjustment?.adjusted_p_value,4)}. Event returns include assumed fees, slippage and a 2 bps round-trip spread; use portfolio replay for cash and overlapping exposures.</p>
      <div className="actions"><button className="button secondary" onClick={()=>onInspect({...p,released_holdout:release,family_adjustment:adjustment})}>Evidence and diagnostics</button>{!release&&<button className="button secondary" disabled={busy} onClick={()=>reveal(p.definition_id)}>Reveal reserved holdout</button>}</div>
    </div>})}
    <p className="panel-note">{counts?.warning}</p>
  </Panel></>;
}
