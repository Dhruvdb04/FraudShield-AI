"""Analyst cases opened by review and block decisions.

Outcomes stay on the case. Nothing here refits the saved model.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import Case, Transaction
from backend.app.synthetic import FEATURE_NAMES, stored_feature

OPEN = "open"
CLOSED = "closed"
OUTCOMES = frozenset({"false_positive", "confirmed_fraud"})
DECISIONS_THAT_OPEN = frozenset({"review", "block"})


def new_case(transaction_id: str, created_at: datetime) -> Case:
    return Case(
        case_id="case_" + uuid.uuid4().hex[:16],
        transaction_id=transaction_id,
        status=OPEN,
        outcome=None,
        note="",
        analyst_email=None,
        created_at=created_at,
        updated_at=created_at,
    )


def close_case(case: Case, outcome: str, note: str, analyst_email: str, now: datetime | None = None) -> None:
    if outcome not in OUTCOMES:
        raise ValueError("outcome must be false_positive or confirmed_fraud")
    cleaned = note.strip()
    if not cleaned:
        raise ValueError("A note is required")
    if len(cleaned) > 2000:
        raise ValueError("Note must be 2000 characters or fewer")
    when = now or datetime.now(timezone.utc)
    case.outcome = outcome
    case.note = cleaned
    case.status = CLOSED
    case.analyst_email = analyst_email
    case.updated_at = when


def build_scored_row(
    *,
    transaction_id: str,
    features: dict[str, float],
    score: float,
    decision: str,
    model_decision: str,
    rules_fired: list[str],
    explanation: list[dict[str, Any]],
    explanation_method: str,
    label: int | None,
    idempotency_key: str,
    created_at: datetime,
) -> tuple[Transaction, Case | None]:
    stored = {name: stored_feature(name, features[name]) for name in FEATURE_NAMES}
    payload = {"method": explanation_method, "reasons": explanation}
    row = Transaction(
        transaction_id=transaction_id,
        amount=float(stored["amount"]),
        hour=float(stored["hour"]),
        country_risk=float(stored["country_risk"]),
        device_trust=float(stored["device_trust"]),
        velocity_1h=float(stored["velocity_1h"]),
        merchant_category=int(stored["merchant_category"]),
        card_age_days=int(stored["card_age_days"]),
        distance_from_home_km=float(stored["distance_from_home_km"]),
        is_international=int(stored["is_international"]),
        score=score,
        decision=decision,
        model_decision=model_decision,
        rules_json=json.dumps(list(rules_fired), separators=(",", ":")),
        label=label,
        explanation_json=json.dumps(payload, separators=(",", ":")),
        idempotency_key=idempotency_key,
        created_at=created_at,
    )
    case = new_case(transaction_id, created_at) if decision in DECISIONS_THAT_OPEN else None
    return row, case


def backfill_model_fields(db: Session) -> None:
    """Fill rule columns on rows scored before those columns existed.

    The model decision is the cutoff on the stored probability. Rules were not
    applied to those older rows, so the rule list stays empty.
    """
    from backend.app.scoring import decide

    rows = db.scalars(
        select(Transaction).where(
            (Transaction.model_decision.is_(None)) | (Transaction.rules_json.is_(None))
        )
    ).all()
    changed = False
    for row in rows:
        if row.model_decision not in {"allow", "review", "block"}:
            row.model_decision = decide(float(row.score))
            changed = True
        if not row.rules_json:
            row.rules_json = "[]"
            changed = True
    if changed:
        db.commit()


def ensure_open_cases(db: Session) -> None:
    """Open a case for every review or block row that does not have one yet."""
    linked = set(db.scalars(select(Case.transaction_id)).all())
    pending = db.scalars(
        select(Transaction).where(Transaction.decision.in_(tuple(DECISIONS_THAT_OPEN)))
    ).all()
    created = False
    for row in pending:
        if row.transaction_id in linked:
            continue
        db.add(new_case(row.transaction_id, row.created_at))
        created = True
    if created:
        db.commit()
