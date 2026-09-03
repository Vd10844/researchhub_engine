"""Engine orchestration — the phase-separated research pipeline.

``run_research`` is the production replacement for the POC monolith. It builds a
canonical ``PropertyContext`` (geocode → parcel → references), then fetches the
requested documents through per-source adapters, producing a ``ResearchResult``
whose per-step shape is the frozen frontend contract.
"""
from .runner import run_research

__all__ = ["run_research"]
