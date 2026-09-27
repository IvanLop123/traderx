"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowUpRight as Arrow,
  ChevronRight,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { api, money, number, pct, date } from "@/lib/api";
import { Badge, Empty, Panel, Stat, Plot, Records } from "./Common";
type Data = Record<string, any>;
export function Overview({
  data,
  healthy,
  onInspect,
}: {
  data: Data;
  healthy: number;
  onInspect: (v: Data) => void;
}) {
  const p = data.portfolio;
  const [history, setHistory] = useState<Data[]>([]);
  const [selected, setSelected] = useState("BTC-USD");
  useEffect(() => {
    api("/assets/" + selected)
      .then((d) => setHistory(d.bars))
      .catch(() => setHistory([]));
  }, [selected, data.worker?.last_cycle]);
  const q = data.quotes.find((q: Data) => q.symbol === selected);
  const f = data.features[selected];
  return (
    <>
      <div className="stats">
        <Stat
          label="PAPER PORTFOLIO VALUE"
          value={money(p.equity)}
          detail="Internal simulator · starting capital $100,000"
        />
        <Stat
          label="TOTAL PAPER P&L"
          value={money(p.equity - p.initial_cash)}
          detail={`${money(p.fees)} in simulated fees`}
          positive={p.equity >= p.initial_cash}
        />
        <Stat
          label="RESEARCH CANDIDATES"
          value={String(data.candidates.length)}
          detail="Subject to expiry and deterministic risk"
        />
        <Stat
          label="OPENAI SPEND TODAY"
          value={money(data.ai.usage.daily_cost)}
          detail={`${data.ai.current_provider.toUpperCase()} · $${data.ai.settings.daily_budget.toFixed(2)} daily budget`}
        />
      </div>
      <div className="dashboard-grid">
        <Panel
          title="Market pulse"
          eyebrow="PRICE & PARTICIPATION"
          action={
            <div className="segmented">
              {["BTC-USD", "ETH-USD", "SOL-USD"].map((s) => (
                <button
                  key={s}
                  className={s === selected ? "selected" : ""}
                  onClick={() => setSelected(s)}
                >
                  {s.split("-")[0]}
                </button>
              ))}
            </div>
          }
        >
          <div className="market-number">
            <strong>{money(q?.price)}</strong>
            <Badge tone="green">{f?.regime?.trend || "Waiting for data"}</Badge>
            <span>Coinbase · USD · daily candles</span>
          </div>
          {history.length ? (
            <Plot data={history.slice(-100)} height={280} />
          ) : (
            <Empty title="Waiting for market history">
              Public market data loads automatically. No API key or AI model is
              needed.
            </Empty>
          )}
          <div className="chart-bottom">
            <span>Completed historical bars · revisions possible</span>
            <Link href={"/asset/" + selected}>
              Explore asset <Arrow size={14} />
            </Link>
          </div>
        </Panel>
        <Panel title="System snapshot" eyebrow="YOUR OPERATING ENVIRONMENT">
          <div className="system-row">
            <span className="system-icon">
              <Activity size={19} />
            </span>
            <div>
              Market data<small>{healthy} providers responding</small>
            </div>
            <Badge tone={healthy ? "green" : ""}>
              {healthy ? "CONNECTED" : "CONNECTING"}
            </Badge>
          </div>
          <div className="system-row">
            <span className="system-icon">
              <ShieldCheck size={19} />
            </span>
            <div>
              Trading controls
              <small>
                New paper orders{" "}
                {p.kill_switch ? "blocked" : "allowed after risk review"}
              </small>
            </div>
            <Badge tone={p.kill_switch ? "amber" : "green"}>
              {p.kill_switch ? "HALTED" : "READY"}
            </Badge>
          </div>
          <div className="system-row">
            <span className="system-icon">
              <Zap size={19} />
            </span>
            <div>
              AI intelligence
              <small>
                {data.ai.current_model ||
                  "Quantitative research remains active"}
              </small>
            </div>
            <Badge>{data.ai.current_provider.toUpperCase()}</Badge>
          </div>
          <div className="callout">
            <span className="callout-label">DESIGNED FOR CONTROL</span>
            <p>
              Market data, research, risk and accounting run locally. AI only
              handles selected text and your questions.
            </p>
            <Link href="/settings">
              Manage AI settings <Arrow size={14} />
            </Link>
          </div>
        </Panel>
      </div>
      <Panel
        title="Watchlist"
        eyebrow="PUBLIC MARKET COVERAGE"
        action={
          <Link className="text-link" href="/scanner">
            Open scanner <Arrow size={14} />
          </Link>
        }
      >
        <MarketTable data={data} />
      </Panel>
      <div className="two-col">
        <Panel title="Research pipeline" eyebrow="FROM INFORMATION TO ACTION">
          <div className="pipeline">
            {[
              ["01", "Evidence", data.activity.length],
              ["02", "Signals", data.signals.length],
              ["03", "Candidates", data.candidates.length],
              ["04", "Risk review", "Required"],
            ].map(([n, label, count]) => (
              <div key={n}>
                <span>{n}</span>
                <strong>{count}</strong>
                <small>{label}</small>
              </div>
            ))}
          </div>
          <p className="panel-note">
            Signals require historical validation. A candidate is never an
            order.
          </p>
        </Panel>
        <Panel title="Latest observations" eyebrow="SOURCE ACTIVITY">
          <div className="activity-list">
            {data.activity.slice(0, 4).map((r: Data) => (
              <button key={r.id} onClick={() => onInspect(r)}>
                <span className="activity-dot" />
                <div>
                  <strong>
                    {r.symbol || r.payload.provider}{" "}
                    <span>{r.payload.event_type.replaceAll("_", " ")}</span>
                  </strong>
                  <small>
                    {r.payload.provider} · {date(r.created_at)}
                  </small>
                </div>
                <ChevronRight size={14} />
              </button>
            ))}
            {!data.activity.length && (
              <p className="panel-note">
                Real provider observations will appear here.
              </p>
            )}
          </div>
        </Panel>
      </div>
    </>
  );
}

