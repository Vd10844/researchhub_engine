"""Engine vocabulary — the single source of truth for all status/outcome/confidence values.

Every module in the engine imports from here.  Do not define ad-hoc string literals
elsewhere; if a new status or outcome is needed, add it here first.

Frozen FE-facing step statuses are *additive-safe*: the old values `ok / link / empty / error`
keep their meaning; new engine-internal classification rides alongside in
`source_outcome` and `confidence` fields.
"""
from __future__ import annotations

import enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------- enums

class StepStatus(str, enum.Enum):
    """What the frontend renders today — frozen, backward-compatible with the POC."""
    ok = "ok"
    link = "link"
    empty = "empty"
    error = "error"


class SourceOutcome(str, enum.Enum):
    """Engine-internal reliability classification for *why* a source returned what it did.

    This replaces the ad-hoc if/elif chains in research.py with a single vocabulary
    that can be filtered, monitored, and surfaced to ops dashboards.

    Mapped from HTTP exceptions + adapter behaviour:
      auto         — data fetched successfully (fetcher returned structured data)
      link_only    — no auto-download exists; a deep-link was provided (by design, not failure)
      blocked      — source returned 401/403/406/429 (WAF/bot block — opens in a real browser)
      broken       — source returned 404/410/5xx (the URL is wrong or the server errored)
      retryable    — source timed out or had a connection error after exhausting retries
      manual_review — data is present but ambiguous (e.g. parcel matched via buffered
                      point with no address confirmation); needs human eyeballs
    """
    auto = "auto"
    link_only = "link_only"
    blocked = "blocked"
    broken = "broken"
    retryable = "retryable"
    manual_review = "manual_review"


class Confidence(str, enum.Enum):
    """How sure the engine is that the result actually pertains to the searched property."""
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


class JobState(str, enum.Enum):
    """Full lifecycle of a research job — persisted in DB, polled by consumers.

    Transitions:
      queued   → running          (runner picks it up)
      running  → completed        (every adapter returned designed outcome)
      running  → partial          (≥1 adapter hit an unexpected failure: blocked/broken/retryable)
      running  → failed           (context resolution failed — no geocode, no parcel-id match)
      completed | partial → reviewed   (human confirms documents are correct)
      reviewed → archived         (retention / hide from default list)
    """
    queued = "queued"
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"
    reviewed = "reviewed"
    archived = "archived"


class SourceState(str, enum.Enum):
    """Per-source row status — renders the right-hand source rail in the UI.

    Lives on ``qp_order_sources.state``; driven by the research runner's
    ``_apply_result`` mapping.  Kept separate from ``SourceOutcome`` because
    it describes the *state of the UI row*, not the *reason behind the result*.
    """
    idle = "idle"
    fetching = "fetching"
    fetched = "fetched"
    failed = "failed"
    unavailable = "unavailable"


# ------------------------------------------------------------------- data models

class ProvenanceRecord(BaseModel):
    """Where this piece of data came from — stamped by the engine, not by adapters."""
    source_id: str = Field(..., description="Unique source identifier, e.g. 'parcel.state_fl', 'fema.nfhl'")
    provider: str = Field(default="", description="How the data was obtained: arcgis-rest, census, playwright, etc.")
    url: str = Field(default="", description="Source URL or endpoint hit")
    retrieved_utc: str = Field(default="", description="ISO-8601 timestamp of the retrieval")
    attempt: int = Field(default=1, description="Which attempt succeeded (1-based)")
    fallback_chain: list[str] = Field(default_factory=list, description="Ordered list of source_ids tried before success")
    file: Optional[str] = Field(default=None, description="Relative path of saved artifact within the job folder")
    sha256: Optional[str] = Field(default=None, description="SHA-256 digest of the saved artifact (if any)")


class ErrorInfo(BaseModel):
    """Structured error from a failed source adapter — never a raw exception string."""
    code: str = Field(default="", description="Machine-readable error code, e.g. 'TIMEOUT', 'HTTP_403', 'PARSE_FAILED'")
    message: str = Field(default="", description="Human-readable summary")
    retryable: bool = Field(default=False, description="True if the engine should retry later")


