# QuickPlot — Integration Guide

Everything another team needs to run, call, or embed the Research Hub: the API surface with
working `curl` for every endpoint, the database schema, the external data sources the pipeline
depends on, and the seams that make it SaaS-deployable (tenancy, object storage, a swappable
Evidence Locker backend, background work).

Companion docs: [`../CLAUDE.md`](../CLAUDE.md) (project guardrails), [`HANDOFF.md`](HANDOFF.md)
(coverage status and expansion), [`NATIONWIDE_PLAN.md`](NATIONWIDE_PLAN.md).

---

## 1. What this is

Two applications share one FastAPI process:

| | Path | API | Purpose |
|---|---|---|---|
| **Classic** | `/` | `/api/*` (v1) | The original address-first research tool: search → job folder → evidence locker. Unchanged. |
| **QuickPlot** | `/quickplot` | `/api/v2/*` | The Mapperty-styled, **order-centric** research hub. Orders, per-document review & lock, audit log. |

QuickPlot is the slice intended to live inside the larger Mapperty product. It reuses the v1
research pipeline (`services/orchestrator.py`) as its auto-fetch engine but owns its own data
model, so it can be deployed multi-tenant without touching the classic app.

```
                       ┌──────────────────────────────────────────┐
  Browser  ─────────►  │  FastAPI (app.main)                      │
  /quickplot           │   ├─ /api/v2  quickplot.router           │
                       │   │    ├─ orders / sources / checklist   │
                       │   │    └─ documents ──► LockerProvider ──┼──► local DB + blob store
                       │   │                        (or)          │        or Mapperty API
                       │   ├─ /api/*   classic v1 routes          │
                       │   └─ quickplot.research ──► orchestrator ─┼──► county GIS · clerk ·
                       └──────────────────────────────────────────┘     FEMA · NGS · Census
```

---

## 2. Running it

```bash
# Windows, from the repo root
run.bat                       # or: run-hidden.vbs (no console), stop.bat to stop

# or manually
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload --reload-dir app
```

* Classic UI → <http://127.0.0.1:8000/>
* QuickPlot  → <http://127.0.0.1:8000/quickplot>
* OpenAPI    → <http://127.0.0.1:8000/docs>

Seed a realistic order to click through the whole flow:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/demo/seed \
     -H 'X-Org-Id: default' | jq '.order.id'
```

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `QP_DEFAULT_ORG` | `default` | Tenant used when `X-Org-Id` is absent. |
| `QP_LOCKER_PROVIDER` | `local` | `local` (our DB + storage) or `remote` (Mapperty API). |
| `QP_LOCKER_API_BASE` | – | Base URL of the remote Evidence Locker API. Required for `remote`. |
| `QP_LOCKER_API_KEY` | – | Bearer token for the remote locker. |
| `QP_STORAGE_BACKEND` | `local` | `local` filesystem or `s3`. |
| `QP_STORAGE_ROOT` | `<repo>/evidence/_qp` | Root dir for the local blob store. |
| `QP_S3_BUCKET` / `QP_S3_PREFIX` | – / `quickplot` | S3 target (plus the usual `AWS_*` credentials). |
| `QP_MAX_UPLOAD_MB` | `50` | Largest single document accepted. Over this → `413`. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_HOST` / `POSTGRES_DB` | – | When all set, builds the Postgres URL. |
| `DATABASE_URL` | `sqlite:///<repo>/survey_research.db` | Explicit override; used when the `POSTGRES_*` set is incomplete. |
| `SURVEY_JOBS_DIR` / `SURVEY_EVIDENCE_DIR` | `<repo>/jobs`, `<repo>/evidence` | v1 research output + classic locker. |

Bad configuration never takes the app down: an unreachable S3 or a misconfigured remote locker
falls back to the local implementation and logs a line at startup.

### Tenancy and identity

There is **no authentication yet** — deliberately. Every v2 request carries two headers:

```
X-Org-Id: acme-surveying      # tenant; every row is scoped by it
X-Actor:  Owen Ranford        # display name recorded in the audit log
```

Every table has an `org_id` column and every query filters on it, so adding auth means
replacing exactly two functions in [`backend/app/quickplot/router.py`](../backend/app/quickplot/router.py)
— `org_of()` and `actor_of()` — with token-claim lookups. Nothing else changes.

