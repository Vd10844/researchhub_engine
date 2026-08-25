# Source Contract — Per-Adapter Rules

Each adapter is responsible for one step in the research pipeline.  This document defines
the contract every adapter must fulfill: what it receives, what it returns, how it classifies
its result, and what fallback chain it tries before giving up.

## Adapter contract (all adapters)

Every adapter must:

1. Accept a `ResolvedContext` (geocode + county + parcel_id).
2. Return a `StepResult` with at minimum: `key`, `status`, `source_outcome`, `confidence`, `provenance`.
3. If it tries multiple sources internally, populate `provenance[].fallback_chain` with the ordered list.
4. On failure, populate `error` with a structured `ErrorInfo` (never a raw exception).
5. Never raise — return an error `StepResult` instead.

## Per-source fallback chains

### geocode (`step: geocode`)

```
1. Census Geocoder (geocoding.geo.census.gov)
   → on success: confidence=high, provider="census"
2. ArcGIS World Geocoder (geocode.arcgis.com)
   → on success: confidence=high, provider="arcgis"  (only if Census fails)
3. Nominatim (nominatim.openstreetmap.org)
   → on success: confidence=medium, provider="nominatim"  (only if Census+ArcGIS fail)
4. All fail → status=error, source_outcome=retryable
```

**Confidence rules:**
- Census or ArcGIS match → `high`
- Nominatim match → `medium`
- Fallback to county centroid → `low`, with warning `"Fell back to county centroid"`

---

### parcel (`step: parcel`)

```
1. county gis_rest (MapServer query) — if county has a REGISTRY entry
   → on success: confidence=high, provider="arcgis-rest"
2. STATE_PARCEL statewide FeatureServer — if state has one registered
   → on success: confidence=medium, provider="arcgis-statewide"
   → NOTE: county gis_rest is tried first even when statewide exists,
     because county layers are more authoritative for situs addresses
3. Appraiser deep-link (directory fallback) — always present per county
   → on success: confidence=none, status=link, source_outcome=link_only
4. All fail → status=empty, source_outcome=broken
```

**Retry policy:**
- Point queries retry with a 40 m buffer (geocoder points land on street centerlines)
- On buffered match: confidence=medium, warning="Address matches via 40m buffer — verify location"

**Coverage gates (for adding new county services):**
- Must return a parcel for ≥60% of a grid of points inside the county polygon
- Must have ≥400 features
- Must expose a parcel-id field
- Must distinguish situs vs mailing address (set `situs_exclude` when CAMA carries both)

---

### deed + plat (`steps: deed, plat`)

```
1. clerk_scraper (Playwright) — if county has clerk_url in REGISTRY
   → on success: confidence=high, provider="playwright"
   → Saves PDF to documents/ folder
2. Deep-link to clerk portal — always available
   → status=link, source_outcome=link_only
3. Playwright fails → status=link, source_outcome=blocked, warning="Clerk portal blocked — opens in browser"
```

**Key rules:**
- Playwright scraping only runs when explicitly enabled (user must have Chromium installed)
- If scraping is not enabled, every deed/plat step returns `link` + `link_only`
- Never invent a records URL — verify it points to the right county portal

---

### flood (`step: flood`)

```
1. FEMA NFHL (hazards.fema.gov)
   → on success: confidence=high, provider="fema-nfhl"
   → Saves flood-map image (PNG) to documents/
2. FEMA MSC link (msc.fema.gov/portal)
   → status=link, source_outcome=link_only (always available as fallback)
3. FEMA blocked by WAF/K7 → status=link, source_outcome=blocked, warning="FEMA blocked — opens in browser"
```

**Key rules:**
- FEMA is blocked by K7 antivirus on user machines — the link fallback is expected, not a failure
- In the sandbox (this test environment), FEMA is also blocked — tests use fixture recordings
- The flood map image is composited from FEMA WMS only when the fetch succeeds

---

### NGS benchmarks (`step: benchmarks`)

```
1. NGS datasheet (geodesy.noaa.gov)
   → on success: confidence=medium, provider="ngs"
   → Extracts benchmark data (PID, name, lat, lon, NAVD88 elevation)
2. No benchmarks found → status=empty, source_outcome=auto
   (This is normal — many areas have no NGS control points nearby)
```

**Key rules:**
- NGS benchmarks are a bonus, not required — `empty` is a valid designed outcome
- Only marks `retryable` if the NGS server itself errors (5xx, timeout)

---

### site_info + lot_size (`steps: site_info, lot_size`)

```
1. Derived from parcel data + appraiser data (no separate fetch)
2. If parcel data is available → populate land_sqft, land_acres, situs from parcel
3. If not available → status=empty, source_outcome=auto (valid — no separate fetch needed)
```

---

## SourceOutcome → Status mapping (for the adapter contract)

Every adapter must set both `status` (FE-facing) and `source_outcome` (engine-internal):

| `source_outcome`  | `status`     | When                                         |
|-------------------|--------------|-----------------------------------------------|
| `auto`            | `ok`         | Fetched data successfully                     |
| `auto`            | `empty`      | Source responded but returned no results       |
| `link_only`       | `link`       | No auto-download exists (by design)           |
| `blocked`         | `link`       | Source blocked us, deep-link is the fallback  |
| `broken`          | `link`       | Source URL wrong/down, link is the fallback   |
| `broken`          | `empty`      | Source down, no fallback link available       |
| `retryable`       | `error`      | Timeout / connection reset after retries      |
| `blocked`         | `error`      | Fatal bot-block with no link fallback         |
| `manual_review`   | `link`       | Ambiguous match needs human verification      |

## Confidence rules (summary)

| Condition                                           | Confidence |
|-----------------------------------------------------|------------|
| Exact address match from authoritative source       | `high`     |
| Buffered point match (40m retry)                    | `medium`   |
| Nominatim geocode (best available)                  | `medium`   |
| County centroid fallback                            | `low`      |
| No data available, link provided                    | `none`     |
| NGS benchmarks near search point                    | `medium`   |
| FEMA flood zone determination                       | `high`     |
