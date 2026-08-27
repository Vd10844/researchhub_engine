"""Adapters — concrete implementations of the service's injected dependencies.

The service layer is dependency-injected so tests can run fully offline.
These adapters are the production wiring:

  - ``order_provider``   reads the Order + OrderAddress rows from the DB
  - ``document_fetcher`` wraps ``orchestrator.run_research`` + S3 upload

During integration into the parent repo, ``order_provider`` is replaced by
code that reads ``app/modules/orders`` models (which carry the same columns);
the document fetcher is unchanged.
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.engine.service import FetchedDocument, OrderData
from app.engine.schemas import ResearchDocStatus

logger = logging.getLogger("researchhub.adapters")

# Map orchestrator step keys → the engine's DocumentType string.
# The orchestrator emits steps keyed by short names (parcel, deed, plat,
# appraiser, flood, ngs). The engine contract uses the parent's DocumentType.
STEP_TO_DOC_TYPE: dict[str, str] = {
    "parcel": "PARCEL_RECORD",
    "appraiser": "PROPERTY_APPRAISER_TAX_RECORD",
    "plat": "RECORDED_PLAT_SUBDIVISION_MAP",
    "deed": "DEED_SUBJECT_PARCEL",
    "flood": "FEMA_FLOOD_ZONE_FIRM",
    "ngs": "NGS_CONTROL",
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

    Calls ``orchestrator.run_research`` once for the whole set, then slices
    the result steps that match the requested doc types. Downloaded artifacts
    (on disk under the job's ``documents/`` folder) are copied into the blob
    store via ``app.services.storage``.
    """
    from pathlib import Path

    from app.services import orchestrator
    from app.services.storage import build_key, store

    storage = store

    def fetch(order: OrderData, doc_types: list[str]) -> dict[str, FetchedDocument]:
        include_steps = [DOC_TYPE_TO_STEP[d] for d in doc_types if d in DOC_TYPE_TO_STEP]

        result = orchestrator.run_research(
            job_number="",
            address=order.address_line_1,
            survey_type=None,
            include=include_steps,
            selected_state=order.state or "",
            selected_county_fips=order.county or "",
            order_number=str(order.id),
            search_parcel_id=order.parcel_id or "",
        )

        out: dict[str, FetchedDocument] = {}
        for step in result.get("steps", []):
            doc_type = STEP_TO_DOC_TYPE.get(step.get("key"))
            if doc_type not in doc_types:
                continue

            status = _map_step_status(step, doc_type)
            doc = FetchedDocument(
                doc_type=doc_type,
                status=status,
                summary=step.get("summary", ""),
                link=step.get("link", ""),
                link_label=step.get("link_label", ""),
                provenance=_build_provenance(step),
                warnings=step.get("warnings", []),
            )

            # Copy the first downloaded artifact into the blob store.
            docs_dir = Path(str(result.get("folder", ""))) / "documents"
            for filename in (step.get("downloaded") or []):
                src = docs_dir / filename
                if not src.is_file():
                    logger.warning("artifact missing on disk: %s", src)
                    continue
                try:
                    key = build_key(
                        org_id="",  # tenant prefix added by parent middleware
                        order_id=str(order.id),
                        document_id=doc_type,
                        filename=filename,
                    )
                    storage.copy_in(key=key, src=src)
                    doc.file_key = key
                    doc.file_name = filename
                    doc.file_size = src.stat().st_size
                    doc.sha256 = hashlib.sha256(src.read_bytes()).hexdigest()
                    doc.status = ResearchDocStatus.uploaded
                    break  # first downloaded artifact wins
                except Exception as e:  # noqa: BLE001
                    logger.warning("blob upload failed for %s: %s", filename, e)
                    doc.status = ResearchDocStatus.failed
                    doc.error_message = str(e)
            out[doc_type] = doc
        return out

    return fetch


def _map_step_status(step: dict, doc_type: str) -> ResearchDocStatus:
    status = step.get("status")
    if status == "ok":
        return ResearchDocStatus.uploaded
    if status == "link":
        return ResearchDocStatus.fetched  # link-only, no file to upload
    if status == "empty":
        return ResearchDocStatus.skipped
    return ResearchDocStatus.failed


def _build_provenance(step: dict) -> list:
    """Normalize the orchestrator's provenance/error info into the contract shape."""
    prov = step.get("provenance") or []
    return list(prov)