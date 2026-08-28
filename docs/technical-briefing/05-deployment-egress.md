# 05 — Deployment & US Egress (DevOps + backend team)

Every way this system runs, and the one question that used to consume whole meetings —
**"how do the US-only government APIs work?"** — answered from the code.

## 0. One application, three run modes

| Mode | What runs | How to start |
|---|---|---|
| **Local laptop** (fastest) | uvicorn + SQLite + in-process orchestration | `../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload --reload-dir app` (or `run.bat`) |
| **Docker stack** (full engine) | Postgres + Redis + uvicorn + Celery worker | `docker compose up -d --build` |
| **E2E harness** (real everything) | real Postgres + Redis + uvicorn + real worker, driven over HTTP | `.venv/Scripts/python.exe scripts/e2e_local.py` |
| **Production** (parent) | AWS `us-east-1` ECS: `quickplot-dev-api` + `quickplot-dev-worker`, Cognito, alembic as one-off task | parent `deploy-dev.yml` workflow → ECR → ECS |

### Local quick-start details
- `RUN_ENV=local` shortcuts migrations — the app does `Base.metadata.create_all` at startup
  (`backend/app/main.py`), so a laptop never needs alembic. `RUN_ENV=test` is the same path for
  tests.
- uvicorn `--reload --reload-dir app` watches `.py`; the frontend is served **no-cache** by
  middleware (`main.py:35`), so JS/HTML edits appear on a plain browser refresh.
- Headless mode: `run-hidden.vbs` (output → `server.log`) + `stop.bat` (kills port owner and
  the whole process tree — with `--reload` there is a watcher **and** a multiprocessing worker).

## 1. The Docker stack (engine `docker-compose.yml`)

Four services, health-gated:

```
Browser ─► api (uvicorn, :8000) ─► db  (postgres:15, named volume `researchhub_pgdata`)
             │                    └► redis:7-alpine  (/0 broker for Celery)
             └► worker (celery -A app.engine.worker.celery_app --queues=research)
```

- `Dockerfile`: `python:3.13-slim`, `PYTHONPATH=/app/backend`, default CMD
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `api` mounts `./backend` as a volume (hot code + `--reload` in dev); `worker` mounts the
  same backend and runs the Celery app with `--queues=research` to match the broker
  `redis://redis:6379/0` / result backend `/1`.
- Migrations run once, as its own step: `alembic upgrade head` (config: `alembic.ini` →
  `script_location = backend/alembic`).
- `.env.example` documents every knob: `DATABASE_URL`, `REDIS_URL`/`CELERY_*`, S3
  (`AWS_REGION=us-east-1`, `S3_ARTIFACTS_BUCKET`), `CORS_ORIGINS`, `MAX_RETRIES_PER_DOCUMENT=3`,
  `DOCUMENT_TIMEOUT_SECONDS=60`.

### Windows worker note — `--pool=solo`
Celery's default billiard *process* pool raises WinError 6/5 on Windows. Locally the worker must
run `celery ... worker --pool=solo` (the E2E does this automatically). Linux prod uses the
default prefork.

## 2. The E2E harness (`scripts/e2e_local.py`)

The proof that the whole contract works on **real infra** — not mocks:

1. picks a free API port (`e2e_local.py:42`), starts uvicorn and a **real** Celery worker
   (`--pool=solo`) with an env pointing at Postgres on port **5433** and the stock Redis;
2. runs `alembic upgrade head` on Postgres (proving the 0002→0001 chain);
3. seeds a tenant + order via the dev `orders` stand-in;
4. `POST /api/v1/research/jobs` → worker consumes over Redis → polling
   `GET /jobs/{id}` until terminal;
5. reports per-document statuses and **verifies the blob artifacts on disk**
   (sha256 + size match the DB row).

Port 5433 vs the compose default 5432 is the `dc.e2e.yml` override from the sandbox shell
(Native Postgres on 5432 had an unknown password; the Docker `db` runs on 5433 for E2E).
The sandbox's expected degradations (FEMA/clerk TLS-reset/403) are deliberate — each source
falls back to a link/retryable error, the job reaches a terminal state, and the evidence set is
still defensible. Last run: job `a097690c…` → `completed`, 6 fetched / 1 uploaded / 0 failed.

