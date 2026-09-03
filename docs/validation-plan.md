# Validation & Test Plan — ResearchHub Engine

Companion to `docs/regression-matrix.md`, `docs/api-contract-freeze.md`,
`docs/source-contract.md`, and `docs/job-lifecycle.md`. Those docs freeze the
contract and prove the orchestration refactor preserved POC behavior. This doc
answers the next question: **what the 309-test suite does *not* yet exercise,
and how to close each gap.**

## Where the suite stands today

The current 309 tests are strong at what they cover: contract conformance
(106 fixture cases), the API surface (TestClient), the service state machine,
`classify_exception`, terminal-status resolution, and the Celery task *body*
run in-process. That is excellent unit- and contract-level coverage.

But every test shares one boundary, stated plainly in the suite itself
(`test_orchestration_engine.py`): *"The real adapters that touch the network
(geocode, flood, ngs, clerk scrape) are replaced with registered fakes."*
Everything outside the pure Python control flow is faked:

| Real thing | How it's stubbed in the suite | Consequence |
|---|---|---|
| Postgres | SQLite in-memory + `visit_JSONB = visit_JSON` monkeypatch | JSONB, enum `ALTER TYPE`, row locking, real UUID type never run in CI |
| Redis + Celery broker | `CELERY_TASK_ALWAYS_EAGER=true`, task body called directly | real queueing, `acks_late`, retry/`countdown`, prefetch never run |
| S3 | `file_storage=MagicMock()` | upload, re-hash-at-upload, upload-failure→`failed` never run |
| Data sources (geocode, parcel GIS, FEMA, NGS, clerk scrape, appraiser, downloader) | registered `FakeAdapter`s | `services/*.py` (~100 KB incl. `clerk_scraper.py` 34 KB, `parcel.py` 33 KB, `downloader.py` 20 KB) has effectively **no direct test coverage** |
| Playwright browser | not exercised | the clerk deed/plat scraper is untested end to end |

Two structural gaps compound this:

- **There is no CI in the repo.** No `.github/workflows/`. The freeze docs say
  the 309 tests and `export_contracts.py` are "part of CI" and "must exit 0,"
  but nothing enforces that automatically. The gate is documented, not wired.
- **The only real-infra path is a manual script** (`scripts/e2e_local.py`) that
  a human runs on demand. It is good, but it is not a gate and it is not asserted
  in CI.

Net: the *shape* of the system is very well tested; the *behavior against real
Postgres, real S3, and real/recorded source responses* is not tested at all.

---

## Priority 0 — cheap, high-value, do these first

### 0.1 Tenant-isolation (security) tests

`repository.get(...)` is tenant-scoped, but nothing proves a tenant *cannot*
read another tenant's job. This is the highest-severity untested invariant:
a missing `tenant_id` filter anywhere would leak jobs across customers and no
test would notice.

How:

```python
# tests/test_tenant_isolation.py
def test_get_job_is_scoped_to_tenant(test_db):
    svc = service_with()
    job = svc.create_job(test_db, tenant_id=TENANT_A, actor_id=ACTOR_ID,
                         order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None)
    with pytest.raises(JobNotFoundError):
        svc.get_job(test_db, tenant_id=TENANT_B, job_id=job.id)

def test_list_order_jobs_never_crosses_tenants(test_db): ...
def test_cancel_retry_reviewed_archive_reject_foreign_tenant(test_db): ...
```

Add the same assertion at the **HTTP layer** with a second set of
`X-Tenant-Id`/`X-Actor-Id` headers, so the router's dependency wiring is proven
too, not just the service. Parametrize across all five endpoints.

### 0.2 A Postgres-backed test tier  ✅ DONE

