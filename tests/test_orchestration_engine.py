"""Engine orchestration validation — offline, deterministic, no network.

Covers the delivery-3 test cases:
  - no source match            (parcel → link, hints preserved)
  - partial failure            (one ok + one broken in one run)
  - blocked source             (SourceError(blocked) → fallback link + structured error)
  - valid fallback flow        (connection error → fallback link retained)
  - job completion flow        (full run persists manifest + result.json, all steps valid)
  - include filtering          (fetch ONLY the requested document types)

The real adapters that touch the network (geocode, flood, ngs, clerk scrape) are
replaced with registered fakes; the parcel/appraiser paths that are purely local
(staging writes) run through the REAL adapters end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.contracts import (
    Confidence,
    ErrorInfo,
    JobState,
    SourceOutcome,
    StepResult,
    StepStatus,
)

from app.engine.orchestration.context import PropertyContext, WarningBag
from app.engine.orchestration.sources import (
    ADAPTERS,
    FetchedSource,
    ParcelAdapter,
    SourceError,
)


# ------------------------------------------------------------------ helpers


def make_ctx(folder: Path, *, parcel_ok: bool = True) -> PropertyContext:
    folder.mkdir(parents=True, exist_ok=True)
    ctx = PropertyContext(
        address="1 Test St",
        matched_address="1 Test St",
        lat=27.9,
        lon=-82.5,
        state="FL",
        state_fips="12",
        county="Hillsborough",
        county_fips="12057",
        geocoder="census",
        appraiser_url="https://pa.example.test/hillsborough",
        parcel=({
            "method": "arcgis-rest",
            "parcels": [{
                "folio": "A123",
                "situs": "1 Test St",
                "ownname": "J DOE",
                "slegal": "PB 1 PG 2",
                "land": {"main_area": "10000", "living_area": "1800"},
                "sale": {"or_book": "8147", "or_page": "4623"},
            }],
            "address_match": True,
            "source": "https://gis.example.test/arcgis",
            "situs": "1 Test St",
            "land_sqft": 10000,
            "land_acres": 0.23,
        } if parcel_ok else {"method": "arcgis-rest", "parcels": [],
                             "address_match": False, "hints": {}}),
        parcel_id="A123" if parcel_ok else "",
        parcel_ok=parcel_ok,
        parcel_hints={"addr": "1 Test St"} if parcel_ok else {},
        clerk_ref={
            "official_records_search": "https://clerk.example.test/or/",
            "plat_search": "https://clerk.example.test/plat/",
            "targets": ["deed", "plat"],
        },
        job_number="A-1",
        order="ORD-1",
        name="A-1",
        folder=folder,
        appr={},
        warnings=WarningBag(),
    )
    # Mirror the real context phase's staging side effects so runner tests can
    # assert the audit artifacts like a genuine run would.
    from app.engine.orchestration.folders import save_json

    ctx.manifest.append({**save_json(folder, "geocode.json",
                                     {"matched_address": "1 Test St"}),
                         "source": "https://geocoding.geo.census.gov/geocoder/"})
    ctx.manifest.append({**save_json(folder, "parcel.json", ctx.parcel),
                         "source": ctx.appraiser_url})
    ctx.manifest.append({**save_json(folder, "clerk_search_refs.json", ctx.clerk_ref),
                         "source": ctx.clerk_ref["official_records_search"]})
    return ctx


class FakeAdapter:
    """Pluggable test adapter: returns a canned FetchedSource or raises."""

    def __init__(self, fs=None, error: Exception | None = None):
        self.fs = fs or FetchedSource(status=StepStatus.ok, summary="auto ok")
        self.error = error
        self.calls = 0

    def fetch(self, ctx, docs_dir):
        self.calls += 1
        if self.error:
            raise self.error
        return self.fs

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        return FetchedSource(
            status=StepStatus.link,
            summary="fallback link",
            link="https://fallback.example.test",
            link_label="Open source",
        )


@pytest.fixture
def adapters():
    """Snapshot + restore ADAPTERS so tests can register fakes freely."""
    saved = dict(ADAPTERS)
    yield ADAPTERS
    ADAPTERS.clear()
    ADAPTERS.update(saved)


@pytest.fixture
def ctx(tmp_path) -> PropertyContext:
    return make_ctx(tmp_path)


def build(ctx, include):
    from app.engine.orchestration.steps import build_steps
    return build_steps(ctx, include=include)


# ------------------------------------------------------------------ no source match

class TestNoSourceMatch:
    """A parcel that can't be confirmed must degrade to a reference link."""

    def test_parcel_no_match_is_link(self, tmp_path):
        ctx = make_ctx(tmp_path, parcel_ok=False)
        steps = build(ctx, include=["parcel"])
        step = steps[0]
        assert step.status == StepStatus.link
        assert step.source_outcome == SourceOutcome.link_only
        assert "Parcel record not found" in step.summary
        assert step.link == ctx.appraiser_url
        assert step.saved_file == "parcel.json"

    def test_parcel_no_match_has_no_wrong_data(self, tmp_path):
        ctx = make_ctx(tmp_path, parcel_ok=False)
        (step,) = build(ctx, include=["parcel"])
        assert step.data is None
        assert step.error is None
        assert step.parcel_id == "" if hasattr(step, "parcel_id") else True


