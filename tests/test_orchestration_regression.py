"""Regression — POC fixtures vs the refactored engine contract.

Proves the orchestration refactor did NOT break the frontend contract:

  1. every saved POC ``result.json`` still validates as the new
     ``ResearchResult`` / ``StepResult`` schemas (frozen fields unchanged),
  2. every step key in the fixtures maps to a registered source adapter,
  3. fixture statuses stay within the frozen ``ok / link / empty / error`` vocabulary,
  4. the runner reproduces the identical 11-key document set in the same order,
  5. additive (engine v1) fields never collide with frozen POC field meaning.

Run: pytest tests/test_orchestration_regression.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.data.reference import RESIDENTIAL_DOCS
from app.engine.contracts import ResearchResult, StepResult

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "poc_results"

FROZEN_STEP_KEYS = {
    "parcel", "appraiser", "deed", "plat", "adjoiners", "easements",
    "prior_survey", "flood", "benchmarks", "glo", "condo",
}


def _fixtures():
    for f in sorted(FIXTURES.glob("*.json")):
        import json
        yield f.stem, json.loads(f.read_text(encoding="utf-8"))


FIXTURE_LIST = list(_fixtures())


@pytest.fixture
def adapters():
    """Snapshot + restore the source-adapter registry."""
    from app.engine.orchestration.sources import ADAPTERS
    saved = dict(ADAPTERS)
    yield ADAPTERS
    ADAPTERS.clear()
    ADAPTERS.update(saved)


@pytest.fixture(params=FIXTURE_LIST, ids=[n for n, _ in FIXTURE_LIST])
def fixture(request):
    _, data = request.param
    return data


class TestFixtureContractCompatibility:
    """The saved POC outputs parse into the new schemas unchanged."""

    def test_top_level_parses_as_research_result(self, fixture):
        result = ResearchResult(**fixture)
        assert result.steps  # pydantic coerced the nested dicts

    def test_each_step_parses_as_step_result(self, fixture):
        for step in fixture["steps"]:
            parsed = StepResult(**step)
            assert parsed.key == step["key"]
            assert parsed.status.value == step["status"]

    def test_step_keys_match_reference_set(self, fixture):
        keys = {s["key"] for s in fixture["steps"]}
        assert keys == FROZEN_STEP_KEYS

    def test_step_key_order_equals_reference_order(self, fixture):
        # The POC fixture is a historical snapshot: its step keys must be a
        # strict subset of RESIDENTIAL_DOCS, appearing in the same relative
        # order. Steps added to the reference set after the fixture was saved
        # (e.g. zoning) make the fixture a prefix, not an exact match.
        ref_keys = [d["key"] for d in RESIDENTIAL_DOCS]
        ref_idx = {k: i for i, k in enumerate(ref_keys)}
        actual = [s["key"] for s in fixture["steps"]]
        assert set(actual) <= set(ref_keys), f"unknown step keys: {set(actual) - set(ref_keys)}"
        # relative order within the reference set must be preserved
        idxs = [ref_idx[k] for k in actual]
        assert idxs == sorted(idxs), "fixture steps out of reference order"

    def test_statuses_within_frozen_vocabulary(self, fixture):
        valid = {"ok", "link", "empty", "error"}
        for step in fixture["steps"]:
            assert step["status"] in valid

    def test_every_fixture_step_key_has_a_registered_adapter(self, fixture):
        from app.engine.orchestration.sources import ADAPTERS
        for step in fixture["steps"]:
            assert step["key"] in ADAPTERS, (
                f"fixture step '{step['key']}' has no source adapter registered")

    def test_correct_doc_type_mapping(self):
        """Every auto-fetchable fixture step maps to an engine DocumentType."""
        from app.engine.adapters import STEP_TO_DOC_TYPE
        for key in ("parcel", "appraiser", "deed", "plat", "flood", "benchmarks"):
            assert key in STEP_TO_DOC_TYPE


class TestRunnerMatchesReferenceSet:
    """The refactored runner must produce the same document set as the POC."""

    def test_runner_11_step_order(self, tmp_path, adapters, monkeypatch):
        from app.engine.orchestration import context as ctx_mod
        from app.engine.orchestration.runner import run_research
        from app.engine.orchestration.sources import ADAPTERS, FetchedSource, StepStatus

        class _Fake:
            def fetch(self, ctx, docs_dir):
                return FetchedSource(status=StepStatus.ok, summary="ok")

            def fallback(self, ctx, error=None):
                return FetchedSource(status=StepStatus.link, summary="link")

        folder = tmp_path / "jobs" / "A-1" / "research"
        monkeypatch.setattr(ctx_mod, "resolve_property_context",
                            lambda **kw: _make_ctx(folder))
        for key in list(ADAPTERS):
            ADAPTERS[key] = _Fake()

        result = run_research(address="1 Test St")
        assert [s.key for s in result.steps] == [d["key"] for d in RESIDENTIAL_DOCS]
        assert len(result.steps) == len(RESIDENTIAL_DOCS)


def _make_ctx(folder):
    from pathlib import Path as _P

    from app.engine.orchestration.context import PropertyContext, WarningBag
    from app.engine.orchestration.folders import save_json

    folder.mkdir(parents=True, exist_ok=True)
    ctx = PropertyContext(
        address="1 Test St", matched_address="1 Test St", lat=27.9, lon=-82.5,
        state="FL", state_fips="12", county="Hillsborough", county_fips="12057",
        geocoder="census", appraiser_url="https://pa.example.test/",
        parcel={"method": "arcgis-rest", "parcels": [], "address_match": False,
                "hints": {}},
        parcel_id="", parcel_ok=False, parcel_hints={},
        clerk_ref={"official_records_search": "https://clerk.example.test/or/",
                   "plat_search": "https://clerk.example.test/plat/"},
        job_number="A-1", order="ORD-1", name="A-1", folder=folder, appr={},
        warnings=WarningBag(),
    )
    ctx.manifest.append({**save_json(folder, "geocode.json", {}), "source": "x"})
    ctx.manifest.append({**save_json(folder, "parcel.json", {}), "source": "x"})
    ctx.manifest.append({**save_json(folder, "clerk_search_refs.json", {}), "source": "x"})
    return ctx


# ------------------------------------------------------------------- stable fields

class TestStableFrontendFields:
    """The exact fields the frontend already renders must keep meaning forever."""

    FROZEN_TOP = {
        "job_number", "order", "parcel_id", "address", "matched_address",
        "county", "county_fips", "state", "lat", "lon", "name", "geocoder",
        "map_links", "folder", "steps", "warnings",
    }
    FROZEN_STEP = {
        "key", "label", "requirement", "condition", "description", "summary",
        "status", "link", "link_label", "source_url", "saved_file", "data",
        "downloaded", "situs", "land_sqft", "land_acres", "address_match",
    }

    def test_frozen_top_fields_present_on_contract(self):
        model = ResearchResult.model_fields
        assert self.FROZEN_TOP <= set(model), (
            f"missing frozen top-level fields: {self.FROZEN_TOP - set(model)}")

    def test_frozen_step_fields_present_on_contract(self):
        model = StepResult.model_fields
        assert self.FROZEN_STEP <= set(model), (
            f"missing frozen step fields: {self.FROZEN_STEP - set(model)}")

    def test_status_field_type_is_step_status(self):
        from app.engine.contracts import StepStatus
        assert StepResult.model_fields["status"].annotation == StepStatus

    def test_required_flags_match_poc_fixture_values(self, fixture):
        requirements = {s["key"]: s["requirement"] for s in fixture["steps"]}
        # Check every reference doc that the (older) POC fixture actually
        # captured. Steps added to RESIDENTIAL_DOCS after the fixture was
        # saved (e.g. zoning) are intentionally absent and skipped.
        for d in RESIDENTIAL_DOCS:
            if d["key"] not in requirements:
                continue
            assert requirements[d["key"]] == d["requirement"]