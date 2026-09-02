# ResearchHub Engine - Database Schema Guide

## Quick Overview

The engine stores research results in two main tables:

```
┌─────────────────────────────────┐
│      research_jobs              │  (1 per research run)
│  ┌─────────────────────────────┐│
│  │ id (UUID)                   ││
│  │ order_id (UUID)             ││
│  │ tenant_id (UUID)            ││
│  │ status (enum)               ││
│  │ uploaded_documents (int)    ││
│  │ failed_documents (int)      ││
│  │ created_at (timestamp)      ││
│  └──────────┬────────────────┬─┘│
│             │ 1:N            │
│             ▼                ▼
└─────────────────────────────────┘
             │
             │ CASCADE DELETE
             ▼
┌──────────────────────────────────┐
│      research_documents          │  (6 per job, one per doc type)
│  ┌──────────────────────────────┐│
│  │ id (UUID)                    ││
│  │ job_id (UUID) ──────────────→││
│  │ doc_type (string)            ││
│  │ status (enum)                ││
│  │ summary (text)               ││
│  │ link (URL - fallback)        ││
│  │ file_id (UUID → File)        ││
│  │ error_code (enum|null)       ││
│  │ error_message (text|null)    ││
│  └──────────────────────────────┘│
└──────────────────────────────────┘
```

---

## Table: `research_jobs`

**Purpose:** Master record of a single research execution

### Columns

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | UUID | Primary key | `12345678-1234-1234-1234-123456789abc` |
| `order_id` | UUID | The order being researched | `87654321-4321-4321-4321-987654321xyz` |
| `tenant_id` | UUID | Tenant/org isolation key | `c0000000-0000-0000-0000-000000000001` |
| `idempotency_key` | UUID | For idempotent retries | `99999999-9999-9999-9999-999999999xyz` |
| `requested_doc_types` | JSONB | List of doc types requested | `["PARCEL_RECORD", "DEED_SUBJECT_PARCEL", ...]` |
| `status` | ENUM | Job lifecycle state | `queued`, `running`, `completed`, `partial`, `failed`, `cancelled` |
| `total_documents` | INT | Count of documents (= length of requested_doc_types) | `6` |
| `uploaded_documents` | INT | Successfully fetched & stored | `4` |
| `fetched_documents` | INT | Fetched but not uploaded | `1` |
| `failed_documents` | INT | Failed to fetch | `1` |
| `cancelled_documents` | INT | Intentionally skipped | `0` |
| `error_message` | TEXT | Top-level error (if job failed) | `"Redis connection failed"` |
| `callback_url` | VARCHAR(2048) | Webhook URL for completion notification | `"https://api.example.com/research/webhook"` |
| `cancel_reason` | TEXT | Reason if manually cancelled | `"User cancelled via UI"` |
| `created_at` | TIMESTAMP | When job was created | `2026-09-01 10:30:45` |
| `completed_at` | TIMESTAMP | When job reached terminal state | `2026-09-01 10:35:22` |
| `updated_at` | TIMESTAMP | Last modification | `2026-09-01 10:35:22` |
| `created_by` | UUID | Actor who created this job | `c0000000-0000-0000-0000-000000000002` |

### Example Row

```sql
SELECT * FROM research_jobs LIMIT 1;

 id                    | order_id              | tenant_id             | status      | uploaded_documents | failed_documents | created_at
───────────────────────┼───────────────────────┼───────────────────────┼─────────────┼────────────────────┼──────────────────┼──────────────
 12345678-1234-1234... | 87654321-4321-4321... | c0000000-0000-0000... | partial     | 4                  | 1                | 2026-09-01 10:30:45
```

---

## Table: `research_documents`

**Purpose:** Status and result of fetching one document type within a job

### Columns

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | UUID | Primary key | `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` |
| `job_id` | UUID | Foreign key → research_jobs.id | `12345678-1234-1234-1234-123456789abc` |
| `order_id` | UUID | Denormalized for direct queries | `87654321-4321-4321-4321-987654321xyz` |
| `doc_type` | VARCHAR(100) | Document type identifier | `"PARCEL_RECORD"` |
| `status` | ENUM | Lifecycle state | `queued`, `fetching`, `fetched`, `uploaded`, `failed`, `skipped` |
| `source_outcome` | ENUM | Why the source returned what it did | `FOUND`, `NOT_FOUND`, `ERROR`, `RATE_LIMITED` |
| `confidence` | ENUM | How sure the engine is | `HIGH`, `MEDIUM`, `LOW` |
| `summary` | TEXT | One-line description of result | `"Parcel 262828-612-0000-000-60"` |
| `link` | VARCHAR(2048) | Fallback deep-link (when auto-fetch unavailable) | `"https://pa.polk.county.gov/search?parcel=123456"` |
| `link_label` | VARCHAR(255) | UI label for link | `"View in Polk County GIS"` |
| `file_id` | UUID | Reference to File in evidence module (after S3 upload) | `bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb` |
| `order_file_id` | UUID | Reference to OrderFile (links file to order) | `cccccccc-cccc-cccc-cccc-cccccccccccc` |
| `error_code` | ENUM | What went wrong (if failed) | `SOURCE_OFFLINE`, `NETWORK_ERROR`, `PARCEL_NOT_FOUND`, `RATE_LIMITED` |
| `error_message` | TEXT | Human-readable error | `"County server returned 503 Service Unavailable"` |
| `created_at` | TIMESTAMP | When processing started | `2026-09-01 10:30:45` |
| `updated_at` | TIMESTAMP | Last status change | `2026-09-01 10:31:22` |

