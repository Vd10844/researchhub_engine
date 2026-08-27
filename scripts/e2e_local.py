"""Local end-to-end run of the Research Engine on real infrastructure.

Spins up:  real uvicorn API  +  real Celery worker  against  a real Postgres
(`db`) and Redis (`redis`) from `docker-compose.yml` — then drives the whole
contract via HTTP:

    1. alembic upgrade head            (proves the migration chain on Postgres)
    2. seed a tenant + order           (dev `orders` table via order_provider)
    3. POST /api/v1/research/jobs      (real HTTP)
    4. worker consumes the job         (real Redis broker + real Celery)
    5. poll GET /jobs/{id} → terminal  (completed | partial | failed)
    6. report per-document statuses + verify blob artifacts on disk

Requires the compose services (health) on their default ports. The sandbox
may block some data sources (FEMA/clerk WAF, geo-egress) — that is EXPECTED:
each source must degrade to a fallback link / retryable error and the job
must still resolve to a terminal status with a defensible evidence set.

Usage:
    .venv/Scripts/python.exe scripts/e2e_local.py
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PY = ROOT / ".venv" / "Scripts" / "python.exe"

TENANT_ID = uuid.UUID("c0000000-0000-0000-0000-000000000001")
ACTOR_ID = uuid.UUID("c0000000-0000-0000-0000-000000000002")


def free_port() -> int:
    """Pick a free TCP port for the API (avoids clashes with leftovers)."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


API_PORT = free_port()
BASE = f"http://127.0.0.1:{API_PORT}/api/v1/research"

ENV = {
    **os.environ,
    "DATABASE_URL": "postgresql+psycopg://postgres:postgres@localhost:5433/researchhub",
    "RUN_ENV": "local",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/1",
    "QP_STORAGE_ROOT": str(ROOT / "data" / "e2e_evidence"),
    "JOBS_DIR": str(ROOT / "data" / "e2e_jobs"),
}

ALL_DOC_TYPES = [
    "PARCEL_RECORD",
    "PROPERTY_APPRAISER_TAX_RECORD",
    "RECORDED_PLAT_SUBDIVISION_MAP",
    "DEED_SUBJECT_PARCEL",
    "FEMA_FLOOD_ZONE_FIRM",
    "NGS_CONTROL",
]


def log(msg: str) -> None:
    print(f"[e2e] {msg}", flush=True)


def http(method: str, path: str, **kw) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Id": str(TENANT_ID),
        "X-Actor-Id": str(ACTOR_ID),
        "X-Idempotency-Key": str(uuid.uuid4()),
    }
    headers.update(kw.pop("headers", {}))
    data = kw.pop("body", None)
    req = request.Request(
        BASE + path, method=method, headers=headers,
        data=json.dumps(data).encode() if data is not None else None,
    )
    with request.urlopen(req, timeout=30) as res:
        return json.loads(res.read())


