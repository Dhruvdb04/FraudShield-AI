import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, getEmail, getOverview, getTransactions, scoreTransaction } from "./api";
import { CaseQueue } from "./Cases";
import {
  AMOUNT_RULE,
  ODD_HOUR_SPIKE,
  PLAIN_DAYTIME,
  VELOCITY_RULE,
  featureLabel,
  formatFeature,
  formatMetric,
  formatRate,
  formatStamp,
  labelText,
  reasonLine,
  ruleLabel,
  toneFor,
} from "./format";
import type { Overview, ScoreInput, Transaction } from "./types";

type ConsoleProps = {
  onLogout: () => void;
};

const FIELDS: { key: keyof ScoreInput; label: string; step: string; min: number; max: number }[] = [
  { key: "amount", label: "Amount", step: "0.01", min: 0.01, max: 1000000 },
  { key: "hour", label: "Hour", step: "0.1", min: 0, max: 23.99 },
  { key: "country_risk", label: "Country risk", step: "0.01", min: 0, max: 1 },
  { key: "device_trust", label: "Device trust", step: "0.01", min: 0, max: 1 },
  { key: "velocity_1h", label: "Velocity 1h", step: "0.1", min: 0, max: 500 },
  { key: "card_age_days", label: "Card age days", step: "1", min: 0, max: 20000 },
  { key: "distance_from_home_km", label: "Distance km", step: "0.1", min: 0, max: 20000 },
];