> Until auth exists, do not expose this beyond a trusted network: `X-Org-Id` is
> self-asserted, so any caller can read any tenant.

---

## 3. Database

SQLAlchemy 2.0 ORM. SQLite in dev, Postgres in prod — no dialect-specific types are used, and
`db.init_db()` (called at startup) creates everything plus additive column migrations.

### v2 — QuickPlot tables

**`qp_orders`** — one survey order. [`quickplot/models.py`](../backend/app/quickplot/models.py)

| Column | Type | Notes |
|---|---|---|
| `id` | `varchar(32)` PK | uuid4 hex |
| `org_id` | `varchar(64)` idx | tenant |
| `order_no`, `title`, `order_type`, `survey_type` | text | `order_no` is the human "#123-45" |
| `stage` | `varchar(24)` idx | `created`→`placed`→`research`→`field_survey`→`cad_drafting`→`delivered` |
| `stage_dates` | JSON | `{stage: iso}` — the ticks under the stage rail |
| `research_state` | `varchar(24)` idx | `not_started` \| `in_progress` \| `submitted` |
| `address`, `matched_address`, `city`, `county`, `county_fips`, `state`, `postal` | text | `matched_address` is filled by the geocoder |
| `parcel_id`, `lot_area_sqft`, `lot_area_acres`, `lat`, `lon` | text / float | filled by the parcel service |
| `client`, `access_contact` | JSON | `{name, role, email, phone}` / `{name, phone}` |
| `buyer_owner`, `lender`, `title_company`, `underwriter` | text | |
| `client_notes`, `legal_description` | text | |
| `scope_tags` | JSON array | e.g. `["Structures / Improvements", "Easements"]` |
| `received_at`, `due_at` | datetime | |
| `created_by`, `researcher` | text | |
| `research_started_at`, `research_submitted_at`, `researcher_note` | datetime / text | |
| `job_name` | text | folder of the v1 job that produced the auto-fetch (`jobs/<name>`) |
| `created_at`, `updated_at` | datetime | |

**`qp_documents`** — one file in an order's Evidence Locker.

| Column | Type | Notes |
|---|---|---|
| `id` | `varchar(32)` PK | uuid4 hex |
| `org_id`, `order_id` | idx | `order_id` → `qp_orders.id` |
| `filename`, `content_type`, `size_bytes`, `pages` | | `pages` is a best-effort PDF count |
| `doc_type` | `varchar(64)` | catalog key; `""` = still needs classifying |
| `source_key` | `varchar(64)` | which registry source produced it |
| `origin` | `varchar(24)` | `auto_fetch` \| `manual_upload` |
| `status` | `varchar(24)` idx | `review_needed` \| `locked` |
| `source_label`, `source_url` | text | provenance shown in the review modal |
| `storage_key`, `sha256` | text | blob-store key + content digest |
| `retrieved_at`, `retrieved_by` | | |
| `locked_at`, `locked_by`, `lock_seal`, `lock_checks` | | `lock_seal` = first 6 of `sha256`; `lock_checks` records the three reviewer confirmations |
| `deleted`, `deleted_at`, `delete_reason` | | **soft delete** — the audit trail must keep pointing at a real row |

**`qp_order_sources`** — per-order state of each research source (the right-hand rail).
Unique on `(order_id, key)`.

| Column | Notes |
|---|---|
| `key`, `label`, `requirement` | from the catalog (`parcel`, `deed`, `flood`, …) |
| `state` | `idle` \| `fetching` \| `fetched` \| `failed` \| `unavailable` |
| `message`, `open_url`, `doc_count`, `last_run_at` | `open_url` is resolved county-first, then statewide, then the NETROnline directory |

**`qp_audit`** — append-only change log.

| Column | Notes |
|---|---|
| `scope` | `order` (Order information log) \| `locker` (Evidence locker log) |
| `action` | `order_created`, `order_details_captured`, `quote_sent`, `order_updated`, `research_started`, `research_submitted`, `uploaded`, `auto_fetched`, `auto_fetch`, `doc_type_set`, `locked`, `unlocked`, `deleted` |
| `title`, `subtitle`, `reason`, `actor`, `detail` (JSON), `ts` | rendered directly by the log modals |

