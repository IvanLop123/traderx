"use client";
import {DocumentComparisons} from "./DocumentComparisons";
import { useEffect, useState, useCallback } from "react";
import { ArrowUpRight as Arrow, BookOpen } from "lucide-react";
import { api, money, number, pct } from "@/lib/api";
import { Badge, Panel, JsonView, Records } from "./Common";
import { ObservationMetrics } from "./ObservationMetrics";
import { CopyReplay } from "./CopyReplay";
import { SemanticResearch } from "./SemanticResearch";
import { EvidenceResearch } from "./EvidenceResearch";
import { InstitutionalConsensus } from "./InstitutionalConsensus";
type Data = Record<string, any>;
export function Options({ act }: { act: any }) {
  const [form, setForm] = useState<Data>({
    spot: 100,
    strike: 100,
    years: 1,
    rate: 0.04,
    volatility: 0.3,
    kind: "call",
    dividend: 0,
  });
  const [result, setResult] = useState<Data | null>(null);
  return (
    <>
      <Panel
        title="European options calculator"
        eyebrow="DETERMINISTIC PYTHON · NO AI"
      >
        <div className="form-grid cols4">
          {Object.entries(form).map(([key, v]) => (
            <label key={key}>
              {key.replaceAll("_", " ")}
              {key === "kind" ? (
                <select
                  value={v}
                  onChange={(e) => setForm({ ...form, kind: e.target.value })}
                >
                  <option>call</option>
                  <option>put</option>
                </select>
              ) : (
                <input
                  type="number"
                  step="any"
                  value={v}
                  onChange={(e) => setForm({ ...form, [key]: +e.target.value })}
                />
              )}
            </label>
          ))}
        </div>
        <button
          className="button primary"
          onClick={async () =>
            setResult(
              await act(
                () => api("/options/calculate", form),
                "Option values calculated",
              ),
            )
          }
        >
          Calculate price & Greeks
        </button>
        <p className="panel-note">
          User-entered assumptions, not live options prices. European exercise
          with constant volatility and dividend yield.
        </p>
      </Panel>
      {result && (
        <Panel title="Calculated values">
          <div className="metric-list">
            {Object.entries(result).map(([k, v]) => (
              <div key={k}>
                <span>{k}</span>
                <strong>
                  {typeof v === "number" ? number(v, 6) : String(v)}
                </strong>
              </div>
            ))}
          </div>
        </Panel>
      )}
      <p className="panel-note">Current sourced option surfaces are in Research → Market structure → Options. These are snapshot analytics; options trading is not supported.</p>
    </>
  );
}

export function DataRecords({ kind }: { kind: string }) {
  const [rows, setRows] = useState<Data[]>([]);
  const [item, setItem] = useState<Data | null>(null);
  useEffect(() => {
    api("/records/" + kind).then(setRows);
  }, [kind]);
  return (
    <>
      <Records records={rows} onInspect={setItem} />
      {item && <JsonView value={item} />}
    </>
  );
}

