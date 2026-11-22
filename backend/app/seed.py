"""Seed the local analyst and a small scored ledger."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.cases import build_scored_row
from backend.app.config import DEMO_EMAIL, DEMO_PASSWORD
from backend.app.db import Case, Transaction, User
from backend.app.scoring import score_features
from backend.app.security import hash_password
from backend.app.synthetic import FEATURE_NAMES, generate_synthetic

logger = logging.getLogger("fraudshield")


def seed_user(db: Session) -> None:
    existing = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if existing is not None:
        return
    db.add(
        User(
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    logger.info("Seeded local analyst %s", DEMO_EMAIL)


def seed_transactions(db: Session, bundle: dict, n_rows: int = 40) -> None:
    existing = db.scalar(select(func.count()).select_from(Transaction))
    if existing:
        return
    frame = generate_synthetic(n_rows=n_rows, seed=7, fraud_rate=0.25)
    ages = np.random.default_rng(7).integers(3, 36 * 60, size=n_rows)
    now = datetime.now(timezone.utc)
    rows: list[Transaction] = []
    cases: list[Case] = []
    for index in range(n_rows):
        source = frame.iloc[index]
        features = {name: float(source[name]) for name in FEATURE_NAMES}
        scored = score_features(bundle, features)
        created_at = now - timedelta(minutes=int(ages[index]), seconds=index)
        row, case = build_scored_row(
            transaction_id=f"txn_seed_{index:04d}",
            features=features,
            score=scored.score,
            decision=scored.decision,
            model_decision=scored.model_decision,
            rules_fired=scored.rules_fired,
            explanation=scored.explanation,
            explanation_method=str(bundle["explanation_method"]),
            label=int(source["label"]),
            idempotency_key=f"seed-{index:03d}",
            created_at=created_at,
        )
        rows.append(row)
        if case is not None:
            cases.append(case)
    try:
        db.add_all(rows)
        db.flush()
        db.add_all(cases)
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("Seeded %s scored transactions", n_rows)
