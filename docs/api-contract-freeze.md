# API Contract Freeze — Research Engine `/api/v1/research/*`

The transport contract for the Research Engine HTTP API. Frozen on the date
this wave shipped; the breach report (`docs/regression-matrix.md` §1b) called
out five contract oddities that were fixed **in the implementation** so the
schema, DB state machine and frontend renderers agree. This document is the
freeze: what may and may not change, what the frontends consume, and how the
freeze is enforced by CI.

Companion docs (read together):

| doc | freezes |
|---|---|
| `docs/result-schema.md` | the research **result payload** vocabulary (`ResearchResult`/`StepResult`) |
| `docs/source-contract.md` | the adapter interface + `SourceOutcome` taxonomy |
| `docs/job-lifecycle.md` | the persisted job/documented state machines |
| **this doc** | the **HTTP surface**, envelope rules, and stability gates |

## 1. The frozen surface

`router.py` registers one APIRouter: `prefix="/api/v1/research"`. These five
endpoints are the contract — no path or verb may be removed or renamed.

| method | path | request | response (200) | errors |
|---|---|---|---|---|
| POST | `/jobs` | `CreateResearchJobRequest` | `DataEnvelope[ResearchJob]` | 404, 409, 422 |
| GET | `/jobs/{job_id}` | — | `DataEnvelope[ResearchJob]` | 404 |
| POST | `/jobs/{job_id}/retry` | `RetryResearchJobRequest` (optional) | `DataEnvelope[ResearchJob]` | 404, 409 |
| POST | `/jobs/{job_id}/cancel` | `CancelJobRequest` (optional) | `DataEnvelope[ResearchJob]` | 404, 409 |
| GET | `/orders/{order_id}/jobs` | — | `DataEnvelope[list[ResearchJobSummary]]` | 404 |

`retry` creates a **new job**; the original row is never mutated.

## 2. Envelope and header rules

- **Success:** `{ "data": … }` (`DataEnvelope[T]`). **Failure:** `{ "error":
  { code, message, details? } }` (`ErrorEnvelope`) — a single error shape
  everywhere, `code` from `ResearchErrorCode`, `message` never a traceback.
- **Tenant/actor:** `X-Tenant-Id` and `X-Actor-Id` headers (self-asserted,
  placeholders until Cognito auth lands — deliberate engine choice, distinct
  from the POC/QuickPlot `X-Org-Id`/`X-Actor`). Every query paths through the
  tenant scope first.
- **Idempotency:** `X-Idempotency-Key` on `POST /jobs`. A duplicate
  `(tenant_id, key)` returns the existing job (409 `IDEMPOTENCY_CONFLICT` only
  when tenant resolution is ambiguous). Server generates a key when absent.

## 3. Frozen vocabulary

Enum values shipped in the POC **keep identity forever**. *New* values may be
appended; existing values are never renamed, removed, or re-purposed.

- `ResearchJobStatus`: `queued` `running` `completed` `partial` `failed`
  `cancelling` `cancelled` `reviewed` `archived`.
  Transition guards:

  | transition | guard |
  |---|---|
  | `queued → running` | worker claims the job |
  | `running → completed/partial/failed` | document-set outcome (see §5) |
  | `queued → cancelled` | cancel before the worker starts |
  | `running → cancelling → cancelled` | drain: remaining docs → `skipped` |
  | `completed/partial → reviewed → archived` | sign-off moves, human-gated |
  | terminal → new state | impossible (except reviewed/archived) — retry = new job |

- `ResearchDocStatus`: `queued` `fetching` `fetched` `uploading` `uploaded`
  `failed` `skipped`.
- `ResearchErrorCode`: grouped client `ORDER_NOT_FOUND` … `MISSING_ADDRESS` /
  document `GEOCODE_FAILED` … `TIMEOUT` / system `INTERNAL_ERROR`
  `RATE_LIMITED`.

## 4. Field stability — required vs additive on HTTP responses

A field is **required** if the POC renderers (classic card grid, QuickPlot
research hub) read it to draw a card, a link, or a state. Everything else is
**additive** — it may appear alongside required fields, must default and
degrade gracefully, and no renderer may *require* it before this freeze is
revised.

### `ResearchJob` response

