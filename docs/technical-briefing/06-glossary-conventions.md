# 06 — Glossary & Conventions (every team, quick reference)

The words, variable names, and rules everyone must use the same way. This is the single
dictionary; if a term isn't here, it was probably renamed or doesn't exist.

## 1. Status vVocabulary (FROZEN — never change meaning)

### Document step statuses (what the UI renders) — `engine/contracts.py:20` `StepStatus`
| Value | Meaning front-to-back |
|---|---|
| `ok` | a real artifact was fetched/saved for the step |
| `link` | no auto-fetch; a working records link is provided as the fallback |
| `empty` | queried for real, found nothing (valid answer — e.g. no NGS marks nearby) |
| `error` | the step failed and needs review/retry |

### Engine-only outcomes (why a status is what it is) — `contracts.py:28` `SourceOutcome`
`auto` · `link_only` · `blocked` (401/403/406/429 → WAF/browser-fine) · `broken` (404/410/5xx →
URL wrong) · `retryable` (timeout/connection) · `manual_review`.

### Job lifecycle — `engine/schemas.py` `ResearchJobStatus`
`queued → running → { completed | partial | failed | cancelled }` (+ `cancelling`);
terminal rules: all ok → `completed`, some failed → `partial`, none ok → `failed`
(`engine/service.py:99`).

### Per-document job statuses — `ResearchDocStatus`
`queued → fetching → fetched → uploading → uploaded → (failed | skipped)`.

### Confidence — `contracts.py:51`
`high` (address-matched parcel) · `medium` (deed/plat from a clerk scrape) · `low` · `none`.

## 2. Document keys (one canonical key per document; legacy aliases map onto them)

| Engine `doc_type` | Classic step key | UI label |
|---|---|---|
| `PARCEL_RECORD` | `parcel` | Parcel / Parcel ID |
| `PROPERTY_APPRAISER_TAX_RECORD` | `appraiser` | Appraiser / tax card |
| `DEED_SUBJECT_PARCEL` | `deed` | Deed (current vesting) |
| `RECORDED_PLAT_SUBDIVISION_MAP` | `plat` | Plat / subdivision map |
| `FEMA_FLOOD_ZONE_FIRM` | `flood` | FEMA flood map + zone |
| `NGS_CONTROL` | `benchmarks` / `ngs` | Survey control / benchmarks |
| `—` | `adjoiners` `easements` `prior_survey` `condo` | link-only clerk docs |
| `—` | `glo` | BLM GLO (always link) |

Alias normalization: `"flood"` → `FEMA_FLOOD_ZONE_FIRM` (any casing), step short-names →
canonical (`engine/service.py:248`). **Rejected doc types are a 422**, never a silent skip.

## 3. The QuickPlot lockdown variables (server-sided on purpose)

- `research_state`: `not_started` → `in_progress` → `submitted` (order moves to **field_survey**).
- Lock requires `doc_type` **and all three** confirmations `legible` + `matches_parcel` +
  `source_recorded` (`quickplot/modals.js:7`, enforced again in `router.py`).
- Locked documents: cannot be re-typed, re-fetched or deleted. **Deletes are soft** — the audit
  log keeps pointing at a real row.
- **Submit is blocked at 0 locked documents** (the lock-seal is the evidence gate).
- `X-Org-Id` / `X-Actor` headers: every `/api/v2` query is `org_id`-scoped; `org_of()` /
  `actor_of()` are the two functions to replace when real auth lands.

## 4. Geocoding / parcel rules

- **Address is the only required field.** State/County are dropdowns; the *selected* county
  wins over the geocoded one, with a mismatch warning (multi-county edge case).
- Parcel chain: county `gis_rest` (MapServer) → `STATE_PARCEL` (FeatureServer) → appraiser /
  NETROnline link.
- Point misses widen by `75 m → 150 m → 300 m` (`services/parcel.py:349`) and stop at the first
  radius with an address match; a buffered-but-unmatched hit is `buffered_match` + **`verify`**,
  never silently adopted.
- `situs_exclude` / `compose_situs` (`parcel.py:153-157`): per-county overrides so the owner
  **mailing** address never leaks into the situs used for matching.
- TxGIO StratMap: URL says `2019_…` but serves 2025 data — **do not "fix" the URL**.
- Coverage gate for new parcel services: ≥60% of a county-point grid, ≥400 features, a
  parcel-id field, and a situs-vs-mailing check (`situs_exclude` set when both present).

## 5. Storage & keys

- **Never build blob paths below `services/storage.py`.** `build_key(org, order, doc_id,
  fn)` **raises** on a falsy/`"None"` document_id (`storage.py:42-43`) — that guard is what
  fixes the "every document shared one blob" regression.
- `QP_STORAGE_BACKEND=local|s3`; a broken S3 config falls back to local with a log line —
  bad config never takes the app down.
- Scratch folders (`jobs/`, `data/`) hold staging artifacts + `manifest.json`/`result.json`;
  the blob store is the record of record.

## 6. Registry & data rules

- Merge order: hand-verified FL seed → `STATE_COUNTIES` `REGISTRY.update` → `records_links.json`
  with **`setdefault`, so curated state-module entries always win** (`data/county_platforms.py:502,522-528`).
- Add a state = add one file under `data/states/` exporting any of
  `STATE/PARCEL/COUNTIES/DEED_LINK/PLAT_LINK/APPRAISER_LINK`; the pkgutil loader aggregates it.
- `id_only` statewide layers don't count as "auto-fetch from address" coverage (OH ODNR).
- **Never invent a records URL.** Prefer `.gov/.org/.us`; verify live before merging.
- Every document step carries a `link` fallback (`ok|link|empty|error`); adopters raise
  `SourceError`, steps classify, the job still completes.

## 7. Egress & connectivity verdicts (`services/http.py:33` `check_url`)

- `ok` (<400) · `blocked` (401/403/406/429 — browser-fine) · `broken` (404/410/5xx — fix the
  URL) · `offline` (TLS reset/timeout — AV/firewall, the K7 case).
- 403 in `/api/linkcheck` = **"opens in browser"** — do not report the site as dead.

## 8. Deployment vocabulary

- `RUN_ENV=local|test` → `create_all` at startup (no migrations); prod runs
  `alembic upgrade head` (engine chain `0002` shim → `0001` → `0003` → `0004`;
  parent drops `0002`).
- Producer→worker contract: `ack_late`, `worker_prefetch_multiplier=1`, `--queues=research`,
  Windows `--pool=solo`.
- US egress: native on AWS `us-east-1` (parent ECS `quickplot-dev`); dev-PC VPN (WireGuard or
  HTTP proxy overrides) is a *developer convenience*, not an engine concern.

## 9. Testing vocabulary

- `scripts/export_contracts.py` re-exports `contracts/` — a drift in the checked-in schemas is
  a contract break by definition.
- `scripts/qp_integrity.py` re-hashes stored blobs against recorded digests
  (`MISSING`/`MISMATCH`/`SHARED`) — run after any storage/ingest change.
- E2E green = contract green: real uvicorn + real worker + real Postgres(5433)/Redis over HTTP.