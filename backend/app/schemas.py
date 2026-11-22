"""Request and response bodies."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.config import SCORE_AMOUNT_MAX


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str


class ScoreRequest(BaseModel):
    amount: float = Field(gt=0, le=SCORE_AMOUNT_MAX)
    hour: float = Field(ge=0, lt=24)
    country_risk: float = Field(ge=0, le=1)
    device_trust: float = Field(ge=0, le=1)
    velocity_1h: float = Field(ge=0, le=500)
    merchant_category: int = Field(ge=0, le=11)
    card_age_days: int = Field(ge=0, le=20_000)
    distance_from_home_km: float = Field(ge=0, le=20_000)
    is_international: Literal[0, 1]


class Reason(BaseModel):
    feature: str
    value: float
    median: float
    scale: float
    importance: float
    contribution: float
    direction: str


class TransactionOut(BaseModel):
    transaction_id: str
    amount: float
    hour: float
    country_risk: float
    device_trust: float
    velocity_1h: float
    merchant_category: int
    card_age_days: int
    distance_from_home_km: float
    is_international: int
    score: float
    decision: str
    model_decision: str
    rules_fired: list[str]
    label: int | None
    explanation: list[Reason]
    explanation_method: str
    idempotency_key: str
    created_at: str


class ScoreResponse(TransactionOut):
    replayed: bool


class HistogramBucket(BaseModel):
    low: float
    high: float
    count: int


class MerchantOut(BaseModel):
    code: int
    name: str


class CaseOut(BaseModel):
    case_id: str
    transaction_id: str
    status: str
    outcome: Literal["false_positive", "confirmed_fraud"] | None
    note: str
    analyst_email: str | None
    amount: float
    velocity_1h: float
    score: float
    model_decision: str
    decision: str
    rules_fired: list[str]
    created_at: str
    updated_at: str


class CaseUpdate(BaseModel):
    outcome: Literal["false_positive", "confirmed_fraud"]
    note: str = Field(min_length=1, max_length=2000)


class OverviewOut(BaseModel):
    total: int
    allow: int
    review: int
    block: int
    open_cases: int
    precision: float | None
    recall: float | None
    f1: float | None
    roc_auc: float | None
    training_rows: int | None
    training_fraud_rate: float | None
    holdout_rows: int | None
    metric_cutoff: float
    review_threshold: float
    block_threshold: float
    note: str
    histogram: list[HistogramBucket]
    merchant_categories: list[MerchantOut]


class HealthOut(BaseModel):
    status: str
    model_loaded: bool
