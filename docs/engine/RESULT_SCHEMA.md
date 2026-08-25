# Result Schema — Frozen vs Additive

The research result is the primary contract consumed by the frontend. Every field below is
verifiable against the 7 saved POC jobs in `tests/fixtures/poc_results/`.

## Frozen fields (shipped in POC — will not change meaning or type)

These fields exist on every `result.json` that the POC produced.  Removing any of them is a
breaking change.  Adding new fields alongside them is not.

### Top-level

| Field            | Type     | Example                          | Notes                                        |
|------------------|----------|----------------------------------|----------------------------------------------|
| `job_number`     | string   | `"010-067474"`                   | May be empty                                 |
| `order`          | string   | `"order_20260818_001"`           | May be empty                                 |
| `parcel_id`      | string   | `"00381276"`                     | May be empty                                 |
| `address`        | string   | `"90 W Broad St"`                | User-provided input                          |
| `matched_address`| string   | `"90 W Broad St, Columbus"`      | Geocoder-resolved canonical address           |
| `county`         | string   | `"Franklin"`                     | Selected county (dropdown wins over geocoder) |
| `county_fips`    | string   | `"39049"`                        | 5-digit FIPS                                 |
| `state`          | string   | `"OH"`                           | 2-letter state code                          |
| `lat`            | float    | `39.9613`                        | May be null                                  |
| `lon`            | float    | `-82.9997`                       | May be null                                  |
| `name`           | string   | `"010-067474_-_90_W_Broad_St"`   | Job folder name                              |
| `geocoder`       | string   | `"census"`                       | Which geocoder matched                       |
| `map_links`      | array    | `[{"label":"Google Maps",...}]`  | Array of `{label, url}` objects              |
| `folder`         | string   | `"jobs/010-067474_-_90_W_Broad"`| Relative job folder path                     |
| `steps`          | array    | (see below)                      | Array of 11 step objects                     |
| `warnings`       | array    | `[]`                             | Non-fatal warnings (e.g. FEMA blocked)       |

### Per-step (`steps[]`)

| Field            | Type     | Example                          | Notes                                        |
|------------------|----------|----------------------------------|----------------------------------------------|
| `key`            | string   | `"parcel"`                       | Step identifier                              |
| `label`          | string   | `"Parcel"`                       | Human label                                  |
| `requirement`    | string   | `"mandatory"`                    | mandatory / conditional / recommended         |
| `condition`      | string   | `""`                             | When conditional (e.g. "if subdivision")     |
| `summary`        | string   | `"Parcel found via StrMap..."`   | One-line result summary                      |
| `status`         | string   | `"ok"`                           | **Frozen**: `ok` / `link` / `empty` / `error`|
| `link`           | string   | `"https://..."`                  | Deep-link fallback                           |
| `link_label`     | string   | `"View on NETROnline"`           | Button label                                 |
| `source_url`     | string   | `"https://gis.city..."`          | Primary source URL                           |
| `saved_file`     | string   | `"parcel.json"`                  | May be null                                  |
| `data`           | any      | (source-specific)                | Raw data payload                             |
| `downloaded`     | array    | `["deed.pdf"]`                   | Filenames of saved docs                      |

## Additive fields (engine v1 — new, backward-compatible)

These fields are added by the engine and **ignored** by existing POC consumers.  They give the
frontend ops dashboards, per-source health visibility, and a full audit trail.

### Per-step (`steps[]`) — new fields

| Field            | Type              | Example            | Notes                                      |
|------------------|-------------------|--------------------|---------------------------------------------|
| `description`    | string            | `"Deed document"`  | What this document is and why it matters    |
| `source_outcome` | SourceOutcome     | `"auto"`           | Why the result is what it is                |
| `confidence`     | Confidence        | `"high"`           | How sure the engine is                      |
| `provenance`     | ProvenanceRecord[]| (see below)        | Full audit trail of source hits             |
| `warnings`       | string[]          | `["buffered match"]`| Per-step warnings                          |
| `error`          | ErrorInfo         | `null` or `{...}`  | Structured error when status == `error`     |
| `situs`          | string            | (parcel step only) | Physical address from assessor              |
| `land_sqft`      | float             | (parcel step only) | Parcel area in sqft                         |
| `land_acres`     | float             | (parcel step only) | Parcel area in acres                        |
| `address_match`  | bool              | (parcel step only) | Whether parcel address matches searched     |

### Top-level — new fields

| Field            | Type      | Example               | Notes                                    |
|------------------|-----------|-----------------------|------------------------------------------|
| `completed_utc`  | string    | `"2026-08-25T..."`    | ISO-8601 timestamp when pipeline finished|
| `job_state`      | JobState  | `"completed"`         | Persisted lifecycle state                 |

### Provenance record shape

```json
{
  "source_id": "parcel.state_fl",
  "provider": "arcgis-rest",
  "url": "https://services.arcgis.com/.../MapServer/0/query",
  "retrieved_utc": "2026-08-25T14:32:01Z",
  "attempt": 1,
  "fallback_chain": ["parcel.county_hillsborough_fl", "parcel.state_fl"],
  "file": "documents/parcel.json",
  "sha256": "a3f1c..."
}
```

### ErrorInfo shape

```json
{
  "code": "HTTP_403",
  "message": "WAF blocked request — opens in a real browser",
  "retryable": false
}
```

## Status → source_outcome mapping

| `status` | Likely `source_outcome`  | When                                           |
|----------|--------------------------|------------------------------------------------|
| `ok`     | `auto`                   | Fetched structured data successfully            |
| `link`   | `link_only`              | No auto-download exists (by design)            |
| `link`   | `blocked`                | Source blocked the request, link is fallback   |
| `link`   | `broken`                 | Source URL wrong or down, link still valid     |
| `empty`  | `auto`                   | Source responded but returned no data           |
| `error`  | `retryable`              | Timeout / connection reset after retries       |
| `error`  | `blocked`                | Fatal bot-block (FEMA, K7)                    |

## Verifying against POC fixtures

Every field above is verifiable against the 7 saved jobs in `tests/fixtures/poc_results/`:

| Fixture                          | Status mix                            | coverage                   |
|----------------------------------|---------------------------------------|-----------------------------|
| 90 W Broad St (OH)               | 3 ok, 8 link                         | Full success                |
| 141 Pryor St (GA)                 | 3 ok, 8 link                         | Full success                |
| 50 Oakmont Dr (OH)                | 3 ok, 8 link                         | Full success                |
| 228 Ave E SE (TX)                 | 3 ok, 8 link                         | Full success                |
| 7670 Kelvinway Dr (FL)            | 2 ok, 1 empty, 8 link                | NGS no coordinates          |
| 200 Westcliff (FL)                | 11 link                               | Full link-only (K7 blocks)  |
| 113 Merry Valley Dr (FL)          | 10 link, 1 empty                     | Mostly link-only, NGS empty |
