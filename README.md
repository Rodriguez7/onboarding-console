# SaaS Customer Onboarding & Integration Console

A platform for **implementation specialists** to take a new customer from configuration to go-live, and keep an eye on the integration afterwards.

![Field mapping step: columns from an uploaded CSV are matched to the platform schema automatically](docs/screenshot-import-mapping.jpg)

*Not deployed. To try it, run `docker compose up --build` (see Quick start) and upload `samples/customers.csv`.*

```
Create workspace → Import CSV → Map fields → Credentials & webhooks → Validation & integration tests
   → Fix failed records / webhook errors → UAT checklist → Go live → Handover document → Monitoring
```

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript |
| Backend | FastAPI, SQLAlchemy 2, Pydantic 2 |
| Database | PostgreSQL 16 (SQLite works for local dev/tests) |
| Integrations | REST ingest API (API-key auth), HMAC-signed outbound webhooks |
| Tests | pytest (API + unit), Playwright (full end-to-end workflow) |
| Ops | Docker, docker-compose, GitHub Actions, Railway |

## Features

**Workspace** — one per customer, with owner, contact, target go-live date and a progress tracker that is derived from real state (not manually ticked).

**CSV import** — UTF-8 CSV upload (comma, semicolon, tab or pipe delimited, auto-detected), up to 5 MB / 50k rows. Rejects empty files, blank or duplicate headers.

**Field mapping** — auto-suggests a mapping from incoming columns to the platform schema using names, aliases and fuzzy matching (`Subscripton Plan` → `plan`, shown with a confidence badge). Each platform field can be mapped once; required fields must be mapped before validation.

**Validation** — every row is validated and normalised: emails, phone numbers (7–15 digits), plan enum, non-negative numbers (`$1,250.50` → `1250.5`), dates (`03/02/2023` → `2023-03-02`, no future dates), ISO country codes, and duplicate external IDs within a file. The same rules apply to the REST API.

**Failed records** — invalid rows are listed with per-field errors and can be fixed in place. Fixes are stored as overrides on top of the original CSV values, so the source data stays auditable. Valid rows are upserted into the customer's records on commit.

**API credentials** — `oc_live_…` / `oc_test_…` keys, shown once and stored as SHA-256 hashes. Revocation is immediate; requests made with revoked keys are logged so they show up in monitoring.

**Webhooks** — per-endpoint event subscriptions (`records.imported`, `record.upserted`, `integration.test`, `workspace.live`), each signed with `X-Onboarding-Signature: t=<ts>,v1=<hmac-sha256("<ts>." + body)>`. Every delivery is recorded; failures appear in the error view and can be retried. A built-in sink (`/sink/ok`, `/sink/fail`) lets you try this without an external receiver.

**Validation & integration tests** — one click runs the go-live gate: import present, required fields mapped, records valid, data committed, active and production keys, and a live signed test event to every active webhook. Results are `passed` / `warning` / `failed`; any failure blocks go-live.

**UAT checklist** — seeded with 8 standard items across Data, Integration, Security, Training and Sign-off; custom items can be added. Ticking an item records who signed off and when.

**Go-live** — refused (HTTP 409 with the list of blockers) until data is committed, the latest test run passed and every UAT item is signed off.

**Handover document** — a Markdown document generated from the workspace: summary, field mapping, API access (key prefixes only, never secrets), webhook setup and signature verification, test results, UAT sign-off and a support runbook. View in the console, print to PDF, or download `.md`.

**Monitoring** — API request volume, error rate, p95 latency, webhook delivery and failure rate, hourly charts, and recent errors, with a `healthy` / `degraded` (≥ 5% errors) / `down` (≥ 50%) status.

## Quick start

### Docker (everything)

```bash
docker compose up --build
# Console: http://localhost:3000   API docs: http://localhost:8000/docs
```

### Local development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # or skip: defaults to SQLite ./onboarding.db
uvicorn app.main:app --reload     # http://localhost:8000/docs

# Frontend (second terminal)
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Try it with [`samples/customers.csv`](samples/customers.csv): 8 rows, 3 valid, 5 with realistic problems (bad email, unknown plan, invalid date and country, a duplicate ID).

## Tests

```bash
cd backend && pytest                                   # SQLite
DATABASE_URL=postgresql://user:pass@localhost/db pytest # PostgreSQL

cd frontend && npm run build && npx playwright test    # starts API + web automatically
```

The Playwright test drives the whole workflow in a browser: create workspace → upload sample CSV → check suggested mapping → fix a failed record → commit → generate a production key → add a healthy and a failing webhook → see the test run fail and the error in the webhook view → pause the broken endpoint → tests pass → sign off UAT → go live → check the handover document → send API traffic → verify monitoring.

CI (`.github/workflows/ci.yml`) runs pytest on SQLite and Postgres, typechecks and builds the frontend, runs the Playwright suite, and builds the Docker images.

## Customer REST API

```bash
curl -X POST "$API/api/v1/records" \
  -H "Authorization: Bearer oc_live_..." -H "Content-Type: application/json" \
  -d '{"records": [{"external_id": "C-1", "email": "a@acme.com", "plan": "pro"}]}'
# 200 {"accepted": 1, "rejected": []}
# Partially invalid batches return 200 with per-record errors; fully invalid ones return 422.

curl "$API/api/v1/records?limit=50" -H "Authorization: Bearer oc_live_..."
```

### Verifying webhook signatures (Python)

```python
import hashlib, hmac, time

def verify(secret: str, header: str, body: bytes, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    ts = int(parts["t"])
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

## Deploying to Railway

The repo is a monorepo with two services, each with its own `Dockerfile` and `railway.json`.

1. Create a Railway project and add a **PostgreSQL** database.
2. Add a service from this repo with **Root Directory** `backend`. Set variables:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - `CORS_ORIGINS` = the frontend's public URL (e.g. `https://console-production.up.railway.app`)
3. Add a second service with **Root Directory** `frontend`. Set `NEXT_PUBLIC_API_URL` to the backend's public URL (it's baked in at build time, so redeploy after changing it).
4. Generate public domains for both. The backend health check is `/health`.

Tables are created on startup. For schema changes in production, add Alembic migrations.

## Project layout

```
backend/
  app/
    main.py              FastAPI app, CORS, /health, demo webhook sink
    models.py            SQLAlchemy models
    platform_schema.py   Target schema + validation/normalisation rules
    mapping.py           Column → field suggestions, mapping checks
    webhooks.py          Signing, delivery, event fan-out
    readiness.py         Progress steps and go-live blockers
    routers/             workspaces (+UAT, go-live), imports, integrations,
                         testing, handover, monitoring, ingest (customer API)
  tests/                 pytest suite
frontend/
  app/                   Next.js routes: workspace list + one page per workflow step
  components/            UI primitives, workspace context, hourly chart
  lib/                   API client and types
  e2e/                   Playwright workflow test
samples/customers.csv    Demo data with deliberate errors
```

## Design notes

- **Webhooks are delivered synchronously** with a 5 s timeout and every attempt is persisted. That keeps the console deterministic and easy to reason about at onboarding scale; for high volume, move `webhooks.emit` onto a queue (e.g. Redis + RQ/Celery) with automatic exponential-backoff retries.
- **No authentication on the console** itself — it's meant to sit behind your SSO/reverse proxy. The customer-facing `/api/v1` is authenticated by API key.
- **Skipped rows are a warning, not a blocker**: before commit, invalid rows fail the test run; once a specialist commits and deliberately skips them, the check downgrades to a warning and the handover document records the count.
