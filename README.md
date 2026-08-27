# ResearchHub Engine

Automated research for land-survey orders. Given an order (with address, county, parcel), the
engine auto-fetches the survey document set — parcel, deed, plat, flood, survey control,
appraiser — from public sources, uploads each document to S3, and records an audit trail.

This is a **standalone HTTP service** consumed by the frontend team (UI) and the backend team
(order management, review workflow) via the frozen API contract. When ready it drops into the
parent repo's `app/modules/research/` unchanged.

## API

`/api/v1/research/*` — 5 endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /research/jobs` | Create a research job (idempotent via `X-Idempotency-Key`) |
| `GET /research/jobs/{id}` | Poll job + per-document progress |
| `POST /research/jobs/{id}/retry` | Retry failed docs (creates a new job) |
| `POST /research/jobs/{id}/cancel` | Cancel a queued/running job |
| `GET /research/orders/{order_id}/jobs` | List an order's job history |

Contracts: `contracts/openapi.json` + `contracts/schemas/` (generated — do not hand-edit).

## Run

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# clerk auto-download needs a browser once:  .venv/Scripts/python -m playwright install chromium

cp .env.example .env                # set DATABASE_URL etc.
docker compose up db redis          # infra (Postgres + Redis)
alembic upgrade head                # apply migrations
cd backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

Worker (processes jobs):

```bash
cd backend && celery -A app.engine.worker.celery_app worker --loglevel=info --queues=research
```

Docs: <http://127.0.0.1:8000/docs>

## Test

```bash
.venv/Scripts/python.exe -m pytest tests -q     # 125 tests, fully offline
```

## Layout

```
backend/app/
  engine/      the service: contracts, models, repository, service, router, worker, adapters
  services/    research sources (parcel, geocode, fema, ngs, clerk, appraiser, downloader)
  data/        per-state registry modules + county platform registry (verified data)
  db/          SQLAlchemy base + mixins (UUID PKs, tenant/audit/timestamp/soft-delete)
alembic/       database migrations (research_jobs, research_documents)
contracts/     generated OpenAPI + JSON Schemas consumed by FE/BE teams
tests/         offline conformance + API + service tests
docker-compose.yml  Postgres + Redis + api + worker
Dockerfile     production container
```

## Load-bearing domain data

`backend/app/data/` holds the battle-tested county registry (`county_platforms.py`) and the
per-state modules under `data/states/`. This is domain data accumulated in the POC — treat it
as the source of truth; do not regenerate blindly.

## Status

Engine v1 contract + service skeleton. See `contracts/openapi.json` for the frozen API.