### v1 — classic index tables (unchanged)

`jobs` (name PK, address, county, state, parcel_id, docs, generated, locker_order),
`evidence_items` (order, file, doc_key, label, source_job, source_url, sent_at),
`events` (ts, action, job, address, detail JSON). See [`backend/app/db.py`](../backend/app/db.py).

### Inspecting it

```bash
# SQLite (dev)
sqlite3 survey_research.db ".tables"
sqlite3 survey_research.db "SELECT order_no,title,stage,research_state FROM qp_orders;"
sqlite3 survey_research.db \
  "SELECT filename,doc_type,status,lock_seal FROM qp_documents WHERE deleted=0;"

# Postgres (prod)
psql "$DATABASE_URL" -c "\d qp_documents"
```

Postgres setup — the app creates its own tables, so all it needs is a database and a role:

```sql
CREATE DATABASE quickplot;
CREATE USER quickplot WITH PASSWORD '…';
GRANT ALL PRIVILEGES ON DATABASE quickplot TO quickplot;
```

```bash
export POSTGRES_USER=quickplot POSTGRES_PASSWORD='…' \
       POSTGRES_HOST=db POSTGRES_DB=quickplot
```

---

## 4. API v2 reference

Base URL `http://127.0.0.1:8000/api/v2`. All requests take `X-Org-Id` and `X-Actor`.
Examples below assume:

```bash
BASE=http://127.0.0.1:8000/api/v2
H=(-H "X-Org-Id: default" -H "X-Actor: Owen Ranford")
```

### 4.1 Meta

```bash
curl -s "${H[@]}" $BASE/meta
```
```json
{
  "org_id": "default",
  "locker_provider": "local",
  "storage_backend": "local",
  "stages": [{"key": "created", "label": "Order Created"}, "…"],
  "doc_types": [{"key": "parcel", "label": "Parcel record / Parcel ID"}, "…"],
  "sources":   [{"key": "parcel", "label": "…", "requirement": "mandatory",
                 "step": "parcel", "auto": true, "blurb": "…"}, "…"]
}
```

```bash
curl -s $BASE/doc-types      # just the dropdown options
```

### 4.2 Orders

```bash
# list (optional ?q= free text, ?stage=, ?limit=)
curl -s "${H[@]}" "$BASE/orders?q=oakmont"

# create
curl -s "${H[@]}" -X POST $BASE/orders -H 'Content-Type: application/json' -d '{
  "order_no": "123-45",
  "title": "Oakmont Elevation",
  "order_type": "Boundary Survey",
  "survey_type": "Residential Land Survey",
  "address": "1100 Bougainvillea Ave, Lakeland, FL 33815",
  "city": "Lakeland", "county": "Polk", "county_fips": "12105",
  "state": "FL", "postal": "33815",
  "client": {"name":"Aron Smith","role":"Realtor","email":"aron@mail.com","phone":"+1 123 456 7980"},
  "access_contact": {"name":"John Doe","phone":"+1 987 654 3210"},
  "buyer_owner": "Mary Joe", "lender": "SBI Bank",
  "title_company": "Dan Surveyors", "underwriter": "ICICI",
  "scope_tags": ["Structures / Improvements","Easements"],
  "due_at": "2026-08-25", "researcher": "Owen Ranford"
}'
```

`201` with the full order plus `counts: {documents, locked, review_needed}`.

```bash
OID=<order id>

curl -s "${H[@]}" $BASE/orders/$OID                       # read
curl -s "${H[@]}" -X PATCH $BASE/orders/$OID \
     -H 'Content-Type: application/json' \
     -d '{"lender":"Chase","due_at":"2026-09-01"}'        # partial update
curl -s "${H[@]}" -X DELETE $BASE/orders/$OID             # delete (cascades docs+audit)

# change log — scope=order | locker | all
curl -s "${H[@]}" "$BASE/orders/$OID/log?scope=order"
```

### 4.3 Research