| field | stability | consumer (frontend, from briefing 03) |
|---|---|---|
| `id`, `order_id`, `status` | required | QP order rail + status pill |
| `requested_doc_types` | required | QP research hub "gathering set" row filter |
| `total_documents`, `fetched_documents`, `uploaded_documents`, `failed_documents` | required | QP progress bar + badge row |
| `cancelled_documents` | required | QP cancelled badge |
| `documents[]` | required (single-job GET) | per-document rows |
| `started_at`, `completed_at`, `created_at`, `updated_at`, `created_by` | required | QP history/summary table |
| `error_code`, `error_message` | required | top-level error banner |
| `cancel_reason` | **additive** | audit log only; render defensively (`None` until a cancel records it) |

### `ResearchDocument` (in `documents[]`)

| field | stability | consumer |
|---|---|---|
| `id`, `doc_type`, `status` | required | doc row state + row key |
| `summary`, `link`, `link_label` | required | card text + deep-link button |
| `file` | required (nullable) | download link when a blob exists |
| `source_outcome`, `confidence` | **additive** | engine "why" chip; must not be required |
| `provenance`, `warnings` | **additive** | drill-down audit panel |
| `error_code`, `error_message`, `retryable`, `retry_count` | required (nullable) | failure row + retry affordance |
| `fetched_at` | **additive** | timestamp column |

### `ResearchJobSummary` (`GET /orders/{id}/jobs`)

Required: `id` `order_id` `status` `total_documents` `fetched_documents`
`uploaded_documents` `failed_documents` `cancelled_documents` `created_at`
`completed_at`. **Additive:** `cancel_reason`. The list payload deliberately
excludes `documents[]`, `requested_doc_types` and `created_by` — a compact
listing is part of the contract, so those fields must not be lifted into it.
Detail lives at `GET /jobs/{id}`.

### Frozen `step`/result vocabulary (rendered by the classic card grid)

Restated from `result-schema.md` because the freeze binds them: `status`
`ok|link|empty|error` drives the card color; `summary` is always safe to
render; `link`/`link_label` are the fallback action; `data` is never rendered
directly; `source_outcome`/`confidence`/`provenance`/`warnings`/`error` are
additive classifications riding beside the frozen status.

## 5. Contested-state rulings (this wave)

These were the five observed contract oddities; the fix + regression test for
each is in `docs/regression-matrix.md` §1b:

1. **Cancel is honoring and observable.** `POST /cancel` accepts a `reason`.
   Queued jobs go `cancelled` immediately; running jobs go `cancelling` and
   the worker drains (`skipped` the rest) to `cancelled` — it never flips back
   to `running`. In-flight documents finish their current step.
2. **`reviewed`/`archived` are real enum members** (API + persisted enum),
   reached by sign-off endpoints on the service.
3. **`manual_review` is reachable**: a buffered parcel match (geocoder point
   on a street centerline, ≥40 m buffer) yields `source_outcome=manual_review`,
   `confidence=low`, a warning, and `status=link` — the frozen card shape is
   unchanged.
4. **Job summaries are compact** — `list` returns `ResearchJobSummary`, not
   full jobs with nested documents.
5. **`cancel_reason`** rides on the job row and the summary; `ResearchJob` and
   `ResearchJobSummary` are the only homes for it.

### Rules implied by the rulings

- `skipped` documents never count as `failed`; a drained run must land on
  `cancelled` even when some documents uploaded.
- `cancelling → cancelled` is evaluated **before** document-derived resolution.
- Post-cancel deliveries are drained: `calls == 0`, docs → `skipped`, job →
  `cancelled`.

## 6. The freeze gate

`scripts/export_contracts.py` serializes `openapi.json` + per-schema JSON to
`contracts/`. It is part of CI and **must exit 0** — any drift between
`schemas.py` and the exported contracts fails it. Renderers consuming the
frozen vocabulary must treat the exported schemas as the contract, and must
not require additive fields.

The full gate checklist: engine unit suite green (236 tests), `pytest
tests/test_contract_conformance.py` green, `export_contracts.py` exit 0,
`docs/regression-matrix.md` counts match the suite.

## 7. How to change the contract

1. Additive field only → add to schema, re-export, done.
2. New enum value → additive by rule 3; update the transition table above.
3. New endpoint → additive (new path), update table in §1.
4. Required-field change / rename / removal → **this freeze must be revised**:
   update §1–§4, add a §1b fix-log row, and update the renderers in the same
   wave. The freeze revision is the deliverable, not the code change.