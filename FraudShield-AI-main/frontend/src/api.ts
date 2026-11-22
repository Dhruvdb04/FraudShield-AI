import type { CaseOutcome, CaseRecord, LoginResult, Overview, ScoreInput, Transaction } from "./types";

const TOKEN_KEY = "fraudshield_token";
const EMAIL_KEY = "fraudshield_email";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function getEmail(): string | null {
  return sessionStorage.getItem(EMAIL_KEY);
}

export function setSession(token: string, email: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(EMAIL_KEY, email);
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(EMAIL_KEY);
}

function messageFromBody(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === "object" && "msg" in item) {
        const record = item as { msg: unknown; loc?: unknown };
        const loc = Array.isArray(record.loc)
          ? record.loc.filter((part) => part !== "body").join(".")
          : "";
        const msg = String(record.msg);
        return loc ? `${loc}: ${msg}` : msg;
      }
      return String(item);
    });
    return parts.join(" ") || fallback;
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Start uvicorn on 127.0.0.1:8000.");
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(
      response.status,
      messageFromBody(body, response.statusText || "Request failed"),
    );
  }
  return (await response.json()) as T;
}

export function login(email: string, password: string): Promise<LoginResult> {
  return request<LoginResult>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getOverview(): Promise<Overview> {
  return request<Overview>("/api/overview");
}

export function getTransactions(): Promise<Transaction[]> {
  return request<Transaction[]>("/api/transactions");
}

export function getCases(): Promise<CaseRecord[]> {
  return request<CaseRecord[]>("/api/cases?limit=200");
}

export function updateCase(caseId: string, outcome: CaseOutcome, note: string): Promise<CaseRecord> {
  return request<CaseRecord>(`/api/cases/${encodeURIComponent(caseId)}`, {
    method: "PATCH",
    body: JSON.stringify({ outcome, note }),
  });
}

export function scoreTransaction(features: ScoreInput, idempotencyKey: string): Promise<Transaction> {
  return request<Transaction>("/api/score", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(features),
  });
}
