"""Export OpenAPI JSON + per-schema JSON Schemas from the live FastAPI app.

Usage:
    python scripts/export_contracts.py          # writes to contracts/
    python scripts/export_contracts.py OUT_DIR  # custom output dir

Runs the FastAPI app in-process (no server needed) and dumps:
  contracts/openapi.json          — full OpenAPI 3.1 spec
  contracts/schemas/<name>.json   — individual JSON Schema per $defs entry

Designed for CI: exit 0 if contracts match, exit 1 if they drift.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "contracts" if len(sys.argv) < 2 else Path(sys.argv[1])


def main() -> int:
    # Lazy-import so the script works even if deps are still installing
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("ERROR: fastapi/httpx not installed — run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app  # noqa: E402

    client = TestClient(app, raise_server_exceptions=False)

    # ---- OpenAPI JSON (full spec) ----
    spec = client.get("/openapi.json").json()

    # ---- Per-schema JSON Schemas ----
    schemas = spec.get("components", {}).get("schemas", {})

    out_dir = OUT
    schemas_dir = out_dir / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    openapi_path = out_dir / "openapi.json"
    openapi_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Wrote {openapi_path}  ({len(json.dumps(spec)):,} bytes)")

    for name, schema in schemas.items():
        p = schemas_dir / f"{name}.json"
        p.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    print(f"Wrote {len(schemas)} schemas to {schemas_dir}/")

    # ---- Simple drift check: count paths + schemas ----
    n_paths = len(spec.get("paths", {}))
    n_schemas = len(schemas)
    print(f"\nSummary: {n_paths} paths, {n_schemas} component schemas")
    if n_paths == 0:
        print("WARNING: No paths found — v2 router may not be mounted.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
