# ResearchHub — Technical Briefing (Index)

Everything a new developer, a frontend engineer, a backend engineer, or the BA needs to
understand about how the ResearchHub survey-research product actually works — from the
smallest variable up to the deployment graph. Written from the code, with `file:line`
citations so nothing is "trust me".

## The three codebases (why there are three)

| # | Repo | Path | What it is | Status |
|---|---|---|---|---|
| 1 | **SurveyResearch (POC)** | `poc01/SurveyResearch` | The original working prototype: a local FastAPI web app with two UIs — **Classic** (address-first tool) and **QuickPlot** (order-centric hub). Contains the battle-tested county registry and the data-source **services** (`parcel`, `fema`, `ngs`, `clerk`, `geocode`, …). | Working; **do not break** its classic app. Its data + services are the crown jewels. |
| 2 | **researchhub-engine** | `researchhub-engine` | The **standalone engine** extracted from the POC: a production-shaped FastAPI service with a two-phase research pipeline, a Celery worker, its own tables (Postgres migrations), and a frozen `/api/v1/research/*` contract. | This is the forward-looking codebase. Most of this briefing is about it. |
| 3 | **mapperty-reference (parent)** | `mapperty-reference` | The larger monolith this product will live inside. Already deployed to **AWS us-east-1 (ECS)**, with **Cognito** auth. Its `orders`/`evidence`/`identity` modules are where the engine's stand-ins will be swapped in. | Parent owns auth, hosting, tenants. |

> The engine was deliberately built **standalone** (own `orders`/`tenants`/`files` stand-ins)
> so it can be tested and demoed on its own; at integration it drops onto the parent's real
> tables. That swap list is the "seams" table in every deep-dive.

## The one-sentence product

A surveyor clicks an order, the system fetches/roots out the mortgage-survey evidence for a property:
**Parcel ID, Deed, Plat, Flood map, survey control (NGS), and the appraiser tax record** — downloading
what has a public data source and giving a verified one-click link for everything else. Nothing is a
dead end.

## Reading order by audience

```
BA / product owner      → 01 System Overview  → 04 Data Sources → 07 Opportunities
Frontend team           → 01 System Overview  → 03 Frontend Deep Dive → 06 Glossary
Backend team            → 01 System Overview  → 02 Engine Deep Dive → 04 Data Sources
                          → 05 Deployment & Egress → 07 §parent-integration
DevOps / hosting        → 05 Deployment & Egress
Everyone                → 06 Glossary (the vocabulary used everywhere)
```

## Document index

| Doc | Audience | Contents |
|---|---|---|
| `00-INDEX.md` | all | This file — repo map + how to read the set |
| `01-system-overview.md` | **BA + all** | The six survey documents, the two UIs, how a request flows end-to-end, the fallback philosophy, the Evidence Locker + locking rules, live coverage numbers |
| `02-engine-deep-dive.md` | **Backend** | Every module & function of the engine: contracts, schemas, ORM, service, router, worker, orchestration (the 11-adapter two-phase pipeline), storage, alembic chain, all seams |
| `03-frontend-deep-dive.md` | **Frontend** | Classic (`index.html` + `src/*`) and QuickPlot (`quickplot.html` + `src/qp/*`) file-by-file: load order, every component, state flow, the `api()` client, hash router, design tokens, every screen → its API calls, the embed-into-parent path |
| `04-data-sources-registry.md` | Backend/BA | The county registry structure + merge precedence, the state modules, the six data authorities with real sample queries, the coverage-verification gate, linkcheck verdicts |
| `05-deployment-egress.md` | Backend/DevOps | Dev run paths, the live E2E harness, the Docker stack, AWS us-east-1 hosting, **the US-egress/VPN decision**, the real remaining risk (shared-IP WAF/rate-limit blocking) |
| `06-glossary-conventions.md` | all | Every term/variable/convention: statuses, doc-type strings, `org_id`, `lock_seal`, `situs`, the buffered parcel query (75/150/300 m), `build_key` guard, "don't fix the TX URL", … |
| `07-opportunities-roadmap.md` | **BA + product** | Committed backlog P1–P6 with order-volume math, the SaaS productionization table, brainstormed new ideas, and the parent-integration task checklist |

## Repo map (top level)

```
ResearchHub/
├─ poc01/SurveyResearch/          # POC — 2 UIs, services, county registry
│   ├─ backend/app/main.py        #   FastAPI app (classic + /api/v2)
│   ├─ backend/app/services/      #   geocode · parcel · appraiser · clerk·scraper · fema · ngs · downloader · jobs · evidence · storage · http
│   ├─ backend/app/data/          #   county_platforms.py registry · states/* · geography · reference · records_links.json
│   ├─ backend/app/quickplot/     #   v2 layer (orders/research/locker/catalog)
│   └─ frontend/                  #   index.html (Classic) + quickplot.html (QuickPlot)
├─ researchhub-engine/            # THE ENGINE
│   └─ backend/app/engine/        #   contracts · schemas · models · service · router · worker · adapters · orchestration/
│       ├─ orchestration/         #     context.py · sources.py · steps.py · runner.py · folders.py
│       ├─ order_source.py        #   dev `orders` stand-in
│       └─ evidence_source.py     #   dev `files`/`order_files` stand-in
│   ├─ backend/alembic/           #   0002 base shim → 0001 research tables
│   ├─ scripts/                   #   export_contracts.py · e2e_local.py
│   └─ tests/                     #   202 offline tests
└─ mapperty-reference/            # PARENT — AWS us-east-1, Cognito, real orders/evidence/identity
    └─ app/modules/               #   orders (stub) · evidence (gap) · identity · survey · admin …
```

## Ground rules these docs assume

- **The POC's `result.json` vocabulary is frozen** — `ok | link | empty | error`. Engine-only
  reasoning rides in *additive* fields (`source_outcome`, `confidence`, `provenance`, `error`).
- **No URLs are invented.** Every records link came from a live-verified .gov/.org/.us source and
  is re-checkable via `/api/linkcheck`.
- **Address is the only required field.** Selected county wins over the geocoded one.
- File paths cited like `backend/app/engine/service.py:149` are relative to the repo in the header
  of each doc unless stated otherwise.