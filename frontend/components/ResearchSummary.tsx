"use client";
import { Badge, JsonView, Stat } from "./Common";
import { number, pct, date } from "@/lib/api";
type Data = Record<string, any>;
export function ResearchSummary({ result }: { result: Data }) {
  const model = result.result?.artifact
    ? result.result
    : result.artifact
      ? result
      : null;
  const p = model?.prediction;
  const experiment = !model ? result.result || result : null;
  const labels: Record<string, string> = {
    return_forecast_beats_zero:
      "Return forecast improves on a zero-return estimate",
    direction_beats_training_prior:
      "Direction forecast improves on the historical base rate",
    holdout_at_least_200: "At least 200 held-out observations",
    calibration_available: "Probability calibration is available",
  };
  return (
    <>
      {model ? (
        <>
          <div className="stats inside">
            <Stat
              label="EXPECTED RETURN"
              value={pct(p.expected_return)}
              detail={`Over ${model.hyperparameters.horizon} daily bars · estimate only`}
            />
            <Stat
              label="PROBABILITY POSITIVE"
              value={pct(p.probability_positive)}
              detail="Model estimate, not a guarantee"
            />
            <Stat
              label="UNCERTAINTY ALLOWANCE"
              value={"±" + pct(p.uncertainty)}
              detail="From validation forecast errors"
            />
            <Stat
              label="CANDIDATE ELIGIBILITY"
              value={
                model.research_candidate_eligible
                  ? "Further review"
                  : "Not eligible"
              }
              detail="Risk review is still required"
            />
          </div>
          <div className="metric-list">
            {Object.entries(model.research_candidate_gates || {}).map(
              ([key, passed]) => (
                <div key={key}>
                  <span>{labels[key] || key}</span>
                  <Badge tone={passed ? "green" : ""}>
                    {passed ? "Passed" : "Needs evidence"}
                  </Badge>
                </div>
              ),
            )}
          </div>
          <p className="panel-note">
            A positive return estimate alone cannot create a candidate.
            Benchmark checks, enough historical evidence, estimated costs and
            uncertainty all matter.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>DATA PERIOD</th>
                  <th>START</th>
                  <th>END</th>
                  <th>OBSERVATIONS</th>
                </tr>
              </thead>
              <tbody>
                {["training", "validation", "holdout"].map((key) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{date(model.splits[key].start)}</td>
                    <td>{date(model.splits[key].end)}</td>
                    <td>{model.splits[key].samples}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="panel-note">{model.warning}</p>
        </>
      ) : experiment?.information_coefficient !== undefined ? (
        <>
          <div className="stats inside">
            <Stat
              label="OBSERVATIONS"
              value={number(experiment.samples, 0)}
              detail="Completed historical observations"
            />
            <Stat
              label="SIGNAL / RETURN CORRELATION"
              value={number(experiment.information_coefficient, 4)}
              detail="Exploratory rank correlation"
            />
            <Stat
              label="MEAN FORWARD RETURN"
              value={pct(experiment.mean_forward_return)}
              detail="Unconditional; not strategy profit"
            />
            <Stat
              label="COVERAGE"
              value={pct(experiment.coverage)}
              detail="Share of rows with usable history"
            />
          </div>
          <p className="panel-note">{experiment.warning}</p>
        </>
      ) : (
        <p className="panel-note">
          This is a saved research record. Expand the details to inspect its
          source evidence and parameters.
        </p>
      )}
      <details className="panel-note">
        <summary>Technical details and provenance</summary>
        <JsonView value={result} />
      </details>
    </>
  );
}
