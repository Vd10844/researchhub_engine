# Job Lifecycle Specification — Research Engine

How a research job moves through the system: the persisted state machine, the
per-job and per-document lifecycle, retry, cancel, and idempotency. Applies to
the API + worker contract (`engine/schemas.py`, `engine/service.py`,
`engine/worker.py`).

## 1. Resources

- **research_jobs** — one row per research attempt, owns the lifecycle.
- **research_documents** — one row per requested doc type on the job, owns
  per-document progress and the final outcome.
- Both are tenant-scoped (`tenant_id`), actor-audited, soft-deletable.

## 2. Job state machine

`ResearchJobStatus` (persisted in `research_jobs.status`):

```
                ┌──────────┐
        create  │  queued   │
      ─────────►│          │
                └─────┬────┘
                      │ worker picks up
                      ▼
                ┌──────────┐   all designed outcomes      ┌────────────┐
                │  running  │ ───────────────────────────►│  completed  │
                │           │                             └────────────┘
                └─────┬─────┘   ≥1 unexpected failure       ┌─────────┐
                      │         (blocked/broken/retryable) ►│ partial  │
                      │                                     └─────────┘
                      │   context resolution failed          ┌────────┐
                      └────────────────────────────────────►│ failed  │
                                                           └────────┘
   cancel requested while running/queued:
                        running ──► cancelled   (cancel requested → cancelling)
```

Rules:

| transition | guard |
|---|---|
| `queued → running` | worker claims the job; sets `started_at` |
| `running → completed` | every document reached `uploaded`/`fetched`/`skipped` |
| `running → partial` | ≥1 document is `failed`, at least one succeeded |
| `running → failed` | context resolution failed, or all documents failed |
| `queued/running → cancelled` | only via cancel API; queued docs → `skipped` |
| terminal → any new state | impossible on the same row — retries are a NEW job |

## 3. Per-document state machine

`ResearchDocStatus` (persisted in `research_documents.status`):

```
queued ──► fetching ──► fetched ──► uploading ──► uploaded
   │          │              │           │
   │          │              │           └──► failed   (S3 upload error)
   │          │              └──► failed  (adapter error after retries)
   │          └──► failed
   └──► skipped      (not applicable / cancelled before starting)
```

- `fetched` = adapter returned data or a link (nothing uploaded yet).
- `uploaded` = blob copy succeeded + `file_id`/`order_file_id` recorded.
- `failed` carries `error_code`, `error_message`, `retryable`, `retry_count`.

## 4. Terminal job status resolution

`resolve_job_terminal_status(db, job)` computes the job status from its
documents:

```
failed == 0                                   → completed
failed > 0 and ≥1 successful                  → partial
all documents failed (or zero)                → failed
```

`skipped` documents do not count as failed. Same rule drives the job's
denormalized counters (`fetched_documents`, `uploaded_documents`,
`failed_documents`, `cancelled_documents`).

## 5. Retry

POST `/research/jobs/{id}/retry`:

1. Only a **terminal** job is retryable (`completed`/`partial`/`failed`/`cancelled`).
2. Collects the failed doc types (or the caller's explicit subset).
3. **Creates a NEW job** linked to the same order — the original row is never
   mutated. Idempotency key for the retry is a fresh UUID.
4. `run_research(include=[failed_doc_types])` re-fetches ONLY those documents —
   the refactored pipeline honors `include`, so retry does not re-run the whole
   set (this was the POC's silent re-fetch-everything behavior).

## 6. Cancel

POST `/research/jobs/{id}/cancel`:

1. Only `queued`/`running` jobs can be cancelled.
2. The job transitions to `cancelled`; documents not yet started flip to
   `skipped`; in-flight documents finish their current fetch step.

## 7. Idempotency

`X-Idempotency-Key` header (server generates one if absent). A duplicate
`(tenant_id, key)` create returns the existing job instead of creating a second
one. Stored as `research_jobs.idempotency_key`.

## 8. Failure recovery (worker)

- `task_acks_late=True` + `worker_prefetch_multiplier=1`: a crash requeues the
  task instead of silently dropping it.
- A fetch failure for one document never aborts the others; each document row
  is committed independently.
- Top-level worker failure re-raises for Celery retry (`countdown=30`,
  `max_retries=1`).
- `callback_url` (optional): POST a job-summary payload on completion. Delivery
  failures are logged, not fatal.

## 9. Guarantees

- **Locking/evidence integrity is enforced server-side, not in the UI.** A
  document needs a real `doc_type` and all reviewer confirmations before it
  locks; locked documents are not re-typed or hard-deleted (soft delete keeps
  the audit trail pointing at a real row).
- **Research cannot be submitted with zero locked documents.**
- **Context is resolved once per run, not once per document.** The two-phase
  pipeline (`resolve_property_context` → `build_steps`) is the seam that makes
  per-document retry cheap and correct.