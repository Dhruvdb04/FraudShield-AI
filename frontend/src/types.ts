export type Reason = {
  feature: string;
  value: number;
  median: number;
  scale: number;
  importance: number;
  contribution: number;
  direction: string;
};

export type Transaction = {
  transaction_id: string;
  amount: number;
  hour: number;
  country_risk: number;
  device_trust: number;
  velocity_1h: number;
  merchant_category: number;
  card_age_days: number;
  distance_from_home_km: number;
  is_international: number;
  score: number;
  decision: string;
  model_decision: string;
  rules_fired: string[];
  label: number | null;
  explanation: Reason[];
  explanation_method: string;
  idempotency_key: string;
  created_at: string;
  replayed?: boolean;
};

export type ScoreInput = {
  amount: number;
  hour: number;
  country_risk: number;
  device_trust: number;
  velocity_1h: number;
  merchant_category: number;
  card_age_days: number;
  distance_from_home_km: number;
  is_international: number;
};

export type HistogramBucket = {
  low: number;
  high: number;
  count: number;
};

export type MerchantCategory = {
  code: number;
  name: string;
};

export type CaseOutcome = "false_positive" | "confirmed_fraud";

export type CaseRecord = {
  case_id: string;
  transaction_id: string;
  status: string;
  outcome: CaseOutcome | null;
  note: string;
  analyst_email: string | null;
  amount: number;
  velocity_1h: number;
  score: number;
  model_decision: string;
  decision: string;
  rules_fired: string[];
  created_at: string;
  updated_at: string;
};

export type Overview = {
  total: number;
  allow: number;
  review: number;
  block: number;
  open_cases: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  roc_auc: number | null;
  training_rows: number | null;
  training_fraud_rate: number | null;
  holdout_rows: number | null;
  metric_cutoff: number;
  review_threshold: number;
  block_threshold: number;
  note: string;
  histogram: HistogramBucket[];
  merchant_categories: MerchantCategory[];
};

export type LoginResult = {
  access_token: string;
  token_type: string;
  email: string;
};
