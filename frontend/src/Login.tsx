import { FormEvent, useState } from "react";
import { ApiError, login, setSession } from "./api";

type LoginProps = {
  onSuccess: () => void;
};

export function Login({ onSuccess }: LoginProps) {
  const [email, setEmail] = useState("analyst@fraudshield.test");
  const [password, setPassword] = useState("analyst123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await login(email.trim(), password);
      setSession(session.access_token, session.email);
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-card">
        <div className="login-copy">
          <p className="eyebrow">Synthetic card-not-present</p>
          <h1>
            FraudShield <span className="accent">AI</span>
          </h1>
          <p>
            Score made-up checkout features for fraud review. Precision and recall on the desk are
            measured on a holdout split, not a target written into the page.
          </p>
          <ul>
            <li>No real card numbers</li>
            <li>No bank or processor connection</li>
            <li>Decisions are allow, review, or block</li>
            <li>Review and block scores open a case</li>
          </ul>
          <p className="demo">
            <span>Local demo</span>
            <code>analyst@fraudshield.test</code>
            <code>analyst123</code>
          </p>
        </div>
        <form className="login-form" onSubmit={onSubmit}>
          <label htmlFor="email">
            Email
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label htmlFor="password">
            Password
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error ? (
            <p className="banner" role="alert">
              {error}
            </p>
          ) : null}
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Enter the desk"}
          </button>
        </form>
      </section>
    </main>
  );
}