```bash
# move to Research and kick off the first auto-fetch
curl -s "${H[@]}" -X POST $BASE/orders/$OID/research/start

# the source registry rail (creates the rows on first call, with "Open source" links)
curl -s "${H[@]}" $BASE/orders/$OID/sources
```
```json
{"sources": [{"key":"parcel","label":"Parcel record / Parcel ID","requirement":"mandatory",
              "state":"idle","message":"County and federal sources for parcel",
              "open_url":"https://www.polkflpa.gov/CamaSearch.aspx","doc_count":0,
              "last_run_at":null}, "…"],
 "run": {"state":"idle","phase":"","percent":0,"error":"","only":""}}
```

```bash
curl -s "${H[@]}" -X POST $BASE/orders/$OID/sources/fetch-all      # Auto-Fetch All
curl -s "${H[@]}" -X POST $BASE/orders/$OID/sources/deed/fetch     # one source / Retry
curl -s "${H[@]}" $BASE/orders/$OID/research/status                # poll while running
```

`research/status` returns `{"run": {...}, "phases": [...]}`. `run.state` is
`idle` → `running` → `done` | `error`; `run.percent` drives the progress bar. Poll every ~2 s
and stop as soon as the state leaves `running`.

```bash
curl -s "${H[@]}" $BASE/orders/$OID/checklist
# {"items":[{"key":"parcel","label":"…","requirement":"mandatory","done":false}, …],
#  "done":2,"total":8,"percent":25}
```

A checklist row only ticks for a **locked** document of that type — gathering is not the same
as accepting.

```bash
curl -s "${H[@]}" $BASE/orders/$OID/research/summary
# {"counts":{"documents":4,"locked":3,"review_needed":1},"assignee":"Owen Ranford"}

curl -s "${H[@]}" -X POST $BASE/orders/$OID/research/submit \
     -H 'Content-Type: application/json' \
     -d '{"note":"Rear easement unverified — confirm on site."}'
```

Submit sets `research_state=submitted`, advances the stage to `field_survey`, and writes the
audit entry. It returns **409** when nothing is locked.

### 4.4 Documents (Evidence Locker)

```bash
curl -s "${H[@]}" $BASE/orders/$OID/documents               # list (?q= filters by name/type)

# upload — repeat -F files=@… for a batch
curl -s "${H[@]}" -X POST $BASE/orders/$OID/documents \
     -F "files=@Deed_Subject_Parcel.pdf" \
     -F "files=@Subdivision_Map_Bk22_Pg9.png" \
     -F "doc_type=deed"

DID=<document id>
curl -s "${H[@]}" -X PATCH $BASE/orders/$OID/documents/$DID \
     -H 'Content-Type: application/json' -d '{"doc_type":"plat"}'

# review & lock — all three confirmations are mandatory
curl -s "${H[@]}" -X POST $BASE/orders/$OID/documents/$DID/lock \
     -H 'Content-Type: application/json' \
     -d '{"legible":true,"matches_parcel":true,"source_recorded":true}'

curl -s "${H[@]}" -X POST $BASE/orders/$OID/documents/$DID/unlock \
     -H 'Content-Type: application/json' -d '{"reason":"wrong page range fetched"}'

curl -s "${H[@]}" -X DELETE "$BASE/orders/$OID/documents/$DID?reason=duplicate"

# fetch the bytes (inline for the viewer, ?download=1 to force a save)
curl -s "${H[@]}" -o out.pdf "$BASE/orders/$OID/documents/$DID/file?download=1"

curl -s "${H[@]}" $BASE/orders/$OID/locker/log
```

Document JSON:

```json
{
  "id": "0f0ac9e4…", "order_id": "eee065f6…",
  "filename": "Deed_Subject_Parcel.pdf", "doc_type": "deed",
  "source_key": "deed", "origin": "manual_upload", "status": "locked",
  "size_bytes": 704512, "content_type": "application/pdf", "pages": 3,
  "source_label": "County Property Appraiser", "source_url": "https://…",
  "sha256": "2496f3…", "retrieved_at": "2026-08-21T16:11:04+00:00",
  "retrieved_by": "Owen Ranford",
  "locked_at": "2026-08-21T16:12:20+00:00", "locked_by": "Owen Ranford",
  "lock_seal": "2496f3",
  "lock_checks": {"legible": true, "matches_parcel": true, "source_recorded": true},
  "url": "/api/v2/orders/eee065f6…/documents/0f0ac9e4…/file"
}
```

