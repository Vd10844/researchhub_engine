# ResearchHub Engine - Interactive Demo Guide

## Architecture Overview

```
Your Address (with county, parcel_id)
    ↓
POST /api/v1/research/jobs
    ↓
Service Layer (ResearchService)
    ├─ Validates Order + County
    ├─ Creates ResearchJob + ResearchDocument rows
    └─ Enqueues Celery worker
    ↓
Orchestration Pipeline (fetches the 6 requested document sources in order)
    ├─ Parcel Record Fetcher
    ├─ Deed Fetcher
    ├─ Plat Map Fetcher
    ├─ FEMA Flood Zone Fetcher
    ├─ NGS Control/Benchmarks Fetcher
    └─ Property Appraiser Tax Record Fetcher
    ↓
For Each Document:
    ├─ Status: queued → fetching → fetched (or failed/skipped)
    ├─ If successful: Download file → Upload to S3
    ├─ If failed: Create fallback link + error message
    └─ Store metadata in research_documents table
    ↓
Polling GET /api/v1/research/jobs/{id}
    ↓
Results stored in Database:
    ├─ research_jobs (1 row per job)
    ├─ research_documents (6 rows per job, one per document type)
    └─ Files stored in: data/e2e_evidence/{tenant_id}/{order_id}/
```

---

## Step 1: Setup Environment

### 1a. Activate Virtual Environment
```powershell
cd e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine
.venv\Scripts\Activate.ps1
```

### 1b. Start Docker Services (PostgreSQL + Redis)
```powershell
docker compose up db redis -d
```

Wait for health checks:
```powershell
# Check if services are ready
docker compose ps

# Or manually test:
psql -U postgres -h localhost -d researchhub -c "SELECT 1;"
redis-cli ping
```

### 1c. Apply Database Migrations
```powershell
cd e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine
alembic upgrade head
```

---

## Step 2: Run the API + Worker

Open **two separate PowerShell windows** in the project root:

### Window 1: FastAPI Server
```powershell
cd e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine
.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn app.main:app --port 8000 --reload
```

You'll see:
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Visit: `http://127.0.0.1:8000/docs` (interactive API documentation)

### Window 2: Celery Worker
```powershell
cd e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine
.venv\Scripts\Activate.ps1
cd backend
celery -A app.engine.worker.celery_app worker --loglevel=info --queues=research --pool=solo
```

You'll see the worker waiting for tasks.

---

## Step 3: Seed a Test Order (DB)

Open a **third PowerShell window**:

```powershell
cd e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine
.venv\Scripts\Activate.ps1
cd backend

# Create a test order in the database
python -c "
import uuid
from app.db.base import SessionLocal
from app.engine.order_source import seed_dev_order

TENANT = uuid.UUID('c0000000-0000-0000-0000-000000000001')
db = SessionLocal()
try:
    o = seed_dev_order(
        db,
        tenant_id=TENANT,
        address_line_1='2628 US Hwy 98 N',        # <-- CUSTOMIZE THIS
        city='Lakeland',                           # <-- CUSTOMIZE THIS
        state='FL',                                # <-- CUSTOMIZE THIS
        zip_code='33805',
        county='Polk',                             # <-- CUSTOMIZE THIS (FIPS or name)
        parcel_id='262828612000000060',            # <-- CUSTOMIZE THIS
        survey_type='Location Survey',
    )
    print(f'Order created: {o.id}')
    print(f'Address: {o.address_line_1}, {o.city}, {o.state}')
    print(f'County: {o.county}, Parcel: {o.parcel_id}')
finally:
    db.close()
"
```

**Copy the Order ID** from the output. It looks like: `12345678-1234-1234-1234-123456789012`

---

## Step 4: Create a Research Job (API Call)