### Example Rows

```sql
SELECT doc_type, status, summary, link, error_code 
FROM research_documents 
WHERE job_id = '12345678-1234-1234-1234-123456789abc';

 doc_type                          | status  | summary                        | link                                      | error_code
───────────────────────────────────┼─────────┼────────────────────────────────┼───────────────────────────────────────────┼─────────────────
 PARCEL_RECORD                     | uploaded| Parcel 262828-612-00000-000060 | NULL                                      | NULL
 PROPERTY_APPRAISER_TAX_RECORD     | failed  | Appraiser record not available  | https://pa.polk.county.gov/search         | SOURCE_OFFLINE
 RECORDED_PLAT_SUBDIVISION_MAP     | uploaded| Found plat map (2.3 MB)        | NULL                                      | NULL
 DEED_SUBJECT_PARCEL               | fetched | Clerk not responding (retryable)| https://clerk.polk.county.gov/search      | SOURCE_RATE_LIMITED
 FEMA_FLOOD_ZONE_FIRM              | uploaded| Zone X (no special hazard)      | NULL                                      | NULL
 NGS_CONTROL                       | skipped | No benchmarks available        | https://www.ngs.noaa.gov/surveys          | NO_RESULT
```

---

## Enums

### ResearchJobStatus
```python
"queued"      # Waiting to be processed (job created, worker not yet started)
"running"     # Worker is processing documents
"completed"   # All documents fetched successfully
"partial"     # Some docs fetched, some failed (but job is terminal)
"failed"      # Critical failure (no docs fetched)
"cancelled"   # User cancelled or system terminated
```

### ResearchDocStatus
```python
"queued"      # Waiting (initial state)
"fetching"    # Worker is currently fetching this document
"fetched"     # Source provided a result (may be link-only, not a file)
"uploaded"    # File successfully stored in S3 + linked
"failed"      # Could not fetch (may be retryable)
"skipped"     # Intentionally skipped or no data available
```

### ErrorCode (when status = failed or fetched)
```python
"SOURCE_OFFLINE"        # County/source not responding
"SOURCE_RATE_LIMITED"   # WAF/bot protection triggered
"PARCEL_NOT_FOUND"      # Parcel ID not found in county records
"NO_RESULT"             # Source doesn't have data (e.g., no flood zone)
"NETWORK_ERROR"         # Connection timeout or network failure
"PARSING_ERROR"         # Downloaded file, but couldn't parse
"INVALID_INPUT"         # Order address/county invalid
"SYSTEM_ERROR"          # Internal error (check logs)
```

### SourceOutcome
```python
"FOUND"                 # Source found data for this parcel
"NOT_FOUND"             # Source confirmed data doesn't exist
"ERROR"                 # Source returned an error
"RATE_LIMITED"          # Source rejected due to rate limiting
"PARTIAL"               # Source found some data but not complete
```

### Confidence
```python
"HIGH"                  # Highly confident this matches the parcel
"MEDIUM"                # Probable match (e.g., same street, nearby parcel)
"LOW"                   # Uncertain match (address may be approximate)
```

---

## Querying Examples

### Get a complete job with all documents

```sql
SELECT 
  j.id as job_id,
  j.order_id,
  j.status as job_status,
  j.created_at,
  j.completed_at,
  json_agg(
    json_build_object(
      'doc_type', d.doc_type,
      'status', d.status,
      'summary', d.summary,
      'error_code', d.error_code
    )
  ) as documents
FROM research_jobs j
LEFT JOIN research_documents d ON j.id = d.job_id
WHERE j.id = '12345678-1234-1234-1234-123456789abc'
GROUP BY j.id;
```

### Find jobs with failures

```sql
SELECT 
  j.id,
  j.status,
  j.created_at,
  j.failed_documents,
  d.doc_type,
  d.error_code,
  d.error_message
FROM research_jobs j
JOIN research_documents d ON j.id = d.job_id
WHERE d.status = 'failed'
  AND j.created_at > NOW() - INTERVAL '24 hours'
ORDER BY j.created_at DESC;
```

