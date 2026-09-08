#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Interactive Demo: Test ResearchHub Engine with a custom address
.DESCRIPTION
    Orchestrates the full end-to-end demo flow:
    0. Pre-flight: verify Docker, the venv, and (later) the running API + worker
    1. Start Docker services (Postgres + Redis)
    2. Apply migrations (non-fatal in local mode — the API also create_all()s on startup)
    3. Seed a test order with your address
    4. Create a research job
    5. Poll and display results
    6. Show what data was fetched and where it's stored

    PREREQUISITE: the API and the Celery worker must already be running in two
    separate windows (see DEMO_GUIDE.md Step 2). This script talks to the API on
    :8000 and enqueues work the worker consumes — it does NOT start them for you.
.EXAMPLE
    .\demo.ps1
.EXAMPLE
    .\demo.ps1 -Address "123 Main St" -City "Tampa" -State FL -County Hillsborough -ParcelId "..."
#>

param(
    [string]$Address = "2628 US Hwy 98 N",
    [string]$City = "Lakeland",
    [string]$State = "FL",
    [string]$County = "Polk",
    [string]$ParcelId = "262828612000000060",
    [int]$ApiPort = 8000,
    [int]$DbPort = 5433                     # engine Postgres is published on 5433 (see .env)
)

$ErrorActionPreference = "Stop"

$ROOT = Split-Path -Parent $MyInvocation.MyCommandPath
$VENV = Join-Path $ROOT ".venv"
$PYTHON = Join-Path $VENV "Scripts" "python.exe"
$ALEMBIC = Join-Path $VENV "Scripts" "alembic.exe"
$BACKEND = Join-Path $ROOT "backend"
$API = "http://127.0.0.1:$ApiPort"

$TENANT_ID = "c0000000-0000-0000-0000-000000000001"
$ACTOR_ID = "c0000000-0000-0000-0000-000000000002"

function Log {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] $Message" -ForegroundColor $Color
}
function Info    { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }
function Success { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function ErrorMsg { param([string]$Message) Write-Host $Message -ForegroundColor Red }

# ===== SETUP =====
Log "ResearchHub Engine Interactive Demo" "Magenta"
Log ""

# Step 0: Pre-flight — fail fast with actionable messages BEFORE any real work.
Log "Step 0: Pre-flight checks..." "Cyan"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    ErrorMsg "X Docker CLI not found on PATH. Start Docker Desktop and reopen this shell."
    exit 1
}
try { docker info *> $null } catch { }
if ($LASTEXITCODE -ne 0) {
    ErrorMsg "X Docker daemon not responding. Is Docker Desktop running?"
    exit 1
}
if (-not (Test-Path $PYTHON)) {
    ErrorMsg "X venv Python not found at $PYTHON. Create it: python -m venv .venv ; .venv\Scripts\Activate.ps1 ; pip install -r requirements.txt"
    exit 1
}
Success "  OK: Docker + venv present"

# Step 1: Start Docker (idempotent — safe if already up)
Log "Step 1: Starting Docker services (PostgreSQL + Redis)..." "Cyan"
docker compose -f "$ROOT\docker-compose.yml" up db redis -d 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    ErrorMsg "X Docker startup failed. Ensure Docker Desktop is running."
    exit 1
}
Success "  Docker services starting..."

# Wait for Postgres
Log "Waiting for PostgreSQL to be healthy..." "Cyan"
$pgOk = $false
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    $pgId = (docker compose -f "$ROOT\docker-compose.yml" ps -q db)
    if ($pgId) {
        docker exec $pgId pg_isready -U postgres *> $null
        if ($LASTEXITCODE -eq 0) { $pgOk = $true; break }
    }
    Start-Sleep -Seconds 2
}
if ($pgOk) { Success "  PostgreSQL is ready" } else { ErrorMsg "X PostgreSQL did not become healthy in 60s"; exit 1 }

# Wait for Redis
$redisOk = $false
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    $rId = (docker compose -f "$ROOT\docker-compose.yml" ps -q redis)
    if ($rId) {
        $ping = (docker exec $rId redis-cli ping 2>$null)
        if ($ping -match "PONG") { $redisOk = $true; break }
    }
    Start-Sleep -Seconds 2
}
if ($redisOk) { Success "  Redis is ready" } else { ErrorMsg "X Redis did not respond to PING in 30s"; exit 1 }

# Step 2: Apply migrations (NON-FATAL in local mode).
# In RUN_ENV=local the API also runs Base.metadata.create_all() on startup, so a
# migration hiccup should not abort the demo. We run alembic from the project root
# (that's where alembic.ini lives) and only warn on failure.
Log "Step 2: Applying database migrations..." "Cyan"
Push-Location $ROOT
try {
    if (Test-Path $ALEMBIC) {
        $output = & $ALEMBIC upgrade head 2>&1
    } else {
        $output = & $PYTHON -m alembic upgrade head 2>&1
    }
    if ($LASTEXITCODE -eq 0) {
        Success "  Migrations applied"
    } else {
        Info  "  ! Alembic did not exit clean (continuing — local mode create_all() covers schema):"
        Info  ("    " + ($output -join "`n    "))
    }
} catch {
    Info "  ! Alembic error (continuing — local mode create_all() covers schema): $_"
} finally {
    Pop-Location
}

