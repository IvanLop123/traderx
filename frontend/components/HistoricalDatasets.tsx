"use client";
import {useEffect,useState} from 'react';
import {api} from '@/lib/api';
import {Panel,Badge} from './Common';
type Data=Record<string,any>;
export function HistoricalDatasets({act,onInspect}:{act:any;onInspect:any}){
 const [text,setText]=useState(''),[rows,setRows]=useState<Data[]>([]),[error,setError]=useState('');const load=()=>api('/records/historical_dataset').then(setRows);
 useEffect(()=>{load();},[]);
 return <Panel title="Historical datasets & coverage" eyebrow="SOURCE-ATTRIBUTED REPLAY">
  <p className="panel-note">Import an authorized JSON dataset with dated universe membership, quotes, lifecycle events, intents and explicit split/dividend coverage windows. Incomplete coverage blocks replay. Retrospective imports remain labeled. See docs/HISTORICAL_DATA.md for the format; current listings cannot prove a survivorship-free universe.</p>
  <label className="standalone">Dataset JSON<textarea rows={5} value={text} onChange={e=>setText(e.target.value)} placeholder="Paste an authorized HistoricalDataset object"/></label>
  <button className="button secondary" disabled={!text} onClick={async()=>{setError('');try{const d=JSON.parse(text);await act(()=>api('/research/datasets',d),'Dataset and coverage report stored');await load()}catch(e:any){setError(e.message)}}}>Import & check coverage</button>{error&&<p role="alert">{error}</p>}
  {rows.slice(0,10).map(r=><div key={r.id} className="module-result"><h3>{r.payload.name}</h3><Badge>{r.payload.coverage.status}</Badge><p>{r.payload.coverage.issues.join(' · ')}</p><div className="actions"><button className="text-link" onClick={()=>onInspect(r)}>Inspect source and coverage</button><button className="button secondary" disabled={r.payload.coverage.status==='BLOCKED'} onClick={async()=>{const result=await act(()=>api('/research/datasets/'+r.id+'/replay',{}),'Covered dataset replay saved');if(result)onInspect(result)}}>Replay dataset</button></div></div>)}
 </Panel>
}
