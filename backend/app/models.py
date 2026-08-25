"""Pydantic request/response models."""
from typing import Any, Optional
from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    job_number: str = Field(default="", description="e.g. 25-1229 (optional)")
    order_number: str = Field(default="", description="Order # for the Evidence Locker (optional)")
    address: str = Field(default="", description="Full street address (or use parcel_id)")
    parcel_id: str = Field(default="", description="Search by Parcel ID / APN instead of address (needs state)")
    state: str = Field(default="", description="Selected state (FIPS or USPS abbr)")
    county_fips: str = Field(default="", description="Selected 5-digit county FIPS")
    survey_type: str = Field(default="Residential Land Survey")
    include: list[str] = Field(
        default_factory=list,
        description="Unused in the FL residential POC — the full residential doc set always runs.",
    )


class EvidenceItem(BaseModel):
    key: str = Field(..., description="Document step key, e.g. 'deed'")
    label: str = Field(default="", description="Human label, e.g. 'Deed'")
    file: str = Field(..., description="Filename within the job's documents/ dir")
    source_url: str = Field(default="", description="County source URL for provenance")


class EvidenceSendRequest(BaseModel):
    order: str = Field(..., description="Order # the Evidence Locker is keyed by")
    job_name: str = Field(..., description="Source job folder name")
    items: list[EvidenceItem] = Field(default_factory=list)
    new_order: bool = Field(default=False,
                            description="First send of a session — allocate a fresh (suffixed) order")


class FeedbackRequest(BaseModel):
    name: str = Field(..., description="Job folder name (as returned in the result)")
    key: str = Field(..., description="Document/step key, e.g. 'deed', 'parcel', 'location'")
    verdict: str = Field(..., description="'match' | 'mismatch'")
    note: str = Field(default="", description="Optional free-text note from the surveyor")


class StepResult(BaseModel):
    key: str
    label: str
    status: str  # ok | empty | error | skipped | manual
    summary: str = ""
    data: Any = None
    source_url: str = ""
    saved_file: Optional[str] = None


class ResearchResponse(BaseModel):
    job_number: str
    address: str
    matched_address: str = ""
    county: str = ""
    state: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    folder: str = ""
    steps: list[StepResult] = []