export function Intelligence({
  page,
  act,
  onInspect,
}: {
  page: string;
  act: any;
  onInspect: any;
}) {
  const [rows, setRows] = useState<Data[]>([]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [symbol, setSymbol] = useState("");
  const [source, setSource] = useState("");
  const [wallet, setWallet] = useState("");
  const [period, setPeriod] = useState("");
  const [published, setPublished] = useState("");
  const [entity, setEntity] = useState("");
  const [valueUnit, setValueUnit] = useState("unknown");
  const map: Record<string, string> = {
    earnings: "document",
    insiders: "document",
    institutions: "document",
    themes: "theme",
    macro: "macro",
    crypto: "crypto",
    traders: "trader",
  };
  const kind = map[page];
  const load = useCallback(
    () =>
      api("/records/" + kind).then((r: Data[]) =>
        setRows(
          page === "insiders"
            ? r.filter((x) => x.payload.kind === "form4")
            : page === "institutions"
              ? r.filter((x) => x.payload.kind === "13f")
              : page === "earnings"
                ? r.filter((x) =>
                    ["transcript", "filing"].includes(x.payload.kind),
                  )
                : r,
        ),
      ),
    [kind, page],
  );
  useEffect(() => {
    load();
  }, [load]);
  const imports = ["earnings", "insiders", "institutions", "themes"].includes(
    page,
  );
  const explanation: Record<string, string> = {
    earnings:
      "Transcripts, guidance, management language and operational bottlenecks. Every text-derived claim retains its source.",
    insiders:
      "Form 4 XML distinguishes market or private purchases, sales, grants, exercises and withholding. Transactions are evidence, never automatic trades.",
    institutions:
      "13F holdings are delayed. Filing availability must be preserved separately from quarter-end holdings dates.",
    themes:
      "Evidence-backed mentions across nuclear, robotics, AI infrastructure and power. Mentions do not prove supplier relationships.",
    macro:
      "FRED observations retain their vintage. EIA electricity data is available when configured.",
    crypto:
      "Public perpetual market observations. Funding and spot exposures remain distinct.",
    traders:
      "Import authorized observations or inspect a public Hyperliquid wallet. No automatic copying.",
  };
  return (
    <>
      <div className="banner neutral">
        <BookOpen size={18} />
        {explanation[page]}
      </div>
      <EvidenceResearch page={page} revision={rows} />
      {page === "institutions" && <InstitutionalConsensus revision={rows} />}
      {page === "crypto" && rows.length ? (
        <Panel title="Perpetual market observations">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ASSET</th>
                  <th>MARK</th>
                  <th>FUNDING</th>
                  <th>OPEN INTEREST</th>
                  <th>24H NOTIONAL VOLUME</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {Array.from(new Map(rows.map((r) => [r.symbol, r])).values())
                  .slice(0, 35)
                  .map((r) => (
                    <tr key={r.id}>
                      <td>{r.symbol}</td>
                      <td>{money(r.payload.mark_price)}</td>
                      <td>{pct(r.payload.funding)}</td>
                      <td>{number(r.payload.open_interest)}</td>
                      <td>{money(r.payload.day_volume)}</td>
                      <td>
                        <button
                          className="text-link"
                          onClick={() => onInspect(r)}
                        >
                          Evidence <Arrow size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : (
        <Panel title="Collected intelligence" eyebrow="PROVENANCE INCLUDED">
          <Records records={rows} onInspect={onInspect} />
        </Panel>
      )}
      {imports && (
        <Panel
          title={
            page === "insiders"
              ? "Import Form 4 XML"
              : page === "institutions"
                ? "Import 13F XML"
                : "Add a source document"
          }
        >
          <div className="form-grid">
            <label>
              Document title
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Company · Quarter · Source"
              />
            </label>
            <label>
              Asset symbol
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="AAPL"
              />
            </label>
            <label className="wide">
              Source reference
              <input
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="Official filing URL or authorized source"
              />
            </label>
            <label>
              Publication time (optional, your local time)
              <input
                type="datetime-local"
                value={published}
                onChange={(e) => setPublished(e.target.value)}
              />
            </label>
            {(page === "earnings" || page === "institutions") && (
              <label>
                Reporting period end
                <input
                  type="date"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                />
              </label>
            )}
            {page === "institutions" && (
              <>
                <label>
                  Reporting manager CIK or identifier
                  <input
                    value={entity}
                    onChange={(e) => setEntity(e.target.value)}
                    placeholder="Same identifier across periods"
                  />
                </label>
                <label>
                  XML value units
                  <select
                    value={valueUnit}
                    onChange={(e) => setValueUnit(e.target.value)}
                  >
                    <option value="unknown">Not confirmed</option>
                    <option value="dollars">US dollars</option>
                    <option value="thousands">Thousands of US dollars</option>
                  </select>
                </label>
              </>
            )}
            <label className="wide">
              {page === "insiders" || page === "institutions"
                ? "XML content"
                : "Document text"}
              <textarea
                rows={7}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste authorized source text…"
              />
            </label>
          </div>
          <button
            className="button primary"
            disabled={!title || !text || !source}
            onClick={async () => {
              await act(
                () =>
                  api("/documents", {
                    title,
                    text,
                    symbol,
                    source_reference: source,
                    published_at: published
                      ? new Date(published).toISOString()
                      : null,
                    period_end: period || null,
                    entity_id: entity,
                    value_unit: valueUnit,
                    kind:
                      page === "insiders"
                        ? "form4"
                        : page === "institutions"
                          ? "13f"
                          : page === "themes"
                            ? "theme"
                            : "transcript",
                  }),
                "Document and provenance stored",
              );
              load();
            }}
          >
            Store & extract evidence
          </button>
          <p className="panel-note">
            Structured XML uses Python. Narrative analysis is queued only for
            your configured AI policy. Unchanged documents retain cached
            results.
          </p>
        </Panel>
      )}
      <ObservationMetrics page={page} rows={rows} onInspect={onInspect} />
      {["earnings","themes"].includes(page) && <><SemanticResearch revision={rows} onInspect={onInspect} /><DocumentComparisons revision={rows} onInspect={onInspect} /></>}
      {page === "traders" && (
        <div className="two-col">
          <Panel title="Public wallet research">
            <label className="standalone">
              Hyperliquid wallet address
              <input
                placeholder="0x…"
                value={wallet}
                onChange={(e) => setWallet(e.target.value)}
              />
            </label>
            <button
              className="button primary"
              onClick={async () => {
                const r = await act(
                  () => api("/traders/wallet", { address: wallet }),
                  "Public wallet data collected",
                );
                if (r) onInspect(r);
                load();
              }}
            >
              Read public wallet
            </button>
          </Panel>
          <Panel title="Import authorized trades">
            <label className="standalone">
              CSV with pnl,notional columns
              <textarea
                rows={5}
                placeholder={"pnl,notional,timestamp,symbol\n"}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <button
              className="button secondary"
              onClick={async () => {
                await act(
                  () => api("/traders/import", { csv_text: text }),
                  "Trade observations imported",
                );
                load();
              }}
            >
              Import CSV
            </button>
          </Panel>
        </div>
      )}
      {page === "traders" && <CopyReplay act={act} onInspect={onInspect} />}
      {page === "macro" && (
        <Panel title="Electricity & energy">
          <DataRecords kind="energy" />
        </Panel>
      )}
      {page === "earnings" && (
        <Panel title="AI-derived analyses">
          <DataRecords kind="analysis" />
        </Panel>
      )}
    </>
  );
}
