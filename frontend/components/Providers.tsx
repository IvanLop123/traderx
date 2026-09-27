"use client";
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, number, date } from "@/lib/api";
import { Badge, Panel, JsonView } from "./Common";
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
      <Panel title="Provider health" eyebrow="LIVE CONNECTIVITY">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>PROVIDER</th>
                <th>STATUS</th>
                <th>LAST SUCCESS</th>
                <th>LATENCY</th>
                <th>SETUP / DIAGNOSTIC</th>
              </tr>
            </thead>
            <tbody>
              {data.providers.map((p: Data) => (
                <tr key={p.provider}>
                  <td>
                    <strong>
                      {p.provider.replaceAll("_", " ").toUpperCase()}
                    </strong>
                  </td>
                  <td>
                    <Badge
                      tone={
                        p.status.startsWith("WORKING")
                          ? "green"
                          : p.status === "ERROR"
                            ? "red"
                            : ""
                      }
                    >
                      {p.status.replaceAll("_", " ")}
                    </Badge>
                  </td>
                  <td>{date(p.last_success)}</td>
                  <td>
                    {p.latency_ms ? number(p.latency_ms, 0) + " ms" : "—"}
                  </td>
                  <td className="muted">
                    {p.last_error ||
                      p.missing_fields?.join(", ") ||
                      "No credentials needed"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
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
                  "alpha_vantage",
                  "alpaca",
                  "hyperliquid",
                  "kalshi",
                  "x",
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
            {provider === "alpha_vantage" && (
              <>
                <label>
                  Information type
                  <select
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    <option value="news">News</option>
                    <option value="transcript">Earnings transcript</option>
                    <option value="options">Historical options</option>
                  </select>
                </label>
                {kind === "transcript" && (
                  <label>
                    Quarter
                    <input
                      placeholder="2026Q2"
                      value={quarter}
                      onChange={(e) => setQuarter(e.target.value.toUpperCase())}
                    />
                  </label>
                )}
                {kind === "options" && (
                  <label>
                    Observation date (optional)
                    <input
                      type="date"
                      value={observationDate}
                      onChange={(e) => setObservationDate(e.target.value)}
                    />
                    <small>
                      Blank uses the previous trading session. Requires provider
                      entitlement.
                    </small>
                  </label>
                )}
              </>
            )}
            {provider === "x" && (
              <label>
                Search query
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
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
    </>
  );
}