```powershell
# Set variables
$ORDER_ID = "12345678-1234-1234-1234-123456789012"  # <-- From step 3
$TENANT_ID = "c0000000-0000-0000-0000-000000000001"
$ACTOR_ID = "c0000000-0000-0000-0000-000000000002"

# Create a research job
$response = Invoke-WebRequest `
  -Uri "http://127.0.0.1:8000/api/v1/research/jobs" `
  -Method POST `
  -ContentType "application/json" `
  -Headers @{
    "X-Tenant-Id" = $TENANT_ID
    "X-Actor-Id" = $ACTOR_ID
    "X-Idempotency-Key" = ([guid]::NewGuid()).Guid
  } `
  -Body (@{
    order_id = $ORDER_ID
    document_types = @(
      "PARCEL_RECORD"
      "PROPERTY_APPRAISER_TAX_RECORD"
      "RECORDED_PLAT_SUBDIVISION_MAP"
      "DEED_SUBJECT_PARCEL"
      "FEMA_FLOOD_ZONE_FIRM"
      "NGS_CONTROL"
    )
  } | ConvertTo-Json)

$data = $response.Content | ConvertFrom-Json
$JOB_ID = $data.data.id

Write-Host "Job created: $JOB_ID"
Write-Host "Status: $($data.data.status)"
```

You'll see in the **Celery worker window**: the job is being processed!

---

## Step 5: Poll Job Status (Real-time Progress)

```powershell
$ORDER_ID = "12345678-1234-1234-1234-123456789012"  # From step 3
$JOB_ID = "87654321-4321-4321-4321-210987654321"    # From step 4
$TENANT_ID = "c0000000-0000-0000-0000-000000000001"
$ACTOR_ID = "c0000000-0000-0000-0000-000000000002"

# Poll until complete (timeout = 4 minutes)
$deadline = (Get-Date).AddSeconds(240)
$terminal_statuses = @("completed", "partial", "failed", "cancelled")

