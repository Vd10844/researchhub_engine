# Developer Guide — ResearchHub Engine

What this repo is, where everything lives, how to run it, and what's left.
This is the map for the developer team taking over the engine. Read the four
contract docs first for the guarantees:

- `docs/source-contract.md` — source adapter contract, outcome taxonomy, fallback/retry
- `docs/result-schema.md` — frozen vs additive result fields (what the frontend may rely on)
- `docs/job-lifecycle.md` — job/document state machines, retry/cancel, idempotency
- `docs/regression-matrix.md` — the POC-parity validation checklist + freeze tables

## 1. What this is

A standalone, production-oriented Python service that automates **land-survey
research**: given an order (address + county/state + optional parcel id) it
fetches the mortgage-survey document set — Parcel ID, Deed, Plat, Flood map,
control — from live county/state/federal sources, stores evidence blobs, and
serves a frozen API contract on `/api/v1/research/*`.

It was extracted from the POC (`SurveyResearch` app) with two hard rules:

1. **The result contract is frozen.** Every field the POC frontend reads keeps
   its meaning, type and presence. Engine-internal classification rides in
   additive fields only (`docs/result-schema.md`).
2. **Engine-only.** The battle-tested county registry / geocode / parcel /
   clerk / FEMA / NGS service modules are used as-is. Parent-domain concepts
   (orders, evidence Files) have dev stand-ins swapped at integration.

## 2. Layout map

```
backend/app/
  main.py                    FastAPI app: research router, health/readiness, CORS,
                             catch-all error handler (no stack-trace leakage), rate-limit 429
  config.py                  env-driven settings (DATABASE_URL, REDIS/Celery, JOBS_DIR,
                             COGNITO_*, RATE_LIMIT_RESEARCH, POOL_*, REAPER_*, JOB_*_TIME_LIMIT)
  core/
    logging.py                structlog JSON (prod) / console (dev), configure_logging()
    middleware.py              RequestIDMiddleware — per-request correlation ID on every log line
    limiter.py                per-tenant rate limiter (Redis-backed, memory fallback)
  db/                        SQLAlchemy engine/session/mixins + declarative Base
  services/                  BATTLE-TESTED POC modules — do not refactor:
                             geocode.py parcel.py clerk.py clerk_scraper.py appraiser.py
                             fema.py ngs.py downloader.py http.py storage.py
  engine/                    THE ENGINE
    contracts.py             canonical result models + enums (schema of record)
    schemas.py               API request/response models (the OpenAPI contract)
    models.py                research_jobs + research_documents ORM
    repository.py            thin query layer
    service.py               job create/get/retry/cancel, counters, terminal status,
                             doc-type validation/normalization
    router.py                /api/v1/research/* endpoints
    dependencies.py          Cognito JWT tenant/actor (header fallback in dev) — see README §Production posture
    mappers.py               ORM → contract models (incl. FileReference)
    adapters.py              production wiring: order_provider, document_fetcher,
                             build_research_service (single seam for the worker+API)
    worker.py                Celery app + research_job task + enqueue_research_job
    order_source.py          dev `orders`/`tenants` stand-in + DB-backed order_provider
    evidence_source.py       dev `files`/`order_files` stand-in + evidence linkage
    orchestration/           THE PHASE-SEPARATED RESEARCH PIPELINE
      context.py             resolve_property_context (geocode → parcel → clerk refs)
      sources.py             SourceAdapter interface + 8 adapters + ADAPTERS registry
      steps.py               include-aware build_steps, centralized status/provenance
      runner.py              two-phase pipeline → canonical ResearchResult
      folders.py             staging dir + manifest.json / result.json writers
  alembic/versions/          0002 base shim (orders/tenants/files/order_files first),
                             0001 research tables (FKs onto the shim),
                             0003 cancel_reason column + reviewed/archived enum values
scripts/
  export_contracts.py        re-export contracts/openapi.json + schemas (drift-checkable)
  e2e_local.py               FULL E2E: alembic → seed → API+worker → job → verify
tests/                       1108 tests, fully offline except the explicit E2E
docs/                        the four contract docs + this guide
contracts/                   frozen OpenAPI + per-schema JSON (re-export only via script)
docker-compose.yml           db (postgres:15), redis, api, worker
```

## 3. The pipeline (what took the place of the POC monolith)

`services/orchestrator.py` (422 lines) is **gone**. Its logic lives in
`engine/orchestration/`, split into two phases:

```
Phase A  resolve_property_context(ctx)         Phase B  per-document
   geocode · parcel · clerk refs                        adapter.fetch(ctx, docs_dir)
   ───────────────────────────────                     ─────────────────────────────
   runs once per research run                           runs per requested step; `include=[...]`
   → canonical PropertyContext + WarningBag             → FetchedSource (ok/link/empty/error)
```

- **`include` is honored** — a deed-only retry does not re-run geocode,
  parcel, FEMA and NGS (closes dead POC code).
- **No source can crash a run.** Every adapter failure degrades to a fallback
  link step + structured `ErrorInfo`; `run_research` always returns a
  `ResearchResult` with the full 11-step set in declared order.
- **Adapters never fall back internally** — they return data or raise
  `SourceError(outcome, code, message, retryable)`; `steps.py` decides the card.

The orchestrator only runs **inside the Celery worker** (`worker.research_job`).
Requests never block on fetches.

## 4. The request → upload chain (what changed this phase)

`POST /research/jobs`
→ `router.create_research_job` → `service.create_job`
→ commits job + document rows → **`enqueue_research_job`** (Redis task publish)
→ `worker.research_job` (one task per job)
→ per document: `service.document_fetcher(order, [type], tenant_id)`
→ `run_research(include=[step])` → step result
→ `_upload_artifact`: blob `copy_in` → **File + OrderFile rows** → doc row update
→ counters + `resolve_job_terminal_status` → callback (optional)