**Locking rules** (enforced server-side, not just in the UI):

| Attempt | Result |
|---|---|
| Lock without a `doc_type` | `400 set the document type before locking` |
| Lock with any confirmation missing | `400 confirm all three checks before locking` |
| Change `doc_type` of a locked document | `409 unlock it before changing its type` |
| Delete a locked document | `409 locked documents cannot be deleted — unlock first` |
| Submit research with zero locked documents | `409 lock at least one document before submitting` |

### 4.5 Validation rules

Every rule below is enforced **server-side** and covered by a named test in
`tests/test_quickplot_api.py`. The client mirrors them for immediate feedback, but the server
is the authority — a caller bypassing the UI gets the same refusal.

| Rule | Applies to | Response | Message |
|---|---|---|---|
| An order needs a title, order number, address **or** parcel ID | `POST /orders` | `422` | `an order needs at least a title, order number, address or parcel ID` |
| Due date cannot precede the received date (equal is allowed) | `POST`/`PATCH /orders` | `422` | `due date cannot be earlier than the received date` |
| Dates must be ISO (`YYYY-MM-DD`) — never silently dropped | `POST`/`PATCH /orders` | `422` | `'not-a-date' is not a valid date (use YYYY-MM-DD)` |
| `state` must be a real US state code | `POST`/`PATCH /orders` | `422` | `'ZZ' is not a US state code` |
| Contact emails must be well-formed | `POST`/`PATCH /orders` | `422` | `'nope' is not a valid email address` |
| `stage` must be one of the six known stages | `POST`/`PATCH /orders` | `422` | `'banana' is not a known stage; expected one of [...]` |
| Order numbers are unique per tenant | `POST`/`PATCH /orders` | `409` | `order number '123-45' already exists` |
| `doc_type` must come from the catalog | upload, `PATCH` document | `422` | `unknown document type 'made-up'` |
| Uploads must be non-empty | upload | `422` | `the file is empty` |
| Uploads must be ≤ `QP_MAX_UPLOAD_MB` | upload | `413` | `file is 60 MB; the limit is 50 MB` |
| A document needs a type before it can lock | lock | `400` | `set the document type before locking` |
| All three reviewer confirmations are required | lock | `400` | `confirm all three checks before locking` |
| A locked document cannot be re-typed | `PATCH` document | `409` | `document is locked — unlock it before changing its type` |
| A locked document cannot be deleted | delete | `409` | `locked documents cannot be deleted — unlock first` |
| Research needs ≥1 locked document to submit | submit | `409` | `lock at least one document before submitting research` |
| Research cannot be submitted twice | submit | `409` | `research has already been submitted for this order` |
| Research cannot restart after submission | start | `409` | `research has already been submitted for this order; reopen it before running research again` |
| Unknown source key | source fetch | `404` | `unknown source 'nonsense'` |
| Another tenant's data is invisible, not forbidden | every route | `404` | `order not found` |

Two behaviours worth knowing because they are deliberate rather than obvious:

* **Deletes are soft.** A deleted document disappears from listings and its blob is removed, but
  the row survives so the change log keeps pointing at something real. An audit that cannot say
  what was removed is not an audit.
* **Re-fetching a source refreshes its document rather than adding a second copy** — identity is
  `(source_key, filename)`, not the content hash, because several generated reports embed a fetch
  timestamp. **A locked document is never replaced by a re-fetch.**

### 4.6 Errors

Standard FastAPI shape, `{"detail": "message"}`:

| Code | Meaning |
|---|---|
| `400` | A locking rule was violated |
| `404` | Missing id, or the row belongs to another tenant |
| `409` | State conflict — duplicate, or an action invalid for the current state |
| `413` | Upload exceeds the size ceiling |
| `422` | Payload validation failed |

### 4.7 Testing and integrity

```bash
# API regression — 53 tests, no network, throwaway database, ~2.5 s
.venv/Scripts/python.exe -m pytest tests/test_quickplot_api.py -q

# Browser regression — 15 tests, real server + real Chromium
.venv/Scripts/python.exe -m pytest tests/test_quickplot_ui.py -q

# Evidence Locker integrity — re-hashes every blob against its recorded digest
.venv/Scripts/python.exe scripts/qp_integrity.py
.venv/Scripts/python.exe scripts/qp_integrity.py --repair
```

