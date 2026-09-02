#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Interactive Demo: Test ResearchHub Engine with a custom address
.DESCRIPTION
    Orchestrates the full end-to-end demo flow:
    1. Start Docker services
    2. Apply migrations
    3. Seed a test order with your address
    4. Create a research job
    5. Poll and display results
    6. Show what data was fetched and where it's stored
.EXAMPLE
    .\demo.ps1
#>

param(
    [string]$Address = "2628 US Hwy 98 N",
    [string]$City = "Lakeland",
    [string]$State = "FL",
    [string]$County = "Polk",
    [string]$ParcelId = "262828612000000060"
)

$ROOT = Split-Path -Parent $MyInvocation.MyCommandPath
$VENV = Join-Path $ROOT ".venv"
$PYTHON = Join-Path $VENV "Scripts" "python.exe"
$BACKEND = Join-Path $ROOT "backend"

function Log {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] $Message" -ForegroundColor $Color
}

function Info {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Yellow
}

function Success {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Green
}

function ErrorMsg {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Red
}

# ===== SETUP =====
Log "🚀 ResearchHub Engine Interactive Demo" "Magenta"
Log ""

# Step 1: Start Docker
Log "Step 1: Starting Docker services (PostgreSQL + Redis)..." "Cyan"
try {
    $output = docker compose -f "$ROOT\docker-compose.yml" up db redis -d 2>&1
    if ($LASTEXITCODE -eq 0) {
        Success "✓ Docker services starting..."
    } else {
        ErrorMsg "✗ Docker startup failed. Ensure Docker Desktop is running."
        exit 1
    }
} catch {
    ErrorMsg "✗ Docker error: $_"
    exit 1
}

# Wait for services
Log "Waiting for PostgreSQL to be healthy..." "Cyan"
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    try {
        $result = docker exec "$(docker ps -q -f "image=postgres*")" pg_isready -U postgres
        if ($LASTEXITCODE -eq 0) {
            Success "✓ PostgreSQL is ready"
            break
        }
    } catch { }
    Start-Sleep -Seconds 2
}

# Step 2: Apply migrations
Log "Step 2: Applying database migrations..." "Cyan"
try {
    $output = & $PYTHON -m alembic upgrade head --cwd=$ROOT 2>&1
    if ($LASTEXITCODE -eq 0) {
        Success "✓ Migrations applied"
    } else {
        ErrorMsg "✗ Migration failed: $output"
        exit 1
    }
} catch {
    ErrorMsg "✗ Alembic error: $_"
    exit 1
}

# Step 3: Seed order with user's address
Log "Step 3: Creating test order with your address..." "Cyan"
Info "Address: $Address, $City, $State | County: $County | Parcel: $ParcelId"

$TENANT_ID = "c0000000-0000-0000-0000-000000000001"
$ACTOR_ID = "c0000000-0000-0000-0000-000000000002"

# Create temporary Python script file
$tempPyFile = Join-Path $env:TEMP "seed_order_temp.py"
$pythonScript = @"
import uuid
import sys
sys.path.insert(0, '$BACKEND')

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

try {
    $output = & $PYTHON $tempPyFile 2>&1
    $orderLine = $output | Where-Object { $_ -like "*ORDER_ID=*" }
    if ($orderLine) {
        $ORDER_ID = ($orderLine -split "=")[1].Trim()
        Success "✓ Order created: $ORDER_ID"
        Info "  Address: $Address, $City, $State, $County"
    } else {
        ErrorMsg "✗ Failed to create order"
        ErrorMsg ($output -join "`n")
        exit 1
    }
}
catch {
    ErrorMsg "✗ Order seeding error: $_"
    exit 1
}
finally {
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

try {
    $response = Invoke-WebRequest `
        -Uri "http://127.0.0.1:8000/api/v1/research/jobs" `
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
        Success "✓ Job created: $JOB_ID"
        Info "  Total documents: $($data.data.total_documents)"
    } else {
        ErrorMsg "✗ Failed to create job (HTTP $($response.StatusCode))"
        ErrorMsg $response.Content
        exit 1
    }
} catch {
    ErrorMsg "✗ Job creation error: $_"
    ErrorMsg "Note: Ensure API is running on :8000 (see DEMO_GUIDE.md Step 2)"
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
            -Uri "http://127.0.0.1:8000/api/v1/research/jobs/$JOB_ID" `
            -Method GET `
            -Headers @{
                "X-Tenant-Id" = $TENANT_ID
                "X-Actor-Id" = $ACTOR_ID
            } `
            -TimeoutSec 5 `
            -SkipHttpErrorCheck

        if ($response.StatusCode -eq 200) {
            $jobData = $response.Content | ConvertFrom-Json
            $job = $jobData.data
            $status = $job.status
            $uploaded = $job.uploaded_documents
            $failed = $job.failed_documents
            $total = $job.total_documents
            $progress = "[$uploaded/$total ✓] [$failed ✗]"

            if ($status -ne $lastStatus) {
                Log "Status: $status | Documents: $progress" "Green"
                $lastStatus = $status
            }

            if ($terminal_statuses -contains $status) {
                Write-Host ""
                Success "✅ Job Complete!"
                break
            }
        }
    } catch {
        Write-Host "." -NoNewline -ForegroundColor Gray
    }

    Start-Sleep -Seconds 3
}

