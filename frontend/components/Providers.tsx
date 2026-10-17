"use client";
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, number, date } from "@/lib/api";
import { Badge, Panel, JsonView } from "./Common";
import { NewsEvents } from "./NewsEvents";
import { SystemResearch } from "./SystemResearch";
type Data = Record<string, any>;
export function Providers({ data, act }: { data: Data; act: any }) {
  const [provider, setProvider] = useState("sec");
  const [symbol, setSymbol] = useState("AAPL");
  const [kind, setKind] = useState("news");
  const [quarter, setQuarter] = useState("");
  const [cik, setCik] = useState("0000320193");
  const [query, setQuery] = useState("$AAPL");
  const [observationDate, setObservationDate] = useState("");
  return (
    <>
      <div className="banner neutral">
        <ShieldCheck size={17} /> API keys are never sent to the browser.
        Public, credentialed and disabled providers are reported separately.
      </div>
      <div className="status-summary"><span>{data.providers.filter((p:Data)=>p.status.startsWith('WORKING')).length} working</span><span>{data.providers.filter((p:Data)=>p.status==='ENTITLEMENT_REQUIRED').length} need entitlement</span><span>Trading disabled</span></div>
      <div className="health-grid">{data.providers.map((p:Data)=>{const working=p.status.startsWith('WORKING');const label=p.status==='WORKING_LOCAL'?'Local · working':working?'Working':p.status==='ENTITLEMENT_REQUIRED'?'Entitlement required':p.status==='DISABLED'?'Disabled':p.status==='READY_FOR_IMPORT'?'Manual import':p.status==='NOT_CONFIGURED'?'Not configured':'Needs attention';return <article className="health-card" key={p.provider}><header><h2>{p.provider.replaceAll('_',' ').toUpperCase()}</h2><Badge tone={working?'green':p.status==='ENTITLEMENT_REQUIRED'?'amber':''}>{label}</Badge></header><p>{p.scope||'Read-only research data.'}</p><details><summary>Connection details</summary><p>Last success: {date(p.last_success)}</p><p>Status: {p.status.replaceAll('_',' ')}</p><p>{p.last_error||p.missing_fields?.join(', ')||'No outstanding diagnostic.'}</p>{p.quote_status&&<p>Quotes: {p.quote_status} · History: {p.history_status}</p>}</details></article>})}</div>
      <NewsEvents health/>
      <SystemResearch/>
      <details><summary className="section-copy">Advanced data tools and stream diagnostics</summary>
      <Panel title="Public market stream" eyebrow="COINBASE"><div className="metric-list"><div><span>Connection</span><Badge>{data.stream?.status||"NOT_STARTED"}</Badge></div><div><span>Messages observed</span><strong>{number(data.stream?.messages,0)}</strong></div><div><span>Last update</span><strong>{date(data.stream?.updated_at)}</strong></div><div><span>Book sampling / trades</span><strong>{data.stream?.books_enabled?"Books on":"Books off"} · {data.stream?.trades_enabled?"Trades on":"Trades off"}</strong></div></div><p className="panel-note">Public quotes stream without AI. REST polling remains independent. Optional order books are sampled every five seconds; trade gaps are recorded and bounded recovery never claims complete history.</p></Panel>
      <div className="two-col">
        <Panel title="Fetch configured provider data">
          <div className="form-grid">
            <label>
              Provider
              <select
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  setSymbol(e.target.value === "fred" ? "FEDFUNDS" : "AAPL");
                }}
              >
                {[
                  "sec",
                  "fred",
                  "eia",
                  "alpaca",
                  "hyperliquid",
                ].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
            <label>
              {provider === "fred" ? "FRED series identifier" : "Asset symbol"}
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </label>
            {provider === "sec" && (
              <label>
                SEC company CIK
                <input value={cik} onChange={(e) => setCik(e.target.value)} />
              </label>
            )}
          </div>
          <button
            className="button primary"
            onClick={() =>
              act(
                () =>
                  api("/providers/fetch", {
                    provider,
                    symbol,
                    kind,
                    quarter,
                    observation_date: observationDate || null,
                    cik,
                    query,
                  }),
                "Provider data stored",
              )
            }
          >
            Fetch read-only data
          </button>
        </Panel>
        <Panel title="Worker & infrastructure">
          <JsonView value={data.worker} />
          <p className="panel-note">
            AI work runs separately from market polling. Redis failures fall
            back to durable database jobs.
          </p>
        </Panel>
      </div>
      </details>
    </>
  );
}
