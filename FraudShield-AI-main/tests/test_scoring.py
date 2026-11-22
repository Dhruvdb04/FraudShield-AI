"""Train a tiny synthetic set and check the measured holdout recall."""

from __future__ import annotations

import math

from backend.app.scoring import decide, load_bundle, score_features, train_model


def test_decision_thresholds() -> None:
    assert decide(0.75) == "block"
    assert decide(0.749) == "review"
    assert decide(0.45) == "review"
    assert decide(0.449) == "allow"
    assert decide(0.0) == "allow"
    assert decide(1.0) == "block"


def test_holdout_recall_and_score_separation(tmp_path) -> None:
    n_rows = 1000
    metrics = train_model(
        n_rows=n_rows,
        seed=42,
        fraud_rate=0.08,
        n_estimators=80,
        model_path=tmp_path / "fraud_model.joblib",
        metrics_path=tmp_path / "metrics.json",
        csv_path=tmp_path / "synthetic_transactions.csv",
    )
    written = (tmp_path / "metrics.json").read_text(encoding="utf-8")
    assert '"recall"' in written

    recall = metrics["recall"]
    assert isinstance(recall, float)
    assert math.isfinite(recall)
    assert 0.0 <= recall <= 1.0
    for key in ("precision", "f1", "roc_auc"):
        value = metrics[key]
        assert isinstance(value, float)
        assert math.isfinite(value)
        assert 0.0 <= value <= 1.0
    assert metrics["holdout_rows"] + metrics["train_rows"] == n_rows
    assert abs((metrics["holdout_rows"] / n_rows) - 0.2) < 0.02
    assert abs(metrics["fraud_rate"] - 0.08) < 1e-9

    bundle = load_bundle(tmp_path / "fraud_model.joblib")
    extreme = {
        "amount": 4200.0,
        "hour": 2.0,
        "country_risk": 0.95,
        "device_trust": 0.05,
        "velocity_1h": 14.0,
        "merchant_category": 6,
        "card_age_days": 3,
        "distance_from_home_km": 3500.0,
        "is_international": 1,
    }
    plain = {
        "amount": 24.5,
        "hour": 13.0,
        "country_risk": 0.08,
        "device_trust": 0.92,
        "velocity_1h": 0.0,
        "merchant_category": 0,
        "card_age_days": 900,
        "distance_from_home_km": 4.0,
        "is_international": 0,
    }
    extreme_score = score_features(bundle, extreme)
    plain_score = score_features(bundle, plain)
    assert math.isfinite(extreme_score.score)
    assert math.isfinite(plain_score.score)
    assert extreme_score.score > plain_score.score, (extreme_score.score, plain_score.score)