while ((Get-Date) -lt $deadline) {
    $response = Invoke-WebRequest `
      -Uri "http://127.0.0.1:8000/api/v1/research/jobs/$JOB_ID" `
      -Method GET `
      -Headers @{
        "X-Tenant-Id" = $TENANT_ID
        "X-Actor-Id" = $ACTOR_ID
      }
    
    $data = $response.Content | ConvertFrom-Json
    $job = $data.data
    
    Write-Host "Status: $($job.status) | Uploaded: $($job.uploaded_documents)/$($job.total_documents) | Failed: $($job.failed_documents)" -ForegroundColor Cyan
    
    if ($terminal_statuses -contains $job.status) {
        Write-Host "✓ Job terminal!" -ForegroundColor Green
        $job | ConvertTo-Json -Depth 10 | Write-Host
        break
    }
    
    Start-Sleep -Seconds 3
}
```

**Example output:**
```
Status: queued | Uploaded: 0/6 | Failed: 0
Status: running | Uploaded: 1/6 | Failed: 0
Status: running | Uploaded: 2/6 | Failed: 1
Status: partial | Uploaded: 2/6 | Failed: 1
✓ Job terminal!
```

---

## Step 6: Inspect Results in Database

### 6a. View the Job Metadata

```powershell
# Connect to PostgreSQL
psql -U postgres -h localhost -d researchhub

# List all research jobs
SELECT 
  id, status, total_documents, uploaded_documents, failed_documents, created_at
FROM research_jobs
ORDER BY created_at DESC;

# Get details for a specific job
SELECT 
  id, order_id, status, 
  uploaded_documents, failed_documents, total_documents,
  error_message
FROM research_jobs
WHERE id = 'YOUR_JOB_ID';
```

### 6b. View Individual Document Results

```sql
-- See what was fetched for each document type
SELECT 
  id,
  doc_type,
  status,
  summary,
  link,
  link_label,
  file_id,
  error_code,
  error_message
FROM research_documents
WHERE job_id = 'YOUR_JOB_ID'
ORDER BY doc_type;
```

**Example output:**
```
 doc_type                          │ status  │ summary                        │ link
───────────────────────────────────┼─────────┼────────────────────────────────┼──────
 PARCEL_RECORD                     │ uploaded│ Found parcel record for... │ <blob key>
 PROPERTY_APPRAISER_TAX_RECORD     │ failed  │ Not found in county system  │ https://pa.polk.county.gov/search
 RECORDED_PLAT_SUBDIVISION_MAP     │ uploaded│ Found plat map              │ <blob key>
 DEED_SUBJECT_PARCEL               │ fetched │ Clerk not responding        │ https://clerk.polk.county.gov
 FEMA_FLOOD_ZONE_FIRM              │ uploaded│ Zone X (no special hazard)   │ <blob key>
 NGS_CONTROL                       │ skipped │ No benchmarks found         │
```

---

## Step 7: View Fetched Files

### 7a. Local Storage Location
```powershell
# Files are stored in: data/e2e_evidence/
ls -Recurse "e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine\data\e2e_evidence\" | 
  Select-Object FullName, Length | 
  Format-Table -AutoSize
```

**Structure:**
```
data/e2e_evidence/
└── c0000000-0000-0000-0000-000000000001/        # TENANT_ID
    └── 12345678-1234-1234-1234-123456789012/    # ORDER_ID
        ├── DEED_SUBJECT_PARCEL.pdf              # Downloaded document
        ├── PARCEL_RECORD.pdf
        ├── FEMA_FLOOD_ZONE_FIRM.pdf
        ├── RECORDED_PLAT_SUBDIVISION_MAP.pdf
        ├── PROPERTY_APPRAISER_TAX_RECORD.pdf
        └── NGS_CONTROL.pdf (if found)
```

### 7b. Open a PDF

```powershell
# Get file_id from research_documents
$PDF_PATH = "e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine\data\e2e_evidence\c0000000-0000-0000-0000-000000000001\12345678-1234-1234-1234-123456789012\PARCEL_RECORD.pdf"

# Open with default viewer
Start-Process $PDF_PATH
```

---

## Step 8: Understanding Error Cases

### Why might a document fail to fetch?

| Scenario | Error Code | Status | Fallback Link |
|----------|-----------|--------|---------------|
| County data not available | `SOURCE_UNAVAILABLE` | fetched | Deep-link to county website |
| WAF/Bot protection triggered | `SOURCE_UNAVAILABLE` | fetched | Link to manual search page |
| Parcel ID invalid | `PARCEL_NOT_FOUND` | failed | County GIS search URL |
| Geocoder / parcel lookup failed | `GEOCODE_FAILED`, `PARCEL_NOT_FOUND` | failed | Search URL |
| Network timeout | `TIMEOUT` | fetched (retryable) | Source website homepage |

### View Errors in Detail
```sql
SELECT 
  doc_type,
  status,
  error_code,
  error_message,
  link,
  link_label
FROM research_documents
WHERE job_id = 'YOUR_JOB_ID'
  AND status IN ('failed', 'fetched');
```

---

## Step 9: Advanced Inspection - Full Job Response

```powershell
# Get complete job details with all documents
$JOB_ID = "YOUR_JOB_ID"
$TENANT_ID = "c0000000-0000-0000-0000-000000000001"
$ACTOR_ID = "c0000000-0000-0000-0000-000000000002"

$response = Invoke-WebRequest `
  -Uri "http://127.0.0.1:8000/api/v1/research/jobs/$JOB_ID" `
  -Method GET `
  -Headers @{
    "X-Tenant-Id" = $TENANT_ID
    "X-Actor-Id" = $ACTOR_ID
  }

$json = $response.Content | ConvertFrom-Json
$json.data | ConvertTo-Json -Depth 10 | Out-File "job_results.json"

Write-Host "Full results saved to: job_results.json"
```

---

## Step 10: Retry Failed Documents

```powershell
# Retry only the failed/fetched documents
$response = Invoke-WebRequest `
  -Uri "http://127.0.0.1:8000/api/v1/research/jobs/$JOB_ID/retry" `
  -Method POST `
  -ContentType "application/json" `
  -Headers @{
    "X-Tenant-Id" = $TENANT_ID
    "X-Actor-Id" = $ACTOR_ID
    "X-Idempotency-Key" = ([guid]::NewGuid()).Guid
  } `
  -Body (@{
    document_types = @("PARCEL_RECORD", "DEED_SUBJECT_PARCEL")
  } | ConvertTo-Json)

$new_job = $response.Content | ConvertFrom-Json
Write-Host "New job created: $($new_job.data.id)"
```

---

## Step 11: Cleanup

```powershell
# Stop services
docker compose down

# Clear local evidence files (optional)
Remove-Item -Recurse "e:\DPR\2026\Q2\August\ResearchHub\researchhub-engine\data\e2e_evidence\*"
```

---

## Understanding the Data Flow

### ResearchJob (Master Record)
```
{
  "id": "job-123",
  "order_id": "order-456",
  "tenant_id": "tenant-789",
  "status": "partial",              # queued → running → completed/partial/failed
  "requested_doc_types": [6],       # Count of requested types
  "total_documents": 6,
  "uploaded_documents": 4,          # Successfully stored in blob storage
  "failed_documents": 1,
  "cancelled_documents": 1,         # Skipped due to cancel/observed terminal state
  "created_at": "2026-09-01T10:30:00Z",
  "completed_at": "2026-09-01T10:35:00Z"
}
```

### ResearchDocument (Per-Document Result)
```
{
  "id": "doc-789",
  "job_id": "job-123",
  "doc_type": "PARCEL_RECORD",
  "status": "uploaded",             # queued → fetching → fetched/uploaded/failed/skipped
  "summary": "Parcel found: Lot 5, Block A",
  "link": "https://county.gov/parcel/123456",    # Fallback link
  "link_label": "View in County GIS",
  "file_id": "file-111",            # Ref to File in evidence module
  "order_file_id": "orderfile-222", # Ref to OrderFile
  "error_code": null,
  "error_message": null,
  "provenance": [],                 # audit trail of source hits
  "created_at": "2026-09-01T10:30:00Z"
}
```

### File Storage Structure
```
Local filesystem (data/e2e_evidence) or S3 (QP_S3_BUCKET in prod):
└── {org_id}/{order_id}/
    ├── PARCEL_RECORD.pdf                    (actual document)
    ├── DEED_SUBJECT_PARCEL.pdf
    ├── FEMA_FLOOD_ZONE_FIRM.pdf
    └── ...

Database reference:
  file_id → File.id (evidence module)
  order_file_id → OrderFile.id (links file to order)
```

---

## Custom Address Template

To test with YOUR address:

```powershell
# 1. Find your county FIPS code or name
#    https://en.wikipedia.org/wiki/List_of_United_States_counties_and_county_equivalents

# 2. Seed a custom order
python -c "
import uuid
from app.db.base import SessionLocal
from app.engine.order_source import seed_dev_order

TENANT = uuid.UUID('c0000000-0000-0000-0000-000000000001')
db = SessionLocal()
try:
    o = seed_dev_order(
        db,
        tenant_id=TENANT,
        address_line_1='123 MAIN STREET',              # Your address
        city='ANYTOWN',                                # Your city
        state='FL',                                    # Your state (2-letter)
        zip_code='12345',                              # Your ZIP
        county='YOUR_COUNTY_NAME_OR_FIPS',             # Your county
        parcel_id='123456789000000000',                # Your parcel ID (if known)
        survey_type='Location Survey',
    )
    print(f'Order: {o.id}')
finally:
    db.close()
"

# 3. Then use that order_id in step 4 (Create Research Job)
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Order not found" | Ensure you ran step 3 (Seed Order) |
| Worker not processing | Check Celery window for errors; restart with `--loglevel=debug` |
| "Column does not exist" | Run `alembic upgrade head` |
| Files not saved | Check `JOBS_DIR` and `QP_STORAGE_ROOT` env vars |
| API 401 Unauthorized | Include `X-Tenant-Id` and `X-Actor-Id` headers |
| "No such table" | Ensure migrations ran: `alembic current` |

---

## Next Steps

1. **Test with multiple addresses** to see how different counties respond
2. **Inspect source adapters** in `backend/app/services/` to see how each data source works
3. **Review orchestration pipeline** in `backend/app/engine/orchestration/` to understand retry logic
4. **Run full test suite** to validate everything: `.venv\Scripts\python -m pytest tests -q`
