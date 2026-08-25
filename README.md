# ResearchHub Engine

The research core of ResearchHub: given a property address (or parcel ID), it resolves the
parcel and assembles the survey research document set — parcel, deed, plat, flood, survey
control, appraiser — auto-fetching from public sources where possible and returning verified
one-click county links everywhere else.

This is an **API-only service**. The product UI is owned by the frontend team; the platform
(order management, users, review workflow) is owned by the backend team. This engine exposes
`/api/v2/*` and nothing else is a committed interface.

- API reference: [`docs/INTEGRATION.md`](docs/INTEGRATION.md)
- Contracts for consumers: [`contracts/`](contracts/) (generated — do not hand-edit)
- Contract docs: [`docs/engine/`](docs/engine/)

## Run

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# clerk auto-download needs a browser once:  .venv/Scripts/python -m playwright install chromium
cd backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

Interactive OpenAPI docs: <http://127.0.0.1:8000/docs>

## Test

```bash
.venv/Scripts/python.exe -m pytest tests -q     # offline; no network access required
```

## Layout

```
backend/app/
  services/   research sources today (parcel, geocode, fema, ngs, clerk, appraiser...)
  quickplot/  /api/v2 layer: orders, documents, research runner, source catalog
  data/       per-state registry modules + county platform registry (verified data)
frontend/     demo client only (reference for the UI team; not a deliverable)
contracts/    generated OpenAPI + JSON Schemas consumed by FE/BE teams
docs/engine/  SOURCE_CONTRACT / RESULT_SCHEMA / JOB_LIFECYCLE
scripts/      export_contracts.py regenerates contracts/
```

## Status

Day-1 baseline of the POC-to-engine rebuild. See `MIGRATION.md` for exactly what was
carried over from `poc01/SurveyResearch` and from where.