# Step 2b: Pre-flight the running API + worker (the parts this script does NOT start).
Log "Step 2b: Checking that the API + worker are running..." "Cyan"
$apiUp = $false
try {
    $h = Invoke-WebRequest -Uri "$API/api/health" -Method GET -TimeoutSec 5 -SkipHttpErrorCheck
    if ($h.StatusCode -eq 200 -or $h.StatusCode -eq 503) { $apiUp = $true }
    if ($h.StatusCode -eq 503) {
        Info "  ! API is up but reports degraded dependencies (check DB/Redis in the API window)."
    }
} catch { $apiUp = $false }
if (-not $apiUp) {
    ErrorMsg "X API not reachable at $API."
    ErrorMsg "  Start it in a separate window (DEMO_GUIDE.md Step 2), then re-run this script:"
    ErrorMsg "    cd $BACKEND ; ..\.venv\Scripts\python -m uvicorn app.main:app --port $ApiPort --reload"
    ErrorMsg "  And the worker in another window:"
    ErrorMsg "    cd $BACKEND ; ..\.venv\Scripts\celery -A app.engine.worker.celery_app worker --loglevel=info --queues=research --pool=solo"
    exit 1
}
Success "  API reachable at $API"
Info "  (Confirm the Celery worker window is also running — this script can't detect it directly.)"

# Step 3: Seed order with user's address
Log "Step 3: Creating test order with your address..." "Cyan"
Info "Address: $Address, $City, $State | County: $County | Parcel: $ParcelId"

$tempPyFile = Join-Path $env:TEMP "seed_order_temp.py"
$pythonScript = @"
import uuid, sys
sys.path.insert(0, r'$BACKEND')
from app.db.base import SessionLocal
from app.engine.order_source import seed_dev_order

TENANT = uuid.UUID('$TENANT_ID')
db = SessionLocal()
try:
    o = seed_dev_order(
        db,
        tenant_id=TENANT,
        address_line_1='$Address',
        city='$City',
        state='$State',
        county='$County',
        parcel_id='$ParcelId',
        survey_type='Location Survey',
    )
    print(f'ORDER_ID={o.id}')
finally:
    db.close()
"@
$pythonScript | Set-Content -Path $tempPyFile -Encoding UTF8

$ORDER_ID = $null
try {
    $output = & $PYTHON $tempPyFile 2>&1
    $orderLine = $output | Where-Object { $_ -like "*ORDER_ID=*" }
    if ($orderLine) {
        $ORDER_ID = ($orderLine -split "=")[1].Trim()
        Success "  Order created: $ORDER_ID"
    } else {
        ErrorMsg "X Failed to create order"
        ErrorMsg ($output -join "`n")
        exit 1
    }
} catch {
    ErrorMsg "X Order seeding error: $_"
    exit 1
} finally {
    Remove-Item -Path $tempPyFile -Force -ErrorAction SilentlyContinue
}

# Step 4: Create research job
Log "Step 4: Creating research job..." "Cyan"
$IDEMPOTENCY_KEY = [guid]::NewGuid()
$jobPayload = @{
    order_id = $ORDER_ID
    document_types = @(
        "PARCEL_RECORD"
        "PROPERTY_APPRAISER_TAX_RECORD"
        "RECORDED_PLAT_SUBDIVISION_MAP"
        "DEED_SUBJECT_PARCEL"
        "FEMA_FLOOD_ZONE_FIRM"
        "NGS_CONTROL"
    )
} | ConvertTo-Json

$JOB_ID = $null
try {
    $response = Invoke-WebRequest `
        -Uri "$API/api/v1/research/jobs" `
        -Method POST `
        -ContentType "application/json" `
        -Headers @{
            "X-Tenant-Id" = $TENANT_ID
            "X-Actor-Id" = $ACTOR_ID
            "X-Idempotency-Key" = $IDEMPOTENCY_KEY
        } `
        -Body $jobPayload `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck

    if ($response.StatusCode -eq 200) {
        $data = $response.Content | ConvertFrom-Json
        $JOB_ID = $data.data.id
        Success "  Job created: $JOB_ID"
        Info "  Total documents: $($data.data.total_documents)"
    } else {
        ErrorMsg "X Failed to create job (HTTP $($response.StatusCode))"
        ErrorMsg $response.Content
        exit 1
    }
} catch {
    ErrorMsg "X Job creation error: $_"
    exit 1
}

