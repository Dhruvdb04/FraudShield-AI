import type { Reason, ScoreInput } from "./types";

export const PLAIN_DAYTIME: ScoreInput = {
  amount: 24.5,
  hour: 13,
  country_risk: 0.08,
  device_trust: 0.92,
  velocity_1h: 0,
  merchant_category: 0,
  card_age_days: 900,
  distance_from_home_km: 4,
  is_international: 0,
};

export const VELOCITY_RULE: ScoreInput = {
  ...PLAIN_DAYTIME,
  velocity_1h: 9,
};

export const AMOUNT_RULE: ScoreInput = {
  ...PLAIN_DAYTIME,
  amount: 200000,
};

export const ODD_HOUR_SPIKE: ScoreInput = {
  amount: 4200,
  hour: 2,
  country_risk: 0.95,
  device_trust: 0.05,
  velocity_1h: 14,
  merchant_category: 6,
  card_age_days: 3,
  distance_from_home_km: 3500,
  is_international: 1,
};

export function featureLabel(name: string): string {
  return name.replaceAll("_", " ");
}

export function directionPhrase(direction: string): string {
  if (direction === "above_median") return "above typical";
  if (direction === "below_median") return "below typical";
  return "at typical";
}

export function formatFeature(name: string, value: number): string {
  if (name === "merchant_category" || name === "card_age_days" || name === "is_international") {
    return String(Math.round(value));
  }
  if (name === "amount" || name === "distance_from_home_km") return value.toFixed(1);
  if (name === "velocity_1h" || name === "hour") return value.toFixed(1);
  return value.toFixed(2);
}

export function reasonLine(reason: Reason): string {
  return `${featureLabel(reason.feature)} ${directionPhrase(reason.direction)}`;
}

export function formatStamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatMetric(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(3);
}

export function formatRate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function ruleLabel(id: string): string {
  if (id === "amount_gte_200000") return "Amount ≥ 200,000";
  if (id === "velocity_1h_gte_8") return "Velocity 1h ≥ 8";
  return id;
}

export function outcomeLabel(outcome: string | null): string {
  if (outcome === "false_positive") return "False positive";
  if (outcome === "confirmed_fraud") return "Confirmed fraud";
  return "Open";
}

export function labelText(label: number | null): string {
  if (label === null) return "—";
  return label === 1 ? "fraud" : "legit";
}

export function toneFor(mid: number, review: number, block: number): string {
  if (mid >= block) return "block";
  if (mid >= review) return "review";
  return "allow";
}
