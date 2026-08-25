# Migration provenance

This repository was carved out of the POC repo `poc01/SurveyResearch`
(git: https://github.com/NageshGsource/SurveyResearch.git) on 2026-08-24.

Base commit of the extraction: `f09e19f` (branch `feat/ga-oh-county-expansion`,
which contains `main` at `e4fa51e`).

## What was carried over

| Path here | Origin there | Notes |
|---|---|---|
| `backend/app/` | verbatim | services, data registry, quickplot v2 layer, db/config/models/main |
| `tests/` | verbatim | conftest + parcel units + QuickPlot API/UI suites |
| `requirements.txt` | verbatim | intentionally unpinned (`>=`) — Python 3.14 has no wheels for old pinned pydantic; do not re-pin |
| `frontend/quickplot.html`, `frontend/src/qp/`, `frontend/vendor/`, `frontend/assets/` | verbatim | demo client for the v2 API only |
| `docs/INTEGRATION.md` | verbatim | living API+DB reference until superseded by contracts |

## What was deliberately left behind

Classic UI (`frontend/index.html`, `frontend/src/{app.js,components,lib,styles}`),
`Knowledge/` business workbooks, POC-era docs (emails, VPN setup, expansion plans),
`deploy/` + Docker Compose variants, root launcher scripts, saved `jobs/`/`evidence/`
output data, and the county-expansion verification reports.

The POC repo remains frozen as the domain reference: its `docs/HANDOFF.md` holds the
per-state coverage status and the source-verification lessons that still apply to
`backend/app/data/`.

## Rule going forward

Engine behavior changes happen here. New county/source *data* continues to be authored
as state modules under `backend/app/data/states/` following the same conventions
(verify coverage on a point grid, never invent a records URL — see POC HANDOFF §4).
