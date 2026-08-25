"""Job folder / evidence-locker management + manifest."""
import datetime
import hashlib
import json
import re

from ..config import JOBS_DIR


def _slug(text: str) -> str:
    text = re.sub(r"[<>:\"/\\|?*]", "", text).strip()
    return re.sub(r"\s+", " ", text)


def job_folder(job_number: str, address: str):
    street = address.split(",")[0].strip()
    name = f"{_slug(job_number)} - {_slug(street)}".strip(" -")
    folder = JOBS_DIR / name / "research"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_json(folder, filename: str, data) -> dict:
    payload = json.dumps(data, indent=2, default=str).encode()
    (folder / filename).write_bytes(payload)
    return {
        "file": filename,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "fetched_utc": datetime.datetime.utcnow().isoformat() + "Z",
    }


def write_manifest(folder, manifest: list, meta: dict):
    doc = {"job": meta, "documents": manifest,
           "generated_utc": datetime.datetime.utcnow().isoformat() + "Z"}
    (folder / "manifest.json").write_bytes(
        json.dumps(doc, indent=2, default=str).encode())


def _safe_research_dir(name: str):
    """Resolve <JOBS_DIR>/<name>/research, rejecting anything outside JOBS_DIR."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    d = JOBS_DIR / name / "research"
    try:
        if d.is_dir() and JOBS_DIR.resolve() in d.resolve().parents:
            return d
    except Exception:  # noqa: BLE001
        return None
    return None


def job_detail(name: str) -> dict | None:
    """Full info for one job: the saved research result (if any), manifest, and file list."""
    research = _safe_research_dir(name)
    if not research:
        return None
    out = {"name": name, "result": None, "manifest": None, "feedback": None, "files": []}
    for p in sorted(research.rglob("*")):
        if p.is_file():
            out["files"].append({"file": p.relative_to(research).as_posix(),
                                 "bytes": p.stat().st_size})
    for key, fn in (("result", "result.json"), ("manifest", "manifest.json"),
                    ("feedback", "feedback.json")):
        f = research / fn
        if f.exists():
            try:
                out[key] = json.loads(f.read_text())
            except Exception:  # noqa: BLE001
                pass
    return out


def delete_job(name: str) -> bool:
    """Delete an entire job folder (<JOBS_DIR>/<name>), safely confined to JOBS_DIR."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return False
    d = JOBS_DIR / name
    try:
        if d.is_dir() and JOBS_DIR.resolve() in d.resolve().parents:
            import shutil
            shutil.rmtree(d)
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


def save_feedback(name: str, entry: dict) -> dict | None:
    """Record the surveyor's verdict on a fetched document (does it match the subject
    property?) in <job>/research/feedback.json, keyed by document. Returns the full
    feedback map, or None if the job doesn't exist."""
    research = _safe_research_dir(name)
    if not research:
        return None
    f = research / "feedback.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            data = {}
    key = str(entry.get("key") or "general")
    verdict = str(entry.get("verdict") or "").lower()
    data[key] = {
        "verdict": verdict if verdict in ("match", "mismatch") else "",
        "note": (entry.get("note") or "")[:2000],
        "updated_utc": datetime.datetime.utcnow().isoformat() + "Z",
    }
    f.write_text(json.dumps(data, indent=2))
    return data


def job_file(name: str, relpath: str):
    """Safely resolve a single file inside a job's research dir for download."""
    research = _safe_research_dir(name)
    if not research or not relpath or ".." in relpath or relpath.startswith(("/", "\\")):
        return None
    p = research / relpath
    try:
        if p.is_file() and research.resolve() in p.resolve().parents:
            return p
    except Exception:  # noqa: BLE001
        return None
    return None


def list_jobs() -> list[dict]:
    jobs = []
    for job_dir in JOBS_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        research = job_dir / "research"
        manifest = research / "manifest.json"
        info = {"name": job_dir.name, "path": str(job_dir),
                "docs": 0, "county": "", "address": "", "generated": "", "parcel_id": ""}
        mtime = 0.0
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                info["docs"] = len(data.get("documents", []))
                info["county"] = data.get("job", {}).get("county", "")
                info["address"] = data.get("job", {}).get("matched_address", "")
                info["parcel_id"] = data.get("job", {}).get("parcel_id", "")
                info["generated"] = data.get("generated_utc", "")
            except Exception:  # noqa: BLE001
                pass
            try:
                mtime = manifest.stat().st_mtime
            except OSError:
                pass
        elif research.exists():
            info["docs"] = len(list(research.glob("*.json")))
            try:
                mtime = research.stat().st_mtime
            except OSError:
                pass
        info["_mtime"] = mtime
        jobs.append(info)
    # Most recent first: prefer the manifest timestamp, fall back to folder mtime.
    jobs.sort(key=lambda j: (j["generated"], j["_mtime"]), reverse=True)
    for j in jobs:
        j["ts"] = j.pop("_mtime", 0.0)   # epoch seconds — used by the UI's this-week filter
    return jobs