class StepResult(BaseModel):
    """One document step in a research result — the canonical output shape.

    This is the contract the frontend team codes against.  Fields marked
    ``frozen`` have shipped in the POC and will not change meaning or type.
    Fields marked ``additive`` are new in the engine; they can appear alongside
    the frozen fields without breaking existing consumers.

    The 7 frozen fields (from the POC's ``result.json``):
        key, label, requirement, condition, summary, status, link
    Plus 5 frozen-but-POC-present fields:
        link_label, source_url, saved_file, data, downloaded
    Plus 3 frozen-but-POC-step-specific:
        situs, land_sqft, land_acres, address_match
    """
    # --- frozen (POC-present, stable meaning) ---
    key: str = Field(..., description="e.g. 'parcel', 'deed', 'flood'")
    label: str = Field(default="", description="Human label for the document type")
    requirement: str = Field(default="mandatory", description="mandatory | conditional | recommended")
    condition: str = Field(default="", description="When this document is required (e.g. 'if in a recorded subdivision')")
    description: str = Field(default="", description="What this document is and why it matters")
    summary: str = Field(default="", description="One-line summary of what was found")
    status: StepStatus = Field(..., description="ok | link | empty | error (frozen for FE)")
    link: str = Field(default="", description="Fallback deep-link when auto-fetch is not available")
    link_label: str = Field(default="", description="Display text for the link button")
    source_url: str = Field(default="", description="Primary source URL for this document type")
    saved_file: Optional[str] = Field(default=None, description="Relative filename of a generated metadata file (e.g. parcel.json)")
    data: Any = Field(default=None, description="Raw data payload (source-specific, not for direct rendering)")
    downloaded: list[str] = Field(default_factory=list, description="Filenames of downloaded documents (inside documents/ folder)")

    # --- frozen POC step-specific (only parcel step uses these) ---
    situs: Optional[str] = Field(default=None)
    land_sqft: Optional[float] = Field(default=None)
    land_acres: Optional[float] = Field(default=None)
    address_match: Optional[bool] = Field(default=None)

    # --- additive (engine v1 new fields, backward-compatible) ---
    source_outcome: SourceOutcome = Field(
        default=SourceOutcome.auto,
        description="Engine classification of why this result is what it is",
    )
    confidence: Confidence = Field(
        default=Confidence.high,
        description="How sure the engine is that this pertains to the searched property",
    )
    provenance: list[ProvenanceRecord] = Field(
        default_factory=list,
        description="Audit trail: every source hit that contributed to this step",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Per-step warnings surfaced to the user (e.g. 'buffered match, verify location')",
    )
    error: Optional[ErrorInfo] = Field(
        default=None,
        description="Structured error when status == 'error'",
    )


class ResearchResult(BaseModel):
    """Full output of a research run — the top-level payload consumers receive.

    Frozen top-level fields match the POC's ``result.json`` exactly.
    New fields are additive and prefixed with comments.
    """
    # --- frozen ---
    job_number: str = Field(default="")
    order: str = Field(default="")
    parcel_id: str = Field(default="")
    address: str = Field(default="")
    matched_address: str = Field(default="")
    county: str = Field(default="")
    county_fips: str = Field(default="")
    state: str = Field(default="")
    lat: Optional[float] = Field(default=None)
    lon: Optional[float] = Field(default=None)
    name: str = Field(default="", description="Job folder name")
    geocoder: str = Field(default="", description="Which geocoder matched: census | arcgis | nominatim")
    map_links: list[dict] = Field(default_factory=list)
    folder: str = Field(default="")
    steps: list[StepResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # --- additive (engine v1) ---
    completed_utc: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp when the pipeline finished (new)",
    )
    job_state: JobState = Field(
        default=JobState.completed,
        description="Persisted lifecycle state of this job (new)",
    )
    docs_dir: Optional[str] = Field(
        default=None,
        description="Additive: research staging directory containing documents/ (internal)",
    )
    survey_type: str = Field(
        default="",
        description="Additive: survey type passed into the run (e.g. Residential Land Survey)",
    )
