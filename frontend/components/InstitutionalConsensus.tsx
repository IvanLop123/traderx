"use client";
import { useEffect, useState } from "react";
import { api, pct } from "@/lib/api";
import { Empty, Panel, JsonView } from "./Common";
type Data = Record<string, any>;
export function InstitutionalConsensus({ revision }: { revision: Data[] }) {
  const [period, setPeriod] = useState("");
  const [result, setResult] = useState<Data | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api("/intelligence/institutions" + (period ? "?period_end=" + period : ""))
      .then((r) => {
        if (active) {
          setResult(r);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [period, revision]);
  return (
    <Panel
      title="Shared institutional holdings"
      eyebrow="SAME REPORTING PERIOD · OBSERVED MANAGERS"
    >
      {error ? (
        <p role="alert">{error}</p>
      ) : !result?.manager_count ? (
        <Empty title="No comparable filings yet">
          Add the reporting manager identifier and period end when importing 13F
          information-table XML.
        </Empty>
      ) : (
        <>
          <label className="standalone">
            Reporting period
            <select
              value={result.period_end}
              onChange={(e) => setPeriod(e.target.value)}
            >
              {result.available_periods.map((p: string) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <p className="panel-note">
            {result.manager_count} observed managers ·{" "}
            {result.managers_with_prior_period} with earlier holdings ·{" "}
            {result.excluded_unidentified_documents} documents excluded for
            missing identifiers or dates
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ISSUER / CUSIP</th>
                  <th>SECURITY</th>
                  <th>HOLDERS</th>
                  <th>OBSERVED MANAGER SHARE</th>
                  <th>ADDING / REDUCING</th>
                </tr>
              </thead>
              <tbody>
                {result.holdings.slice(0, 50).map((h: Data, i: number) => (
                  <tr key={i}>
                    <td>
                      {h.issuer}
                      <small>{h.cusip}</small>
                    </td>
                    <td>
                      {h.class} {h.put_call}
                    </td>
                    <td>{h.manager_count}</td>
                    <td>{pct(h.observed_manager_fraction)}</td>
                    <td>
                      {h.managers_adding} / {h.managers_reducing}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.warnings.map((w: string) => (
            <p className="panel-note" key={w}>
              {w}
            </p>
          ))}
          <details>
            <summary>Manager-level evidence</summary>
            <JsonView value={result} />
          </details>
        </>
      )}
    </Panel>
  );
}
