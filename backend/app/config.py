"""Paths, thresholds, and local-only settings."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"

DB_PATH = DATA_DIR / "fraudshield.db"
CSV_PATH = DATA_DIR / "synthetic_transactions.csv"
MODEL_PATH = MODEL_DIR / "fraud_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"

REVIEW_THRESHOLD = 0.45
BLOCK_THRESHOLD = 0.75
METRIC_CUTOFF = 0.5

# Product rules. They are not features of the saved pipeline.
RULE_AMOUNT_MIN = 200_000.0
RULE_VELOCITY_MIN = 8.0
# Training rows stay clipped at 100_000. Scoring accepts more so the amount rule can fire.
SCORE_AMOUNT_MAX = 1_000_000.0

TRAIN_ROWS = 4000
TRAIN_SEED = 42
FRAUD_RATE = 0.08
N_ESTIMATORS = 120

JWT_SECRET = os.environ.get("FRAUDSHIELD_JWT_SECRET", "local-dev-only-change-me")
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 12

DEMO_EMAIL = "analyst@fraudshield.test"
DEMO_PASSWORD = "analyst123"

RATE_LIMIT = 60
RATE_WINDOW_SECONDS = 60.0

EXPLANATION_METHOD = "importance_times_abs_distance_from_training_median_over_training_std"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


def sqlite_url() -> str:
    return "sqlite:///" + DB_PATH.resolve().as_posix()
