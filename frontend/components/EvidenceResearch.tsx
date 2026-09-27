"use client";
import { useEffect, useState } from "react";
import { api, date, money, number, pct } from "@/lib/api";
import { Badge, Empty, Panel, JsonView } from "./Common";
type Data = Record<string, any>;

export function EvidenceResearch({
  page,
  revision,
}: {
  page: string;
  revision: Data[];
}) {
  const [rows, setRows] = useState<Data[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const kind = (
    {
      earnings: "transcript_research",
      insiders: "insider_research",
      institutions: "institution_research",
    } as Data
  )[page];
  useEffect(() => {
    let active = true;
    if (!kind) return;
    api("/records/" + kind)
      .then((r) => {
        if (active) {
          setRows(r);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [kind, revision]);
  if (!kind) return null;
  const chosen = rows.find((r) => r.id === selected) || rows[0];
  const result = chosen?.payload;
  const labels: Data = {
    earnings: "Transcript research",
    insiders: "Observed insider activity",
    institutions: "Institutional holdings research",
  };
  return (
    <Panel title={labels[page]} eyebrow="LOCAL CALCULATIONS · SOURCE EVIDENCE">
      {error ? (
        <p role="alert">{error}</p>
      ) : !result ? (
        <Empty title="No source analysis yet">
          Import a source below or configure a provider. Research appears after
          the document is processed.
        </Empty>
      ) : (
        <>
          <label className="standalone">
            Research snapshot
            <select
              value={chosen.id}
              onChange={(e) => setSelected(e.target.value)}
            >
              {rows.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.symbol || r.payload.entity_id || "Document"} ·{" "}
                  {r.payload.period_end || date(r.available_at)} ·{" "}
                  {r.id.slice(0, 6)}
                </option>
              ))}
            </select>
          </label>
          <p className="panel-note">
            Available to TraderX: {date(chosen.available_at)} ·{" "}
            {result.evidence_ids?.length || 0} source records ·{" "}
            {result.feature_ids?.length || 0} research features
          </p>
          {page === "insiders" && (
            <>
              <Badge>
                {(result.status || "AVAILABLE").replaceAll("_", " ")}
              </Badge>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>WINDOW</th>
                      <th>PURCHASES</th>
                      <th>SALES</th>
                      <th>KNOWN BUYERS</th>
                      <th>KNOWN PURCHASE VALUE</th>
                      <th>CLUSTER</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.windows || {}).map(
                      ([days, value]) => {
                        const w = value as Data;
                        return (
                          <tr key={days}>
                            <td>{days} days</td>
                            <td>{w.purchase_count}</td>
                            <td>{w.sale_count}</td>
                            <td>{w.known_buyers}</td>
                            <td>{money(w.known_purchase_value)}</td>
                            <td>
                              {w.cluster
                                ? "2+ observed buyers"
                                : "Not observed"}
                            </td>
                          </tr>
                        );
                      },
                    )}
                  </tbody>
                </table>
              </div>
              <p className="panel-note">
                Descriptive counts from collected filings. Missing prices are
                excluded from value totals. An unresolved amendment blocks
                numerical model inputs.
              </p>
            </>
          )}
          {page === "earnings" && (
            <>
              <div className="metric-list">
                <div>
                  <span>Identified Q&A pairs</span>
                  <strong>{result.qa_pairs?.length || 0}</strong>
                </div>
                <div>
                  <span>Guidance passages with numbers</span>
                  <strong>{result.guidance_quotes?.length || 0}</strong>
                </div>
                <div>
                  <span>Constraint passages</span>
                  <strong>{result.bottlenecks?.length || 0}</strong>
                </div>
                <div>
                  <span>Previous period comparison</span>
                  <strong>
                    {result.previous_document_id
                      ? "Available"
                      : "No earlier source"}
                  </strong>
                </div>
              </div>
              {(result.guidance_quotes || [])
                .slice(0, 5)
                .map((quote: string, i: number) => (
                  <blockquote key={i}>{quote}</blockquote>
                ))}
              {!!result.qa_pairs?.length && (
                <details>
                  <summary>Questions and management responses</summary>
                  {result.qa_pairs.map((pair: Data, i: number) => (
                    <div key={i}>
                      <p>
                        <strong>
                          {pair.analyst}: {pair.question}
                        </strong>
                      </p>
                      <p>{pair.answer}</p>
                      <p className="panel-note">
                        Word overlap: {pct(pair.lexical_overlap)}. This does not
                        establish evasiveness or intent.
                      </p>
                    </div>
                  ))}
                </details>
              )}
              {!!Object.keys(result.changes || {}).length && (
                <details>
                  <summary>Changes from the previous period</summary>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>MEASURE</th>
                          <th>PREVIOUS</th>
                          <th>CURRENT</th>
                          <th>CHANGE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(result.changes).map(([key, value]) => {
                          const c = value as Data;
                          return (
                            <tr key={key}>
                              <td>{key.replaceAll("_", " ")}</td>
                              <td>{number(c.previous, 4)}</td>
                              <td>{number(c.current, 4)}</td>
                              <td>{number(c.absolute_change, 4)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </>
          )}
          {page === "institutions" && (
            <>
              <div className="metric-list">
                <div>
                  <span>Reporting manager</span>
                  <strong>{result.entity_id || "Not supplied"}</strong>
                </div>
                <div>
                  <span>Holdings date</span>
                  <strong>{result.period_end || "Not supplied"}</strong>
                </div>
                <div>
                  <span>Reported holdings value</span>
                  <strong>
                    {result.reported_value_usd != null
                      ? money(result.reported_value_usd)
                      : "Units not confirmed"}
                  </strong>
                </div>
                <div>
                  <span>Concentration (HHI)</span>
                  <strong>{number(result.concentration_hhi, 4)}</strong>
                </div>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>ISSUER / CUSIP</th>
                      <th>SECURITY</th>
                      <th>SHARES / PRINCIPAL</th>
                      <th>REPORTED WEIGHT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.holdings || [])
                      .slice(0, 50)
                      .map((h: Data, i: number) => (
                        <tr key={i}>
                          <td>
                            {h.issuer}
                            <small>{h.cusip}</small>
                          </td>
                          <td>
                            {h.class} {h.put_call || ""}
                          </td>
                          <td>
                            {number(h.shares)} {h.share_type}
                          </td>
                          <td>
                            {h.portfolio_weight == null
                              ? "—"
                              : pct(h.portfolio_weight)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              {!!result.changes?.length && (
                <details>
                  <summary>Position changes since the previous filing</summary>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>CUSIP</th>
                          <th>TYPE</th>
                          <th>STATUS</th>
                          <th>SHARE CHANGE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.changes.map((c: Data, i: number) => (
                          <tr key={i}>
                            <td>{c.cusip}</td>
                            <td>
                              {c.class} {c.put_call}
                            </td>
                            <td>{c.status}</td>
                            <td>{number(c.shares_change)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </>
          )}
          {(result.warnings || []).map((warning: string) => (
            <p className="panel-note" key={warning}>
              {warning}
            </p>
          ))}
          <details>
            <summary>Evidence and calculation details</summary>
            <JsonView value={result} />
          </details>
        </>
      )}
    </Panel>
  );
}
