"""FraudShield HTTP API."""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.cases import backfill_model_fields, build_scored_row, close_case, ensure_open_cases
from backend.app.config import (
    BLOCK_THRESHOLD,
    METRIC_CUTOFF,
    MODEL_PATH,
    RATE_LIMIT,
    RATE_WINDOW_SECONDS,
    REVIEW_THRESHOLD,
    ensure_dirs,
)
from backend.app.db import Case, SessionLocal, Transaction, User, get_db, init_db
from backend.app.deps import get_current_user
from backend.app.limiter import RateLimiter
from backend.app.schemas import (
    CaseOut,
    CaseUpdate,
    HealthOut,
    LoginRequest,
    LoginResponse,
    OverviewOut,
    ScoreRequest,
    ScoreResponse,
    TransactionOut,
)
from backend.app.scoring import decide, load_bundle, parse_rules, read_metrics, score_features, train_model
from backend.app.security import create_token, verify_password
from backend.app.seed import seed_transactions, seed_user
from backend.app.synthetic import FEATURE_NAMES, INTEGER_FEATURES, MERCHANT_CATEGORIES

logger = logging.getLogger("fraudshield")
limiter = RateLimiter(RATE_LIMIT, RATE_WINDOW_SECONDS)

HOLDOUT_NOTE = (
    "Holdout on synthetic data. Precision, recall, and F1 use a 0.5 probability "
    "cutoff on the stratified 20% the saved model did not train on."
)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_explanation(raw: str) -> tuple[str, list[dict[str, Any]]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return "unavailable", []
    if isinstance(payload, list):
        return "unavailable", payload
    if isinstance(payload, dict):
        reasons = payload.get("reasons", [])
        method = payload.get("method", "unavailable")
        if isinstance(reasons, list) and isinstance(method, str):
            return method, reasons
    return "unavailable", []


def dump_transaction(row: Transaction, *, replayed: bool | None = None) -> dict[str, Any]:
    method, reasons = _parse_explanation(row.explanation_json)
    payload: dict[str, Any] = {
        "transaction_id": row.transaction_id,
        "amount": float(row.amount),
        "hour": float(row.hour),
        "country_risk": float(row.country_risk),
        "device_trust": float(row.device_trust),
        "velocity_1h": float(row.velocity_1h),
        "merchant_category": int(row.merchant_category),
        "card_age_days": int(row.card_age_days),
        "distance_from_home_km": float(row.distance_from_home_km),
        "is_international": int(row.is_international),
        "score": float(row.score),
        "decision": row.decision,
        "model_decision": _model_decision(row),
        "rules_fired": parse_rules(row.rules_json),
        "label": None if row.label is None else int(row.label),
        "explanation": reasons,
        "explanation_method": method,
        "idempotency_key": row.idempotency_key,
        "created_at": _iso(row.created_at),
    }
    if replayed is not None:
        payload["replayed"] = replayed
    return payload


def _model_decision(row: Transaction) -> str:
    if row.model_decision in {"allow", "review", "block"}:
        return str(row.model_decision)
    return decide(float(row.score))


def dump_case(case: Case, row: Transaction) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "transaction_id": case.transaction_id,
        "status": case.status,
        "outcome": case.outcome,
        "note": case.note or "",
        "analyst_email": case.analyst_email,
        "amount": float(row.amount),
        "velocity_1h": float(row.velocity_1h),
        "score": float(row.score),
        "model_decision": _model_decision(row),
        "decision": row.decision,
        "rules_fired": parse_rules(row.rules_json),
        "created_at": _iso(case.created_at),
        "updated_at": _iso(case.updated_at),
    }


def _same_features(row: Transaction, features: dict[str, float]) -> bool:
    for name in FEATURE_NAMES:
        incoming = stored_feature(name, features[name])
        current = getattr(row, name)
        if name in INTEGER_FEATURES:
            if int(current) != int(incoming):
                return False
        elif abs(float(current) - float(incoming)) > 1e-5:
            return False
    return True


def _histogram(scores: list[float]) -> list[dict[str, float | int]]:
    counts = [0] * 10
    for score in scores:
        if score >= 1:
            index = 9
        elif score <= 0:
            index = 0
        else:
            index = min(9, int(score * 10))
        counts[index] += 1
    return [
        {"low": index / 10, "high": (index + 1) / 10, "count": count}
        for index, count in enumerate(counts)
    ]


def _optional_float(data: dict[str, Any] | None, key: str) -> float | None:
    if not data or data.get(key) is None:
        return None
    value = float(data[key])
    if not math.isfinite(value):
        return None
    return value


def _optional_int(data: dict[str, Any] | None, key: str) -> int | None:
    if not data or data.get(key) is None:
        return None
    return int(data[key])


def _clean_key(raw: str) -> str:
    key = raw.strip()
    if not key or len(key) > 128 or any(ord(char) < 32 for char in key):
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 1-128 printable characters")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_dirs()
    init_db()
    if not MODEL_PATH.exists():
        logger.info("No model on disk; training on synthetic data")
        train_model()
    bundle = load_bundle(MODEL_PATH)
    app.state.bundle = bundle
    db = SessionLocal()
    try:
        seed_user(db)
        seed_transactions(db, bundle)
        backfill_model_fields(db)
        ensure_open_cases(db)
    finally:
        db.close()
    yield
    app.state.bundle = None