The SQLite substitution hides real bugs: JSONB predicate queries, the enum
`ALTER TYPE ... ADD VALUE` from `0003_cancel_reason`, `SELECT ... FOR UPDATE`
job claiming, and transaction isolation all behave differently (or don't exist)
on SQLite. Keep the fast SQLite suite as the default, and add a Postgres tier
that runs the same service/worker tests against a real container.

How — `testcontainers` (spins up Postgres per session, no compose needed):

```python
# tests/conftest_pg.py  (opt-in via marker)
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:15") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg")

@pytest.fixture
def pg_db(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    # run alembic upgrade head against pg_url, then yield a SessionLocal bound to it
```

Mark these `@pytest.mark.pg` and run them as a separate job:
`pytest -m pg`. Re-run at minimum the worker-body scenarios
(`test_execution_scenarios.py`) and the counters/terminal-status tests on real
Postgres — those are where SQLite most flatters you.

### 0.3 Migration round-trip + model/migration parity  ✅ DONE

`e2e_local.py` runs `alembic upgrade head` once. Nothing tests **downgrade**, or
that the ORM models still match the migration chain (the classic drift bug: a
column added to `models.py` but never migrated).

How (needs the Postgres tier from 0.2):

```python
@pytest.mark.pg
def test_migrations_upgrade_then_downgrade_clean(alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")   # proves every down_revision works
    command.upgrade(alembic_cfg, "head")

@pytest.mark.pg
def test_models_match_migrations(alembic_cfg):
    # after upgrade head, autogenerate must produce an EMPTY diff
    from alembic.autogenerate import compare_metadata
    diff = compare_metadata(context, Base.metadata)
    assert diff == [], f"models drifted from migrations: {diff}"
```

This is especially worth it here because your chain is unusual
(`0002` base shim ← `0001` ← `0003`) and `0003` does an enum `ALTER TYPE`,
which is exactly the kind of thing that silently no-ops on SQLite.

### 0.4 Contract-drift gate (make the freeze real)

The freeze says the committed `contracts/openapi.json` is the source of truth and
`export_contracts.py` "must exit 0," but nothing fails when someone edits
`schemas.py` and forgets to re-export.

How — a test that regenerates in a temp dir and diffs against the committed files:

```python
def test_committed_contracts_match_live_schema(tmp_path):
    subprocess.run([sys.executable, "scripts/export_contracts.py", "--out", tmp_path], check=True)
    for f in (tmp_path / "openapi.json", *(tmp_path / "schemas").glob("*.json")):
        committed = Path("contracts") / f.relative_to(tmp_path)
        assert json.loads(f.read_text()) == json.loads(committed.read_text()), \
            f"{committed} is stale — run scripts/export_contracts.py"
```

(If `export_contracts.py` doesn't take `--out`, add it — a few lines — so it can
write to a scratch dir for the test.)

### 0.5 Wire CI (nothing runs automatically today)

Everything above is worthless if it only runs when someone remembers. Add
`.github/workflows/ci.yml`:

- Job **unit**: `pip install -r requirements.txt` → `pytest tests -q` (the fast
  SQLite suite) → fail under a coverage threshold (see 3.5).
- Job **contract**: run 0.4 + assert `regression-matrix.md` counts still match.
- Job **integration**: `services: postgres, redis` → `pytest -m pg` → run
  `scripts/e2e_local.py` and assert exit 0.
- Job **security**: `pip-audit`, `bandit -r backend/app`, `trivy image` on the
  built container (see 3.4).

Cache the pip and Playwright installs. Gate merges on unit + contract; let
integration/security run on push to main + nightly if they're slow.

---

## Priority 1 — the real risk: the source/scraper layer

This is where the untested surface is largest and the production failures will
actually come from. External sites change HTML, add WAFs, rotate URLs — and your
suite would stay green through all of it.

### 1.1 Recorded-response tests for each source adapter  ✅ DONE

Don't hit the live network in CI (flaky, rate-limited, WAF'd). **Record once,
replay forever.** Capture a real HTTP exchange per source and per interesting
shape (hit, empty, 403 WAF, 404, 5xx, timeout), then assert the adapter's
parse + `classify_exception` mapping.

