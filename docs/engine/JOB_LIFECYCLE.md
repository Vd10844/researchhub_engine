# Job Lifecycle

## States

```
queued → running → completed | partial | failed
                                    ↓
                               reviewed → archived
```

| State        | Persisted in DB | Polled by FE | Next valid transitions        |
|--------------|-----------------|--------------|-------------------------------|
| `queued`     | ✓               | ✓            | `running`, `failed`           |
| `running`    | ✓               | ✓            | `completed`, `partial`, `failed` |
| `completed`  | ✓               | ✓            | `reviewed`, `archived`        |
| `partial`    | ✓               | ✓            | `reviewed`, `archived`        |
| `failed`     | ✓               | ✓            | (terminal)                    |
| `reviewed`   | ✓               | ✓            | `archived`                    |
| `archived`   | ✓               | ✓            | (terminal)                    |

### State definitions

- **queued** — submitted, waiting for the runner to pick it up
- **running** — runner is executing the research pipeline
- **completed** — every adapter returned a designed outcome (`auto`, `link_only`, `blocked`, `broken`)
- **partial** — ≥1 adapter hit an unexpected failure (`retryable`) or returned `empty` where `mandatory` was expected
- **failed** — context resolution failed (no geocode, no parcel ID match, fatal exception)
- **reviewed** — human confirmed the documents are correct and locked them
- **archived** — hidden from default list; retained for audit

### What makes `partial` vs `completed`

The distinction is **not** about whether all data was fetched (link-only is a valid designed outcome).
`partial` means something **unexpected** happened: a source timed out after retries, returned
an ambiguous result needing human review, or a mandatory step ended up `empty`.

In practice: if every step's `source_outcome` is in `{auto, link_only, blocked, broken}`, the
job is `completed`.  If any step has `source_outcome == retryable` or `empty` where `requirement == mandatory`,
it's `partial`.

## Storage layout

```
qp_jobs
  id: UUID (PK)
  org_id: str (tenant scope)
  address: str
  job_number: str
  state: str (JobState enum)
  result_json: Text (JSON-serialized ResearchResult — grows with each step)
  result_sha256: str (for integrity checks)
  created_at: datetime
  updated_at: datetime

qp_documents
  id: UUID (PK)
  job_id: UUID (FK → qp_jobs.id)
  source_id: str (e.g. "parcel.county_hillsborough_fl")
  doc_type: str (parcel | deed | plat | flood | appraiser | benchmarks | site_info | lot_size)
  source_state: str (SourceState enum)
  file_key: str (S3 key)
  file_sha256: str
  reviewer_status: str (none | accepted)
  locked: bool
  created_at: datetime
  updated_at: datetime
  deleted_at: datetime (nullable — soft delete for audit trail)

qp_audit
  id: UUID (PK)
  job_id: UUID (FK)
  actor: str (user ID or "system")
  action: str (research.started | research.completed | document.locked | ...)
  details_json: Text (JSON)
  created_at: datetime
```

## Polling contract

```
GET /api/v2/jobs/{job_id}
→ 200 { id, state, result: ResearchResult | null, updated_at }
```

The consumer polls this endpoint.  `state` transitions are the signal to stop polling.
On `completed` or `partial`, `result` contains the full `ResearchResult`.  On `failed`,
`result` contains partial results + `error` fields.

## Callback contract (optional)

```json
POST <callback_url>
{
  "job_id": "uuid",
  "state": "completed",
  "org_id": "org_abc"
}
```

Delivered on the `completed → reviewed` boundary.  Not guaranteed to be delivered exactly once;
consumers should be idempotent.  Implemented as a fire-and-forget POST from the runner.

## Runner state persistence

The POC uses an in-memory `_RUNS` registry in `quickplot/research.py`.  The engine replaces
this with DB-backed rows so multiple uvicorn workers don't lose run state on restart.

```sql
CREATE TABLE qp_research_runs (
  job_id UUID PRIMARY KEY REFERENCES qp_jobs(id),
  state str NOT NULL,          -- JobState
  thread_id str,
  started_at datetime,
  completed_at datetime,
  error_json Text
);
```

On startup, any `running` rows are re-queued (the process crashed mid-run).
