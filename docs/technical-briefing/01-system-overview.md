# 01 — System Overview (BA + everyone)

How the ResearchHub product works end to end, in plain language with diagrams. No code required
to follow this; the deep-dives reference it.

## 1. The problem we automate

For a **residential mortgage / location survey**, a surveyor must first assemble the *research
set* for the property — the public records that prove where the parcel is, what's recorded on it,
whether it floods, and what survey control exists nearby. Today that is hours of clicking county
websites. This product automates the *research phase*: enter the address (or parcel ID), get the
evidence set.

## 2. The six documents (the "research set")

| # | Document | What it is | Where it comes from | Auto-fetch? |
|---|---|---|---|---|
| 1 | **Parcel ID** | The assessor's parcel identifier + situs + lot area | County GIS (ArcGIS) or a statewide cadastral service | ✅ where a queryable service exists (**66.2%** of US counties) |
| 2 | **Appraiser / tax card** | Owner, values, last sale, tax record | County property-appraiser portal | ✅ wherever the parcel resolved |
| 3 | **Deed** | The recorded deed for the subject parcel | County clerk official records | ⚠️ only 5 FL counties (Playwright scraper); else a verified deep-link |
| 4 | **Plat** | The subdivision map / recorded plat | County clerk official records | same as deed |
| 5 | **Flood map + zone** | FEMA NFHL flood zone (A/AE/X/…), FIRMette exhibit | FEMA National Flood Hazard Layer | ✅ all counties (US egress required) |
| 6 | **Survey control (NGS)** | Nearby NGS benchmark datasheets (needed to tie the survey to state control) | NOAA National Geodetic Survey | ✅ all counties |

Four more **link-only** steps exist in the full survey document catalog (they have no public
queryable source): **adjoiners**, **easements/ROW**, **prior surveys**, **condo declarations**,
plus **BLM GLO** land-records as a link. These map to the source-registry checklist but are
never auto-fetched.

> **"Nothing is ever a dead end."** Every step carries a `link` fallback: either the source
> auto-fetches a file, or the user gets a verified one-click link straight to the right search
> screen of the right county portal (or, last resort, the NETROnline directory deep-link for
> that county).

## 3. The four statuses the frontend understands

This vocabulary is **frozen** — the POC shipped it and it will not change meaning:

| Status | Meaning | Example |
|---|---|---|
| `ok` | The engine fetched a real document | NGS datasheet downloaded |
| `link` | No auto-download; here is a verified link | "Open Clerk Official Records — Deed" |
| `empty` | Nothing exists / not applicable | No NGS marks within 3 km |
| `error` | The step failed (blocked / broken / timeout) | FEMA unreachable |

New engine-only reasoning (why a step is what it is) rides in **additive** fields next to these
statuses — `source_outcome`, `confidence`, `provenance`, `error` — so the old consumers keep
working untouched (`backend/app/engine/contracts.py:6`).

## 4. Two UIs today, one engine tomorrow

```
                    ┌─────────────────────────────────────────────────┐
                    │                 FastAPI process                 │
 Browser           │                                                  │
   │  /            │  Classic (/api/*)   address → job → evidence     │
   ├───────────►    │  QuickPlot (/api/v2) orders → review → submit   │
   │  /quickplot    │  (POC: both run in ONE process)                 │
                    └───────────────┬─────────────────────────────────┘
                                    │ run_research (pipeline)
                                    ▼
        county GIS · clerk portals · FEMA NFHL · NOAA NGS · Census geocoder · TIGERweb
```

- **Classic** (`/`): the original address-first tool — paste an address, run the research
  pipeline, and get a job folder with the six documents and an Evidence Locker.
- **QuickPlot** (`/quickplot`): the Mapperty-styled, **order-centric** hub — Orders have a
  stage rail (`created → placed → research → field_survey → cad_drafting → delivered`), a
  right-hand *source registry rail* (parcel, appraiser, plat, deed, flood, … each ticked when
  fetched), per-document **Review & Lock**, and an append-only change log. This is the slice
  that will live inside the parent product.
- **researchhub-engine** (standalone service): the next generation of the pipeline. It takes the
  same county services and adds a two-phase engine, a background **Celery worker**, its own
  `research_jobs`/`research_documents` tables, and a frozen `/api/v1/research/*` API. QuickPlot
  will call this instead of running the pipeline in-process.

## 5. The engine request flow (the important picture)

