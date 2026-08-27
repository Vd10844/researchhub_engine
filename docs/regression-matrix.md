# Regression Matrix — POC Behavior vs the Engine Contract

Validates that the orchestration refactor preserved every behavior the POC
frontend depends on, and pins the fields that must never change. The automated
version lives in `tests/test_orchestration_regression.py` (54 assertions) and
`tests/test_orchestration_engine.py` (12 scenario tests).

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
|---|---|
| `StepStatus` | `ok` `link` `empty` `error` (never removed) |
| `ResearchJobStatus` | `queued running completed partial failed cancelling cancelled` |
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

Re-export after any schema change: `scripts/export_contracts.py` (writes
`contracts/openapi.json` + `contracts/schemas/*.json`). The docs in this folder
and the OpenAPI they describe are the freeze — schema edits require this checklist
to re-run green.