"use client";
import { useEffect, useState } from "react";
import { api, number, pct } from "@/lib/api";
import { Empty, Panel, JsonView } from "./Common";
type Data = Record<string, any>;
export function OptionsResearch() {
  const [rows, setRows] = useState<Data[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api("/records/options_research")
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);
  const row = rows.find((r) => r.id === selected) || rows[0];
  const result = row?.payload;
  return (
    <Panel
      title="Historical options research"
      eyebrow="LOCAL CALCULATIONS · NO AI"
    >
      {error ? (
        <p role="alert">{error}</p>
      ) : !result ? (
        <Empty title="No historical chain collected">
          Fetch historical options in Data Providers after adding an entitled
          Alpha Vantage key. Summaries appear here automatically.
        </Empty>
      ) : (
        <>
          <label className="standalone">
            Stored chain
            <select
              value={row.id}
              onChange={(e) => setSelected(e.target.value)}
            >
              {rows.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.symbol} · {r.payload.observation_date} ·{" "}
                  {r.payload.contract_count} contracts
                </option>
              ))}
            </select>
          </label>
          <div className="metric-list">
            <div>
              <span>Observation date</span>
              <strong>{result.observation_date}</strong>
            </div>
            <div>
              <span>Put / call volume</span>
              <strong>
                {result.totals.put_call_volume_ratio == null
                  ? "Unavailable"
                  : number(result.totals.put_call_volume_ratio, 3)}
              </strong>
            </div>
            <div>
              <span>Two-sided quotes</span>
              <strong>
                {result.quote_coverage.two_sided} / {result.contract_count}
              </strong>
            </div>
            <div>
              <span>Rejected data rows</span>
              <strong>{result.rejected_rows.length}</strong>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>EXPIRATION</th>
                  <th>CONTRACTS</th>
                  <th>MEDIAN SPREAD</th>
                  <th>NEAR 50Δ IV</th>
                  <th>25Δ PUT − CALL IV</th>
                  <th>PUT / CALL VOLUME</th>
                </tr>
              </thead>
              <tbody>
                {result.expirations.map((e: Data) => (
                  <tr key={e.expiration}>
                    <td>{e.expiration}</td>
                    <td>{e.contracts}</td>
                    <td>
                      {e.median_spread_fraction == null
                        ? "—"
                        : pct(e.median_spread_fraction)}
                    </td>
                    <td>
                      {e.near_50_delta_iv == null
                        ? "—"
                        : pct(e.near_50_delta_iv)}
                    </td>
                    <td>
                      {e.put_minus_call_25_delta_iv == null
                        ? "—"
                        : pct(e.put_minus_call_25_delta_iv)}
                    </td>
                    <td>
                      {e.put_call_volume_ratio == null
                        ? "—"
                        : number(e.put_call_volume_ratio, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Contracts ranked by volume / open interest</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>CONTRACT</th>
                    <th>VOLUME</th>
                    <th>OPEN INTEREST</th>
                    <th>RATIO</th>
                    <th>QUOTE QUALITY</th>
                  </tr>
                </thead>
                <tbody>
                  {result.activity_rankings.map((c: Data) => (
                    <tr key={c.contract_id}>
                      <td>{c.contract_id}</td>
                      <td>{number(c.volume, 0)}</td>
                      <td>{number(c.open_interest, 0)}</td>
                      <td>{number(c.volume_to_oi, 3)}</td>
                      <td>{c.quote_status.replaceAll("_", " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          {result.warnings.map((w: string) => (
            <p className="panel-note" key={w}>
              {w}
            </p>
          ))}
          <details>
            <summary>Source and calculation details</summary>
            <JsonView value={result} />
          </details>
        </>
      )}
    </Panel>
  );
}
