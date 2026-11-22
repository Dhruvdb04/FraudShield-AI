"""Deterministic synthetic card-not-present transactions.

Rows are generated. There are no real card numbers, cardholders, or bank records.
Fraud rows lean toward larger amounts, odd hours, high velocity, high country risk,
and low device trust, with enough overlap that the classes are not perfectly separable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_NAMES: tuple[str, ...] = (
    "amount",
    "hour",
    "country_risk",
    "device_trust",
    "velocity_1h",
    "merchant_category",
    "card_age_days",
    "distance_from_home_km",
    "is_international",
)

INTEGER_FEATURES = frozenset({"merchant_category", "card_age_days", "is_international"})

MERCHANT_CATEGORIES: list[dict[str, int | str]] = [
    {"code": 0, "name": "Grocery"},
    {"code": 1, "name": "Fuel"},
    {"code": 2, "name": "Restaurants"},
    {"code": 3, "name": "Travel"},
    {"code": 4, "name": "Electronics"},
    {"code": 5, "name": "Digital goods"},
    {"code": 6, "name": "Jewelry"},
    {"code": 7, "name": "Money transfer"},
    {"code": 8, "name": "Pharmacy"},
    {"code": 9, "name": "Entertainment"},
    {"code": 10, "name": "Lodging"},
    {"code": 11, "name": "Other"},
]

_ODD_HOURS = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 22.0, 23.0])
_FRAUD_MERCHANT_P = np.array([1, 1, 1, 3, 4, 4, 4, 2, 1, 2, 3, 1], dtype=np.float64)
_FRAUD_MERCHANT_P /= _FRAUD_MERCHANT_P.sum()


def _zeros(n: int) -> dict[str, np.ndarray]:
    return {name: np.zeros(n, dtype=np.float64) for name in FEATURE_NAMES}


def _pack(features: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {
        "amount": np.clip(features["amount"], 0.01, 100_000),
        "hour": np.clip(features["hour"], 0, 23),
        "country_risk": np.clip(features["country_risk"], 0, 1),
        "device_trust": np.clip(features["device_trust"], 0, 1),
        "velocity_1h": np.clip(features["velocity_1h"], 0, 500),
        "merchant_category": features["merchant_category"],
        "card_age_days": np.clip(features["card_age_days"], 0, 20_000),
        "distance_from_home_km": np.clip(features["distance_from_home_km"], 0, 20_000),
        "is_international": features["is_international"],
    }


def _legit_features(rng: np.random.Generator, n: int) -> dict[str, np.ndarray]:
    if n == 0:
        return _zeros(0)
    daytime = rng.random(n) < 0.78
    hour = np.where(daytime, rng.normal(14.0, 3.4, n), rng.uniform(0, 23, n))
    distance = rng.exponential(28, n)
    distance = np.where(rng.random(n) < 0.08, rng.uniform(180, 2400, n), distance)
    velocity = rng.poisson(0.7, n).astype(np.float64)
    velocity = np.where(rng.random(n) < 0.09, rng.integers(2, 6, n).astype(np.float64), velocity)
    return _pack(
        {
            "amount": rng.lognormal(3.55, 0.78, n),
            "hour": hour,
            "country_risk": rng.beta(2.1, 6.5, n),
            "device_trust": rng.beta(5.5, 2.4, n),
            "velocity_1h": velocity,
            "merchant_category": rng.integers(0, 12, n).astype(np.float64),
            "card_age_days": rng.integers(8, 2400, n).astype(np.float64),
            "distance_from_home_km": distance,
            "is_international": rng.binomial(1, 0.08, n).astype(np.float64),
        }
    )


def _clear_fraud(rng: np.random.Generator, n: int) -> dict[str, np.ndarray]:
    if n == 0:
        return _zeros(0)
    odd_hour = rng.random(n) < 0.7
    hour = np.where(odd_hour, rng.choice(_ODD_HOURS, size=n) + rng.normal(0, 0.4, n), rng.normal(13.5, 3.0, n))
    return _pack(
        {
            "amount": rng.lognormal(4.55, 0.7, n),
            "hour": hour,
            "country_risk": rng.beta(4.2, 2.6, n),
            "device_trust": rng.beta(2.1, 4.2, n),
            "velocity_1h": rng.poisson(3.0, n).astype(np.float64) + rng.uniform(0, 1.2, n),
            "merchant_category": rng.choice(np.arange(12), size=n, p=_FRAUD_MERCHANT_P).astype(np.float64),
            "card_age_days": rng.integers(1, 500, n).astype(np.float64),
            "distance_from_home_km": rng.exponential(110, n) + 8,
            "is_international": rng.binomial(1, 0.42, n).astype(np.float64),
        }
    )


def _border_fraud(rng: np.random.Generator, n: int) -> dict[str, np.ndarray]:
    """Legitimate-looking rows with only some fraud signals moved."""
    if n == 0:
        return _zeros(0)
    base = _legit_features(rng, n)
    shift_amount = rng.random(n) < 0.62
    shift_hour = rng.random(n) < 0.5
    shift_country = rng.random(n) < 0.48
    shift_trust = rng.random(n) < 0.48
    shift_velocity = rng.random(n) < 0.55
    shift_distance = rng.random(n) < 0.32
    shift_international = rng.random(n) < 0.28
    shift_age = rng.random(n) < 0.35
    amount = np.where(shift_amount, base["amount"] * rng.uniform(1.3, 3.2, n), base["amount"])
    hour = np.where(shift_hour, rng.choice(_ODD_HOURS, size=n), base["hour"])
    country = np.where(shift_country, np.clip(base["country_risk"] + rng.uniform(0.15, 0.45, n), 0, 1), base["country_risk"])
    trust = np.where(shift_trust, np.clip(base["device_trust"] - rng.uniform(0.15, 0.45, n), 0, 1), base["device_trust"])
    velocity = np.where(shift_velocity, base["velocity_1h"] + rng.integers(1, 5, n), base["velocity_1h"])
    distance = np.where(shift_distance, base["distance_from_home_km"] + rng.exponential(80, n), base["distance_from_home_km"])
    international = np.where(shift_international, 1.0, base["is_international"])
    card_age = np.where(shift_age, rng.integers(2, 180, n).astype(np.float64), base["card_age_days"])
    return _pack(
        {
            "amount": amount,
            "hour": hour,
            "country_risk": country,
            "device_trust": trust,
            "velocity_1h": velocity,
            "merchant_category": base["merchant_category"],
            "card_age_days": card_age,
            "distance_from_home_km": distance,
            "is_international": international,
        }
    )


def _fraud_features(rng: np.random.Generator, n: int) -> dict[str, np.ndarray]:
    n_clear = int(round(n * 0.42))
    n_border = n - n_clear
    clear = _clear_fraud(rng, n_clear)
    border = _border_fraud(rng, n_border)
    return {name: np.concatenate([clear[name], border[name]]) for name in FEATURE_NAMES}


def generate_synthetic(n_rows: int = 4000, seed: int = 42, fraud_rate: float = 0.08) -> pd.DataFrame:
    if n_rows < 20:
        raise ValueError("n_rows must be at least 20")
    if not 0 < fraud_rate < 0.5:
        raise ValueError("fraud_rate must be between 0 and 0.5")

    rng = np.random.default_rng(seed)
    n_fraud = int(round(n_rows * fraud_rate))
    n_fraud = min(max(n_fraud, 2), n_rows - 2)
    n_legit = n_rows - n_fraud

    legit = _legit_features(rng, n_legit)
    fraud = _fraud_features(rng, n_fraud)
    order = rng.permutation(n_rows)
    frame = pd.DataFrame(
        {name: np.concatenate([legit[name], fraud[name]])[order] for name in FEATURE_NAMES}
    )
    labels = np.concatenate(
        [np.zeros(n_legit, dtype=np.int64), np.ones(n_fraud, dtype=np.int64)]
    )
    frame["label"] = labels[order]
    for name in INTEGER_FEATURES:
        frame[name] = np.rint(frame[name]).astype(int)
    if int(frame[list(FEATURE_NAMES)].isna().to_numpy().sum()) != 0:
        raise RuntimeError("Synthetic data contains missing values")
    return frame


def stored_feature(name: str, value: object) -> int | float:
    number = float(value)  # type: ignore[arg-type]
    if name in INTEGER_FEATURES:
        return int(round(number))
    return number
