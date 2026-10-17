"use client";
import { useEffect, useState } from "react";
import { RiskAnalytics } from "./RiskAnalytics";
import { ShieldCheck } from "lucide-react";
import { api, money, number } from "@/lib/api";
import { Badge, Empty, Panel, Stat, Records } from "./Common";
type Data = Record<string, any>;
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
              : "Paper trading is enabled"}
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
                ? "Paper trading resumed; venue settings still apply"
                : "All new paper orders blocked",
            )
          }
        >
          {data.portfolio.kill_switch
            ? "Resume paper trading"
            : "STOP ALL TRADING"}
        </button>
      </div>
      <RiskAnalytics risk={risk} act={act} />
      <div className="two-col">
        <Panel title="Deterministic limits">
          <div className="metric-list">
            {Object.entries(risk?.limits || {}).map(([k, v]) => (
              <div key={k}>
                <span>{k.replaceAll("_", " ")}</span>
                <strong>{typeof v === "boolean" ? (v ? "Required" : "Optional") : number(v, 4)}</strong>
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