export function Console({ onLogout }: ConsoleProps) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [rows, setRows] = useState<Transaction[]>([]);
  const [draft, setDraft] = useState<ScoreInput>(PLAIN_DAYTIME);
  const [result, setResult] = useState<Transaction | null>(null);
  const [lastSubmission, setLastSubmission] = useState<{ key: string; features: ScoreInput } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scoring, setScoring] = useState(false);
  const [page, setPage] = useState<"desk" | "cases">("desk");

  const load = useCallback(async () => {
    const [nextOverview, nextRows] = await Promise.all([getOverview(), getTransactions()]);
    setOverview(nextOverview);
    setRows(nextRows);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [nextOverview, nextRows] = await Promise.all([getOverview(), getTransactions()]);
        if (!alive) return;
        setOverview(nextOverview);
        setRows(nextRows);
      } catch (err) {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 401) {
          onLogout();
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load the desk");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [onLogout]);

  async function submit(features: ScoreInput, key: string) {
    setScoring(true);
    setError(null);
    try {
      const scored = await scoreTransaction(features, key);
      setResult(scored);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "Score failed");
    } finally {
      setScoring(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (Object.values(draft).some((value) => !Number.isFinite(value))) {
      setError("Every feature needs a finite number.");
      return;
    }
    const features = { ...draft, merchant_category: Math.round(draft.merchant_category), is_international: draft.is_international ? 1 : 0 } as ScoreInput;
    const key = crypto.randomUUID();
    setLastSubmission({ key, features });
    void submit(features, key);
  }

  const maxCount = Math.max(1, ...(overview?.histogram.map((bucket) => bucket.count) ?? [1]));

  return (
    <div className="shell">
      <a className="skip" href="#score">
        Skip to scoring
      </a>
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark">FS</span>
          <div>
            <strong>FraudShield</strong>
            <em>AI</em>
          </div>
        </div>
        <p className="rail-note">Defensive scoring for synthetic card-not-present traffic.</p>
        <nav>
          <button
            type="button"
            className="nav-link"
            aria-current={page === "desk" ? "page" : undefined}
            onClick={() => setPage("desk")}
          >
            Desk
          </button>
          {page === "desk" ? (
            <>
              <a href="#overview">Overview</a>
              <a href="#score">Score</a>
              <a href="#ledger">Ledger</a>
            </>
          ) : null}
          <button
            type="button"
            className="nav-link"
            aria-current={page === "cases" ? "page" : undefined}
            onClick={() => setPage("cases")}
          >
            Cases
          </button>
        </nav>
        <div className="rail-foot">
          <p className="mono email">{getEmail() ?? "analyst"}</p>
          <button type="button" className="ghost" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </aside>
      {page === "cases" ? (
        <CaseQueue onLogout={onLogout} />
      ) : (
      <main className="desk">
        <header className="page-head">
          <div>
            <p className="eyebrow">Scoring desk</p>
            <h1>Review the queue</h1>
          </div>
            <p className="lede">
            Amounts and device fields are synthetic. The number is the model probability. Rules can
            raise an allow to review.
          </p>
        </header>

        {error ? (
          <p className="banner" role="alert">
            {error}
          </p>
        ) : null}
        {loading || !overview ? (
          <p className="muted">{loading ? "Loading the desk…" : "Overview unavailable."}</p>
        ) : (
          <>
            <section id="overview" className="stats" aria-label="Workspace counts">
              <article className="stat">
                <span>Scored</span>
                <b className="mono">{overview.total}</b>
              </article>
              <article className="stat">
                <span>Allow</span>
                <b className="mono allow">{overview.allow}</b>
              </article>
              <article className="stat">
                <span>Review</span>
                <b className="mono review">{overview.review}</b>
              </article>
              <article className="stat">
                <span>Block</span>
                <b className="mono block">{overview.block}</b>
              </article>
              <button type="button" className="stat" onClick={() => setPage("cases")}>
                <span>Open cases</span>
                <b className="mono">{overview.open_cases}</b>
              </button>
            </section>

            <div className="work">
              <section id="score" className="panel">
                <div className="panel-head">
                  <h2>Score a transaction</h2>
                  <div className="preset-row">
                    <button type="button" className="ghost" onClick={() => setDraft(PLAIN_DAYTIME)}>
                      Daytime purchase
                    </button>
                    <button type="button" className="ghost" onClick={() => setDraft(ODD_HOUR_SPIKE)}>
                      Odd-hour spike
                    </button>
                    <button type="button" className="ghost" onClick={() => setDraft(VELOCITY_RULE)}>
                      Velocity rule
                    </button>
                    <button type="button" className="ghost" onClick={() => setDraft(AMOUNT_RULE)}>
                      Amount rule
                    </button>
                  </div>
                </div>
                <form onSubmit={onSubmit}>
                  <div className="form-grid">
                    {FIELDS.map((field) => (
                      <label key={field.key} htmlFor={field.key}>
                        {field.label}
                        <input
                          id={field.key}
                          type="number"
                          step={field.step}
                          min={field.min}
                          max={field.max}
                          value={draft[field.key]}
                          onChange={(event) =>
                            setDraft((current) => ({
                              ...current,
                              [field.key]: Number(event.target.value),
                            }))
                          }
                          required
                        />
                      </label>
                    ))}
                    <label htmlFor="merchant_category">
                      Merchant category
                      <select
                        id="merchant_category"
                        value={draft.merchant_category}
                        onChange={(event) =>
                          setDraft((current) => ({
                            ...current,
                            merchant_category: Number(event.target.value),
                          }))
                        }
                      >
                        {overview.merchant_categories.map((category) => (
                          <option key={category.code} value={category.code}>
                            {category.code} · {category.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label htmlFor="is_international">
                      International
                      <select
                        id="is_international"
                        value={draft.is_international}
                        onChange={(event) =>
                          setDraft((current) => ({
                            ...current,
                            is_international: Number(event.target.value),
                          }))
                        }
                      >
                        <option value={0}>No</option>
                        <option value={1}>Yes</option>
                      </select>
                    </label>
                  </div>
                  <div className="form-actions">
                    <button className="primary" type="submit" disabled={scoring}>
                      {scoring ? "Scoring…" : "Score transaction"}
                    </button>
                    <p className="fine">
                      The model blocks at {overview.block_threshold.toFixed(2)} and above, and reviews
                      at {overview.review_threshold.toFixed(2)} and above. Amount at least 200,000, or
                      velocity in one hour at least 8, is checked first and forces at least review.
                    </p>
                  </div>
                </form>
                {result ? (
                  <div className={`result ${result.decision}`} role="status">
                    <div className="result-top">
                      <div>
                        <p className="eyebrow">Model score</p>
                        <p className="score-figure mono">{result.score.toFixed(3)}</p>
                      </div>
                      <div className="result-decisions">
                        <span className={`pill ${result.model_decision}`}>model {result.model_decision}</span>
                        <span className={`pill ${result.decision}`}>decision {result.decision}</span>
                      </div>
                    </div>
                    <p className="rule-line">
                      {result.rules_fired.length === 0
                        ? "No rule fired. The decision is the model cutoff only."
                        : `Rules: ${result.rules_fired.map((id) => ruleLabel(id)).join(" · ")}`}
                    </p>
                    {result.model_decision !== result.decision ? (
                      <p className="fine">
                        A rule raised this from {result.model_decision} to {result.decision}. The saved
                        model was not changed.
                      </p>
                    ) : null}
                    <ol className="reasons">
                      {result.explanation.map((reason) => (
                        <li key={reason.feature}>
                          <span>{featureLabel(reason.feature)}</span>
                          <span className="mono">
                            {formatFeature(reason.feature, reason.value)} vs{" "}
                            {formatFeature(reason.feature, reason.median)}
                          </span>
                          <em>{reason.direction === "above_median" ? "above typical" : reason.direction === "below_median" ? "below typical" : "at typical"}</em>
                        </li>
                      ))}
                    </ol>
                    <p className="fine">
                      Top reasons are feature importance times distance from the training median,
                      scaled by the training standard deviation. Not SHAP.
                    </p>
                    <p className="mono fine">
                      {result.transaction_id} · {result.replayed ? "replayed stored decision" : "new decision"} ·{" "}
                      {result.idempotency_key}
                    </p>
                    {lastSubmission ? (
                      <button
                        type="button"
                        className="ghost"
                        disabled={scoring}
                        onClick={() => void submit(lastSubmission.features, lastSubmission.key)}
                      >
                        Replay this key
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </section>

              <section className="panel metrics-panel">
                <p className="eyebrow">Holdout on synthetic data</p>
                <div className="metric-pair">
                  <div>
                    <b className="mono">{formatMetric(overview.recall)}</b>
                    <span>Recall</span>
                  </div>
                  <div>
                    <b className="mono">{formatMetric(overview.precision)}</b>
                    <span>Precision</span>
                  </div>
                </div>
                <p className="fine">
                  F1 {formatMetric(overview.f1)} · ROC AUC {formatMetric(overview.roc_auc)} · cutoff{" "}
                  {overview.metric_cutoff.toFixed(2)} · {overview.holdout_rows ?? "—"} holdout rows
                </p>
                <p className="fine">{overview.note}</p>
                <p className="fine">
                  Training fraud rate {formatRate(overview.training_fraud_rate)} on{" "}
                  {overview.training_rows ?? "—"} rows. Workspace counts are scored rows in this
                  database, including a demo seed with a higher fraud mix.
                </p>
                <figure>
                  <figcaption>Model score histogram</figcaption>
                  <div className="hist" role="list">
                    {overview.histogram.map((bucket) => {
                      const tone = toneFor(
                        (bucket.low + bucket.high) / 2,
                        overview.review_threshold,
                        overview.block_threshold,
                      );
                      return (
                        <div
                          key={bucket.low}
                          role="listitem"
                          className="hist-col"
                          aria-label={`${bucket.low.toFixed(1)} to ${bucket.high.toFixed(1)}: ${bucket.count}`}
                        >
                          <div className="hist-track">
                            <div
                              className={`hist-bar ${tone}`}
                              style={{ height: `${(bucket.count / maxCount) * 100}%` }}
                            />
                          </div>
                          <span className="mono">{bucket.low.toFixed(1)}</span>
                        </div>
                      );
                    })}
                  </div>
                </figure>
              </section>
            </div>

            <section id="ledger" className="panel">
              <div className="panel-head">
                <h2>Ledger</h2>
                <p className="fine">{rows.length} shown, newest first</p>
              </div>
              {rows.length === 0 ? (
                <p className="muted">No scored transactions yet.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Transaction</th>
                        <th>Amount</th>
                        <th>Model score</th>
                        <th>Rules</th>
                        <th>Decision</th>
                        <th>Label</th>
                        <th>Top reasons</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.transaction_id} className={row.decision}>
                          <td className="mono">{formatStamp(row.created_at)}</td>
                          <td className="mono">{row.transaction_id}</td>
                          <td className="mono">{row.amount.toFixed(2)}</td>
                          <td className="mono">{row.score.toFixed(3)}</td>
                          <td>
                            {row.rules_fired.length === 0
                              ? "—"
                              : row.rules_fired.map((id) => ruleLabel(id)).join(" · ")}
                          </td>
                          <td>
                            <span className={`pill ${row.decision}`}>{row.decision}</span>
                          </td>
                          <td
                            className="mono"
                            title="Synthetic generator label when the row was seeded. Analyst outcomes stay on the case."
                          >
                            {labelText(row.label)}
                          </td>
                          <td>{row.explanation.map((reason) => reasonLine(reason)).join(" · ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </main>
      )}
    </div>
  );
}