### Get documents with fallback links (for UI display)

```sql
SELECT 
  d.doc_type,
  d.status,
  d.summary,
  CASE 
    WHEN d.file_id IS NOT NULL THEN 'Downloaded'
    WHEN d.link != '' THEN 'Manual Link'
    ELSE 'Not Available'
  END as availability,
  d.link,
  d.link_label
FROM research_documents d
WHERE d.job_id = '12345678-1234-1234-1234-123456789abc';
```

### Track retry history (jobs for same order)

```sql
SELECT 
  id as job_id,
  status,
  uploaded_documents,
  failed_documents,
  created_at
FROM research_jobs
WHERE order_id = '87654321-4321-4321-4321-987654321xyz'
ORDER BY created_at DESC;
```

### Find jobs completed within SLA

```sql
SELECT 
  id,
  order_id,
  EXTRACT(EPOCH FROM (completed_at - created_at)) as duration_seconds,
  uploaded_documents,
  failed_documents
FROM research_jobs
WHERE status IN ('completed', 'partial')
  AND completed_at IS NOT NULL
  AND (completed_at - created_at) < INTERVAL '5 minutes'
ORDER BY created_at DESC;
```

---

## File Storage Mapping

When `status = "uploaded"`, the file is stored at:

```
{STORAGE_ROOT}/{tenant_id}/{order_id}/{doc_type}.{ext}

Example:
data/e2e_evidence/c0000000-0000-0000-0000-000000000001/12345678-1234-1234-1234-123456789abc/PARCEL_RECORD.pdf
                  └─ TENANT_ID ────────────────────────┘└─ ORDER_ID ──────────────────────────┘└─ DOC_TYPE ──┘
```

In production (S3, via `storage.py` when `QP_STORAGE_BACKEND=s3`):
```
s3://{QP_S3_BUCKET}/{QP_S3_PREFIX}/{org_id}/{order_id}/{doc_type}.{ext}
```
NOTE: the S3 backend reads `QP_S3_BUCKET`/`QP_S3_PREFIX` env vars (default prefix
`quickplot`); `config.py`'s `S3_ARTIFACTS_BUCKET`/`AWS_S3_REGION_NAME` are parent-compatible
naming not yet wired to storage — rewire at parent integration.

The database stores:
- `research_documents.file_id` → File.id in evidence module
- `research_documents.order_file_id` → OrderFile.id (link to order)
- Physical file location is managed by File.path or S3 key

---

## Status Progression Timeline

### Successful Upload
```
Job Status:        queued → running → completed
Doc Status:   queued → fetching → fetched → uploaded
                                           ↓
                                      File in S3
                                    file_id set
```

### Fetch with Fallback Link Only
```
Job Status:        queued → running → partial (some docs have links only)
Doc Status:   queued → fetching → fetched
                                   ↓
                              No file uploaded
                            link field populated
                          error_code = null
```

### Fetch Failure
```
Job Status:        queued → running → partial (some failed)
Doc Status:   queued → fetching → failed
                                   ↓
                            error_code set
                          error_message set
                               link set (fallback)
```

### Retry (New Job)
```
First Job:   completed | partial | failed
                ↓
           User calls POST /retry
                ↓
           New Job ID generated
                ↓
New Job:     queued → running → completed/partial/failed
                ↓
         Only retried doc_types process
        (doesn't re-fetch parcel, FEMA, etc.)
```

---

## Integration Notes

When integrating into parent repo:

1. `order_id` becomes FK → `orders.id` (CASCADE)
2. `tenant_id` becomes FK → `tenants.id` (RESTRICT)
3. `file_id` becomes FK → `files.id` (SET NULL)
4. `order_file_id` becomes FK → `order_files.id` (SET NULL)
5. Add `app/modules/research/` containing these models
6. Swap `order_provider` in `adapters.py` to read from `orders` module

---

## Performance Tips

### Indexes (automatically created)
- `(job_id, doc_type)` — unique
- `(order_id)` — tenants list jobs for order
- `(job_id)` — list documents per job
- `(status)` — find pending jobs

### Common Queries (all indexed)
```sql
-- Fast: By job_id
SELECT * FROM research_documents WHERE job_id = ?

-- Fast: By order_id
SELECT DISTINCT job_id FROM research_documents WHERE order_id = ?

-- Fast: Pending work
SELECT * FROM research_jobs WHERE status = 'running'
```

### Avoid (or add indexes)
```sql
-- Slow: Unindexed doc_type scan
SELECT * FROM research_documents WHERE doc_type = 'PARCEL_RECORD'

-- Solution: If frequently needed, add:
CREATE INDEX idx_research_doc_type ON research_documents(doc_type)
```