export function MarketTable({ data }: { data: Data }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>ASSET</th>
            <th>LAST PRICE</th>
            <th>1D RETURN</th>
            <th>20D MOMENTUM</th>
            <th>REALIZED VOL.</th>
            <th>REGIME</th>
            <th>SOURCE TIME</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.quotes.map((q: Data) => {
            const f = data.features[q.symbol]?.values || {};
            return (
              <tr key={q.symbol}>
                <td>
                  <Link className="asset-cell" href={"/asset/" + q.symbol}>
                    <span className="coin">{q.symbol[0]}</span>
                    <span>
                      <strong>{q.symbol.split("-")[0]}</strong>
                      <small>
                        {q.symbol} ·{" "}
                        {q.asset_class === "stock" ? "Equity" : "Spot"}
                      </small>
                    </span>
                  </Link>
                </td>
                <td className="numeric">{money(q.price)}</td>
                <td className={f.return_1 >= 0 ? "positive" : "negative"}>
                  {pct(f.return_1)}
                </td>
                <td className={f.return_20 >= 0 ? "positive" : "negative"}>
                  {pct(f.return_20)}
                </td>
                <td>{pct(f.realized_volatility)}</td>
                <td>
                  <Badge>{data.features[q.symbol]?.regime?.trend || "—"}</Badge>
                </td>
                <td className="muted">{date(q.timestamp)}</td>
                <td>
                  <Link
                    aria-label={"View " + q.symbol}
                    href={"/asset/" + q.symbol}
                  >
                    <Arrow size={16} />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!data.quotes.length && (
        <Empty title="No live quotes yet">
          Refresh public market data to populate the watchlist.
        </Empty>
      )}
    </div>
  );
}

export function Scanner({ data }: { data: Data }) {
  const [filter, setFilter] = useState("");
  return (
    <Panel title="Market universe" eyebrow="DETERMINISTIC SIGNALS">
      <div className="toolbar">
        <Search size={16} />
        <input
          aria-label="Filter assets"
          placeholder="Search symbol…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <Badge>RESEARCH ONLY</Badge>
      </div>
      <MarketTable
        data={{
          ...data,
          quotes: data.quotes.filter((q: Data) =>
            q.symbol.includes(filter.toUpperCase()),
          ),
        }}
      />
    </Panel>
  );
}

export function Asset({
  symbol,
  onInspect,
}: {
  symbol: string;
  onInspect: (v: Data) => void;
}) {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => {
    api("/assets/" + symbol).then(setData);
  }, [symbol]);
  if (!data) return <p>Loading asset…</p>;
  return (
    <>
      <div className="stats">
        <Stat
          label="LAST PRICE"
          value={money(data.quote?.price)}
          detail="Read-only market observation"
        />
        <Stat
          label="REALIZED VOLATILITY"
          value={pct(data.features.values?.realized_volatility)}
          detail="20-bar realized · annualized"
        />
        <Stat
          label="REGIME"
          value={data.features.regime?.trend || "Unavailable"}
          detail="Price-only regime"
        />
        <Stat
          label="EVIDENCE"
          value={String(data.evidence.length)}
          detail="Observed source records"
        />
      </div>
      <Panel title={symbol + " · Price history"}>
        <Plot data={data.bars} height={340} />
      </Panel>
      <div className="two-col">
        <Panel title="Quantitative features">
          <div className="metric-list">
            {Object.entries(data.features.values || {}).map(([k, v]) => (
              <div key={k}>
                <span>{k.replaceAll("_", " ")}</span>
                <strong>{number(v, 4)}</strong>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Signals & predictions">
          <Records
            records={[...data.signals, ...data.predictions]}
            onInspect={onInspect}
          />
          <p className="panel-note">
            Insider, earnings, options and macro inputs appear when source
            evidence is available. Missing inputs are never synthesized.
          </p>
        </Panel>
      </div>
      <Panel title="Evidence trail">
        <Records records={data.evidence} onInspect={onInspect} />
      </Panel>
    </>
  );
}
