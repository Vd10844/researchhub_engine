# researchhub-engine — Complete Inventory & Assessment

Standalone FastAPI + Celery service that automates the land-survey "research set" (parcel, appraiser, deed, plat, FEMA flood, NGS control) for an order, uploads artifacts to S3, and records an audit trail. Designed to drop into the parent monolith at `app/modules/research/` unchanged. Python 3.13, SQLAlchemy 2.0, Postgres, Redis/Celery. ~236 offline tests.

---

## 1. Complete file tree

```
researchhub-engine/
├── README.md                     # what/how — 5 endpoints, run/test, layout
├── requirements.txt              # pinned to parent's pyproject (fastapi 0.111, sqlalchemy 2.0.46, celery 5.4…)
├── alembic.ini                   # script_location=backend/alembic; url set in env.py from DATABASE_URL
├── Dockerfile                    # python:3.13-slim, PYTHONPATH=/app/backend, uvicorn CMD
├── docker-compose.yml            # db(pg15) + redis(7) + api + worker(celery --queues=research)
├── dc.e2e.yml                    # compose override: db on host port 5433 (E2E)
├── .env.example                  # DATABASE_URL, S3, Redis/Celery, CORS, MAX_RETRIES, timeouts
├── .gitignore
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py             # pydantic-settings Settings (+ legacy HTTP_TIMEOUT/USER_AGENT aliases)
│   │   ├── main.py               # FastAPI app: mounts research router, health, CORS, error handlers
│   │   ├── db/
│   │   │   ├── base.py           # engine/session/DeclarativeBase (UUID PK, naming convention)
│   │   │   ├── mixins.py         # Timestamp/Audit/Tenant/SoftDelete mixins
│   │   │   └── __init__.py
│   │   ├── engine/               # ← THE SERVICE
│   │   │   ├── contracts.py      # frozen vocabulary: StepStatus, SourceOutcome, Confidence, JobState + StepResult/ResearchResult
│   │   │   ├── models.py         # ORM: research_jobs, research_documents
│   │   │   ├── schemas.py        # API request/response models + ResearchJobStatus/DocStatus/ErrorCode enums
│   │   │   ├── router.py         # /api/v1/research/* — 5 endpoints
│   │   │   ├── service.py        # ResearchService (create/get/list/retry/cancel/review/archive) + OrderData/FetchedDocument
│   │   │   ├── repository.py     # tenant-scoped queries for jobs/documents
│   │   │   ├── mappers.py        # ORM → frozen API contract (FileReference build)
│   │   │   ├── worker.py         # Celery app + research_job task (the only place the pipeline runs)
│   │   │   ├── adapters.py       # production wiring: order_provider, document_fetcher, S3 upload, evidence rows
│   │   │   ├── dependencies.py   # PLACEHOLDER auth deps (X-Actor-Id / X-Tenant-Id headers)
│   │   │   ├── errors.py         # ResearchEngineError hierarchy → HTTP status
│   │   │   ├── order_source.py   # dev/standalone Order + Tenant tables + order_provider
│   │   │   ├── evidence_source.py# dev/standalone File + OrderFile tables + create_evidence
│   │   │   └── orchestration/    # the phase-separated pipeline
│   │   │       ├── context.py    # Phase 1-3: geocode → parcel → clerk/appraiser refs → PropertyContext
│   │   │       ├── runner.py     # run_research(): wires context + steps, writes manifest/result.json
│   │   │       ├── steps.py      # build_steps(): per-doc assembly, exceptions→fallback link + ErrorInfo
│   │   │       ├── sources.py    # SourceAdapter framework + ADAPTERS registry (parcel/appraiser/deed/plat/flood/ngs/glo)
│   │   │       └── folders.py    # scratch staging folder + manifest/result writers
│   │   ├── services/             # data-source clients (the POC's battle-tested fetchers)
│   │   │   ├── geocode.py        # Census → ArcGIS → Nominatim fallback chain (keyless)
│   │   │   ├── parcel.py         # point-in-polygon parcel resolution + address-match validation (33KB)
│   │   │   ├── appraiser.py      # county Property Record Card PDF fetch
│   │   │   ├── clerk.py          # clerk/recorder official-records reference URLs + hints
│   │   │   ├── clerk_scraper.py  # Playwright deed/plat scraper (5 FL counties) (34KB)
│   │   │   ├── downloader.py     # file download + report/metadata writers (20KB)
│   │   │   ├── fema.py           # FEMA NFHL flood zone + FIRM
│   │   │   ├── ngs.py            # NOAA NGS benchmarks
│   │   │   ├── http.py           # shared requests session w/ retries
│   │   │   └── storage.py        # blob abstraction: local | s3 (QP_STORAGE_BACKEND)
│   │   └── data/                 # domain registry (POC-accumulated "source of truth")
│   │       ├── county_platforms.py  # county → appraiser/clerk platform registry (22KB)
│   │       ├── geography.py          # FIPS/county-name helpers
│   │       ├── reference.py          # RESIDENTIAL_DOCS checklist (11 doc types)
│   │       ├── states/*.py           # 50 per-state registry modules (ga/oh/tx largest; mostly data)
│   │       ├── _counties_raw.json    # 228KB raw county data (source for registry)
│   │       └── records_links.json    # 103KB deep-link registry
│   ├── alembic/
│   │   ├── env.py                # loads Base + engine.models; url from env
│   │   └── versions/
│   │       ├── 0002_dev_base_tables.py  # down_revision=None — dev stand-ins: tenants/orders/files/order_files
│   │       ├── 0001_research_tables.py  # research_jobs + research_documents (FKs → orders/tenants/files/order_files)
│   │       └── 0003_cancel_reason.py    # +cancel_reason, enum +reviewed/+archived
│   └── app/data/jobs/            # (JOBS_DIR default) runtime scratch
│
├── contracts/                    # GENERATED — do not hand-edit
│   ├── openapi.json              # frozen API (41KB)
│   └── schemas/*.json            # 20 JSON Schemas (ResearchJob, StepResult, …)
├── scripts/
│   ├── e2e_local.py              # real Postgres+Redis+worker E2E over HTTP
│   ├── export_contracts.py       # regenerates contracts/ from schemas
│   └── build_briefing_pdf.py     # renders docs/technical-briefing → PDF
├── tests/                        # ~236 offline tests
│   ├── conftest.py
│   ├── test_engine_api.py, test_engine_service.py
│   ├── test_orchestration_engine.py, test_orchestration_regression.py
│   ├── test_execution_scenarios.py (21KB), test_contract_conformance.py
│   ├── test_order_source.py, test_evidence_source.py
│   └── fixtures/poc_results/*.json  # 7 POC result.json fixtures (golden outputs)
├── docs/
│   ├── DEVELOPER_GUIDE.md, api-contract-freeze.md, job-lifecycle.md,
│   │   regression-matrix.md, result-schema.md, source-contract.md
│   └── technical-briefing/00-07*.md + technical-briefing.pdf (generated, 900KB)
├── data/                         # RUNTIME ARTIFACTS: e2e_*.log, e2e_jobs/, jobs/ (git-ignored output)
├── evidence/_qp/                 # local blob backend output (runtime)
└── .qodo/                        # Qodo agent config (not product code)
```