`qp_integrity.py` should be run **on a schedule in any real deployment** and alerted on. It
exists because a shipped build once wrote every document in an order to the same storage key —
see [`qa/BUG_REPORT_quickplot.md`](qa/BUG_REPORT_quickplot.md) QP-001. Silent evidence
corruption is the worst failure this product can have, so it gets a standing check rather than
a one-off fix.

Quality gate documents:
[`qa/QA_REVIEW_GUIDELINE.md`](qa/QA_REVIEW_GUIDELINE.md) ·
[`qa/QA_REVIEW_quickplot.md`](qa/QA_REVIEW_quickplot.md) ·
[`qa/BUG_REPORT_quickplot.md`](qa/BUG_REPORT_quickplot.md) ·
[`qa/SIGNOFF_quickplot.md`](qa/SIGNOFF_quickplot.md)

---

## 5. Swapping in Mapperty's Evidence Locker

Set:

```bash
export QP_LOCKER_PROVIDER=remote
export QP_LOCKER_API_BASE=https://api.mapperty.example/v1
export QP_LOCKER_API_KEY=…
```

QuickPlot then keeps orders, sources and the research runner locally but proxies every
document operation upstream. Implementation:
[`backend/app/quickplot/locker.py`](../backend/app/quickplot/locker.py) → `RemoteLockerProvider`.

**Contract the remote service must implement.** Every call carries
`Authorization: Bearer <key>` and `X-Org-Id: <tenant>`; responses use the document JSON above.

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/orders/{order_id}/documents` | – | `{"documents": [...]}` |
| `POST` | `/orders/{order_id}/documents` | multipart: `file`, `doc_type`, `source_key`, `origin`, `source_label`, `source_url`, `actor` | document |
| `PATCH` | `/orders/{order_id}/documents/{doc_id}` | `{"doc_type","actor"}` | document |
| `DELETE` | `/orders/{order_id}/documents/{doc_id}` | `{"reason","actor"}` | `{"ok": true}` |
| `POST` | `/orders/{order_id}/documents/{doc_id}/lock` | `{"checks":{legible,matches_parcel,source_recorded},"actor"}` | document |
| `POST` | `/orders/{order_id}/documents/{doc_id}/unlock` | `{"reason","actor"}` | document |
| `GET` | `/orders/{order_id}/documents/{doc_id}/file` | – | raw bytes + `Content-Type` |
| `GET` | `/orders/{order_id}/documents/log` | – | `{"events": [...]}` |

Non-2xx responses are surfaced to the UI verbatim, so return a JSON body with a readable
message. The 4xx codes in §4.4 are the ones the UI already handles correctly.

The reverse direction — Mapperty calling *us* — needs nothing new: the endpoints in §4 are the
integration surface, and `GET /api/v2/orders/{id}/documents` plus the `file` endpoint are
enough to render a read-only locker anywhere.

---

## 6. Upstream data sources

These are the public services the auto-fetch pipeline calls. All are free and keyless.
**US egress is required** — FEMA and most county portals geo-block or WAF-block non-US and
datacenter IPs. See [`unblock-email.md`](unblock-email.md) for the K7 antivirus caveat.

### Geocoding — US Census (primary)

```bash
curl -s "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress" \
  --get \
  --data-urlencode "address=1100 Bougainvillea Ave, Lakeland, FL 33815" \
  --data-urlencode "benchmark=Public_AR_Current" \
  --data-urlencode "vintage=Current_Current" \
  --data-urlencode "format=json" | jq '.result.addressMatches[0].coordinates'
```

Fallbacks, in order: ArcGIS World Geocoder
(`https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates`)
then Nominatim (`https://nominatim.openstreetmap.org/search`). Reverse lookup for county FIPS
uses `…/geographies/coordinates`.

### Counties and cities — Census TIGERweb

```bash
curl -s "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/22/query" \
  --get --data-urlencode "where=STATE='12' AND COUNTY='105'" \
  --data-urlencode "outFields=NAME" --data-urlencode "f=json"
```