def wait_health(url: str, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with request.urlopen(url, timeout=3) as res:
                if res.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main() -> int:
    log("step 1/5  alembic upgrade head")
    subprocess.run(
        [str(PY), "-m", "alembic", "upgrade", "head"],
        check=True, env=ENV, cwd=str(ROOT),
        capture_output=True,
    )

    log("step 2/5  seed tenant + order")
    seed_code = f"""
import uuid
from app.db.base import SessionLocal
from app.engine.order_source import seed_dev_order

TENANT = uuid.UUID("{TENANT_ID}")
db = SessionLocal()
try:
    o = seed_dev_order(
        db,
        tenant_id=TENANT,
        address_line_1="2628 US Hwy 98 N",
        city="Lakeland",
        state="FL",
        zip_code="33805",
        county="Polk",
        parcel_id="262828612000000060",
        survey_type="Location Survey",
    )
    print("ORDER=" + str(o.id))
finally:
    db.close()
"""
    proc = subprocess.run(
        [str(PY), "-c", seed_code], check=True, env=ENV, cwd=str(BACKEND),
        capture_output=True, text=True,
    )
    order_line = next(
        (l for l in proc.stdout.splitlines() if l.startswith("ORDER=")), ""
    )
    order_id = uuid.UUID(order_line.split("=", 1)[1])
    log(f"order seeded: {order_id}")

    log("step 3/5  start API + worker")
    server_log = (ROOT / "data" / "e2e_server.log").open("ab")
    worker_log = (ROOT / "data" / "e2e_worker.log").open("ab")
    api = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "app.main:app", "--port", str(API_PORT), "--log-level", "warning"],
        env=ENV, cwd=str(BACKEND), stdout=server_log, stderr=server_log,
    )
    worker_cmd = [
        str(PY), "-m", "celery", "-A", "app.engine.worker.celery_app", "worker",
        "--loglevel=warning", "--queues=research",
    ]
    if sys.platform.startswith("win"):
        # billiard's process pool crashes on Windows (handle errors); solo is
        # the supported single-process pool here.
        worker_cmd += ["--pool=solo"]
    worker = subprocess.Popen(
        worker_cmd,
        env=ENV, cwd=str(BACKEND), stdout=worker_log, stderr=worker_log,
    )

    try:
        if not wait_health(f"http://127.0.0.1:{API_PORT}/api/health"):
            log("FATAL  API did not become healthy")
            return 2
        log("API healthy")
        time.sleep(6)  # give the worker a moment to attach to the queue

        log("step 4/5  POST research job")
        job = http("POST", "/jobs", body={
            "order_id": str(order_id),
            "document_types": ALL_DOC_TYPES,
        })["data"]
        job_id = job["id"]
        log(f"job created: {job_id}")

        log("step 5/5  poll to terminal")
        status_seen = set()
        terminal = {"completed", "partial", "failed", "cancelled"}
        deadline = time.time() + 240
        data = job
        while time.time() < deadline:
            data = http("GET", f"/jobs/{job_id}")["data"]
            status_seen.add(data["status"])
            if data["status"] in terminal:
                break
            time.sleep(3)

        print("\n================ job summary ================")
        print(f"job          : {job_id}")
        print(f"order        : {order_id}")
        print(f"final status : {data['status']}")
        print(f"counters     : total={data['total_documents']} "
              f"uploaded={data['uploaded_documents']} "
              f"fetched={data['fetched_documents']} "
              f"failed={data['failed_documents']}")
        print("\n-- documents --")
        for d in data["documents"]:
            err = f" [{d.get('error_code') or ''}] {d.get('error_message') or ''}"[:80]
            print(f"  {d['doc_type']:<42s} {d['status']:<10s} {d['summary'][:60]}{err}")
        print("================ end summary ================")

        if data["status"] not in terminal:
            log("FATAL  job never reached a terminal state")
            return 3

        # Blob artifacts must exist on local storage (contract's file.key).
        uploaded = [d for d in data["documents"] if d["status"] == "uploaded" and d.get("file")]
        storage_root = Path(ENV["QP_STORAGE_ROOT"])
        for d in uploaded:
            p = storage_root / d["file"]["key"]
            if not p.is_file():
                log(f"MISSING artifact: {d['file']['key']}")
                return 4
            fsize = d["file"]["size_bytes"]
            log(f"verified artifact {d['file']['filename']} ({fsize}B, sha={d['file']['sha256'][:12]}…)")
        if not uploaded:
            log("WARN  no uploaded artifacts this run (expected only if all sources fell back)")

        # Cancel path: second job, cancel immediately.
        cjob = http("POST", "/jobs", body={
            "order_id": str(order_id),
            "document_types": ["PARCEL_RECORD"],
        }, headers={"X-Idempotency-Key": str(uuid.uuid4())})["data"]
        http("POST", f"/jobs/{cjob['id']}/cancel")
        cjob = http("GET", f"/jobs/{cjob['id']}")["data"]
        log(f"cancel path  : {cjob['status']} (expected cancelled)")
        if cjob["status"] != "cancelled":
            log("WARN  cancel did not reach cancelled")
            return 5

        log("E2E PASSED")
        return 0
    finally:
        for p in (api, worker):
            p.terminate()
        server_log.close()
        worker_log.close()


if __name__ == "__main__":
    raise SystemExit(main())