How — `respx` (for `httpx`) or `vcrpy` (for `requests`); you use both clients:

```python
# tests/adapters/test_parcel_adapter.py
import respx, httpx

@respx.mock
def test_parcel_arcgis_hit_parses_situs_and_acreage():
    respx.get(url__regex=r".*/arcgis/.*/query").mock(
        return_value=httpx.Response(200, json=load_cassette("parcel_fulton_hit.json")))
    fs = ParcelAdapter().fetch(ctx, docs_dir)
    assert fs.status == StepStatus.ok
    assert fs.situs and fs.land_acres > 0

@respx.mock
def test_parcel_waf_403_becomes_blocked_link():
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(403))
    # fetch raises → runner falls back → outcome == blocked, retryable False
```

Build a `tests/cassettes/` dir. The **richest raw material you already have** is
`tests/fixtures/poc_results/*.json` and `evidence/_qp/` — mine the captured POC
runs for real source payloads and turn them into cassettes. Prioritize by blast
radius: `parcel.py` and `clerk_scraper.py` first (biggest + most brittle), then
`geocode`, `fema`, `downloader`, `ngs`, `appraiser`.

Also add a parse-level regression: feed each saved source payload through the
adapter and pin the extracted fields, so a refactor of the 34 KB
`clerk_scraper.py` can't silently change what it pulls out.

### 1.2 S3 / storage tests with `moto`  ✅ DONE

`file_storage` is a `MagicMock`, so the upload path, the re-hash-at-upload
(provenance sha256), and the "S3 upload error → doc `failed`" branch from
`job-lifecycle.md` §3 are never executed.

How:

```python
import boto3, moto

@moto.mock_aws
def test_upload_records_matching_sha256_and_file_reference():
    boto3.client("s3").create_bucket(Bucket="test-artifacts")
    # run a full-success worker job against real (moto) S3
    # assert FileReference.sha256 == sha256 of the staged bytes
    # assert the object actually exists in the bucket

@moto.mock_aws
def test_upload_failure_marks_document_failed():
    # no bucket / access denied → doc.status == failed, retryable set
```

### 1.3 Data-registry integrity tests

`README.md` calls `data/county_platforms.py` (22 KB) and the ~50
`data/states/*.py` modules "load-bearing… the source of truth." A typo in any of
them (bad URL, missing key, wrong FIPS) ships silently. A cheap parametrized
sweep catches registry rot:

```python
import importlib, pkgutil
import app.data.states as states

@pytest.mark.parametrize("mod", [m.name for m in pkgutil.iter_modules(states.__path__)])
def test_every_state_module_imports_and_is_well_formed(mod):
    m = importlib.import_module(f"app.data.states.{mod}")
    for county in m.COUNTIES:            # adapt to the real structure
        assert county["fips"].isdigit() and len(county["fips"]) == 5
        for url in urls_in(county):
            assert url.startswith("https://")

def test_county_platforms_registry_is_consistent(): ...   # no dup keys, required fields present
```

### 1.4 Clerk scraper (Playwright)  ✅ DONE

The Playwright deed/plat scraper needs a browser and is entirely untested.
Two layers:

- **Offline parse test:** save the clerk result page HTML as a fixture, feed it
  to the scraper's parse function, pin the extracted document links. No browser
  needed — this is where most scraper bugs live.
- **Live smoke (nightly, non-gating):** actually drive Playwright against one or
  two known-good counties; allow it to fail to a fallback link (that's the
  designed behavior under WAF) but alert if the *parse* breaks. Keep it out of
  the merge gate — it will be flaky by nature.

---

## Priority 2 — robustness, concurrency, ops

### 2.1 Concurrency / race conditions (needs Postgres)

SQLite + `StaticPool` can't test the races that matter in production:

- **Idempotency race:** two simultaneous `POST /jobs` with the same
  `(tenant_id, X-Idempotency-Key)` must yield one job, not two. Test with two
  threads against Postgres.