### Parcels — statewide services (per `data/county_platforms.STATE_PARCEL`)

```bash
# Florida DOR statewide cadastral — point-in-polygon
curl -s "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query" \
  --get \
  --data-urlencode "geometry=-81.9737,28.0395" \
  --data-urlencode "geometryType=esriGeometryPoint" \
  --data-urlencode "inSR=4326" \
  --data-urlencode "spatialRel=esriSpatialRelIntersects" \
  --data-urlencode "outFields=*" --data-urlencode "returnGeometry=false" \
  --data-urlencode "f=json"
```

Other wired statewide layers: TX `2019_Texas_Parcels_StratMap` (serves the **2025** vintage —
do not "fix" the URL), OH ODNR `Statewide_Parcels`, NJ `maps.nj.gov/.../Cadastral/MapServer/0`.
Counties without a statewide layer fall back to a per-county `gis_rest` MapServer in the
registry, then to an appraiser/NETROnline link.

> Point queries retry with a **40 m buffer**: geocoder points land on street centrelines and
> miss the parcel polygon.

### FEMA flood — National Flood Hazard Layer

```bash
curl -s "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query" \
  --get \
  --data-urlencode "geometry=-81.9737,28.0395" \
  --data-urlencode "geometryType=esriGeometryPoint" \
  --data-urlencode "inSR=4326" \
  --data-urlencode "spatialRel=esriSpatialRelIntersects" \
  --data-urlencode "outFields=FLD_ZONE,ZONE_SUBTY,STATIC_BFE,DFIRM_ID" \
  --data-urlencode "returnGeometry=false" --data-urlencode "f=json"
```

The FIRMette PDF itself is not API-accessible; the app composites a map image and links to the
Map Service Center (`https://msc.fema.gov/portal/home`).

### Survey control — NOAA NGS

```bash
curl -s "https://geodesy.noaa.gov/api/nde/radial?lat=28.0395&lon=-81.9737&radius=2&units=km"
# datasheet for one mark:
# https://geodesy.noaa.gov/cgi-bin/ds_mark.prl?PidBox=AB1234
```

### Deeds and plats — county clerk portals

No public API exists anywhere. The pipeline deep-links to the correct official-records search
and, for the platforms with a Playwright adapter (FL NewVision / Tyler / Manatee / Volusia),
downloads the images directly. Bulk per-county links live in
`backend/app/data/records_links.json`; state modules override them.

```bash
# which portal a county uses
curl -s "http://127.0.0.1:8000/api/reference/counties?state=FL" | jq '.counties[0]'
```

### Reachability from the user's own machine

```bash
curl -s "http://127.0.0.1:8000/api/linkcheck?county_fips=12105" | jq '.results[]'
```

Verdicts: `ok` · `blocked` (403 — WAF/bot block, opens fine in a browser) · `broken`
(404/5xx — fix the URL) · `offline` (TLS reset or timeout — antivirus/firewall).

---

## 7. Classic API (v1) — still available

Unchanged and independent of QuickPlot. Useful when you want the address-first pipeline
without an order.

```bash
API=http://127.0.0.1:8000/api

curl -s $API/health
curl -s $API/stats

curl -s -X POST $API/research -H 'Content-Type: application/json' -d '{
  "job_number":"25-1229",
  "address":"1100 Bougainvillea Ave, Lakeland, FL 33815",
  "state":"FL","county_fips":"12105"
}'

curl -s $API/jobs
curl -s "$API/jobs/detail?name=25-1229%20-%201100%20Bougainvillea%20Ave"
curl -s "$API/jobs/file?name=<job>&file=documents/deed.pdf&download=1" -o deed.pdf

curl -s -X POST $API/evidence/send -H 'Content-Type: application/json' \
  -d '{"order":"123-45","job_name":"<job>","items":[{"key":"deed","label":"Deed","file":"deed.pdf"}]}'
curl -s $API/evidence
curl -s "$API/evidence/detail?order=123-45"

curl -s $API/reference/coverage | jq '.national'
curl -s "$API/reference/counties?state=GA" | jq '.counties | length'
curl -s "$API/linkcheck?portals=1" | jq '[.results[] | select(.verdict!="ok")]'
```