---

## 2. Architecture summary

**API surface** (`engine/router.py`, prefix `/api/v1/research`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/jobs` | create job (idempotent via `X-Idempotency-Key`) |
| GET | `/jobs/{id}` | poll job + per-document progress |
| POST | `/jobs/{id}/retry` | new job from failed docs (original untouched) |
| POST | `/jobs/{id}/cancel` | cancel queued/running |
| GET | `/orders/{order_id}/jobs` | job history for an order |

Responses use `{data:…}` envelope; errors `{error:{code,message}}`. Auth via `X-Actor-Id` + `X-Tenant-Id` headers (placeholder).

**Job lifecycle:** `queued → running → completed | partial | failed`, plus `cancelling → cancelled`, `reviewed → archived`. Per-document: `queued → fetching → fetched → uploading → uploaded | failed | skipped`. The worker re-reads the job each doc iteration (with `db.expire`) so an out-of-band cancel is observed mid-run.

**Orchestration pipeline** (`engine/orchestration/`) — the clean rewrite of the POC monolith, phase-separated so a single-document retry does NOT re-run geocode/parcel:
- `context.py` Phases 1-3: geocode (Census→ArcGIS→Nominatim) or parcel-ID pre-resolve → parcel resolution with address-match guard (a buffered/neighbor match is suppressed rather than shown as wrong data) → clerk/appraiser reference assembly, producing a `PropertyContext`.
- `steps.py` Phase 4: for each doc in `RESIDENTIAL_DOCS`, run its `SourceAdapter`; every exception is classified (blocked/broken/retryable) and converted to a fallback deep-link step + structured `ErrorInfo` — nothing crashes the run.
- `sources.py`: adapter registry — `ParcelAdapter, AppraiserAdapter, DeedAdapter, PlatAdapter, FloodAdapter, NgsAdapter, GloAdapter` + `register_source()` seam.
- `runner.py`: wires the two phases, builds `ResearchResult`, writes `manifest.json` + `result.json` to the scratch folder.

**Data-source clients** (`services/`): keyless/free where possible — Census/ArcGIS/Nominatim geocode, county GIS/statewide parcel, FEMA NFHL, NOAA NGS; appraiser PDF + Playwright clerk scraper (5 FL counties) are the hard-network ones. `storage.py` is a local|s3 blob abstraction.

**Models & DB** (`engine/models.py`, alembic):
- `research_jobs` (tenant/order refs, idempotency_key, requested_doc_types JSONB, status, denormalized counters, cancel_reason, callback_url) — TenantMixin/Audit/Timestamp/SoftDelete, `__versioned__` for sqlalchemy-history.
- `research_documents` (job_id CASCADE FK, order_id, doc_type, status, source_outcome, confidence, file_id/order_file_id, summary/link, provenance/warnings JSONB, retry tracking).
- Migration chain: `0002` (dev base) → `0001` (research tables) → `0003` (cancel/enum). **0001's FKs deliberately target the parent's `orders/tenants/files/order_files`**; 0002 creates minimal stand-ins so it runs standalone.

**Integration seam** — the whole design is built to be swapped in cleanly (`adapters.py`, `order_source.py`, `evidence_source.py`, `dependencies.py`): the service is dependency-injected (`order_provider`, `document_fetcher`, `enqueue`), and each seam has a one-line swap documented in its docstring.

**Deployment/egress:** Docker (api+worker+pg+redis), or AWS `us-east-1` ECS in the parent (a US region satisfies FEMA/county geo-blocks natively — no VPN in prod). Local uses `Base.metadata.create_all` (SQLite/Postgres); prod uses alembic.

---

## 3. File-by-file: needed for production vs POC cruft

**Core engine — all production-needed, clean:** `contracts.py, models.py, schemas.py, router.py, service.py, repository.py, mappers.py, worker.py, errors.py`, all of `orchestration/*`, `db/*`, `config.py`, `main.py`. Well-documented, tenant-scoped, DI-tested. No dead code of note.

**Integration shims — production-needed but designed to be REPLACED at merge** (each says so in its docstring):
- `engine/dependencies.py` — placeholder header auth; swap for `identity/dependencies.get_current_user` + `get_current_tenant_id`.
- `engine/order_source.py` — dev `Order`/`Tenant` tables + `order_provider`; swap for a reader over parent `orders`.
- `engine/evidence_source.py` — dev `File`/`OrderFile` tables + `create_evidence`; swap for parent `evidence`.
- `adapters.py:order_provider` — thin indirection over the above (one-line swap).
- alembic `0002_dev_base_tables.py` — **drop at integration** and retarget `0001.down_revision` onto the parent's chain head.

**Minor cruft / smells (non-blocking):**
- `config.py` keeps duplicate `HTTP_TIMEOUT`/`USER_AGENT` module-level aliases "the legacy service modules import directly" — a small POC coupling to clean up.
- `steps.py` has a `_CTX_STACK_REMOVED = None  # noqa: F841` leftover marker (dead).
- `main.py` lifespan imports `order_source`/`evidence_source` to register dev tables — local-only; must be gated/removed in parent.
- `services/*` are POC-origin (heaviest: `parcel.py` 33KB, `clerk_scraper.py` 34KB, `downloader.py` 20KB) — functional and battle-tested, but the largest, least-uniform code; carry hardcoded per-county/portal specifics (by design).
- `data/states/*` (50 files) + `_counties_raw.json`/`records_links.json` are domain DATA, not logic — README warns "do not regenerate blindly."

**Not product code / runtime artifacts (safe to ignore or gitignore):** `data/` logs+jobs, `evidence/_qp/`, `jobs/`, `.qodo/`, `.pytest_cache/`, `docs/technical-briefing/technical-briefing.pdf` (generated), `contracts/*` (generated from schemas).

---

## 4. Integration signals (how it plugs into the parent)

- **Path already parent-shaped:** router prefix `/api/v1/research` (parent mounts under `/v1`).
- **Tables named for the parent:** `research_jobs`/`research_documents` FK to `orders.id`, `tenants.id`, `files.id`, `order_files.id` — the parent's real tables.
- **Header identity matches parent:** engine's `X-Tenant-Id`/`X-Actor-Id` placeholder maps 1:1 to the parent's Cognito-JWT + `X-Tenant-ID` model.
- **Contract frozen & documented:** `contracts/openapi.json`, `docs/api-contract-freeze.md`, `docs/technical-briefing/*` explicitly describe the drop-in plan ("When ready it drops into the parent repo's `app/modules/research/` unchanged").
- **Envelope + versioning conventions** (`{data}`/`{error}`, `__versioned__`, UUID PK, TenantMixin) mirror the parent's.

---

## 5. Production-readiness & cruft verdict

**Solid / production-grade:** the engine core (contracts, models, service, worker, orchestration, repository, mappers, errors) — clean, layered, DI, ~236 offline tests + real-infra E2E, frozen documented contract, thoughtful cancel/idempotency/retry semantics, exhaustive technical briefing.

**Deliberate standalone-only scaffolding (remove/swap at merge, not "bugs"):** `dependencies.py`, `order_source.py`, `evidence_source.py`, alembic `0002`, and the `main.py` dev-table registration. All flagged in-code.

**Real watch-items for the merge (see parent report):** the parent has **no `orders` table and no `order_files` table yet**, and its `evidence.File` schema differs from the engine's stand-in (`file_path`+`status` vs `content_key`+`size`+`sha256`, no OrderFile join). These are the substantive integration gaps, not cruft.

**Low-value cruft:** duplicate config aliases, one dead marker line, generated PDF/contracts in-tree, large POC service files with embedded county specifics. None block integration.
