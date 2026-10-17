"use client";
import {useEffect,useState} from 'react';
import {api,date,number} from '@/lib/api';
import {Panel,Badge} from './Common';
type D=Record<string,any>;
export function NewsEvents({symbol,health=false}:{symbol?:string;health?:boolean}){
 const [data,setData]=useState<D|null>(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;const load=()=>api('/news?limit='+(symbol?'10':'5')+(symbol?'&symbol='+encodeURIComponent(symbol):health?'':'&important=true')).then(d=>{if(active){setData(d);setError('')}}).catch(()=>{if(active)setError('News collection is unavailable')});load();const timer=setInterval(load,30000);return()=>{active=false;clearInterval(timer)}},[symbol,health]);
 const status=data?.status;
 return <Panel title={health?'News access & delivery':symbol?'Recent News / Events':'Important events'} eyebrow="ALPACA NEWS">
 {error&&<p role="status">{error}</p>}
 {!data&&!error&&<p>Checking news collection…</p>}
 {status&&<><p><Badge>{status.entitlement}</Badge> · {status.status.replaceAll('_',' ')}</p>
 {health?<><div className="metric-list"><div><span>REST collection</span><strong>{status.rest_status||'Not checked'}</strong></div><div><span>Last poll</span><strong>{date(status.last_poll_at)}</strong></div><div><span>Last streamed story</span><strong>{date(status.last_stream_story_at)}</strong></div><div><span>Observed publication-to-receipt age</span><strong>{status.observed_stream_publication_age_seconds==null?'Not measured yet':number(status.observed_stream_publication_age_seconds,1)+' seconds'}</strong></div></div><p>{status.collection}</p><p className="panel-note">{status.limitations} Publication age includes editorial time and revisions; it is not a guaranteed network latency. {status.recovery_pending?'Recovering a backlog in bounded batches.':''}</p></>:<><p className="panel-note">Forward-collected, rule-based evidence. Duplicate stories count once. News is not a validated return forecast.</p>{!data.events.length&&<p>No {symbol?'mapped':'high-materiality'} events collected yet.</p>}<div className="news-events">{data.events.map((e:D)=><article key={e.cluster_id}><p><Badge tone={e.direction==='negative'?'amber':''}>{e.categories.join(' · ')}</Badge> · {e.materiality} materiality</p><h3>{e.url?<a href={e.url} target="_blank" rel="noreferrer noopener">{e.headline} ↗</a>:e.headline}</h3><p>{e.symbols.join(', ')||'Macro context'} · {e.source} via Alpaca</p><small>Published {date(e.published_at)} · Received {date(e.received_at)}</small><p className="panel-note">Direction: {e.direction} · Uncertainty: {e.uncertainty} · {e.novelty}</p></article>)}</div></>}
 </>}
 </Panel>
}
