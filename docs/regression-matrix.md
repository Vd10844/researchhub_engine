# Regression Matrix — POC Behavior vs the Engine Contract

Validates that the orchestration refactor preserved every behavior the POC
frontend depends on, and pins the fields that must never change. The automated
version lives in `tests/test_orchestration_regression.py` (54 assertions),
`tests/test_orchestration_engine.py` (12 scenario tests),
`tests/test_contract_conformance.py` (141 fixture cases, incl. requirement
domain / map_links / warnings checks) and `tests/test_execution_scenarios.py`
(36 worker-path + boundary tests, incl. worker INTERNAL_ERROR, callback
delivery+failure, provenance/warnings propagation, retry/review/archive
transitions, SSLError classification).
Also covered: `tests/test_tenant_isolation.py` (10 cross-tenant + soft-delete
security tests), `tests/test_auth_dependencies.py` (6 missing/invalid header
401 boundary tests), `tests/test_engine_api.py` (18 API tests, incl.
idempotency, 422 validation, error-envelope shape, health). Full suite:
**305 tests**, all offline.

## 1. Validation checklist

| # | check | automated where |
|---|---|---|
| 1 | Every saved POC `result.json` parses into the new `ResearchResult`/`StepResult` models unchanged | regression `TestFixtureContractCompatibility` |
| 2 | Fixture step keys == reference registry keys (11/11, same order) | regression `test_step_keys_match_reference_set` |
| 3 | Fixture statuses stay in `ok / link / empty / error` | regression + conformance `test_status_values_valid` |
| 4 | Every fixture step key has a registered source adapter | regression `test_every_fixture_step_key_has_a_registered_adapter` |
| 5 | Frozen top-level (16 fields) + frozen step (17 fields) present on the models | regression `TestStableFrontendFields` |
| 6 | New runner reproduces the 11-key set in declared order | regression `test_runner_11_step_order` |
| 7 | No-source-match → parcel degrades to link (no neighbor data shown) | engine `TestNoSourceMatch` |
| 8 | Partial failure → one ok + one broken in one run, both steps present | engine `TestPartialFailure` |
| 9 | Blocked source (403) → fallback link + `error.code` + `retryable=False` | engine `TestBlockedSource` |
| 10 | Valid fallback flow → connection error surfaces deep link + `retryable=True` | engine `TestValidFallback` |
| 11 | Job completion → runner persists `manifest.json` + `result.json`, `job_state=completed` | engine `TestJobCompletion` |
| 12 | `include=[...]` fetches ONLY the requested documents (no work for others) | engine `TestIncludeFiltering` |
| 13 | Worker full success → job `completed`, docs `uploaded`, `FileReference` populated | scenarios `test_worker_full_success_resolves_completed_with_file_reference` |
| 14 | Worker partial failure → job `partial`, per-doc ok/failed + structured error | scenarios `test_worker_partial_failure_resolves_partial_with_error_details` |
| 15 | Worker all-failed → job `failed`; zero-docs job → `failed` | scenarios `test_worker_all_failed_resolves_failed` + `test_terminal_zero_docs_is_failed` |
| 16 | Cancel mid-run → `running → cancelling`, worker drains, resolves `cancelled` | scenarios `test_worker_observes_cancelling_mid_run_and_drains`; API `test_cancel_records_reason_roundtrip` |
| 17 | `CancelJobRequest.reason` is persisted, not dropped | service `test_cancel_queue_stores_reason` / `test_cancel_running_job_goes_cancelling_and_records_reason` |
| 18 | `manual_review` outcome reachable (buffered parcel match → hint flag → outcome) | scenarios `test_manual_review_outcome_reachable_for_buffered_parcel` |
| 19 | `classify_exception` HTTP branching: 401/403/406/429 blocked, 404/410/5xx broken, timeout retryable | scenarios `TestClassify*` row |
| 20 | Fallback raising → last-resort blank link + `error.code`, never a traceback | scenarios `test_fallback_internal_raise_yields_last_resort_link` |
| 21 | `reviewed`/`archived` reachable statuses (service transitions, persisted enum) | service `test_mark_reviewed_from_completed` / `test_archive_only_from_reviewed` |
| 22 | `GET /orders/{id}/jobs` returns the compact `ResearchJobSummary` list (no doc array) | API `test_list_order_jobs_returns_compact_summaries` |
| 23 | `GET /jobs/{id}` full JSON: 17 top-level + 16 per-doc keys with promise defaults | API `test_get_job_full_contract_json` |

## 1b. Contract-oddity fix log (this wave)

The freeze audit flagged five declared-but-not-honored contract points. Each was
fixed in source and pinned by a test that reproduces the old behavior:

