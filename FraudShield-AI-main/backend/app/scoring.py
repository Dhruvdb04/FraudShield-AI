"""Train, persist, and score the synthetic fraud model."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from backend.app.config import (
    BLOCK_THRESHOLD,
    CSV_PATH,
    EXPLANATION_METHOD,
    FRAUD_RATE,
    METRIC_CUTOFF,
    METRICS_PATH,
    MODEL_PATH,
    N_ESTIMATORS,
    REVIEW_THRESHOLD,
    RULE_AMOUNT_MIN,
    RULE_VELOCITY_MIN,
    TRAIN_ROWS,
    TRAIN_SEED,
    ensure_dirs,
)
from backend.app.synthetic import FEATURE_NAMES, generate_synthetic

logger = logging.getLogger("fraudshield")


RULE_AMOUNT = "amount_gte_200000"
RULE_VELOCITY = "velocity_1h_gte_8"


@dataclass(frozen=True)
class Scored:
    score: float
    decision: str
    explanation: list[dict[str, float | str]]
    model_decision: str
    rules_fired: list[str]


def decide(score: float, *, review: float = REVIEW_THRESHOLD, block: float = BLOCK_THRESHOLD) -> str:
    if score >= block:
        return "block"
    if score >= review:
        return "review"
    return "allow"


def _fraud_index(pipeline: Pipeline) -> int:
    classes = [int(label) for label in pipeline.named_steps["clf"].classes_]
    if 1 not in classes:
        raise RuntimeError("The trained model has no fraud class")
    return classes.index(1)


def fraud_probability(pipeline: Pipeline, rows: np.ndarray) -> np.ndarray:
    index = _fraud_index(pipeline)
    return pipeline.predict_proba(rows)[:, index]


def train_model(
    *,
    n_rows: int = TRAIN_ROWS,
    seed: int = TRAIN_SEED,
    fraud_rate: float = FRAUD_RATE,
    n_estimators: int = N_ESTIMATORS,
    model_path: Path | None = None,
    metrics_path: Path | None = None,
    csv_path: Path | None = None,
) -> dict[str, Any]:
    """Fit on a stratified 80% split and write holdout metrics for that same model."""
    ensure_dirs()
    model_path = model_path or MODEL_PATH
    metrics_path = metrics_path or METRICS_PATH
    csv_path = csv_path or CSV_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    frame = generate_synthetic(n_rows=n_rows, seed=seed, fraud_rate=fraud_rate)
    frame.to_csv(csv_path, index=False, lineterminator="\n")

    x_values = frame.loc[:, list(FEATURE_NAMES)].to_numpy(dtype=np.float64)
    y_values = frame["label"].to_numpy(dtype=np.int64)
    if len(np.unique(y_values)) < 2:
        raise RuntimeError("Synthetic data must contain both classes")

    x_train, x_test, y_train, y_test = train_test_split(
        x_values,
        y_values,
        test_size=0.2,
        random_state=seed,
        stratify=y_values,
    )

    n_pos = int((y_train == 1).sum())
    n_neg = int((y_train == 0).sum())
    if n_pos == 0 or n_neg == 0:
        raise RuntimeError("Training split is missing a class")
    # Weights apply only to the fit. Holdout metrics stay on the natural mix.
    pos_weight = n_neg / n_pos
    sample_weight = np.where(y_train == 1, pos_weight, 1.0)

    pipeline = Pipeline(
        steps=[
            (
                "clf",
                GradientBoostingClassifier(
                    n_estimators=n_estimators,
                    learning_rate=0.08,
                    max_depth=3,
                    subsample=0.9,
                    min_samples_leaf=4,
                    random_state=seed,
                ),
            )
        ]
    )
    pipeline.fit(x_train, y_train, clf__sample_weight=sample_weight)

    probabilities = fraud_probability(pipeline, x_test)
    predicted = (probabilities >= METRIC_CUTOFF).astype(np.int64)
    metrics: dict[str, Any] = {
        "precision": float(precision_score(y_test, predicted, pos_label=1, zero_division=0)),
        "recall": float(recall_score(y_test, predicted, pos_label=1, zero_division=0)),
        "f1": float(f1_score(y_test, predicted, pos_label=1, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, probabilities)),
        "positive_class": "fraud",
        "label_value": 1,
        "metric_cutoff": METRIC_CUTOFF,
        "review_threshold": REVIEW_THRESHOLD,
        "block_threshold": BLOCK_THRESHOLD,
        "rows": int(n_rows),
        "fraud_rows": int(y_values.sum()),
        "fraud_rate": float(y_values.mean()),
        "train_rows": int(len(y_train)),
        "holdout_rows": int(len(y_test)),
        "holdout_fraud": int((y_test == 1).sum()),
        "holdout_legit": int((y_test == 0).sum()),
        "seed": int(seed),
        "model": "GradientBoostingClassifier",
        "n_estimators": int(n_estimators),
        "positive_sample_weight": float(pos_weight),
        "imbalance_strategy": "sample_weight on the training split only; holdout metrics are unweighted",
        "fit_on": "stratified 80 percent; the persisted pipeline is not refit on the holdout",
        "explanation": EXPLANATION_METHOD,
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
    }
    for key in ("precision", "recall", "f1", "roc_auc"):
        if not np.isfinite(metrics[key]):
            raise RuntimeError(f"Training produced a non-finite {key}")

    medians: dict[str, float] = {}
    scales: dict[str, float] = {}
    for index, name in enumerate(FEATURE_NAMES):
        column = x_train[:, index]
        medians[name] = float(np.median(column))
        scale = float(np.std(column))
        scales[name] = scale if scale >= 1e-6 else 1.0

    bundle = {
        "pipeline": pipeline,
        "feature_names": list(FEATURE_NAMES),
        "medians": medians,
        "scales": scales,
        "review_threshold": REVIEW_THRESHOLD,
        "block_threshold": BLOCK_THRESHOLD,
        "explanation_method": EXPLANATION_METHOD,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    joblib.dump(bundle, model_path)
    logger.info(
        "trained rows=%s holdout recall=%.4f precision=%.4f f1=%.4f roc_auc=%.4f",
        n_rows,
        metrics["recall"],
        metrics["precision"],
        metrics["f1"],
        metrics["roc_auc"],
    )
    return metrics


def load_bundle(path: Path | None = None) -> dict[str, Any]:
    bundle = joblib.load(path or MODEL_PATH)
    if not isinstance(bundle, dict) or "pipeline" not in bundle or "feature_names" not in bundle:
        raise RuntimeError("Model file is missing the scoring pipeline")
    return bundle


def read_metrics(path: Path | None = None) -> dict[str, Any]:
    metrics_path = path or METRICS_PATH
    if not metrics_path.exists():
        raise FileNotFoundError(metrics_path)
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("metrics.json must be an object")
    return data


def explain(bundle: dict[str, Any], features: dict[str, float]) -> list[dict[str, float | str]]:
    """Rank features by importance times scaled distance from the training median.

    This is not a SHAP value. The scale is the training-split standard deviation
    so a large-range feature such as amount does not crowd out a 0-1 feature.
    """
    pipeline: Pipeline = bundle["pipeline"]
    importances = pipeline.named_steps["clf"].feature_importances_
    names: list[str] = list(bundle["feature_names"])
    medians: dict[str, float] = bundle["medians"]
    scales: dict[str, float] = bundle["scales"]
    ranked: list[dict[str, float | str]] = []
    for index, name in enumerate(names):
        value = float(features[name])
        median = float(medians[name])
        scale = float(scales[name]) or 1.0
        contribution = float(importances[index]) * (abs(value - median) / scale)
        if value > median:
            direction = "above_median"
        elif value < median:
            direction = "below_median"
        else:
            direction = "at_median"
        ranked.append(
            {
                "feature": name,
                "value": value,
                "median": median,
                "scale": scale,
                "importance": float(importances[index]),
                "contribution": contribution,
                "direction": direction,
            }
        )
    ranked.sort(key=lambda item: (-float(item["contribution"]), str(item["feature"])))
    return ranked[:3]


def rules_fired(features: dict[str, float]) -> list[str]:
    """Product rules. Evaluated before the saved model is asked for a probability."""
    fired: list[str] = []
    if float(features["amount"]) >= RULE_AMOUNT_MIN:
        fired.append(RULE_AMOUNT)
    if float(features["velocity_1h"]) >= RULE_VELOCITY_MIN:
        fired.append(RULE_VELOCITY)
    return fired


def apply_rule_floor(model_decision: str, fired: list[str]) -> str:
    """A fired rule forces at least review. A model block stays a block."""
    if fired and model_decision == "allow":
        return "review"
    return model_decision


def parse_rules(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def score_features(bundle: dict[str, Any], features: dict[str, float]) -> Scored:
    names: list[str] = list(bundle["feature_names"])
    missing = [name for name in names if name not in features]
    if missing:
        raise KeyError("Missing features: " + ", ".join(missing))
    fired = rules_fired(features)
    row = np.array([[float(features[name]) for name in names]], dtype=np.float64)
    probability = float(fraud_probability(bundle["pipeline"], row)[0])
    score = float(np.clip(probability, 0.0, 1.0))
    model_decision = decide(score)
    return Scored(
        score=score,
        decision=apply_rule_floor(model_decision, fired),
        explanation=explain(bundle, features),
        model_decision=model_decision,
        rules_fired=fired,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(json.dumps(train_model(), indent=2))


if __name__ == "__main__":
    main()