- **Worker double-claim:** two workers pulling the same queued job — only one
  should transition `queued → running` (this is what `SELECT ... FOR UPDATE`
  / the claim guard is for). SQLite can't exercise it.
- **Cancel-vs-complete race** on real row locking, not the `expire_all()`
  simulation the current thread test uses.

### 2.2 Negative / malformed API inputs  ✅ DONE

The suite tests empty `document_types` (nice) but not the rest of the hostile
surface: malformed UUID in the path, missing `X-Tenant-Id`/`X-Actor-Id`,
unknown `doc_type` enum value, unknown/extra body fields, wrong content-type,
oversized payload. Each should return the `ErrorEnvelope` shape with a
`ResearchErrorCode`, never a traceback. Parametrize it.

### 2.3 `callback_url` delivery  ✅ DONE

`job-lifecycle.md` §8 promises an optional job-summary POST on completion, with
"delivery failures logged, not fatal." Untested. Add a test with a `respx`-mocked
callback endpoint: assert the payload shape on success, and assert a 500/timeout
from the callback does **not** fail the job.

### 2.4 Property-based tests (Hypothesis)

A few high-leverage targets where example-based tests miss edge cases:

- `classify_exception`: generate arbitrary HTTP status codes and assert the
  outcome/retryable mapping is total and never raises.
- Geography/FIPS resolution and address normalization: fuzz with odd casing,
  unicode, empty components; assert no crash and stable output.

### 2.5 Load / performance smoke

Not a merge gate, but you'll want a number before this "drops into the parent
repo." Run `locust` or `k6` against the `e2e_local` stack: N concurrent
`POST /jobs` + poll, watch worker throughput, DB connection-pool exhaustion, and
memory with large PDF downloads. Establish a baseline and a regression alarm.

### 2.6 Security scanning

- `pip-audit` (you pin exact versions — a pinned CVE stays pinned until someone
  looks): fail CI on a known-vuln dependency.
- `bandit -r backend/app`: catches the usual (subprocess, unsafe deserialization,
  requests without timeout — relevant given the scraper layer).
- `trivy image` on the built container + `trivy fs` on the repo.
- `gitleaks` / secret scan — you have `.env.example` and boto3; make sure no real
  keys ever land.

### 2.7 Live-source canary + monitoring (operational validation)

CI can't tell you a county flipped its GIS endpoint or added Cloudflare. A small
scheduled job (outside CI) that runs one real fetch per source against a known
address and alerts on a *parse* regression (not on an expected WAF fallback) is
the only thing that catches source drift before your users do. This is the
production-validation counterpart to the offline cassette tests in 1.1.

### 2.8 Measure coverage and set a floor  ✅ DONE

You can't manage what you don't measure. Run:

```bash
.venv/Scripts/python -m pytest tests --cov=app --cov-report=term-missing --cov-report=html
```

This will confirm the picture in the table above — expect `app/services/*` and
the Playwright path to show near-zero line coverage while `app/engine/*` shows
high coverage. Then add `--cov-fail-under=<N>` to CI, and consider a
per-package floor so the well-tested engine can't mask the untested services.

---

## Suggested sequencing

1. **Week 1 (gates):** 0.5 CI skeleton, 0.4 contract-drift, 0.1 tenant isolation,
   2.8 coverage baseline. Cheap, and they stop regressions immediately.
2. **Week 2 (real infra):** 0.2 Postgres tier, 0.3 migrations, 1.2 S3/moto,
   2.1 concurrency. This is where SQLite has been flattering you.
3. **Week 3 (the source layer):** 1.1 cassette tests (parcel + clerk first),
   1.3 registry integrity, 1.4 scraper parse tests. The biggest real-world risk.
4. **Ongoing:** 2.7 canary, 2.5 load, 2.6 security, 1.4 live smoke — nightly /
   non-gating.

The one-line summary: your **contract and control-flow** testing is genuinely
strong; your **infrastructure and data-source** testing is absent. Close it in
that order — gates, then real infra, then the scrapers.