| # | oddity (before) | fix (after) | test |
|---|---|---|---|
| F1 | `CancelJobRequest.reason` accepted, then dropped | `research_jobs.cancel_reason` column + schema + mapper + service stores it (`0003_cancel_reason`) | API `test_cancel_records_reason_roundtrip`, service `test_cancel_queue_stores_reason` |
| F2 | `cancelling` defined but never set | queued→`cancelled` directly; running→`cancelling`; worker re-reads per doc (`db.expire` after each commit) and `resolve_job_terminal_status` maps `cancelling→cancelled` | scenarios `test_worker_observes_cancelling_mid_run_and_drains` + `test_worker_skips_delivered_after_cancel` |
| F3 | `manual_review` outcome unreachable | `FetchedSource.manual_review` hint; ParcelAdapter flags buffered matches; `_outcome_for`/`_default_confidence` honor it | scenarios `test_manual_review_outcome_reachable_for_buffered_parcel` |
| F4 | `ResearchJobSummary` unused; list returned full jobs | router list endpoint now returns `DataEnvelope[list[ResearchJobSummary]]` via `to_job_summary_schema` | API `test_list_order_jobs_returns_compact_summaries` |
| F5 | `reviewed`/`archived` absent from API `ResearchJobStatus` / persisted enum | added to enum (API + model) + `ALTER TYPE` in `0003_cancel_reason` + `mark_reviewed`/`archive_job` transitions | service `test_mark_reviewed_*` / `test_archive_*` |

Migration chain: `down_revision = "0001_research_tables"` ← `0003_cancel_reason`
(0001 keeps `down_revision = "0002_dev_base_tables"`).

## 2. Fixture coverage (the 7 captured POC jobs)

All fixtures are real POC runs re-validated against the new contract on every
test run. Status distribution across their 11 steps:

| fixture (county / state) | parcel ID | ok | link | empty | warnings |
|---|---|---|---|---|---|
| Franklin OH · 010-067474 | Y | 3 | 8 | 0 | 0 |
| Houston GA · unnamed | N | 0 | 10 | 1 | 2 |
| Fulton GA · 14 007700061068 | Y | 3 | 8 | 0 | 0 |
| Cobb GA · 16122000330 | Y | 3 | 8 | 0 | 0 |
| Houston GA · unnamed | N | 0 | 11 | 0 | 1 |
| Polk FL · 262828612000000060 | Y | 3 | 8 | 0 | 0 |
| Franklin OH · 610-205505 | Y | 2 | 8 | 1 | 0 |

Observed POC states exercised by the corpus: **auto-fetch `ok`**, **link-only
fallback**, **`empty`** (ngs/benchmarks), **no-parcel-match with warnings**.
Not yet in the corpus: an `error` step fixture (POC never emitted one — blocked
sources were classified through the same link fallback; engine now carries the
classification additively in `source_outcome`/`error`).

## 3. Field freeze

`docs/result-schema.md` defines frozen vs additive. The matrix below is the
POC → engine mapping that must never regress.

### Top level

| POC field | engine field | status |
|---|---|---|
| `job_number` `order` `parcel_id` `address` `matched_address` | `ResearchResult` same name | **frozen** |
| `lat` `lon` | same | **frozen** (nullable) |
| `county` `county_fips` `state` `geocoder` | same | **frozen** |
| `name` `folder` `map_links` `steps` `warnings` | same | **frozen** |
| — | `completed_utc` `job_state` `docs_dir` `survey_type` | additive |

### Per step

| POC field | engine field | status |
|---|---|---|
| `key` `label` `requirement` `condition` `description` `summary` `status` | `StepResult` same | **frozen** |
| `link` `link_label` `source_url` `saved_file` `data` `downloaded` | same | **frozen** |
| `situs` `land_sqft` `land_acres` `address_match` | same (parcel step) | **frozen** |
| — | `source_outcome` `confidence` `provenance` `warnings` `error` | additive |

### Vocabulary freeze

| enum | values guaranteed |
|---|---|---|
| `StepStatus` | `ok` `link` `empty` `error` (never removed) |
| `ResearchJobStatus` | `queued running completed partial failed cancelling cancelled reviewed archived` |
| `ResearchDocStatus` | `queued fetching fetched uploading uploaded failed skipped` |

## 4. API contract freeze

The `/api/v1/research/*` surface (OpenAPI exported):

| endpoint | verb | shape |
|---|---|---|
| `/api/v1/research/jobs` | POST | `CreateResearchJobRequest` → `DataEnvelope[ResearchJob]` |
| `/api/v1/research/jobs/{id}` | GET | `DataEnvelope[ResearchJob]` |
| `/api/v1/research/jobs/{id}/retry` | POST | `DataEnvelope[ResearchJob]` |
| `/api/v1/research/jobs/{id}/cancel` | POST | `DataEnvelope[ResearchJob]` |
| `/api/v1/research/orders/{order_id}/jobs` | GET | `DataEnvelope[list[ResearchJobSummary]]` |
| any failure | — | `ErrorEnvelope{error:{code,message,details?}}` |

Additive-with-default fields on `ResearchJob`/`ResearchJobSummary` (safe to ship
alongside the frozen ones): `cancel_reason` (null unless cancelled with a reason).
`ResearchJobStatus` now includes `reviewed`/`archived` as valid returned values.

Re-export after any schema change: `scripts/export_contracts.py` (writes
`contracts/openapi.json` + `contracts/schemas/*.json`). The docs in this folder
and the OpenAPI they describe are the freeze — schema edits require this checklist
to re-run green.