# Step 6: Display results
if ($jobData) {
    $job = $jobData.data

    Write-Host ""
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "RESEARCH JOB RESULTS" -ForegroundColor Cyan
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Job ID:       $JOB_ID" -ForegroundColor Yellow
    Write-Host "Order ID:     $ORDER_ID" -ForegroundColor Yellow
    Write-Host "Status:       $($job.status)" -ForegroundColor $(if ($job.status -eq "completed") { "Green" } else { "Yellow" })
    Write-Host "Created:      $($job.created_at)" -ForegroundColor Gray
    Write-Host "Completed:    $($job.completed_at)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "SUMMARY:" -ForegroundColor Cyan
    Write-Host "  ✓ Uploaded:  $($job.uploaded_documents)" -ForegroundColor Green
    Write-Host "  ✗ Failed:    $($job.failed_documents)" -ForegroundColor $(if ($job.failed_documents -gt 0) { "Red" } else { "Green" })
    Write-Host "  ⊘ Skipped:   $($job.cancelled_documents)" -ForegroundColor Yellow
    Write-Host "  Total:      $($job.total_documents)" -ForegroundColor Cyan
    Write-Host ""

    # Per-document summary
    Write-Host "DOCUMENTS:" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────────────────────────" -ForegroundColor Gray
    foreach ($doc in $job.documents) {
        $icon = switch ($doc.status) {
            "uploaded" { "✓" }
            "fetched" { "◐" }
            "failed" { "✗" }
            "skipped" { "⊘" }
            default { "○" }
        }
        $color = switch ($doc.status) {
            "uploaded" { "Green" }
            "fetched" { "Yellow" }
            "failed" { "Red" }
            default { "Gray" }
        }
        Write-Host "$icon $($doc.doc_type.PadRight(40)) | Status: $($doc.status.PadRight(10)) | $($doc.summary)" -ForegroundColor $color
        if ($doc.error_message) {
            Write-Host "  └─ Error: $($doc.error_message)" -ForegroundColor Red
        }
        if ($doc.link) {
            Write-Host "  └─ Link: $($doc.link)" -ForegroundColor Gray
        }
    }
    Write-Host ""
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
}

# Step 7: Show where data is stored
Log "Step 7: Data storage locations..." "Cyan"
Write-Host ""
Write-Host "📁 LOCAL FILES:" -ForegroundColor Yellow
$storageRoot = Join-Path $ROOT "data" "e2e_evidence" $TENANT_ID $ORDER_ID
if (Test-Path $storageRoot) {
    Write-Host "   Location: $storageRoot" -ForegroundColor Gray
    Get-ChildItem $storageRoot -File | ForEach-Object {
        $size = [math]::Round($_.Length / 1MB, 2)
        Write-Host "   ├─ $($_.Name) ($size MB)" -ForegroundColor Green
    }
} else {
    Write-Host "   (No files stored yet - check if job had errors)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "🗄️  DATABASE:" -ForegroundColor Yellow
Write-Host "   Host:     localhost:5432" -ForegroundColor Gray
Write-Host "   Database: researchhub" -ForegroundColor Gray
Write-Host "   User:     postgres" -ForegroundColor Gray
Write-Host ""
Write-Host "   To inspect: psql -U postgres -h localhost -d researchhub" -ForegroundColor Cyan
Write-Host "   Queries:" -ForegroundColor Cyan
Write-Host "   SELECT * FROM research_jobs WHERE id = '$JOB_ID';" -ForegroundColor Gray
Write-Host "   SELECT doc_type, status, summary, link FROM research_documents WHERE job_id = '$JOB_ID';" -ForegroundColor Gray
Write-Host ""

# Offer to open browser
Write-Host ""
Log "Demo Summary" "Magenta"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. View API docs:     http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "2. Check DB:          psql -U postgres -h localhost -d researchhub" -ForegroundColor Cyan
Write-Host "3. Open fetched PDFs: $storageRoot" -ForegroundColor Cyan
Write-Host "4. Read guide:        $ROOT\DEMO_GUIDE.md" -ForegroundColor Cyan
Write-Host ""
Success "✅ Demo complete!"

# Cleanup prompt
Write-Host ""
$response = Read-Host "Keep Docker services running? (Y/n)"
if ($response -eq "n") {
    Log "Stopping Docker services..." "Yellow"
    docker compose down
    Log "Stopped" "Green"
}
