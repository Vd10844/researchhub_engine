# Source Contract — Research Engine Orchestration

The contract between the research runner and the data sources it fetches.
Defines the adapter interface, the outcome taxonomy, fallback and retry
semantics, and the provenance stamped on every result.

## 1. The pipeline split

The POC ran one monolithic `run_research()`. The engine splits it into two
resolved phases:

```
Phase A — context            Phase B — documents
─────────────────            ─────────────────────────────
geocode | parcel | refs  →   adapter.fetch(ctx, docs_dir) per document
  PropertyContext             (honors `include` — fetch ONLY what's asked)
```

`PropertyContext` (canonical, `app.engine.orchestration.context`) carries every
resolved fact a source might need:

| field | meaning |
|---|---|
| `address` / `matched_address` | search vs normalized (fastfwd for flood/ngs) |
| `lat` / `lon` | geocoder point (fallback matched via ArcGIS/OSM) |
| `state`, `state_fips`, `county`, `county_fips` | resolved geography |
| `geocoder` | `census` / `arcgis` / `nominatim` / `parcel-id` |
| `parcel`, `parcel_ok`, `parcel_id`, `parcel_hints` | confirmed parcel (or not) |
| `appraiser_url` | county appraiser / statewide / NETROnline fallback |
| `clerk_ref` | `official_records_search` + `plat_search` + hints |
| `appr`, `_clerk_docs` | cached best-effort shared artifacts |
| `folder` | the run's staging dir (has `documents/`) |
| `warnings` | deduplicated, ordered user-facing warnings |
| `manifest` | audit trail (files + sources + digests) |

## 2. Source adapter interface

Every document step has one adapter
(`app.engine.orchestration.sources.SourceAdapter`):

```python
class SourceAdapter:
    key: str
    def fetch(self, ctx, docs_dir) -> FetchedSource: ...
    def fallback(self, ctx, error=None) -> FetchedSource: ...
```

- `fetch` returns a `FetchedSource` on success — **including “nothing found”**
  (status `empty`/`link`). It must not perform its own fallback logic.
- `fetch` raises `SourceError(outcome, code, message, retryable)` (or an
  HTTP/requests exception) when the source is unreachable. It is **never**
  allowed to produce partial garbage — either real data or a raised error.
- `fallback` returns the deep-link step the user sees when `fetch` raised.

`FetchedSource`:

| field | meaning |
|---|---|
| `status` | the frozen vocabulary `ok` / `link` / `empty` (never `error`) |
| `data` | raw source payload (source-specific, not for direct rendering) |
| `summary` / `link` / `link_label` | the one-line card text + fallback deep link |
| `source_url` | primary source URL for this document |
| `downloaded` | filenames staged under `documents/` (copied to S3 by the adapter) |
| `saved_file` | metadata JSON generated for this step (`parcel.json`, …) |
| `records` | manifest entries `{file, source, sha256, fetched_utc}` → provenance |
| `confidence` | engine's belief this result is the searched property |
| `situs` / `land_sqft` / `land_acres` / `address_match` | parcel step extras |

The registry (`ADAPTERS`) maps step key → adapter. Registering a new source is
one entry; the runner, status logic and manifest handling stay untouched.

## 3. Outcome taxonomy (why a source returned what it did)

`SourceOutcome` (engine-additive; lives beside the frozen `status`):

| outcome | meaning | mapped from |
|---|---|---|
| `auto` | data fetched programmatically | adapter returned data |
| `link_only` | no auto-download exists — deep-link by design | adapter status `link` |
| `blocked` | 401/403/406/429 — WAF/bot/geo block, fine in a browser | HTTP status |
| `broken` | 404/410/5xx — the URL is wrong or the server errored | HTTP status |
| `retryable` | timeout / connection reset after retries | TLS/DNS/timeout |
| `manual_review` | data present but ambiguous (reserved for buffered matches) | — |

Frozen `status` stays backward-compatible:
`ok` → data (or card + link), `link` → manual action needed, `empty` → source
reached, nothing there. The *why* always rides in `source_outcome` + `error`.

## 4. Fallback and retry semantics

- **Every document step carries a `link` fallback.** Auto-fetch failure degrades
  the step to `link` with the deep-link retained — never a dead card.
- An unreachable source commits a structured `ErrorInfo{code, message, retryable}`;
  never a raw traceback.
- **Pier-retry granularity:** `run_research(include=[...])` fetches ONLY the
  requested document types. Context (geocode + parcel) is re-resolved cheaply
  per run; the heavy per-source work is not repeated.
- Retry on the API creates a **new job** from the original's failed doc types
  (see `docs/job-lifecycle.md`); the original job is immutable.
- Retirement is decided by `retryable` (True for `retryable`/most `broken`,
  False for `blocked` — a WAF block won't clear by hammering).

## 5. Provenance

Every manifest entry (file + source + sha256 + UTC) becomes a
`ProvenanceRecord` on the step. The blob upload records the same digest, so the
stored artifact is auditable end-to-end (see `scripts/qp_integrity.py` for the
POC lineage; the engine re-hashes at upload from `documents/` staging).