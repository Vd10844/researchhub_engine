# Result Schema — Research Engine

The canonical output of a research run. This is the contract the frontend team
codes against. Two documents define it:

- `backend/app/engine/contracts.py` — `ResearchResult`, `StepResult`, and the
  vocabulary enums (the schema of record),
- this document — the human explanation of what may and may not change.

## 1. Field stability model

Every field is one of:

| marker | meaning |
|---|---|
| **frozen** | shipped in the POC frontend. Meaning, type and presence will NEVER change. New values may be added to enums, but old values keep identity. |
| **additive** | new in the engine. May appear alongside frozen fields. Do not build logic that requires them until they are promoted; they populate `default` and degrade gracefully. |

The conformance test `tests/test_orchestration_regression.py` enforces: all
frozen fields are present on the models, POC fixtures still parse, and fixture
statuses stay within `ok/link/empty/error`.

## 2. Top level — `ResearchResult`

**Frozen** (byte-for-byte POC parity):

| field | type | notes |
|---|---|---|
| `job_number` | str | Parcel ID when known, else passed job number |
| `order` | str | order number → Parcel ID → job folder name |
| `parcel_id` | str | the key that drives deed/plat/appraiser search |
| `address` | str | search address (post parcel-ID rewrite = situs) |
| `matched_address` | str | normalized/geocoded address |
| `county`, `county_fips`, `state` | str | resolved geography |
| `lat`, `lon` | float? | null when geocode failed entirely |
| `name` | str | job folder name |
| `geocoder` | str | `census` / `arcgis` / `nominatim` / `parcel-id` |
| `map_links` | list[{label,url}] | verification links (Google/Bing/appraiser) |
| `folder` | str | job-level staging folder |
| `steps` | list[StepResult] | the documents |
| `warnings` | list[str] | user-facing, deduplicated, ordered |

**Additive**:

| field | type | notes |
|---|---|---|
| `completed_utc` | str? | ISO-8601 when the run finished |
| `job_state` | `JobState` | `completed` for a successful local run (persisted lifecycle lives on the DB row — see job-lifecycle.md) |
| `docs_dir` | str? | research staging dir containing `documents/` (internal; blob upload reads from here) |
| `survey_type` | str | survey type passed into the run |

## 3. Per-document — `StepResult`

**Frozen** (all present in POC `result.json` step cards):

| field | type | notes |
|---|---|---|
| `key` | str | `parcel, appraiser, deed, plat, adjoiners, easements, prior_survey, flood, benchmarks, glo, condo` |
| `label` | str | card title |
| `requirement` | str | `mandatory` / `conditional` / `recommended` |
| `condition` | str | when the doc is required |
| `description` | str | what it is and why it matters |
| `summary` | str | one-line outcome — always safe to render |
| `status` | `ok` / `link` / `empty` / `error` | frozen vocabulary |
| `link` | str | fallback deep link (mandatory, may be `""`) |
| `link_label` | str | button text |
| `source_url` | str | primary source URL |
| `saved_file` | str? | generated metadata JSON for the step |
| `data` | any | raw payload — never rendered directly |
| `downloaded` | list[str] | filenames staged in `documents/` |
| `situs` / `land_sqft` / `land_acres` / `address_match` | parcel step only | |

**Additive** (engine classification riding beside the frozen status):

| field | type | notes |
|---|---|---|
| `source_outcome` | `SourceOutcome` | why: `auto`/`link_only`/`blocked`/`broken`/`retryable`/`manual_review` |
| `confidence` | `Confidence` | high/medium/low/none |
| `provenance` | list[ProvenanceRecord] | files + sources + digests + UTC |
| `warnings` | list[str] | per-step warnings |
| `error` | `ErrorInfo?` | code + message + retryable when the source failed |

## 4. Stable-for-frontend rules

1. `status` drives the card: `ok` green, `link` blue action, `empty`/`error` grey.
   `error` is reserved for unreachable sources; its explanation is a
   human-readable `summary` (never a traceback).
2. Never render `data` directly — it is schema-per-source and can change shape.
3. `additive` fields degrade to their defaults when absent (POC data has none of
   them) — defensive frontend must not require them.
4. `key` order follows `RESIDENTIAL_DOCS` and is stable; do not reorder cards by
   name — rely on the array position.

## 5. Where the schema lives

`contracts.py` is the single source of truth — do not fork these models in the
router or the DB layer. The API envelope differs (see `engine/schemas.py`):
`{data: …}` success / `{error: …}` failure, with per-document status duplicated
onto `ResearchDocument` for polling.