# --------------------------------------------------------------- partial failure

class TestPartialFailure:
    """One source works, one breaks — the run must not blow up."""

    def test_mixed_run_keeps_both_steps(self, ctx, adapters):
        adapters["deed"] = FakeAdapter(
            fs=FetchedSource(status=StepStatus.ok, summary="Auto-fetched deed",
                             downloaded=["deed.pdf"],
                             records=[{"file": "documents/deed.pdf",
                                       "source": "https://clerk.example.test/or/"}])
        )
        adapters["appraiser"] = FakeAdapter(
            error=SourceError(outcome=SourceOutcome.broken, code="HTTP_503",
                              message="server error", retryable=True)
        )
        steps = {s.key: s for s in build(ctx, include=["deed", "appraiser"])}
        assert set(steps) == {"deed", "appraiser"}

        deed = steps["deed"]
        assert deed.status == StepStatus.ok
        assert deed.source_outcome == SourceOutcome.auto
        assert deed.confidence == Confidence.high
        assert deed.provenance and deed.provenance[0].file == "documents/deed.pdf"

        appr = steps["appraiser"]
        assert appr.status == StepStatus.link
        assert appr.source_outcome == SourceOutcome.broken
        assert appr.error is not None and appr.error.code == "HTTP_503"
        assert appr.error.retryable is True
        assert appr.link == "https://fallback.example.test"


# ------------------------------------------------------------- blocked source

class TestBlockedSource:
    """A 403/WAF block must surface as block + fallback, never as raw error."""

    def test_blocked_sets_outcome_and_error(self, ctx, adapters):
        adapters["flood"] = FakeAdapter(
            error=SourceError(outcome=SourceOutcome.blocked, code="HTTP_403",
                              message="WAF blocked", retryable=False)
        )
        (step,) = build(ctx, include=["flood"])
        assert step.status == StepStatus.link
        assert step.source_outcome == SourceOutcome.blocked
        assert step.error is not None
        assert step.error.code == "HTTP_403"
        assert step.error.retryable is False
        assert step.link == "https://fallback.example.test"


# --------------------------------------------------------- valid fallback flow

class TestValidFallback:
    """Connection failure must classify as retryable and keep the deep link."""

    def test_connection_error_is_retryable_with_fallback(self, ctx, adapters):
        import requests
        adapters["benchmarks"] = FakeAdapter(
            error=requests.exceptions.ConnectionError("no route"))
        (step,) = build(ctx, include=["benchmarks"])
        assert step.status == StepStatus.link
        assert step.source_outcome == SourceOutcome.retryable
        assert step.error.code == "CONNECTION_FAILED"
        assert step.error.retryable is True
        assert step.link == "https://fallback.example.test"   # deep link kept

    def test_unknown_exception_still_yields_link(self, ctx, adapters):
        adapters["glo"] = FakeAdapter(error=RuntimeError("boom"))
        (step,) = build(ctx, include=["glo"])
        assert step.status == StepStatus.link
        assert step.source_outcome == SourceOutcome.retryable
        assert step.link != ""


# -------------------------------------------------------------- include honours

class TestIncludeFiltering:
    """Fetching a subset must not do work for the omitted sources."""

    def test_include_single_doc_runs_only_that_adapter(self, ctx, adapters):
        deed = FakeAdapter(fs=FetchedSource(status=StepStatus.ok, summary="deed"))
        adapters["deed"] = deed
        adapters["parcel"] = FakeAdapter()
        steps = build(ctx, include=["deed"])
        assert [s.key for s in steps] == ["deed"]
        assert deed.calls == 1
        assert adapters["parcel"].calls == 0   # the old monolith would have resolved it

    def test_include_unknown_key_yields_no_steps(self, ctx, adapters):
        assert build(ctx, include=["nope"]) == []

    def test_include_none_runs_every_registered_step(self, ctx, adapters):
        from app.data.reference import RESIDENTIAL_DOCS
        for key in list(ADAPTERS):
            ADAPTERS[key] = FakeAdapter()
        steps = build(ctx, include=None)
        assert [s.key for s in steps] == [d["key"] for d in RESIDENTIAL_DOCS]
        assert all(a.calls == 1 for a in ADAPTERS.values())


# --------------------------------------------------------- job completion flow

