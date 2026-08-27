"""Adapters — concrete implementations of the service's injected dependencies.

The service layer is dependency-injected so tests can run fully offline.
These adapters are the production wiring:

  - ``order_provider``   reads the Order + OrderAddress rows from the DB
  - ``document_fetcher`` runs the engine's phase-separated pipeline
    (``engine.orchestration.run_research``) and copies staged artifacts
    into the blob store.

During integration into the parent repo, ``order_provider`` is replaced by
code that reads ``app/modules/orders`` models (which carry the same columns);
the document fetcher is unchanged.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.engine.contracts import Confidence, StepStatus
from app.engine.orchestration.runner import run_research
from app.engine.service import FetchedDocument, OrderData
from app.engine.schemas import ResearchDocStatus, ResearchErrorCode

logger = logging.getLogger("researchhub.adapters")

# Map orchestrator step keys → the engine's DocumentType string.
# The engine emits steps keyed by short names (parcel, deed, plat,
# appraiser, flood, benchmarks). The engine contract uses the parent's
# DocumentType. Clerk-family steps without an auto-fetch (adjoiners,
# easements, prior surveys, condo) have no DocumentType yet and are
# never requested by callers — they stay outside this map.
STEP_TO_DOC_TYPE: dict[str, str] = {
    "parcel": "PARCEL_RECORD",
    "appraiser": "PROPERTY_APPRAISER_TAX_RECORD",
    "plat": "RECORDED_PLAT_SUBDIVISION_MAP",
    "deed": "DEED_SUBJECT_PARCEL",
    "flood": "FEMA_FLOOD_ZONE_FIRM",
    "benchmarks": "NGS_CONTROL",
}

DOC_TYPE_TO_STEP: dict[str, str] = {v: k for k, v in STEP_TO_DOC_TYPE.items()}


def order_provider(order_id: UUID, tenant_id: UUID) -> OrderData | None:
    """Read an order's research context from the DB.

    During integration this reads the parent's Order + OrderAddress. It is
    mocked in tests; the standalone engine's orders table is absent, so this
    returns None unless backed by a real integration.
    """
    raise NotImplementedError(
        "order_provider is wired during integration into the parent repo "
        "(reads app/modules/orders). Standalone tests inject their own."
    )


def build_document_fetcher():
    """Return a fetch function: (order: OrderData, doc_types) -> dict[str, FetchedDocument].

    Runs the engine pipeline for exactly the requested document types (the
    runner honors ``include`` — a deed-only retry does NOT re-run geocode,
    parcel, FEMA and NGS), then copies each staged artifact into the blob
    store via ``app.services.storage``.
    """
    from app.services.storage import build_key, store

    storage = store

    def fetch(order: OrderData, doc_types: list[str]) -> dict[str, FetchedDocument]:
        include_steps = [DOC_TYPE_TO_STEP[d] for d in doc_types if d in DOC_TYPE_TO_STEP]
        if not include_steps:
            return {}

        result = run_research(
            job_number="",
            address=order.address_line_1,
            survey_type=order.survey_type or None,
            include=include_steps,
            selected_state=order.state or "",
            selected_county_fips=order.county or "",
            order_number=str(order.id),
            search_parcel_id=order.parcel_id or "",
        )

        out: dict[str, FetchedDocument] = {}
        for step in result.steps:
            doc_type = STEP_TO_DOC_TYPE.get(step.key)
            if doc_type not in doc_types:
                continue

            status = _map_step_status(step.status)
            doc = FetchedDocument(
                doc_type=doc_type,
                status=status,
                summary=step.summary,
                link=step.link,
                link_label=step.link_label,
                provenance=[p.model_dump() for p in step.provenance],
                warnings=step.warnings,
            )
            if step.error is not None:
                doc.error_code = _error_code_for(step.source_outcome, step.error.code)
                doc.error_message = step.error.message or step.error.code
                doc.retryable = bool(step.error.retryable)

            if status == ResearchDocStatus.uploaded:
                _upload_artifact(doc, step.downloaded, result.docs_dir, order.id, doc_type,
                                 storage=storage, build_key=build_key)

            out[doc_type] = doc
        return out

    return fetch


def _upload_artifact(doc: FetchedDocument, downloaded: list[str],
                     docs_dir: str | None, order_id: UUID, doc_type: str,
                     storage=None, build_key=None) -> None:
    """Copy the first downloadable artifact of a step into the blob store."""
    if not downloaded:
        return  # 'ok' without a file (e.g. appraiser record card handled later)
    for filename in downloaded:
        src = Path(docs_dir or "") / "documents" / filename
        if not src.is_file():
            logger.warning("artifact missing on disk: %s", src)
            continue
        try:
            key = build_key(
                org_id="",  # tenant prefix added by parent middleware
                order_id=str(order_id),
                document_id=doc_type,
                filename=filename,
            )
            storage.copy_in(key=key, src=src)
            doc.file_key = key
            doc.file_name = filename
            doc.file_size = src.stat().st_size
            doc.sha256 = hashlib.sha256(src.read_bytes()).hexdigest()
            doc.status = ResearchDocStatus.uploaded
            return
        except Exception as e:  # noqa: BLE001
            logger.warning("blob upload failed for %s: %s", filename, e)
            doc.status = ResearchDocStatus.failed
            doc.error_code = ResearchErrorCode.S3_UPLOAD_FAILED
            doc.error_message = str(e)
            return


def _map_step_status(status: StepStatus) -> ResearchDocStatus:
    if status == StepStatus.ok:
        return ResearchDocStatus.uploaded
    if status == StepStatus.link:
        return ResearchDocStatus.fetched   # link-only, no file to upload
    if status == StepStatus.empty:
        return ResearchDocStatus.skipped
    return ResearchDocStatus.failed


def _error_code_for(outcome, code: str) -> ResearchErrorCode:
    from app.engine.contracts import SourceOutcome

    if outcome == SourceOutcome.blocked:
        return ResearchErrorCode.SOURCE_UNAVAILABLE
    if outcome == SourceOutcome.broken:
        return ResearchErrorCode.SOURCE_UNAVAILABLE
    if outcome == SourceOutcome.retryable:
        return ResearchErrorCode.TIMEOUT
    if code == "PARCEL_NOT_FOUND":
        return ResearchErrorCode.PARCEL_NOT_FOUND
    if code == "LINK_ONLY":
        return ResearchErrorCode.SOURCE_UNAVAILABLE
    return ResearchErrorCode.INTERNAL_ERROR