```mermaid
sequenceDiagram
    participant FE as Browser (QuickPlot)
    participant API as FastAPI /api/v1/research
    participant SVC as ResearchService
    participant DB as Postgres (research_jobs)
    participant REDIS as Redis broker
    participant WORKER as Celery worker
    participant SRC as Data sources (county/state/federal)

    FE->>API: POST /research/jobs {order_id, document_types}
    API->>SVC: create_job(tenant_id, actor_id, order_id, doc_types)
    SVC->>DB: insert job + N document rows (status=queued)
    SVC->>REDIS: enqueue research_job task (job_id, tenant_id, actor_id)
    API-->>FE: 201 {job, documents:[queued...]}
    REDIS->>WORKER: pick task
    WORKER->>DB: job.status=running
    loop each document
        WORKER->>WORKER: run_research(include=[step]) → FetchedSource
        WORKER->>DB: persist status/summary/link/error; commit
        alt auto-fetched artifact
            WORKER->>SRC: (already fetched inside run_research)
            WORKER->>WORKER: _upload_artifact → blob → File/OrderFile rows
            WORKER->>DB: doc.status=uploaded; file_id/order_file_id
        end
    end
    WORKER->>DB: recalc counters → terminal (completed/partial/failed)
    FE->>API: GET /research/jobs/{id} (poll)
```

The request/response happens in milliseconds; all the fetching happens **in the background
worker**. `POST /jobs` just validates + persists + enqueues. The UI polls `GET /jobs/{id}`.

## 6. The fallback philosophy (why "error" is rare)

The pipeline is built so a source is never allowed to crash a run:

1. **Adapters never fall back internally.** An adapter either returns data or raises
   `SourceError(outcome, code, message, retryable)`.
2. **The step builder catches everything.** Any exception is *classified*
   (`blocked` = 401/403/406/429 WAF/geo block; `broken` = 404/410/5xx broken URL; `retryable` =
   timeout/connection) and degraded to a **link step + structured `ErrorInfo`**.
3. **The job still completes.** A run where 5 of 6 sources returned links and 1 auto-fetched
   reaches `completed`; a run with ≥1 hard failure reaches `partial`, and the failed documents
   can be re-run via `POST /research/jobs/{id}/retry` (creates a fresh job for just those).

This is what the live E2E proves: from this sandbox's network, FEMA is blocked and the run
still finishes `completed` with a FEMA link card.

## 7. From evidence to a defensible survey

The business value is an **evidence set you can defend**:

- Every auto-fetched file is stored as a blob under a tenant-scoped key, with a recorded
  `sha256` digest and a provenance record (which source, when, fallback chain).
- In QuickPlot, a document only **locks** after the reviewer confirms three things — the file is
  **legible**, it **matches the subject parcel**, and it's from the **source recorded** for the
  order. These three checks are recorded with the lock.
- Locked documents cannot be re-typed or deleted; deletes are **soft** so the audit trail
  always points at a real row; the checklist ticks on **locked**, not on fetched.
- Research cannot be submitted with **zero locked documents** (API returns 409).

The standalone engine keeps the evidence linkage too: each uploaded artifact becomes a `File`
plus an `OrderFile` link row, so the blob ↔ order ↔ document chain is queryable.

## 8. Live coverage (as of the POC data — always check `/api/reference/coverage`)

Order-weighted, **FL + GA + TX = 92.6% of all orders**:

| State | % orders | Parcel | Deed/Plat | Appraiser |
|---|---|---|---|---|
| FL | 51.7% | 67/67 ✅ | 67/67 ✅ (5 auto-download deeds) | 67/67 ✅ |
| GA | 33.8% | 90/159 (gap = polygon, paid API needed) | 159/159 ✅ | 159/159 ✅ |
| TX | 7.1% | 254/254 ✅ | 212/254 | 254/254 ✅ |
| OH | 1.5% | 88/88 ✅ | 72/88 | 79/88 |
| NJ | 1.1% | 21/21 ✅ | 21/21 ✅ | 21/21 ✅ |

Nationwide parcels: **2,082 / 3,144 counties (66.2%)**; 34 states have a statewide parcel
service; every county has at least a NETROnline directory fallback.

## 9. Who runs where — the three-tier story for the BA

| Tier | Repo | Runs on | For |
|---|---|---|---|
| POC Classic + QuickPlot | SurveyResearch | the user's Windows PC (dev) / office server (prod) | demo & current validation |
| Engine | researchhub-engine | Docker (db+redis+api+worker) anywhere; will join the parent on AWS | the productized pipeline |
| Parent | mapperty-reference | **AWS us-east-1 (ECS)** with Cognito | the real tenant-facing product |

US egress (needed because FEMA & county portals geo-block non-US IPs) is answered fully in
`05-deployment-egress.md`. Short version: **the parent is already on AWS us-east-1, so it's
native — no VPN needed in production**; the POC's VPN was a developer-machine workaround.

---
Next: `02-engine-deep-dive.md` (backend) · `03-frontend-deep-dive.md` (frontend) ·
`04-data-sources-registry.md` (data) · `05-deployment-egress.md` (hosting) ·
`06-glossary-conventions.md` (vocabulary) · `07-opportunities-roadmap.md` (what's next).