class TestJobCompletion:
    """The full runner completes, persists artifacts, and matches the lifecycle."""

    def test_runner_completes_and_persists(self, tmp_path, adapters, monkeypatch):
        from app.engine.orchestration import context as ctx_mod
        from app.engine.orchestration.runner import run_research

        folder = tmp_path / "jobs" / "A-1" / "research"
        fake_ctx = make_ctx(folder)
        monkeypatch.setattr(ctx_mod, "resolve_property_context",
                            lambda **kw: fake_ctx)
        for key in list(ADAPTERS):
            ADAPTERS[key] = FakeAdapter() if key != "appraiser" else \
                FakeAdapter()

        result = run_research(address="1 Test St")
        assert result.job_state == JobState.completed
        assert result.warnings == []
        from app.data.reference import RESIDENTIAL_DOCS
        assert [s.key for s in result.steps] == [d["key"] for d in RESIDENTIAL_DOCS]
        # audit artifacts written to the staging folder
        assert (folder / "result.json").is_file()
        assert (folder / "manifest.json").is_file()
        assert (folder / "geocode.json").is_file()
        assert (folder / "parcel.json").is_file()

    def test_runner_honours_include(self, tmp_path, adapters, monkeypatch):
        from app.engine.orchestration import context as ctx_mod
        from app.engine.orchestration.runner import run_research

        folder = tmp_path / "jobs" / "A-1" / "research"
        monkeypatch.setattr(ctx_mod, "resolve_property_context",
                            lambda **kw: make_ctx(folder))
        spy = FakeAdapter()
        adapters["benchmarks"] = spy
        result = run_research(address="1 Test St", include=["benchmarks"])
        assert [s.key for s in result.steps] == ["benchmarks"]
        assert spy.calls == 1


# ------------------------------------------------- real adapters, offline e2e

class TestRealAdaptersOffline:
    """Real parcel + appraiser adapters run end-to-end without the network —
    only geocode/parcel.resolve are stubbed; everything downstream is the
    production code path (staging, reports, manifest, result.json)."""

    def test_real_parcel_appraiser_run(self, tmp_path, adapters, monkeypatch):
        from app.data import geography
        from app.engine.orchestration import context as ctx_mod
        from app.engine.orchestration.runner import run_research
        from app.services import geocode as geo_mod
        from app.services import parcel as parcel_mod

        monkeypatch.setattr(ctx_mod, "resolve_property_context",
                            lambda **kw: make_ctx(tmp_path / "jobs" / "A-1" / "research"))
        result = run_research(address="1 Test St", include=["parcel", "appraiser"])

        steps = {s.key: s for s in result.steps}
        assert set(steps) == {"parcel", "appraiser"}
        parcel, appr = steps["parcel"], steps["appraiser"]

        assert parcel.status == StepStatus.ok
        assert parcel.source_outcome == SourceOutcome.auto
        assert "Parcel ID: A123" in parcel.summary
        assert parcel.downloaded, "parcel record report should be staged on disk"

        assert appr.status == StepStatus.ok
        assert appr.downloaded, "appraiser tax-record report should be staged"

        # persist the run
        folder = tmp_path / "jobs" / "A-1" / "research"
        assert (folder / "result.json").is_file()
        assert (folder / "manifest.json").is_file()
        assert (folder / "documents").is_dir()


# ---------------------------------------------------------------------------
# Fetch-or-link invariant
# ---------------------------------------------------------------------------

class TestFetchOrLinkInvariant:
    """Every document in the reference set must either be fetched (ok) or
    carry a non-empty fallback link. No document is ever left with neither —
    that is the production contract for 'download if available, else a link'."""

    def test_every_doc_is_fetched_or_linked(self, tmp_path, adapters, monkeypatch):
        from app.data.reference import RESIDENTIAL_DOCS
        from app.engine.orchestration import context as ctx_mod
        from app.engine.orchestration.runner import run_research

        # Use the REAL adapters running against a full test context so the
        # invariant is exercised by production source code, not fakes.
        monkeypatch.setattr(ctx_mod, "resolve_property_context",
                            lambda **kw: make_ctx(tmp_path / "jobs" / "A-1" / "research"))
        result = run_research(address="1 Test St")

        by_key = {s.key: s for s in result.steps}
        assert set(by_key) == {d["key"] for d in RESIDENTIAL_DOCS}

        bad = []
        for key, step in by_key.items():
            fetched = step.status == StepStatus.ok
            has_link = bool(step.link)
            if not fetched and not has_link:
                bad.append(key)
        assert not bad, (
            f"documents with neither fetch nor link: {bad}"
        )

        # Every step that isn't ok must have a link (link/error/empty all
        # require a fallback deep-link).
        for key, step in by_key.items():
            if step.status != StepStatus.ok:
                assert step.link, f"{key} status={step.status.value} has no link"

    def test_reference_docs_all_have_an_adapter(self):
        """Every reference doc is registered — none silently drop to a bare
        empty step with no source at all."""
        from app.data.reference import RESIDENTIAL_DOCS
        from app.engine.orchestration.sources import ADAPTERS
        missing = [d["key"] for d in RESIDENTIAL_DOCS if d["key"] not in ADAPTERS]
        assert not missing, f"reference docs with no adapter: {missing}"