Three bugs this newest code fixes (found by code review and the E2E):

1. **Nothing enqueued the task.** `create_job` persisted rows and stopped; jobs
   stalled in `queued`. The `enqueue` dependency is injected into the service
   (`worker.enqueue_research_job` in production; `None`/no-op in tests).
2. **The worker built a dependency-less `ResearchService()`** — `order_provider`
   and `document_fetcher` were `None`. Both the router and the worker now share
   `adapters.build_research_service()`.
3. **Blob keys escaped storage scope.** `build_key(org_id="", …)` produced
   `/orders/…` keys rejected by `LocalStorage._p`. Keys are now tenant-scoped
   (`{tenant_id}/{order_id}/{doc_type}{ext}`) and verified by the E2E.

## 5. Run it

```bash
# venv (Python 3.14)
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt

# unit + regression suite (1108 tests, offline)
.venv/Scripts/python.exe -m pytest tests -q

# plain API against a local Postgres (create_all in RUN_ENV=local)
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/researchhub \
RUN_ENV=local .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload

# migrations path (needs the shim base tables — see 0002)
.venv/Scripts/python.exe -m alembic upgrade head
```

### The full E2E (real everything)

```bash
docker compose -f docker-compose.yml -f dc.e2e.yml up -d db redis   # db on 5433
.venv/Scripts/python.exe scripts/e2e_local.py
```

`e2e_local.py` runs alembic on real Postgres, seeds a Polk FL order, boots a
real uvicorn + a real Celery worker (solo pool — billiard's process pool
crashes on Windows), POSTs a job over HTTP, polls to terminal, verifies the
blob artifact and File/OrderFile rows, and exercises cancel. Works every time,
even when the network blocks sources — sources degrade to fallback links and
the job still completes. (Last run: `completed`, NGS uploaded a real
3-datasheet evidence file, sha-verified on disk.)

## 6. Contract discipline

- `backend/app/engine/contracts.py` is the schema of record. Enums and additive
  fields may extend; frozen values never change (`docs/result-schema.md`).
- API responses come from `schemas.py` via `mappers.py` — never raw ORM dicts.
- Change a schema? Re-run `scripts/export_contracts.py` and confirm `git diff
  contracts/` shows exactly the intended drift. CI fails on drift (exit 1).
- The fixture regression suite (`tests/test_orchestration_regression.py`, 54)
  pins the 11-step key order, the frozen vocabulary and every stable field.
  The execution scenarios (`tests/test_execution_scenarios.py`, 26) pin the
  running system: worker-path outcomes, `classify_exception` branches,
  cancel-`cancelling` drains and last-resort fallbacks. A schema change that
  breaks either is a contract break.

## 7. What is remaining

**Not a bug — documented seams still to close at parent integration:**

| # | seam | where | swap for |
|---|---|---|---|
| 1 | `order_provider` reads dev `orders` | `engine/order_source.py` | parent `app/modules/orders` (Order+OrderAddress) |
| 2 | `File`/`OrderFile` stand-in | `engine/evidence_source.py` | parent evidence module (same columns/names) |
| 3 | Cognito JWT auth **wired** — set `COGNITO_*` env vars with parent pool | `engine/dependencies.py` + `config.py` | parent Cognito pool ID, client ID, issuer, audience |
| 4 | alembic base shim `0002` | `0002_dev_base_tables.py` | drop at parent merge (tables already exist); keep `0001`; `0003` (cancel_reason + enum values) requires the table names from `0001` |
| 5 | `doc_types` vs source registry | `service._validate_doc_types` | validate against the live catalog at startup (TODO remains) |
| 6 | Celery `--pool=solo` | E2E only | default prefork pool on Linux workers in prod |

**Production hardening — completed:**
- Cognito JWT auth (RS256/HS256) wired in `dependencies.py`, switched by env.
- Real health/readiness checks (`/api/health`, `/api/health/live`).
- Per-tenant rate limiting (`core/limiter.py`, Redis-backed).
- Structured logging + per-request correlation ID (`core/logging.py`,
  `core/middleware.py`).
- Catch-all error handler (no stack-trace leakage).
- Worker hardening: retries (3× backoff+jitter), hard/soft time limits,
  orphan-reaper beat task (5 min).
- Production Dockerfile (non-root, HEALTHCHECK, multi-stage).
- CI workflow: ruff + mypy + pytest + contract-freeze gate.

**Still remaining:**
- Real-world fixture capture for `error`-status steps (none of the 7 POC
  fixtures emitted one; the engine classifies blocked/broken/retryable
  additively — capture one from the user's VPN'd machine for CI).
- S3 storage backend smoke test (`QP_STORAGE_BACKEND=s3`) once AWS SSO is
  reachable.

## 8. Environment gotchas

- **Windows Celery:** billiard's process pool raises handle errors
  (`WinError 6/5`). Use `--pool=solo` on dev machines; Linux workers use default.
- **Docker:** the daemon must be running for `docker compose up`; port 5432 may
  already be owned by a local Postgres — `dc.e2e.yml` maps db to 5433.
- **Network:** this sandbox blocks FEMA/clerk and needs US egress. A 403 from a
  source in the E2E is *expected* — it means the fallback link path fired, not
  that the E2E failed.
- **`RUN_ENV=local`** does `create_all` (dev speed); production runs alembic.
  SQLite-only tricks (JSONB patch) are test-scoped — do not split them into the
  app.