"""Evidence linkage tests — regression for the worker INTERNAL_ERROR
('FetchedDocument' object has no attribute 'file_id') fixed by wiring the
upload → File/OrderFile rows → doc-row ids chain.

Covers: blob copy happens, File + OrderFile rows persist with the real
storage key/size/sha, the FetchedDocument carries ids, and the mapper reads
the stored metadata back (no fabricated zeros).
"""
from __future__ import annotations

import uuid

from app.engine.adapters import _upload_artifact
from app.engine.evidence_source import File, OrderFile, get_file_reference
from app.engine.mappers import _to_file_reference
from app.engine.models import ResearchDocument
from app.engine.schemas import ResearchDocStatus
from app.engine.service import FetchedDocument

TENANT = uuid.UUID("f0000000-0000-0000-0000-000000000090")
ORDER = uuid.UUID("f0000000-0000-0000-0000-000000000091")


def _staged_artifact(tmp_path: Path) -> tuple[Path, Path]:
    """Create docs_dir/documents/NGSD.txt on disk; return (docs_dir, file_path)."""
    docs_dir = tmp_path / "docs"
    (docs_dir / "documents").mkdir(parents=True)
    src = docs_dir / "documents" / "NGSD.txt"
    src.write_bytes(b"hello evidence world")
    return docs_dir, src


def _fake_storage():
    class FakeStorage:
        def __init__(self):
            self.copies: list[tuple[str, Path]] = []

        def copy_in(self, *, key, src):
            self.copies.append((key, src))

    return FakeStorage()


def _fake_build_key(org_id, order_id, document_id, filename):
    return f"{org_id}/{order_id}/{document_id}/{filename}"


# ---------------------------------------------------------------- upload


def test_upload_persists_evidence_rows_and_sets_ids(test_db, tmp_path):
    docs_dir, src = _staged_artifact(tmp_path)
    storage = _fake_storage()
    doc = FetchedDocument(
        doc_type="NGS_CONTROL", status=ResearchDocStatus.fetching, summary="", link="",
    )

    _upload_artifact(
        doc, downloaded=["NGSD.txt"], docs_dir=str(docs_dir), order_id=ORDER,
        doc_type="NGS_CONTROL", storage=storage, build_key=_fake_build_key,
        tenant_id=TENANT,
    )

    key = f"{TENANT}/{ORDER}/NGS_CONTROL/NGSD.txt"
    assert doc.status == ResearchDocStatus.uploaded
    assert doc.file_key == key
    assert doc.file_name == "NGSD.txt"
    assert doc.file_size == len(b"hello evidence world")
    assert doc.sha256
    assert doc.file_id and doc.order_file_id
    assert storage.copies == [(key, src.resolve())] or storage.copies[0][0] == key

    file = test_db.query(File).filter(File.content_key == key).one()
    link = test_db.query(OrderFile).filter(OrderFile.order_id == ORDER).one()
    assert file.size == doc.file_size
    assert file.sha256 == doc.sha256
    assert link.order_id == ORDER
    assert link.file_id == file.id == doc.file_id


def test_upload_failure_marks_doc_failed(test_db, tmp_path):
    docs_dir, _ = _staged_artifact(tmp_path)
    doc = FetchedDocument(
        doc_type="NGS_CONTROL", status=ResearchDocStatus.fetching, summary="", link="",
    )

    class BoomStorage:
        def copy_in(self, *, key, src):
            raise OSError("disk full")

    _upload_artifact(
        doc, downloaded=["NGSD.txt"], docs_dir=str(docs_dir), order_id=ORDER,
        doc_type="NGS_CONTROL", storage=BoomStorage(), build_key=_fake_build_key,
        tenant_id=TENANT,
    )

    assert doc.status == ResearchDocStatus.failed
    assert doc.error_code == "S3_UPLOAD_FAILED"
    assert doc.error_message == "disk full"
    assert doc.file_id is None


def test_upload_no_downloads_is_noop(test_db):
    doc = FetchedDocument(
        doc_type="PARCEL_RECORD", status=ResearchDocStatus.fetched, summary="", link="",
    )
    _upload_artifact(doc, downloaded=[], docs_dir=None, order_id=ORDER,
                     doc_type="PARCEL_RECORD", storage=_fake_storage(),
                     build_key=_fake_build_key, tenant_id=TENANT)
    assert doc.status == ResearchDocStatus.fetched
    assert doc.file_id is None


# ------------------------------------------------------------ mapper


def test_mapper_reads_stored_evidence_metadata(test_db):
    file_id, order_file_id = None, None
    from app.engine.evidence_source import create_evidence

    file_id, order_file_id = create_evidence(
        order_id=ORDER, tenant_id=TENANT, storage_key=f"{TENANT}/{ORDER}/NGS_CONTROL/x.txt",
        filename="x.txt", file_size=42, sha256="abcd1234", mime_type="text/plain",
    )

    row = ResearchDocument(job_id=uuid.uuid4(), doc_type="NGS_CONTROL",
                           status=ResearchDocStatus.uploaded)
    row.file_id = file_id
    row.order_file_id = order_file_id
    row.job_id = uuid.uuid4()

    ref = _to_file_reference(row)
    assert ref is not None
    assert ref.file_id == file_id
    assert ref.order_file_id == order_file_id
    assert ref.key == f"{TENANT}/{ORDER}/NGS_CONTROL/x.txt"
    assert ref.size_bytes == 42
    assert ref.sha256 == "abcd1234"
    assert ref.mime_type == "text/plain"


def test_mapper_no_ids_returns_none():
    row = ResearchDocument(job_id=uuid.uuid4(), doc_type="PARCEL_RECORD",
                           status=ResearchDocStatus.queued)
    assert _to_file_reference(row) is None