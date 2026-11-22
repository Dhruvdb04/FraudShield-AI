import { useCallback, useEffect, useState } from "react";
import { ApiError, getCases, updateCase } from "./api";
import { formatStamp, outcomeLabel, ruleLabel } from "./format";
import type { CaseOutcome, CaseRecord } from "./types";

type CaseQueueProps = {
  onLogout: () => void;
};

export function CaseQueue({ onLogout }: CaseQueueProps) {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [showClosed, setShowClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const next = await getCases();
    setCases(next);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const next = await getCases();
        if (!alive) return;
        setCases(next);
      } catch (err) {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 401) {
          onLogout();
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load cases");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [onLogout]);

  const openCount = cases.filter((item) => item.status === "open").length;
  const visible = showClosed ? cases : cases.filter((item) => item.status === "open");

  async function save(item: CaseRecord, outcome: CaseOutcome, note: string) {
    setError(null);
    try {
      const saved = await updateCase(item.case_id, outcome, note);
      setCases((current) => current.map((row) => (row.case_id === saved.case_id ? saved : row)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "Could not store the outcome");
      await load().catch(() => undefined);
    }
  }

  return (
    <main className="desk">
      <header className="page-head">
        <div>
          <p className="eyebrow">Case queue</p>
          <h1>Open cases</h1>
        </div>
        <p className="lede">
          Review and block scores open a case. A false positive or confirmed fraud label is stored
          here. The gradient boosting model is not retrained on those labels.
        </p>
      </header>
      {error ? (
        <p className="banner" role="alert">
          {error}
        </p>
      ) : null}
      <div className="panel-head">
        <p className="fine mono">
          {loading ? "Loading cases…" : `${openCount} open · ${cases.length} stored`}
        </p>
        <button
          type="button"
          className="ghost"
          aria-pressed={showClosed}
          onClick={() => setShowClosed((current) => !current)}
        >
          {showClosed ? "Hide closed" : "Show closed"}
        </button>
      </div>
      {loading ? null : visible.length === 0 ? (
        <section className="panel">
          <p className="muted">
            {cases.length === 0
              ? "No cases yet. A review or block score opens one."
              : "No open cases. Closed labels stay stored and are not used to retrain the model."}
          </p>
        </section>
      ) : (
        <div className="case-list">
          {visible.map((item) => (
            <CaseCard key={item.case_id} item={item} onSave={save} />
          ))}
        </div>
      )}
    </main>
  );
}

type CaseCardProps = {
  item: CaseRecord;
  onSave: (item: CaseRecord, outcome: CaseOutcome, note: string) => Promise<void>;
};

function CaseCard({ item, onSave }: CaseCardProps) {
  const [note, setNote] = useState(item.note);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const closed = item.status === "closed";

  async function saveOutcome(outcome: CaseOutcome) {
    const cleaned = note.trim();
    if (!cleaned) {
      setLocalError("Add a note before setting an outcome.");
      return;
    }
    setBusy(true);
    setLocalError(null);
    try {
      await onSave(item, outcome, cleaned);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`panel case-card ${item.decision}`}>
      <div className="case-top">
        <div>
          <p className="eyebrow">{formatStamp(item.created_at)}</p>
          <h2 className="mono">{item.case_id}</h2>
        </div>
        <span className={`pill ${closed ? item.outcome ?? "open" : "open"}`}>
          {closed ? outcomeLabel(item.outcome) : "Open"}
        </span>
      </div>
      <div className="case-facts">
        <span className="mono">{item.transaction_id}</span>
        <span className="mono">{item.amount.toFixed(2)}</span>
        <span>
          Model score <b className="mono">{item.score.toFixed(3)}</b>
        </span>
        <span className={`pill ${item.model_decision}`}>model {item.model_decision}</span>
        <span className={`pill ${item.decision}`}>{item.decision}</span>
      </div>
      <p className="rule-line">
        {item.rules_fired.length === 0
          ? "No rule fired"
          : item.rules_fired.map((id) => ruleLabel(id)).join(" · ")}
      </p>
      {closed ? (
        <div className="case-note">
          <p>{item.note}</p>
          <p className="fine">
            {item.analyst_email ? `Stored by ${item.analyst_email}` : "Stored on the case"}. Not used
            to retrain the model.
          </p>
        </div>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void saveOutcome("confirmed_fraud");
          }}
        >
          <label htmlFor={`note-${item.case_id}`}>
            Note
            <textarea
              id={`note-${item.case_id}`}
              value={note}
              maxLength={2000}
              onChange={(event) => setNote(event.target.value)}
              placeholder="What you saw in this synthetic row"
            />
          </label>
          {localError ? (
            <p className="banner" role="alert">
              {localError}
            </p>
          ) : null}
          <div className="case-actions">
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() => void saveOutcome("false_positive")}
            >
              False positive
            </button>
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={() => void saveOutcome("confirmed_fraud")}
            >
              Confirmed fraud
            </button>
          </div>
        </form>
      )}
    </article>
  );
}