# Step 5: Poll for completion
Log "Step 5: Polling job progress (timeout: 4 minutes)..." "Cyan"
$terminal_statuses = @("completed", "partial", "failed", "cancelled")
$deadline = (Get-Date).AddSeconds(240)
$lastStatus = ""
$jobData = $null

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest `
            -Uri "$API/api/v1/research/jobs/$JOB_ID" `
            -Method GET `
            -Headers @{ "X-Tenant-Id" = $TENANT_ID; "X-Actor-Id" = $ACTOR_ID } `
            -TimeoutSec 5 `
            -SkipHttpErrorCheck

        if ($response.StatusCode -eq 200) {
            $jobData = $response.Content | ConvertFrom-Json
            $job = $jobData.data
            $progress = "[$($job.uploaded_documents)/$($job.total_documents) up] [$($job.failed_documents) fail]"
            if ($job.status -ne $lastStatus) {
                Log "Status: $($job.status) | Documents: $progress" "Green"
                $lastStatus = $job.status
            }
            if ($terminal_statuses -contains $job.status) {
                Write-Host ""
                Success "Job complete."
                break
            }
        }
    } catch {
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
    Start-Sleep -Seconds 3
}

if (-not $jobData) {
    ErrorMsg "X Never received a job status. Is the Celery worker window running?"
    exit 1
}

# Step 6: Display results
$job = $jobData.data
Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "RESEARCH JOB RESULTS" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Job ID:    $JOB_ID" -ForegroundColor Yellow
Write-Host "Order ID:  $ORDER_ID" -ForegroundColor Yellow
Write-Host "Status:    $($job.status)" -ForegroundColor $(if ($job.status -eq "completed") { "Green" } else { "Yellow" })
Write-Host "Created:   $($job.created_at)" -ForegroundColor Gray
Write-Host "Completed: $($job.completed_at)" -ForegroundColor Gray
Write-Host ""
Write-Host "SUMMARY:" -ForegroundColor Cyan
Write-Host "  Uploaded: $($job.uploaded_documents)" -ForegroundColor Green
Write-Host "  Failed:   $($job.failed_documents)" -ForegroundColor $(if ($job.failed_documents -gt 0) { "Red" } else { "Green" })
Write-Host "  Skipped:  $($job.cancelled_documents)" -ForegroundColor Yellow
Write-Host "  Total:    $($job.total_documents)" -ForegroundColor Cyan
Write-Host ""
Write-Host "DOCUMENTS:" -ForegroundColor Cyan
Write-Host "-----------------------------------------------------------------" -ForegroundColor Gray
foreach ($doc in $job.documents) {
    $color = switch ($doc.status) {
        "uploaded" { "Green" }
        "fetched"  { "Yellow" }
        "failed"   { "Red" }
        default    { "Gray" }
    }
    Write-Host "$($doc.doc_type.PadRight(38)) | $($doc.status.PadRight(10)) | $($doc.summary)" -ForegroundColor $color
    if ($doc.error_message) { Write-Host "    error: $($doc.error_message)" -ForegroundColor Red }
    if ($doc.link)          { Write-Host "    link:  $($doc.link)" -ForegroundColor Gray }
}
Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan

# Step 7: Show where data is stored
Log "Step 7: Data storage locations..." "Cyan"
Write-Host ""
Write-Host "LOCAL FILES (default QP_STORAGE_ROOT = evidence\_qp):" -ForegroundColor Yellow
# Default blob root is <repo>/evidence/_qp/<tenant>/<order>/. If QP_STORAGE_ROOT
# is overridden in .env, look there instead.
$storageRoot = Join-Path $ROOT "evidence" "_qp" $TENANT_ID $ORDER_ID
$altRoot     = Join-Path $ROOT "data" "e2e_evidence" $TENANT_ID $ORDER_ID
if (-not (Test-Path $storageRoot) -and (Test-Path $altRoot)) { $storageRoot = $altRoot }
if (Test-Path $storageRoot) {
    Write-Host "   Location: $storageRoot" -ForegroundColor Gray
    Get-ChildItem $storageRoot -File | ForEach-Object {
        $size = [math]::Round($_.Length / 1MB, 2)
        Write-Host "   - $($_.Name) ($size MB)" -ForegroundColor Green
    }
} else {
    Write-Host "   (No files stored — normal if every source was link-only/failed for this address)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "DATABASE (engine Postgres is on port $DbPort):" -ForegroundColor Yellow
Write-Host "   psql -U postgres -h localhost -p $DbPort -d researchhub" -ForegroundColor Cyan
Write-Host "   SELECT doc_type, status, summary, link FROM research_documents WHERE job_id = '$JOB_ID';" -ForegroundColor Gray
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  API docs:   $API/docs" -ForegroundColor Cyan
Write-Host "  Guide:      $ROOT\DEMO_GUIDE.md" -ForegroundColor Cyan
Write-Host ""
Success "Demo complete."

# Cleanup prompt
Write-Host ""
$keep = Read-Host "Keep Docker services running? (Y/n)"
if ($keep -eq "n") {
    Log "Stopping Docker services..." "Yellow"
    docker compose -f "$ROOT\docker-compose.yml" down
    Log "Stopped" "Green"
}
