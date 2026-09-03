"""Contract-drift gate — makes the API freeze real (validation-plan 0.4).

The committed ``contracts/openapi.json`` + ``contracts/schemas/*.json`` are the
source of truth that frontend/backend teams code against. Editing ``schemas.py``
or the router without re-exporting silently squad-shifts that contract. This
test regenerates the contract from the live app into a scratch dir and diffs it
against the committed files, so a drift fails CI instead of shipping.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "scripts" / "export_contracts.py"
CONTRACTS = ROOT / "contracts"


def _export_contracts(out_dir: Path) -> None:
    """Regenerate the contract into ``out_dir`` (exit 0 => success)."""
    proc = subprocess.run(
        [sys.executable, str(EXPORT), str(out_dir)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"export_contracts failed:\n{proc.stdout}\n{proc.stderr}"


def _load_committed(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_generated(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_openapi_contract_not_drifted(tmp_path):
    out = tmp_path / "gen"
    out.mkdir()
    _export_contracts(out)

    committed = CONTRACTS / "openapi.json"
    generated = out / "openapi.json"

    assert committed.exists(), "committed contracts/openapi.json is missing"
    assert generated.exists(), "export did not produce openapi.json"

    c = _load_committed(committed)
    g = _load_generated(generated)

    # Compare paths + per-path operation shapes, and the component schemas.
    assert c.get("paths") == g.get("paths"), (
        "API contract drifted — run scripts/export_contracts.py and commit the result"
    )
    assert c.get("components", {}).get("schemas") == g.get("components", {}).get("schemas"), (
        "Component schemas drifted — run scripts/export_contracts.py and commit"
    )


def test_every_committed_schema_matches_live(tmp_path):
    out = tmp_path / "gen"
    out.mkdir()
    _export_contracts(out)

    committed_schemas = sorted((CONTRACTS / "schemas").glob("*.json"))
    assert committed_schemas, "no committed schema files found"

    for committed in committed_schemas:
        generated = out / "schemas" / committed.name
        assert generated.exists(), f"live schema for {committed.name} is missing (renamed?)"
        assert _load_committed(committed) == _load_generated(generated), (
            f"contracts/schemas/{committed.name} is stale — run scripts/export_contracts.py"
        )


def test_no_orphan_committed_schema(tmp_path):
    """A committed schema file with no live counterpart is a sign of a renamed/enum change."""
    out = tmp_path / "gen"
    out.mkdir()
    _export_contracts(out)

    live_names = {p.name for p in (out / "schemas").glob("*.json")}
    for committed in (CONTRACTS / "schemas").glob("*.json"):
        assert committed.name in live_names, (
            f"contracts/schemas/{committed.name} has no live counterpart (renamed/deleted?)"
        )
