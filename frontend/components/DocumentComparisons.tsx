"use client";
import {useEffect,useState} from 'react';
import {api} from '@/lib/api';
import {Panel} from './Common';
type Data=Record<string,any>;
export function DocumentComparisons({revision,onInspect}:{revision:Data[];onInspect:(r:Data)=>void}){
 const [docs,setDocs]=useState<Data[]>([]),[pairs,setPairs]=useState<Data[]>([]),[neighbors,setNeighbors]=useState<Data[]>([]),[selected,setSelected]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const load=()=>api('/records/document_comparison').then(setPairs);
 useEffect(()=>{api('/records/document').then(r=>setDocs(r.filter((d:Data)=>!['form4','13f'].includes(d.payload.kind))));load();},[revision]);
 useEffect(()=>{setNeighbors([]);if(selected)api('/documents/'+selected+'/neighbors').then(setNeighbors).catch(e=>setMessage(e.message));},[selected]);
 return <Panel title="Changes between sources" eyebrow="BOUNDED DOCUMENT COMPARISON">
  <label className="standalone">Current document<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Choose a document</option>{docs.map(d=><option key={d.id} value={d.id}>{d.payload.title}</option>)}</select></label>
  <p className="panel-note">Finds up to two related earlier documents for the same asset using local text matching. Publication dates are required. A comparison uses your configured AI policy and cache.</p>
  {selected&&!neighbors.length&&<p className="panel-note">No eligible earlier source found. Add a related dated document first.</p>}
  {neighbors.map(n=><button key={n.id} className="button secondary" disabled={busy} onClick={async()=>{setBusy(true);try{const r=await api('/documents/'+selected+'/compare/'+n.id,{});setMessage(r.status);await load();}catch(e:any){setMessage(e.message)}finally{setBusy(false)}}}>Compare with {n.title}</button>)}
  {message&&<p role="status">{message}</p>}
  {pairs.slice(0,20).map(r=><div className="module-result" key={r.id}><h3>{r.payload.current_title} / {r.payload.prior_title}</h3>{r.payload.comparisons.map((c:Data,i:number)=><p key={i}><strong>{c.relation.replaceAll('_',' ')}</strong>: {c.explanation}<br/>Earlier: {c.prior_quote||'No matching claim identified'}<br/>Current: {c.current_quote}</p>)}<p className="panel-note">{r.payload.provider} / {r.payload.model} · {r.payload.scope}</p><button className="text-link" onClick={()=>onInspect(r)}>Inspect both sources</button></div>)}
 </Panel>
}
