"use client";
import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, money, number } from "@/lib/api";
import { Badge, Empty, Panel, Stat, Records } from "./Common";
type Data = Record<string, any>;
export function Portfolio({ data, act }: { data: Data; act: any }) {
  const p = data.portfolio;
  return (
    <>
      <div className="stats">
        <Stat
          label="EQUITY"
          value={money(p.equity)}
          detail="Internal paper account"
        />
        <Stat
          label="AVAILABLE CASH"
          value={money(p.cash)}
          detail="Simulated buying power"
        />
        <Stat
          label="REALIZED P&L"
          value={money(p.realized_pnl)}
          detail="Closed paper positions"
        />
        <Stat
          label="FEES"
          value={money(p.fees)}
          detail="Simulated execution costs"
        />
      </div>
      <Panel title="Open positions">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>ASSET</th>
                <th>QUANTITY</th>
                <th>AVERAGE COST</th>
                <th>MARK</th>
                <th>MARKET VALUE</th>
                <th>UNREALIZED P&L</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(p.positions).map(([symbol, v]: [string, any]) => (
                <tr key={symbol}>
                  <td>{symbol}</td>
                  <td>{number(v.quantity, 6)}</td>
                  <td>{money(v.average_cost)}</td>
                  <td>{money(v.market_price)}</td>
                  <td>{money(v.quantity * v.market_price)}</td>
                  <td>
                    {money(v.quantity * (v.market_price - v.average_cost))}
                  </td>
                  <td>
                    <button
                      className="button secondary"
                      onClick={() =>
                        act(
                          () =>
                            api(
                              "/portfolio/" +
                                encodeURIComponent(symbol) +
                                "/close-candidate",
                              {},
                            ),
                          "Exit candidate created. Open Orders to review risk and execute.",
                        )
                      }
                    >
                      Prepare exit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!Object.keys(p.positions).length && (
          <Empty title="Your paper portfolio is in cash">
            Positions appear only after a stored candidate passes risk and you
            execute its approved paper order.
          </Empty>
        )}
      </Panel>
    </>
  );
}

export function Risk({
  data,
  act,
  onInspect,
}: {
  data: Data;
  act: any;
  onInspect: any;
}) {
  const [risk, setRisk] = useState<Data | null>(null);
  useEffect(() => {
    api("/risk").then(setRisk);
  }, [data]);
  return (
    <>
      <div
        className={"risk-hero " + (data.portfolio.kill_switch ? "halted" : "")}
      >
        <ShieldCheck size={32} />
        <div>
          <h2>
            {data.portfolio.kill_switch
              ? "Trading is halted"
              : "Internal paper trading is enabled"}
          </h2>
          <p>
            Live exchange execution is disabled. Risk checks cannot be bypassed
            by AI, candidates or the browser.
          </p>
        </div>
        <button
          className={
            "button " + (data.portfolio.kill_switch ? "secondary" : "danger")
          }
          onClick={() =>
            act(
              () => api("/risk/halt", { halted: !data.portfolio.kill_switch }),
              data.portfolio.kill_switch
                ? "Internal paper trading resumed"
                : "All new paper orders blocked",
            )
          }
        >
          {data.portfolio.kill_switch
            ? "Resume internal paper"
            : "STOP ALL TRADING"}
        </button>
      </div>
      <div className="two-col">
        <Panel title="Deterministic limits">
          <div className="metric-list">
            {Object.entries(risk?.limits || {}).map(([k, v]) => (
              <div key={k}>
                <span>{k.replaceAll("_", " ")}</span>
                <strong>{number(v, 4)}</strong>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Risk decisions">
          <Records records={risk?.assessments || []} onInspect={onInspect} />
        </Panel>
      </div>
    </>
  );
}

export function Orders({ act, onInspect }: { act: any; onInspect: any }) {
  const [rows, setRows] = useState<Data[]>([]);
  const load = () =>
    Promise.all(
      ["candidate", "approved_order", "fill"].map((k) => api("/records/" + k)),
    ).then((a) => setRows(a.flat()));
  useEffect(() => {
    load();
  }, []);
  return (
    <Panel
      title="Candidate → risk approval → paper fill"
      eyebrow="AUDITABLE EXECUTION"
    >
      {rows.length ? (
        rows.map((r) => (
          <div className="order-row" key={r.id}>
            <button onClick={() => onInspect(r)}>
              <strong>{r.symbol}</strong>
              <small>
                {r.kind.replaceAll("_", " ")} · {r.id.slice(0, 8)}
              </small>
            </button>
            <Badge>
              {r.kind === "candidate"
                ? "RESEARCH CANDIDATE"
                : r.kind === "approved_order"
                  ? "RISK APPROVED"
                  : "PAPER FILL"}
            </Badge>
            {r.kind === "candidate" && (
              <button
                className="button secondary"
                onClick={async () => {
                  const x = await act(
                    () => api("/candidates/" + r.id + "/assess", {}),
                    "Risk assessment stored",
                  );
                  if (x) onInspect(x);
                  load();
                }}
              >
                Evaluate risk
              </button>
            )}
            {r.kind === "approved_order" && (
              <button
                className="button secondary"
                onClick={async () => {
                  await act(
                    () => api("/orders/" + r.id + "/execute", {}),
                    "Internal paper fill stored",
                  );
                  load();
                }}
              >
                Execute paper order
              </button>
            )}
          </div>
        ))
      ) : (
        <Empty title="No orders or candidates">
          A model may correctly produce NO_TRADE. Candidates require enough
          estimated edge after costs and uncertainty before risk review.
        </Empty>
      )}
    </Panel>
  );
}
