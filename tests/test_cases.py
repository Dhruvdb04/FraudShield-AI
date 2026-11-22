"""Rules raise a low model score to review, and a confirmed case stays stored."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from backend.app.config import DEMO_EMAIL, METRICS_PATH, REVIEW_THRESHOLD
from backend.app.db import Base, Case, User
from backend.app.main import app, list_cases, overview, score_transaction, update_case
from backend.app.schemas import CaseOut, CaseUpdate, ScoreRequest, ScoreResponse
from backend.app.scoring import apply_rule_floor, load_bundle, rules_fired, score_features, train_model
from backend.app.seed import seed_user


def test_rules_force_at_least_review() -> None:
    assert rules_fired({"amount": 199_999.99, "velocity_1h": 7.9}) == []
    assert apply_rule_floor("allow", []) == "allow"
    assert rules_fired({"amount": 200_000, "velocity_1h": 0}) == ["amount_gte_200000"]
    assert rules_fired({"amount": 10, "velocity_1h": 8}) == ["velocity_1h_gte_8"]
    assert rules_fired({"amount": 200_000, "velocity_1h": 9}) == [
        "amount_gte_200000",
        "velocity_1h_gte_8",
    ]
    assert apply_rule_floor("allow", ["velocity_1h_gte_8"]) == "review"
    assert apply_rule_floor("review", ["velocity_1h_gte_8"]) == "review"
    assert apply_rule_floor("block", ["amount_gte_200000"]) == "block"
    accepted = ScoreRequest(
        amount=200_000,
        hour=13,
        country_risk=0.08,
        device_trust=0.92,
        velocity_1h=9,
        merchant_category=0,
        card_age_days=900,
        distance_from_home_km=4,
        is_international=0,
    )
    assert accepted.amount == 200_000
    with pytest.raises(ValidationError):
        ScoreRequest(
            amount=1_000_000.01,
            hour=13,
            country_risk=0.08,
            device_trust=0.92,
            velocity_1h=0,
            merchant_category=0,
            card_age_days=900,
            distance_from_home_km=4,
            is_international=0,
        )


def _request() -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/score",
        "raw_path": b"/api/score",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
        "app": app,
    }
    return Request(scope)


def test_velocity_rule_forces_review_and_confirmed_case_persists(tmp_path) -> None:
    metrics_before = METRICS_PATH.read_text(encoding="utf-8") if METRICS_PATH.exists() else None
    train_model(
        n_rows=1000,
        seed=42,
        fraud_rate=0.08,
        n_estimators=80,
        model_path=tmp_path / "fraud_model.joblib",
        metrics_path=tmp_path / "metrics.json",
        csv_path=tmp_path / "synthetic_transactions.csv",
    )
    if metrics_before is not None:
        assert METRICS_PATH.read_text(encoding="utf-8") == metrics_before

    bundle = load_bundle(tmp_path / "fraud_model.joblib")
    features = {
        "amount": 24.5,
        "hour": 13.0,
        "country_risk": 0.08,
        "device_trust": 0.92,
        "velocity_1h": 9.0,
        "merchant_category": 0,
        "card_age_days": 900,
        "distance_from_home_km": 4.0,
        "is_international": 0,
    }
    scored = score_features(bundle, features)
    assert features["velocity_1h"] == 9.0
    assert math.isfinite(scored.score)
    assert scored.score < REVIEW_THRESHOLD
    assert scored.model_decision == "allow"
    assert scored.rules_fired == ["velocity_1h_gte_8"]
    assert scored.decision == "review"

    engine = create_engine(
        "sqlite:///" + (tmp_path / "cases.db").resolve().as_posix(),
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    app.state.bundle = bundle
    try:
        seed_user(db)
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        assert user is not None
        body = ScoreRequest(**features)
        payload = score_transaction(body, _request(), db, user, "velocity-rule-9")
        stored = ScoreResponse.model_validate(payload)
        assert stored.replayed is False
        assert stored.score < REVIEW_THRESHOLD
        assert stored.model_decision == "allow"
        assert stored.rules_fired == ["velocity_1h_gte_8"]
        assert stored.decision == "review"

        desk = overview(db, user)
        assert desk["open_cases"] == 1
        queued = list_cases(db, user)
        assert len(queued) == 1
        opened = CaseOut.model_validate(queued[0])
        assert opened.transaction_id == stored.transaction_id
        assert opened.status == "open"
        assert opened.outcome is None
        assert opened.rules_fired == ["velocity_1h_gte_8"]
        assert opened.score < REVIEW_THRESHOLD

        note = "Synthetic row reviewed on the queue."
        updated = update_case(
            opened.case_id,
            CaseUpdate(outcome="confirmed_fraud", note=note),
            db,
            user,
        )
        closed = CaseOut.model_validate(updated)
        assert closed.status == "closed"
        assert closed.outcome == "confirmed_fraud"
        assert closed.note == note
        assert closed.analyst_email == DEMO_EMAIL
        assert overview(db, user)["open_cases"] == 0
        case_id = opened.case_id
    finally:
        db.close()
        app.state.bundle = None

    check = Session()
    try:
        saved = check.scalar(select(Case).where(Case.case_id == case_id))
        assert saved is not None
        assert saved.status == "closed"
        assert saved.outcome == "confirmed_fraud"
        assert saved.note == note
        assert saved.analyst_email == DEMO_EMAIL
        analyst = check.scalar(select(User).where(User.email == DEMO_EMAIL))
        assert analyst is not None
        again = list_cases(check, analyst)
        match = next(item for item in again if item["case_id"] == case_id)
        assert match["outcome"] == "confirmed_fraud"
        assert match["note"] == note
        assert match["status"] == "closed"
    finally:
        check.close()