## 3. Production — AWS us-east-1 (from `mapperty-reference`'s `deploy-dev.yml`)

The parent deploys the merged stack to **AWS `us-east-1`**:

- **ECR** `quickplot-api` (image push, prod account) → **ECS cluster** `quickplot-dev` with two
  services — `quickplot-dev-api` and `quickplot-dev-worker`; API stores are:
  `APP_SECRET_KEY`, `COGNITO_CLIENT_SECRET`, `STRIPE_SECRET_KEY` in Secrets Manager
  (`deploy-dev.yml:15-28`).
- **Cognito** user pool `us-east-1_EHikamkop` guards the API (the auth headers the engine's
  `dependencies.py` placeholder will replace from).
- **`alembic upgrade head` runs as a one-off ECS task inside the VPC** (`deploy-dev.yml:190-265`)
  — the migration chain ships with the image, then the service comes up.

This is the doc-defining point: **a US-region host satisfies FEMA/county geo-blocks natively.**
Outbound calls originate from a US IP automatically; no VPN, no fixed IP, no per-machine setup
(`poc01/SurveyResearch/docs/DOCKER_AWS_DEPLOY.md:17-21`).

## 4. US egress — the decision, honestly documented

**Production:** native. See §3.

**Dev on a personal PC:** the developer's PC needed a fixed **US VPN IP** because FEMA and many
appraiser/clerk endpoints geo-block non-US IPs. That was the POC workaround, not a product
requirement. Supporting files in the POC repo:

- `docker-compose.vpn.yml` — WireGuard override (provider-agnostic; gluetun sidecar routes
  **only** the outbound research calls through a US WireGuard endpoint, leaves your LAN alone).
  Set from any provider's `.conf`: `WIREGUARD_PRIVATE_KEY/ADDRESSES/PUBLIC_KEY/ENDPOINT_IP/
  ENDPOINT_PORT`.
- `docker-compose.proxy.yml` — the same, via an HTTP forward proxy.
- `run-on-vpnbox.bat`, `reverse-tunnel.bat`, `vpn-proxy.bat`, `docs/vpn-proxy-setup.md` — the
  VPN-box script lives to tunnel the laptop's traffic until the AWS deploy existed.

**Why this matters for engineers reading this briefing:** do NOT re-introduce a VPN dependency
into the engine. The contract should treat egress as an infrastructure concern. If a future
tenant is non-US-hosted, the WireGuard/proxy overrides compose in at the infra layer — the
engine's callers keep pointing at the plain session in `services/http.py`.

## 5. Remaining real-world risks (what *still* needs engineering, not infrastructure)

1. **Shared-IP WAF/rate limiting** — QA finding **L-5**. A cloud region IP is shared by many
   users; clerk/appraiser portals WAF-block datacenter IP ranges. Expected symptoms: 403 on
   `check_url` ("opens in browser") and throttled Playwright scrapes. Mitigations are app-level
   (per-source cool-downs, backoff, honoring `Retry-After`), not re-deployments.
2. **K7-style AV on the operator's machine** blocks FEMA + some clerk/appraiser domains with a
   TLS reset (verdict `offline`). That's an AV allow-list fix, not a code fix — Connection
   Check exists precisely to surface it.
3. **Portals move** — verified URLs rot (Volusia `/or/` → `/or_m/`; Hillsborough/Lake were
   stale). `check_url` reports `broken`; the registry + `records_links.json` re-verification
   scripts (`scripts/verify_links.py`, `scripts/verify_county_portals.py`) are the sweep.

## 6. Integration checklist (deployment shape that makes all of this work)

- Static frontend mounts (`/static`, `/`, `/quickplot`) — no build step, ship the same folders.
- Alembic: drop `0002_dev_base_tables.py`, retarget `0001`'s `down_revision` onto the parent
  chain; run `upgrade head` as the one-off (already the parent's pattern).
- Worker partition: `--queues=research` matches `enqueue_research_job`; `task_acks_late` + the
  retry policy requeue on crash.
- Storage: keep `build_key()`'s "reject falsy document_id" guard; choose `local` or `s3` via
  `QP_STORAGE_BACKEND` once per deployment.