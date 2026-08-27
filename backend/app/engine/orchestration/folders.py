"""Staging-folder + manifest helpers for a research run.

The core engine stages fetched artifacts on local disk (keyed by job folder),
then the adapters copy them into the blob store. Nothing below the blob store
ever builds the path to a stored object — this module only manages the
*scratch* folder for one run.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re

from app.config import settings


def _slug(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]', "", text).strip()
    return re.sub(r"\s+", " ", text)


def job_folder(job_number: str, address: str):
    """Scratch staging dir for one research run: <JOBS_DIR>/<name>/research."""
    street = (address or "").split(",")[0].strip()
    name = f"{_slug(job_number or '')} - {_slug(street)}".strip(" -") or "job"
    import pathlib

    folder = pathlib.Path(settings.JOBS_DIR) / name / "research"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_json(folder, filename: str, data) -> dict:
    """Persist a JSON artifact + return the manifest entry describing it."""
    payload = json.dumps(data, indent=2, default=str).encode()
    (folder / filename).write_bytes(payload)
    return {
        "file": filename,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "fetched_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def write_manifest(folder, manifest: list, meta: dict) -> None:
    doc = {"job": meta, "documents": manifest,
           "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (folder / "manifest.json").write_bytes(
        json.dumps(doc, indent=2, default=str).encode())


def write_result(folder, result: dict) -> None:
    (folder / "result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")