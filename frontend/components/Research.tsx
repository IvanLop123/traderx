"use client";
import { StrategyFamilies } from "./StrategyFamilies";
import { ModelLab } from "./ModelLab";
import { ExperimentLab } from "./ExperimentLab";
import { ModelRegistry } from "./ModelRegistry";
import { TrainingSchedule } from "./TrainingSchedule";
import { PortfolioReplay } from "./PortfolioReplay";
import { ResearchSummary } from "./ResearchSummary";
import { useEffect, useState, useCallback } from "react";
import { FlaskConical, Loader2 } from "lucide-react";
import { api, money, number, pct } from "@/lib/api";
import { Badge, Panel, Stat, Plot, JsonView, Records } from "./Common";
type Data = Record<string, any>;
export function Research({
  page,
  act,
  onInspect,
}: {
  page: string;
  act: any;
  onInspect: (v: Data) => void;
}) {
  const [symbol, setSymbol] = useState("BTC-USD");
  const [lookback, setLookback] = useState(20);
  const [horizon, setHorizon] = useState(5);
  const [fee, setFee] = useState(5);
  const [slip, setSlip] = useState(5);
  const [strict, setStrict] = useState(false);
  const [records, setRecords] = useState<Data[]>([]);
  const [result, setResult] = useState<Data | null>(null);
  const [sourceRecord, setSourceRecord] = useState<Data | null>(null);
  const [running, setRunning] = useState(false);
  const kind =
    page === "models"
      ? "model"
      : page === "strategies"
        ? "strategy_comparison"
        : page === "experiments" || page === "research"
          ? "experiment"
          : "backtest";
  const load = useCallback(
    () => Promise.all((kind === "model" ? ["model","model_comparison"] : kind === "backtest" ? ["backtest","replay"] : [kind]).map(k=>api("/records/"+k))).then(groups=>setRecords(groups.flat().sort((a,b)=>b.created_at.localeCompare(a.created_at)))),
    [kind],
  );
  useEffect(() => {
    load();
  }, [load]);
  const run = async (type: string) => {
    setRunning(true);
    const r = await act(
      () =>
        api(
          type === "model-compare"
            ? "/research/model-comparison"
            : type === "model"
            ? "/models/train"
            : type === "experiment"
              ? "/experiments"
              : type === "compare"
                ? "/research/compare"
                : "/backtests",
          type === "backtest"
            ? {
                symbol,
                lookback,
                fee_bps: fee,
                slippage_bps: slip,
                strict_observed: strict,
              }
            : { symbol, horizon },
        ),
      "Research run stored",
    );
    if (r) {
      setResult(r);
      setSourceRecord(null);
    }
    await load();
    setRunning(false);
  };
  return (
    <>
      <div className="banner neutral">
        <FlaskConical size={18} /> Research outputs are exploratory. Model
        training uses chronological training, validation and holdout periods
        with a purged boundary.
      </div>
      {(page === "experiments" || page === "research") && <ExperimentLab act={act} onInspect={onInspect} />}
      {page === "models" && <ModelLab act={act}/>}
      {page === "strategies" && <StrategyFamilies/>}
      <details open={page !== "models"}><summary className="section-copy">{page === "models" ? "Existing baseline models, schedules and advanced research tools" : "Research tools"}</summary>
      <Panel
        title={
          page === "strategies"
            ? "Lagged momentum · v1"
            : "Configure a research run"
        }
        eyebrow="LOCAL COMPUTE · NO LLM"
      >
        <div className="form-grid cols4">
          <label>
            Asset
            <input
              aria-label="Research asset"
              list="research-assets"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            />
            <datalist id="research-assets">
              {["BTC-USD", "ETH-USD", "SOL-USD", "AAPL", "MSFT", "NVDA"].map(
                (s) => (
                  <option key={s} value={s} />
                ),
              )}
            </datalist>
          </label>
          <label>
            Lookback (bars)
            <input
              type="number"
              min="2"
              max="252"
              value={lookback}
              onChange={(e) => setLookback(+e.target.value)}
            />
          </label>
          <label>
            Prediction horizon (bars)
            <input
              type="number"
              min="1"
              max="20"
              value={horizon}
              onChange={(e) => setHorizon(+e.target.value)}
            />
          </label>
          <label>
            Fee / slippage (bps)
            <div className="inline-inputs">
              <input
                aria-label="Fee bps"
                type="number"
                min="0"
                value={fee}
                onChange={(e) => setFee(+e.target.value)}
              />
              <input
                aria-label="Slippage bps"
                type="number"
                min="0"
                value={slip}
                onChange={(e) => setSlip(+e.target.value)}
              />
            </div>
          </label>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={strict}
            onChange={(e) => setStrict(e.target.checked)}
          />{" "}
          Strict first-observed replay (recently downloaded history cannot trade
          in the past)
        </label>
        <div className="actions">
          <button
            disabled={running}
            className="button primary"
            onClick={() => run("backtest")}
          >
            Run backtest
          </button>
          <button
            disabled={running}
            className="button secondary"
            onClick={() => run("experiment")}
          >
            Evaluate signal
          </button>
          <button
            disabled={running}
            className="button secondary"
            onClick={() => run("model")}
          >
            Train local baseline
          </button>
          <button
            disabled={running}
            className="button secondary"
            onClick={() => run("compare")}
          >
            Compare & stress-test
          </button>
          <button disabled={running} className="button secondary" onClick={()=>run("model-compare")}>Compare forecasting models</button>
          {running && <Loader2 className="spin" size={18} />}
        </div>
        <p className="panel-note">
          Default backtests use retrospective completed daily bars with next-bar
          execution, spread, slippage and fees. They cannot prove historical
          revision safety. No strategy automatically trades.
        </p>
      </Panel>
      {(page === "backtests" || page === "strategies") && <PortfolioReplay act={act} onInspect={onInspect} />}
      {result && (
        <Panel
          title="Run results"
          action={
            <div className="top-right">
              <Badge>{result.decision || "RESEARCH RESULT"}</Badge>
              <button
                className="text-link"
                onClick={() => onInspect(sourceRecord || result)}
              >
                Source details
              </button>
            </div>
          }
        >
          {result.model_comparison ? <><div className="table-scroll"><table><thead><tr><th>FORECASTER</th><th>VALIDATION ERROR</th><th>HOLDOUT ERROR</th></tr></thead><tbody>{result.model_comparison.map((r:Data)=><tr key={r.model}><td>{r.model.replaceAll("_"," ")}</td><td>{number(r.validation_mse,8)}</td><td>{number(r.holdout_mse,8)}</td></tr>)}</tbody></table></div><p className="panel-note">Selected using validation only: {result.selected_on_validation_only}. Lower error is better. A zero-return estimate is a valid winner. Fixed settings; no automatic activation.</p><p className="panel-note">{result.warnings.join(" ")}</p></> : result.strategies ? (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>STRATEGY</th>
                      <th>DEVELOPMENT SHARPE</th>
                      <th>HOLDOUT RETURN</th>
                      <th>HOLDOUT DRAWDOWN</th>
                      <th>HIGHER-COST RETURN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.strategies.map((r: Data) => (
                      <tr key={r.strategy}>
                        <td>{r.strategy.replaceAll("_", " ")}</td>
                        <td>{number(r.development.sharpe)}</td>
                        <td>{pct(r.holdout.total_return)}</td>
                        <td>{pct(r.holdout.max_drawdown)}</td>
                        <td>{pct(r.holdout_cost_stress.total_return)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="panel-note">
                Selected using development only:{" "}
                {result.selected_on_development_only}.{" "}
                {result.walk_forward_folds.length} purged walk-forward folds.
                Research only; no automatic trading.
              </p>
              {result.statistical_governance && <><div className="table-scroll"><table><thead><tr><th>STRATEGY</th><th>MEAN DAILY RETURN RANGE</th><th>ADJUSTED P-VALUE</th></tr></thead><tbody>{Object.entries(result.statistical_governance.tests).map(([name,r]:[string,any])=><tr key={name}><td>{name.replaceAll("_"," ")}</td><td>{r.mean_daily_return_ci_95?.map((v:number)=>pct(v)).join(" to ")||"Insufficient observations"}</td><td>{number(r.adjusted_p_value_by,4)}</td></tr>)}</tbody></table></div><p className="panel-note">95% block-bootstrap intervals with within-family multiple-testing adjustment. Development CSCV fraction below the out-of-sample median: {pct(result.development_cscv?.probability_below_oos_median)}. These are exploratory diagnostics, not evidence of future profit.</p></>}
              <details className="panel-note">
                <summary>
                  Evaluation periods, fold results and limitations
                </summary>
                <JsonView
                  value={{
                    split: result.split,
                    walk_forward: result.walk_forward_folds,
                    statistical_governance:result.statistical_governance,
                    development_cscv:result.development_cscv,
                    warnings: result.warnings,
                  }}
                />
              </details>
            </>
          ) : result.curve ? (
            <>
              <div className="stats inside">
                <Stat
                  label="TOTAL RETURN"
                  value={pct(result.metrics.total_return)}
                  detail="After simulated costs"
                />
                <Stat
                  label="MAX DRAWDOWN"
                  value={pct(result.metrics.max_drawdown)}
                  detail="Marked equity"
                />
                <Stat
                  label="SHARPE"
                  value={number(result.metrics.sharpe)}
                  detail="Annualized historical estimate"
                />
                <Stat
                  label="COSTS"
                  value={money(result.total_cost)}
                  detail={`${result.fills.length} fills`}
                />
              </div>
              <Plot
                data={result.curve}
                value="equity"
                second={result.engine ? undefined : "benchmark"}
                height={300}
              />
              <p className="panel-note">
                {result.engine ? "Marked portfolio equity; open positions remain at final marks. " : "Copper: strategy. Slate: buy-and-hold benchmark. "}
                {result.data_policy}
              </p>
            </>
          ) : (
            <ResearchSummary result={result} />
          )}
        </Panel>
      )}
      {page === "models" && <><TrainingSchedule act={act} /><ModelRegistry act={act} /></>}
      <Panel title="Saved research history" eyebrow="APPEND-ONLY RESULTS">
        <Records
          records={records}
          onInspect={(r) => {
            setResult(r.payload);
            setSourceRecord(r);
          }}
        />
      </Panel>
      </details>
    </>
  );
}
