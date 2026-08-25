"""Blob storage abstraction for QuickPlot evidence documents.

The POC writes to the local filesystem, but every call goes through this interface so a
SaaS deployment can swap in S3/Azure Blob by setting one env var and nothing above this
module changes:

    QP_STORAGE_BACKEND = local | s3            (default: local)
    QP_STORAGE_ROOT    = <dir>                 (local backend, default: <repo>/evidence/_qp)
    QP_S3_BUCKET / QP_S3_PREFIX / AWS_*        (s3 backend)

Keys are opaque, tenant-scoped strings: "<org_id>/<order_id>/<document_id><ext>".
Callers never build filesystem paths themselves — that keeps path traversal impossible and
makes the object-store migration a drop-in.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
from typing import BinaryIO, Protocol

BACKEND = os.environ.get("QP_STORAGE_BACKEND", "local").strip().lower()

#: Largest single document we accept. County record PDFs and plat scans run large
#: (a full plat book page can be 20 MB+), so the ceiling is generous — but it has to
#: exist, or one caller can fill the disk.
MAX_UPLOAD_BYTES = int(os.environ.get("QP_MAX_UPLOAD_MB", "50")) * 1024 * 1024

_DEFAULT_ROOT = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "_qp"
ROOT = pathlib.Path(os.environ.get("QP_STORAGE_ROOT", str(_DEFAULT_ROOT))).resolve()


def build_key(org_id: str, order_id: str, document_id: str, filename: str) -> str:
    """Tenant-scoped, collision-free storage key. The extension is kept so a browser
    served the blob back still sniffs the right content type.

    `document_id` MUST already be assigned. Passing a not-yet-flushed ORM id here once
    produced keys like "<org>/<order>/None.pdf", so every document in an order shared one
    blob and overwrote each other — including locked ones. Guard against a repeat.
    """
    if not document_id or document_id == "None":
        raise ValueError("build_key needs a real document id (got %r)" % (document_id,))
    ext = pathlib.PurePath((filename or "").replace("\\", "/")).suffix[:12]
    safe_ext = "".join(c for c in ext if c.isalnum() or c == ".")
    return f"{org_id}/{order_id}/{document_id}{safe_ext}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> int: ...
    def get(self, key: str) -> bytes: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def local_path(self, key: str) -> pathlib.Path | None: ...


class LocalStorage:
    """Filesystem backend. `local_path` lets FastAPI stream with FileResponse (zero-copy)."""

    name = "local"

    def __init__(self, root: pathlib.Path = ROOT):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> pathlib.Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError("storage key escapes the storage root")
        return p

    def put(self, key: str, data: bytes) -> int:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return len(data)

    def get(self, key: str) -> bytes:
        return self._p(key).read_bytes()

    def open(self, key: str):
        return self._p(key).open("rb")

    def delete(self, key: str) -> None:
        try:
            self._p(key).unlink()
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001
            pass

    def exists(self, key: str) -> bool:
        try:
            return self._p(key).is_file()
        except Exception:  # noqa: BLE001
            return False

    def local_path(self, key: str) -> pathlib.Path | None:
        p = self._p(key)
        return p if p.is_file() else None

    def copy_in(self, key: str, src: pathlib.Path) -> int:
        """Import a file already on disk (e.g. one the research pipeline downloaded)."""
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, p)
        return p.stat().st_size


class S3Storage:
    """S3 backend — used when QP_STORAGE_BACKEND=s3. boto3 is imported lazily so the POC
    never needs the dependency installed."""

    name = "s3"

    def __init__(self):
        import boto3  # noqa: PLC0415 — optional dependency, only for the s3 backend

        self.bucket = os.environ["QP_S3_BUCKET"]
        self.prefix = os.environ.get("QP_S3_PREFIX", "quickplot").strip("/")
        self.client = boto3.client("s3")

    def _k(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes) -> int:
        self.client.put_object(Bucket=self.bucket, Key=self._k(key), Body=data)
        return len(data)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()

    def open(self, key: str):
        return self.client.get_object(Bucket=self.bucket, Key=self._k(key))["Body"]

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except Exception:  # noqa: BLE001
            return False

    def local_path(self, key: str) -> pathlib.Path | None:
        return None  # object store — stream through get()/open() instead

    def copy_in(self, key: str, src: pathlib.Path) -> int:
        data = src.read_bytes()
        self.put(key, data)
        return len(data)


def _make() -> Storage:
    if BACKEND == "s3":
        try:
            return S3Storage()
        except Exception as e:  # noqa: BLE001 — never let storage config kill startup
            print(f"[storage] s3 backend unavailable ({e}); falling back to local")
    return LocalStorage()


store: Storage = _make()
