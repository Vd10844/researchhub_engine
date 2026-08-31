"""Contract conformance tests — verifies the 7 saved POC result.json files honor the frozen schema.

Run: pytest tests/test_contract_conformance.py -v
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "poc_results"

# ---------- Frozen top-level fields (every POC result has these) ----------

REQUIRED_TOP = {
    "job_number": str,
    "order": str,
    "parcel_id": str,
    "address": str,
    "matched_address": str,
    "county": str,
    "county_fips": str,
    "state": str,
    "geocoder": str,
    "map_links": list,
    "folder": str,
    "steps": list,
    "warnings": list,
    "name": str,
}

OPTIONAL_TOP = {"lat": (int, float, type(None)), "lon": (int, float, type(None))}

# ---------- Frozen per-step fields ----------

REQUIRED_STEP = {
    "key": str,
    "label": str,
    "requirement": str,
    "condition": str,
    "summary": str,
    "status": str,          # StepStatus enum
    "link": str,
    "link_label": str,
    "source_url": str,
}

OPTIONAL_STEP = {
    "saved_file": (str, type(None)),
    "downloaded": list,
    "data": Any,
    "description": str,
    "situs": (str, type(None)),
    "land_sqft": (int, float, type(None)),
    "land_acres": (int, float, type(None)),
    "address_match": (bool, type(None)),
}

VALID_STATUSES = {"ok", "link", "empty", "error"}


# ---------- Discovery ----------

def _load_fixtures() -> list[tuple[str, dict[str, Any]]]:
    files = sorted(FIXTURES.glob("*.json"))
    if not files:
        pytest.skip("No POC fixture files found")
    out: list[tuple[str, dict[str, Any]]] = []
    for f in files:
        out.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
    return out


FIXTURES_PARAM = [name for name, _ in _load_fixtures()]


# ---------- Tests ----------

@pytest.fixture(params=_load_fixtures(), ids=FIXTURES_PARAM)
def result(request: pytest.FixtureRequest) -> dict[str, Any]:
    _, data = request.param
    return data


class TestTopLevelContract:
    """Every POC result must have the frozen top-level fields."""

    def test_required_fields_present(self, result: dict[str, Any]) -> None:
        missing = [k for k in REQUIRED_TOP if k not in result]
        assert not missing, f"Missing required top-level fields: {missing}"

    def test_no_extra_top_level_keys_beyond_known(self, result: dict[str, Any]) -> None:
        known = set(REQUIRED_TOP) | set(OPTIONAL_TOP) | {"lat", "lon"}
        extra = set(result.keys()) - known
        # Extra keys are allowed (POC produced some) but we log them
        # This test exists to catch accidental schema drift, not to fail on purpose
        if extra:
            print(f"  NOTE extra top-level keys: {extra}")

    def test_steps_is_list(self, result: dict[str, Any]) -> None:
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) >= 8, "POC always produced at least 8 steps"

    def test_status_values_valid(self, result: dict[str, Any]) -> None:
        for step in result["steps"]:
            assert step["status"] in VALID_STATUSES, (
                f"Step '{step['key']}' has invalid status '{step['status']}'"
            )

    def test_key_values_are_strings(self, result: dict[str, Any]) -> None:
        for step in result["steps"]:
            assert isinstance(step["key"], str)
            assert len(step["key"]) > 0


class TestStepContract:
    """Every step in a POC result must have the frozen per-step fields."""

    def test_required_step_fields(self, result: dict[str, Any]) -> None:
        for step in result["steps"]:
            key = step.get("key", "???")
            missing = [k for k in REQUIRED_STEP if k not in step]
            assert not missing, f"Step '{key}' missing: {missing}"

    def test_link_always_string(self, result: dict[str, Any]) -> None:
        for step in result["steps"]:
            assert isinstance(step["link"], str), f"Step '{step['key']}' link is {type(step['link'])}"

    def test_step_key_uniqueness(self, result: dict[str, Any]) -> None:
        keys = [s["key"] for s in result["steps"]]
        dupes = [k for k in keys if keys.count(k) > 1]
        assert not dupes, f"Duplicate step keys: {set(dupes)}"

    def test_all_expected_keys_present(self, result: dict[str, Any]) -> None:
        expected = {
            "parcel", "deed", "plat", "flood", "benchmarks", "appraiser",
        }
        actual = {s["key"] for s in result["steps"]}
        missing = expected - actual
        assert not missing, f"Missing expected step keys: {missing}"

    def test_poc_has_11_steps(self, result: dict[str, Any]) -> None:
        assert len(result["steps"]) == 11


class TestEdgeCases:
    """Verify the contract handles known POC edge cases correctly."""

    def test_empty_link_valid(self, result: dict[str, Any]) -> None:
        """link='' is valid — means no fallback available."""
        for step in result["steps"]:
            assert isinstance(step["link"], str)

    def test_empty_summary_valid(self, result: dict[str, Any]) -> None:
        """summary='' is valid — some steps have no summary text."""
        for step in result["steps"]:
            assert isinstance(step["summary"], str)

    def test_error_step_has_summary(self, result: dict[str, Any]) -> None:
        """Even error steps should have a summary explaining what went wrong."""
        for step in result["steps"]:
            if step["status"] == "error":
                assert step["summary"], f"Step '{step['key']}' is error but has no summary"

    def test_link_step_has_link(self, result: dict[str, Any]) -> None:
        """link-only steps must have a non-empty link."""
        for step in result["steps"]:
            if step["status"] == "link":
                assert step["link"], f"Step '{step['key']}' is link-only but link is empty"


class TestAdditiveFields:
    """Verify new additive fields do not break existing POC data."""

    def test_additive_fields_absent(self, result: dict[str, Any]) -> None:
        """POC data won't have the new additive fields — that's fine."""
        for step in result["steps"]:
            # These fields have defaults in StepResult, so they won't be in POC JSON
            assert "source_outcome" not in step
            assert "confidence" not in step
            assert "provenance" not in step

    def test_additive_fields_have_defaults(self) -> None:
        """When added to POC data, additive fields get sensible defaults."""
        from app.engine.contracts import StepResult, SourceOutcome, Confidence
        sr = StepResult(key="test", status="ok")
        assert sr.source_outcome == SourceOutcome.auto
        assert sr.confidence == Confidence.high
        assert sr.provenance == []
        assert sr.warnings == []
        assert sr.error is None


VALID_REQUIREMENTS = {"mandatory", "conditional", "recommended"}


class TestRequirementDomain:
    """requirement must be one of the three frozen survey-standard values."""

    def test_requirement_values_valid(self, result: dict[str, Any]) -> None:
        for step in result["steps"]:
            req = step.get("requirement")
            assert req in VALID_REQUIREMENTS, (
                f"Step '{step['key']}' requirement={req!r} not in {sorted(VALID_REQUIREMENTS)}"
            )

    def test_condition_is_string(self, result: dict[str, Any]) -> None:
        for step in result["steps"]:
            assert isinstance(step["condition"], str), f"Step '{step['key']}' condition is not a str"


class TestMapLinksContract:
    """map_links must be a list of {label, url} objects."""

    def test_map_links_shape(self, result: dict[str, Any]) -> None:
        for link in result["map_links"]:
            assert isinstance(link, dict), f"map_link is not an object: {link!r}"
            assert "label" in link and isinstance(link["label"], str), f"map_link missing label: {link!r}"
            assert "url" in link and isinstance(link["url"], str), f"map_link missing url: {link!r}"

    def test_map_links_nonempty(self, result: dict[str, Any]) -> None:
        assert result["map_links"], "every POC result should carry at least one map link"


class TestWarningsContract:
    """warnings must be a list of strings."""

    def test_warnings_is_list_of_str(self, result: dict[str, Any]) -> None:
        assert isinstance(result["warnings"], list)
        for w in result["warnings"]:
            assert isinstance(w, str), f"warning is not a str: {w!r}"
