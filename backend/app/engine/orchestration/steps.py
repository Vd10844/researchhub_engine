"""Step assembly — the single place that decides what status/summary each document gets.

Centralization guarantees:
  - every step honors ``include`` (fetch ONLY the requested document types),
  - every exception is converted to a fallback ``link`` step + structured
    ``ErrorInfo`` (never a raw traceback to the frontend),
  - manifest logging and provenance are appended in exactly one place,
  - no adapter can silently skip a step.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.data.reference import RESIDENTIAL_DOCS
from app.engine.contracts import (
    Confidence,
    ErrorInfo,
    ProvenanceRecord,
    SourceOutcome,
    StepResult,
    StepStatus,
)
from app.services import downloader

from .sources import (
    ADAPTERS,
    FetchedSource,
    SourceAdapter,
    SourceError,
    classify_exception,
)


def build_steps(ctx, include: Iterable[str] | None = None) -> list[StepResult]:
    """Assemble the documents for this run, in the declared reference order.

    ``include`` filters by step key (e.g. ``["deed"]`` fetches ONLY the deed).
    ``None`` means every document in ``RESIDENTIAL_DOCS``.
    """
    wanted = set(include) if include is not None else None
    docs_dir = downloader.docs_dir(ctx.folder)
    steps: list[StepResult] = []
    for d in RESIDENTIAL_DOCS:
        if wanted is not None and d["key"] not in wanted:
            continue
        adapter = ADAPTERS.get(d["key"])
        if adapter is None:   # no adapter yet → link-only, never crash the run
            step = _assemble(ctx, d, FetchedSource(status=StepStatus.link),
                             SourceOutcome.link_only, None, Confidence.low)
            steps.append(step)
            continue
        steps.append(_run_one(ctx, d, adapter, docs_dir))
    return steps


def _run_one(ctx, d: dict, adapter: SourceAdapter, docs_dir) -> StepResult:
    try:
        fs = adapter.fetch(ctx, docs_dir)
        return _assemble(ctx, d, fs, _outcome_for(fs), None,
                         fs.confidence or _default_confidence(fs.status, fs.manual_review))
    except SourceError as e:
        fs = adapter.fallback(ctx)
        error = ErrorInfo(code=e.code or _code_for(e.outcome), retryable=e.retryable)
        if e.message:
            error.message = e.message
        return _assemble(ctx, d, fs, e.outcome, error, Confidence.none)
    except Exception as e:
        outcome, code, message, retryable = classify_exception(e)
        try:
            fs = adapter.fallback(ctx)
        except Exception:
            fs = FetchedSource(link="", link_label="", summary="Couldn't reach this source.")
        error = ErrorInfo(code=code, message=message, retryable=retryable)
        return _assemble(ctx, d, fs, outcome, error, Confidence.none)


def _assemble(ctx, d: dict, fs: FetchedSource, outcome: SourceOutcome,
              error: ErrorInfo | None, confidence: Confidence) -> StepResult:
    """One canonical StepResult + the manifest logging for this document."""
    if ctx is not None:
        for entry in fs.records:
            ctx.log(entry)
    return StepResult(
        key=d["key"],
        label=d["label"],
        requirement=d["requirement"],
        condition=d.get("condition", ""),
        description=d.get("description", ""),
        summary=fs.summary or "",
        status=fs.status,
        link=fs.link or "",
        link_label=fs.link_label or "",
        source_url=fs.source_url or "",
        saved_file=fs.saved_file,
        data=fs.data,
        downloaded=fs.downloaded,
        situs=fs.situs,
        land_sqft=fs.land_sqft,
        land_acres=fs.land_acres,
        address_match=fs.address_match,
        source_outcome=outcome,
        confidence=confidence,
        provenance=[_provenance_from(e) for e in fs.records],
        warnings=fs.warnings,
        error=error,
    )


def _outcome_for(fs: FetchedSource) -> SourceOutcome:
    if fs.manual_review:
        return SourceOutcome.manual_review
    if fs.status == StepStatus.ok:
        return SourceOutcome.auto
    if fs.status == StepStatus.empty:
        return SourceOutcome.auto
    return SourceOutcome.link_only


def _default_confidence(status: StepStatus, manual_review: bool = False) -> Confidence:
    if manual_review:
        return Confidence.low
    if status == StepStatus.ok:
        return Confidence.high
    if status == StepStatus.empty:
        return Confidence.medium
    return Confidence.low


def _code_for(outcome: SourceOutcome) -> str:
    return {
        SourceOutcome.blocked: "SOURCE_BLOCKED",
        SourceOutcome.broken: "SOURCE_BROKEN",
        SourceOutcome.retryable: "SOURCE_UNREACHABLE",
        SourceOutcome.link_only: "LINK_ONLY",
        SourceOutcome.auto: "AUTO",
        SourceOutcome.manual_review: "MANUAL_REVIEW",
    }[outcome]


def _provenance_from(entry: dict) -> ProvenanceRecord:
    return ProvenanceRecord(
        source_id=entry.get("source", ""),
        provider=entry.get("source", ""),
        url=entry.get("source", ""),
        retrieved_utc=entry.get("fetched_utc", ""),
        file=entry.get("file"),
        sha256=entry.get("sha256"),
    )
