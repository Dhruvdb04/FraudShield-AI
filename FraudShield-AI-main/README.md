# FraudShield AI

Defensive scoring of **synthetic** card-not-present transactions. The generator invents feature rows. There are no real PANs, cardholders, merchants, or bank connections. Scores rank those made-up rows so an analyst can practice allow / review / block. This project does not explain how to commit fraud, steal cards, or evade a bank.

## Demo login

- Email: `analyst@fraudshield.test`
- Password: `analyst123`

The password is hashed with PBKDF2-HMAC-SHA256 before it is stored. The API issues a 12-hour HS256 JWT. Set `FRAUDSHIELD_JWT_SECRET` if you do not want the local default.

## Run on Windows

From the repo root, in PowerShell:

```powershell
Set-Location "C:\Users\raj shekhar\Downloads\FraudShield-AI"
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

If script activation is blocked, skip `Activate.ps1` and call the venv Python directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The first start trains a model when `models/fraud_model.joblib` is missing. That writes:

- `data/synthetic_transactions.csv` (gitignored)
- `data/fraudshield.db` (gitignored)
- `models/fraud_model.joblib` (gitignored)
- `models/metrics.json` (real holdout numbers)

It also seeds the analyst and about 40 already-scored rows so the desk is not empty. The seed uses a higher fraud mix than training so review and block rows show up. Those counts are workspace traffic, not the training base rate.

In a second PowerShell window:

```powershell
Set-Location "C:\Users\raj shekhar\Downloads\FraudShield-AI\frontend"
npm install
npm run dev
```

Open `http://localhost:5175`. Vite proxies `/api` to `127.0.0.1:8000`. The console uses IBM Plex Sans and IBM Plex Mono from Google Fonts, with Segoe UI and `ui-monospace` as fallbacks.

## How metrics are produced

`python -m backend.app.scoring` (or the first server start) does all of the following in code:

1. Build about 4,000 synthetic rows with NumPy seed 42 and a fraud rate of about 8%.
2. Hold out 20% with a stratified split. The holdout is not used to fit the model and is not upsampled.
3. Fit a scikit-learn `Pipeline` whose only step is `GradientBoostingClassifier`.
4. On the training split only, weight fraud rows by `n_legitimate / n_fraud`.
5. On the holdout, compute precision, recall, and F1 for the fraud class at probability cutoff 0.5, plus ROC AUC on the fraud probability.
6. Write those measured numbers to `models/metrics.json`. Nothing in the source code substitutes a target such as 0.90.

The saved pipeline is the one that was scored on that holdout. It is not refit on the full sample. Product decisions start from that model probability: block at 0.75 and above, review at 0.45 and above, otherwise allow. The number stored as `score` stays that probability. Analyst labels do not refit the pipeline, and `models/metrics.json` is left as measured.

Explanations are the top three features by `feature_importances_ * abs(value - training_median) / training_std`. That is not SHAP.

## Rules before the model

Two rules are evaluated before the saved model is asked for a probability:

- `amount_gte_200000` when amount is at least 200,000
- `velocity_1h_gte_8` when velocity in the last hour is at least 8

If either fires and the model decision would be allow, the stored decision is review. A model review or block stays as it is. `model_decision` and `rules_fired` are stored beside the model score. The joblib file is still only the gradient boosting pipeline. It does not contain these rules.

The score API accepts amounts up to 1,000,000 so the amount rule can be exercised. Training rows are still clipped at 100,000 in the generator. That clip is unchanged.

## Cases

A review or block decision opens a case with status `open`. Allow does not. `GET /api/cases` lists them. `PATCH /api/cases/{case_id}` takes `outcome` of `false_positive` or `confirmed_fraud` and a note, then stores that label and closes the case. The overview count `open_cases` is the number of cases still open.

Those labels stay on the case. They are not written back as training labels, and the model is not retrained. Rows scored before this rules layer keep the decision they already had; new scores record which rules fired.

`POST /api/score` requires `Authorization: Bearer <token>` and `Idempotency-Key`. The same key returns the stored decision. A different body with a used key returns 409. Scoring is limited to about 60 requests per minute per analyst, in this process only.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

`tests/test_scoring.py` trains a smaller synthetic set, checks that holdout recall is a finite number from 0 through 1, and checks that a hand-built odd-hour high-amount vector scores higher than a plain daytime low-amount vector.

`tests/test_cases.py` checks that amount and velocity rules force at least review, that a low model-score vector with `velocity_1h` 9 is stored as review, and that confirming that case as `confirmed_fraud` is still there in a new database session. The test writes its model under a temp directory and does not replace `models/metrics.json`.

## Limits

- One local analyst and one SQLite file.
- The rate limit lives in memory and resets when the process stops.
- Explanations are not SHAP values.
- Analyst outcomes are stored on cases. They are not used to refit the model.
- The demo password and default JWT secret are for this machine only.