app = FastAPI(title="FraudShield AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175", "http://127.0.0.1:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthOut, tags=["catalog"])
def health(request: Request) -> HealthOut:
    loaded = getattr(request.app.state, "bundle", None) is not None
    return HealthOut(status="ok", model_loaded=loaded)


@app.post("/api/auth/login", response_model=LoginResponse, tags=["auth"])
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> LoginResponse:
    email = body.email.strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return LoginResponse(access_token=create_token(user.email), email=user.email)


@app.post("/api/score", response_model=ScoreResponse, tags=["scoring"])
def score_transaction(
    body: ScoreRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, Any]:
    key = _clean_key(idempotency_key)
    if not limiter.allow(user.email, time.monotonic()):
        raise HTTPException(status_code=429, detail="Rate limit of 60 requests per minute exceeded")

    bundle = getattr(request.app.state, "bundle", None)
    if bundle is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")

    features = {name: float(getattr(body, name)) for name in FEATURE_NAMES}
    existing = db.scalar(select(Transaction).where(Transaction.idempotency_key == key))
    if existing is not None:
        if not _same_features(existing, features):
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used with a different transaction",
            )
        return dump_transaction(existing, replayed=True)

    scored = score_features(bundle, features)
    if scored.decision not in {"allow", "review", "block"}:
        raise HTTPException(status_code=500, detail="Model returned an unknown decision")
    created_at = datetime.now(timezone.utc)
    row, case = build_scored_row(
        transaction_id="txn_" + uuid.uuid4().hex[:16],
        features=features,
        score=scored.score,
        decision=scored.decision,
        model_decision=scored.model_decision,
        rules_fired=scored.rules_fired,
        explanation=scored.explanation,
        explanation_method=str(bundle["explanation_method"]),
        label=None,
        idempotency_key=key,
        created_at=created_at,
    )
    try:
        db.add(row)
        db.flush()
        if case is not None:
            db.add(case)
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(select(Transaction).where(Transaction.idempotency_key == key))
        if winner is None:
            raise
        if not _same_features(winner, features):
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used with a different transaction",
            ) from None
        return dump_transaction(winner, replayed=True)
    return dump_transaction(row, replayed=False)


@app.get("/api/transactions", response_model=list[TransactionOut], tags=["scoring"])
def list_transactions(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    stmt = (
        select(Transaction)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [dump_transaction(row) for row in db.scalars(stmt).all()]


@app.get("/api/cases", response_model=list[CaseOut], tags=["cases"])
def list_cases(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    if status is not None and status not in {"open", "closed"}:
        raise HTTPException(status_code=400, detail="status must be open or closed")
    stmt = (
        select(Case, Transaction)
        .join(Transaction, Transaction.transaction_id == Case.transaction_id)
        .order_by(Case.created_at.desc(), Case.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Case.status == status)
    return [dump_case(case, row) for case, row in db.execute(stmt).all()]


@app.patch("/api/cases/{case_id}", response_model=CaseOut, tags=["cases"])
def update_case(
    case_id: str,
    body: CaseUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    case = db.scalar(select(Case).where(Case.case_id == case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    row = db.scalar(select(Transaction).where(Transaction.transaction_id == case.transaction_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        close_case(case, body.outcome, body.note, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    db.commit()
    return dump_case(case, row)


@app.get("/api/overview", response_model=OverviewOut, tags=["catalog"])
def overview(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    grouped = db.execute(select(Transaction.decision, func.count()).group_by(Transaction.decision)).all()
    counts = {"allow": 0, "review": 0, "block": 0}
    total = 0
    for decision, count in grouped:
        total += int(count)
        if decision in counts:
            counts[str(decision)] = int(count)
    scores = [float(value) for value in db.scalars(select(Transaction.score)).all()]
    try:
        metrics = read_metrics()
    except FileNotFoundError:
        metrics = None
    return {
        "total": total,
        "allow": counts["allow"],
        "review": counts["review"],
        "block": counts["block"],
        "open_cases": int(
            db.scalar(select(func.count()).select_from(Case).where(Case.status == "open")) or 0
        ),
        "precision": _optional_float(metrics, "precision"),
        "recall": _optional_float(metrics, "recall"),
        "f1": _optional_float(metrics, "f1"),
        "roc_auc": _optional_float(metrics, "roc_auc"),
        "training_rows": _optional_int(metrics, "rows"),
        "training_fraud_rate": _optional_float(metrics, "fraud_rate"),
        "holdout_rows": _optional_int(metrics, "holdout_rows"),
        "metric_cutoff": METRIC_CUTOFF,
        "review_threshold": REVIEW_THRESHOLD,
        "block_threshold": BLOCK_THRESHOLD,
        "note": HOLDOUT_NOTE,
        "histogram": _histogram(scores),
        "merchant_categories": MERCHANT_CATEGORIES,
    }


@app.get("/api/metrics", tags=["catalog"])
def metrics(_: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    try:
        return read_metrics()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="metrics.json not found") from None