Response shape of `/api/research`: `{job_number, order, parcel_id, address, matched_address,
county, county_fips, state, lat, lon, name, geocoder, map_links[], folder, steps[], warnings[]}`
where each step is `{key, label, requirement, status, summary, data, source_url, link,
link_label, saved_file, downloaded[]}` and `status ∈ ok | link | empty | error | skipped`.

---

## 8. Making it a SaaS

What is already in place, and what is deliberately left:

| Concern | Now | To productionise |
|---|---|---|
| **Tenancy** | `org_id` on every row; `X-Org-Id` header | Replace `org_of()`/`actor_of()` with JWT claims; add an `orgs`/`users` table and RBAC (researcher / reviewer / admin). |
| **Database** | SQLite dev / Postgres prod via env; `create_all` + additive migrations | Move to Alembic once the schema is shared across environments. |
| **Blob storage** | `services/storage.py` — `LocalStorage`, `S3Storage` behind one interface | Set `QP_STORAGE_BACKEND=s3`; add lifecycle rules and server-side encryption. Locked documents should go to an **object-lock / WORM** bucket — that is what makes "immutable evidence" true at the infrastructure layer, not just in application code. |
| **Evidence Locker** | Pluggable provider (`local` / `remote`) | Point at Mapperty's service; see §5. |
| **Background work** | `ThreadPoolExecutor` + an in-process `_RUNS` dict | **This is the one real single-process assumption.** Behind >1 uvicorn worker the poll endpoint can hit a worker that never saw the run. Move to Celery/RQ + Redis; the seam is `research.start_run()` / `research.run_status()` and nothing else. |
| **Auto-fetch egress** | Runs from the app host, needs a US IP | Give the worker pool a US egress (NAT/proxy), separate from the API pods. |
| **Audit** | Append-only `qp_audit`, soft-deleted documents, content digests | Ship the log to durable storage; consider signing `lock_seal`. |
| **Rate limits / retries** | Shared pooled session with 2 retries and backoff | Per-tenant quotas on auto-fetch; county portals will throttle. |
| **Observability** | stdout | Structured logs keyed by `org_id`/`order_id`; alert on `run.state == "error"` rates per source. |

### Sizing note

The pipeline is I/O-bound on third-party portals, not CPU-bound. One run takes roughly
20–70 s depending on the county. Concurrency should be limited **per upstream host**, not
globally, or a busy tenant will get a county portal to block the shared egress IP.

---

## 9. Frontend notes

No build step, by design — the same constraint as the classic app.

```
frontend/quickplot.html          entry point (served at /quickplot)
frontend/src/qp/quickplot.css    design tokens + components, from the Figma export
frontend/src/qp/ui.js            api client, icons, Btn/Chip/Modal/Drawer/Toasts, formatters
frontend/src/qp/modals.js        review & lock, unlock, delete, upload, submit, change logs
frontend/src/qp/research.js      the research hub screen + source registry rail
frontend/src/qp/orders.js        orders list, order detail, intake/edit form
frontend/src/qp/app.js           shell + hash router
```

React and Babel are vendored locally (`frontend/vendor/`) — no CDN. Tailwind is **not** loaded
on this page; QuickPlot ships its own CSS. Routes are hash-based
(`#/orders`, `#/orders/:id`, `#/orders/:id/research`), so the server returns the same shell for
any `/quickplot/*` path.

Design tokens (from `Knowledge/Design/figmadesign.txt`):

| Token | Value |
|---|---|
| Brand/600 — primary action | `#3FA424` |
| Brand/700 — hover | `#2E7D32` |
| Logo gradient | `#7EFF46 → #61D32F` |
| Brand tints 50/100/200/300 | `#F3FBEE` `#E6F7DB` `#D1F2BF` `#B7E89D` |
| Grays 950→100 | `#181D27 #252B37 #414651 #535862 #717680 #A4A7AE #D5D7DA #E9EAEB #F5F5F5` |
| Font | Figtree (falls back to Inter / system) |
| Radius | 8px controls · 12px cards · 16px modals |

To embed the hub inside Mapperty rather than run this shell, mount `ResearchHub` directly and
supply `orderId` + a `nav` callback; it has no other dependency on the shell.
