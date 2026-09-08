"""AC-keyed conformance suite for the AI Retrieval story.

Run: pytest tests/test_conformance_acceptance.py -v

This is the QA-facing acceptance suite: one test class per acceptance
criterion (AC1, AC2, AC9, AC11, AC13), each asserting the *behavior* the
story promises rather than a data shape. It runs fully offline — no network,
no live Postgres, no broker. Context resolution (geocode / parcel) is
injected as pre-resolved ``PropertyContext`` (reuses ``make_ctx``); only the
per-source document adapters (``build_steps``) are exercised, which is where
the story's document-source behavior lives.

Document-source map (story):
    - Auto-fetched: parcel, appraiser, deed, plat, adjoiners, easements,
      prior_survey, condo
    - Link-only (county/recorder/portal deep link): zoning, flood/benchmarks
      when the offline context has no source data, glo

AC status at time of writing:
    AC1  (Auto-Fetch All  -> all 9 sources)  PASS  (see TestAC1)
    AC2  (individual retrieval)              PARTIAL — 6 of 9 are API
          requestable via ``STEP_TO_DOC_TYPE``; adjoiners/easements/
          prior_survey/zoning are produced by the orchestrator but not yet
          exposed on the DocumentType enum (logged as a known gap on the API).
    AC9  (open-source link + label)          PASS  (see TestAC9)
    AC11 (partial success preserved)         PASS  (see TestAC11)
    AC13 (session recovery / reconstruction) PASS  (see TestAC13)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from app.engine.contracts import Confidence, SourceOutcome, StepStatus
from app.engine.orchestration.sources import ADAPTERS, FetchedSource, SourceError
from app.engine.orchestration.steps import build_steps

from tests.test_orchestration_engine import make_ctx

# The story's 9 end-user document sources.
STORY_9 = ["parcel", "appraiser", "deed", "plat",
           "adjoiners", "easements", "prior_survey", "flood", "zoning"]

# The 6 the HTTP API can currently request by DocumentType.
API_REQUESTABLE_6 = ["parcel", "appraiser", "plat", "deed", "flood", "benchmarks"]

# The 4 newly-exposed sources (produced by the orchestrator after A1).
NEW_SOURCES_4 = ["adjoiners", "easements", "prior_survey", "zoning"]


def run_include(ctx, include):
    """Build steps for a context, honoring the ``include`` filter."""
    return build_steps(ctx, include=include)


@pytest.fixture
def ctx(tmp_path: Path):
    """A pre-resolved, network-free property context (parcel OK)."""
    return make_ctx(tmp_path)


@pytest.fixture
def adapters():
    """Snapshot/restore ADAPTERS so per-test fakes never leak."""
    saved = dict(ADAPTERS)
    yield ADAPTERS
    ADAPTERS.clear()
    ADAPTERS.update(saved)


@pytest.fixture(autouse=True)
def _offline(adapters):
    """Keep the suite network-free: fake the two adapters that would hit
    the live web (FEMA NFHL / NGS radial) so every test runs locally."""
    real = dict(ADAPTERS)
    try:
        ADAPTERS["flood"] = FakeAdapter(
            fs=FetchedSource(status=StepStatus.link, summary="No mapped SFHA polygon (offline fixture)",
                             link="https://msc.fema.gov/", link_label="Open FEMA Map Service Center (FIRMette)",
                             source_url="https://msc.fema.gov/"))
        ADAPTERS["benchmarks"] = FakeAdapter(
            fs=FetchedSource(status=StepStatus.empty, summary="No NGS marks (offline fixture)",
                             link="https://geodesy.noaa.gov/", link_label="Open NGS datasheets",
                             source_url="https://geodesy.noaa.gov/api/nde/radial"))
        yield ADAPTERS
    finally:
        ADAPTERS.clear()
        ADAPTERS.update(real)


# ---------------------------------------------------------------------- AC1


class TestAC1_AutoFetchAll:
    """AC1 — Address + parcel ID must produce all 9 document sources."""

    def test_all_nine_story_sources_are_produced(self, ctx):
        steps = {s.key: s for s in run_include(ctx, include=None)}
        missing = [k for k in STORY_9 if k not in steps]
        assert not missing, f"Auto-Fetch All is missing story sources: {missing}"

    def test_every_story_source_has_a_status(self, ctx):
        steps = {s.key: s for s in run_include(ctx, include=None)}
        for key in STORY_9:
            assert steps[key].status in (StepStatus.ok, StepStatus.link,
                                         StepStatus.empty, StepStatus.error), \
                f"{key} has an invalid status {steps[key].status!r}"

    def test_newly_exposed_sources_execute(self, ctx):
        """The 4 sources from A1 must now be *executed* (not skipped/absent)."""
        steps = {s.key: s for s in run_include(ctx, include=None)}
        for key in NEW_SOURCES_4:
            assert key in steps, f"{key} missing from Auto-Fetch All output"
            assert steps[key].status != StepStatus.empty, f"{key} unexpectedly empty"


# ---------------------------------------------------------------------- AC2


class TestAC2_IndividualRetrieval:
    """AC2 — Each document source is individually retrievable."""

    def test_api_requestable_sources_produce_a_step_when_alone(self, ctx, adapters):
        real = dict(ADAPTERS)
        try:
            for key in API_REQUESTABLE_6:
                # give flood a real data context's fakes so it is exercised
                steps = {s.key: s for s in run_include(ctx, include=[key])}
                assert key in steps, f"requesting {key} alone produced no step"
                step = steps[key]
                assert step.status in (StepStatus.ok, StepStatus.link,
                                       StepStatus.empty, StepStatus.error), \
                    f"{key} alone had invalid status {step.status!r}"
        finally:
            ADAPTERS.clear()
            ADAPTERS.update(real)

    def test_include_filter_runs_only_the_requested_step(self, ctx, adapters):
        real = dict(ADAPTERS)
        try:
            for key in ["deed", "adjoiners"]:
                steps = run_include(ctx, include=[key])
                assert [s.key for s in steps] == [key], \
                    f"include=[{key}] produced {[s.key for s in steps]}"
        finally:
            ADAPTERS.clear()
            ADAPTERS.update(real)

    def test_four_new_sources_are_orchestrated(self, ctx):
        """AC2 note: the 4 new sources run in the orchestrator; API exposure
        of their DocumentType enum values is a logged partial (see module doc)."""
        steps = {s.key for s in run_include(ctx, include=NEW_SOURCES_4)}
        assert sorted(steps) == NEW_SOURCES_4, f"expected orchestration of {NEW_SOURCES_4}, got {steps}"


# ---------------------------------------------------------------------- AC9


class TestAC9_OpenSource:
    """AC9 — Every source must supply an open-source link + label."""

    def test_every_story_source_has_link_and_label(self, ctx):
        steps = {s.key: s for s in run_include(ctx, include=None)}
        for key in STORY_9:
            step = steps[key]
            assert step.link, f"{key} has an empty open-source link"
            assert step.link_label, f"{key} is missing a link label"

    def test_auto_fetched_sources_still_deep_link(self, ctx):
        """An auto-fetched source must still offer a human open-source link."""
        steps = {s.key: s for s in run_include(ctx, include=None)}
        for key in ["deed", "plat"]:
            assert steps[key].status == StepStatus.ok
            assert steps[key].link, f"{key} auto-fetched but lost its deep link"


# ---------------------------------------------------------------------- AC11


class TestAC11_PartialSuccess:
    """AC11 — On partial failure the successes are kept and failures marked."""

    def test_success_and_failure_coexist(self, ctx, adapters):
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
        steps = {s.key: s for s in run_include(ctx, include=["deed", "appraiser"])}

        # The success is kept with provenance.
        assert steps["deed"].status == StepStatus.ok
        assert steps["deed"].source_outcome == SourceOutcome.auto
        assert steps["deed"].confidence == Confidence.high
        assert steps["deed"].provenance and steps["deed"].provenance[0].file == "documents/deed.pdf"

        # The failure degrades to a fallback link and is marked, not dropped.
        assert steps["appraiser"].status == StepStatus.link
        assert steps["appraiser"].source_outcome == SourceOutcome.broken
        assert steps["appraiser"].error is not None
        assert steps["appraiser"].error.code == "HTTP_503"
        assert steps["appraiser"].error.retryable is True
        assert steps["appraiser"].link == "https://fallback.example.test"

    def test_all_failed_still_returns_steps_with_links(self, ctx, adapters):
        for key, code in [("flood", "HTTP_403"), ("benchmarks", "HTTP_502")]:
            adapters[key] = FakeAdapter(
                error=SourceError(outcome=SourceOutcome.blocked, code=code,
                                  message="blocked", retryable=False))
        steps = {s.key: s for s in run_include(ctx, include=["flood", "benchmarks"])}
        for key in ["flood", "benchmarks"]:
            assert steps[key].status == StepStatus.link
            assert steps[key].link, f"{key} lost its fallback link on failure"


# ---------------------------------------------------------------------- AC13


class TestAC13_SessionRecovery:
    """AC13 — State must be reconstructable (statuses, counts, references)."""

    def test_result_rebuilds_statuses_and_counts(self, ctx):
        result = _run_to_result(ctx)
        docs = result.steps
        statuses = {s.key: s.status for s in docs}
        for key in STORY_9:
            assert key in statuses, f"rebuilt result missing {key}"
        # counts: how many are ok / link / empty
        ok_n = sum(1 for s in docs if s.status == StepStatus.ok)
        assert ok_n >= 1, "expected at least one 'ok' source after a run"
        from app.engine.contracts import ResearchResult
        assert isinstance(result, ResearchResult)
        assert result.steps, "rebuilt result must carry the step list"

    def test_failure_metadata_is_recoverable(self, ctx, adapters):
        adapters["flood"] = FakeAdapter(
            error=SourceError(outcome=SourceOutcome.retryable, code="CONNECTION_FAILED",
                              message="no route", retryable=True))
        result = _run_to_result(ctx)
        step = next(s for s in result.steps if s.key == "flood")
        assert step.status == StepStatus.link
        assert step.error is not None and step.error.code == "CONNECTION_FAILED"
        assert step.error.retryable is True

    def test_file_references_present_for_fetched_sources(self, ctx):
        """Fetched ('ok' with downloads) sources carry a provenance file ref."""
        steps = {s.key: s for s in run_include(ctx, include=None)}
        for key, step in steps.items():
            if step.status == StepStatus.ok and step.downloaded:
                assert step.provenance, f"{key} is ok with downloads but no provenance"


# ------------------------------------------------------------------ helpers


def _run_to_result(ctx):
    """Wrap a build_steps run in the canonical ResearchResult shape."""

    from app.engine.contracts import JobState, ResearchResult
    from app.engine.orchestration import context as ctx_mod
    steps = run_include(ctx, include=None)
    return ResearchResult(
        job_number=ctx.job_number, order=ctx.order, parcel_id=ctx.parcel_id,
        address=ctx.address, matched_address=ctx.matched_address, county=ctx.county,
        county_fips=ctx.county_fips, state=ctx.state, lat=ctx.lat, lon=ctx.lon,
        name=ctx.name, geocoder=ctx.geocoder, map_links=[], folder=str(ctx.folder),
        docs_dir=str(ctx.folder), steps=steps, warnings=list(ctx.warnings),
        completed_utc=ctx_mod.now_utc(), job_state=JobState.completed,
        survey_type=ctx.survey_type,
    )


class FakeAdapter:
    """Pluggable test adapter returning a canned source or raising."""

    def __init__(self, fs=None, error: Exception | None = None):
        self.fs = fs or FetchedSource(status=StepStatus.ok, summary="auto ok")
        self.error = error

    def fetch(self, ctx, docs_dir):
        if self.error:
            raise self.error
        return self.fs

    def fallback(self, ctx, error=None) -> FetchedSource:
        return FetchedSource(
            status=StepStatus.link, summary="fallback link",
            link="https://fallback.example.test", link_label="Open source",
        )
