"""Postgres migration round-trip + model/migration parity (validation-plan 0.3).

The offline SQLite suite silently no-ops things that matter on Postgres: enum
``ALTER TYPE ... ADD VALUE`` (0003), row locking, real JSONB. This tier runs the
Alembic chain against a REAL Postgres to prove:

  1. ``upgrade head`` applies cleanly on Postgres,
  2. ``downgrade base`` reverse-applies cleanly (every down_revision works),
  3. ``upgrade head`` again is idempotent,
  4. the ORM models still match the migration chain (autogenerate produces an
     EMPTY diff — a column added to models.py but never migrated fails here).

It targets a dedicated scratch database so it NEVER touches the dev ``researchhub``
db. Gated by ``@pytest.mark.pg`` (run with ``-m pg``), and the actual alembic run
happens in a subprocess so the shared in-memory SQLite ``app.db`` import is irrelevant.

Requires a reachable Postgres. Configure the host/port via ``PG_HOST`` / ``PG_PORT``
env or the defaults below (defaults match the engine's docker-compose).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5433")

MIG_USER = os.environ.get("PG_MIGRATION_USER", "postgres")
MIG_PASS = os.environ.get("PG_MIGRATION_PASSWORD", "postgres")
MIG_DB = os.environ.get("PG_MIGRATION_DB", "researchhub_migtest")

URL = f"postgresql+psycopg://{MIG_USER}:{MIG_PASS}@{PG_HOST}:{PG_PORT}/{MIG_DB}"

pytestmark = pytest.mark.pg


def _alembic(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, DATABASE_URL=URL, RUN_ENV="test")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )


def test_pg_migration_upgrade_roundtrip():
    # Fresh state: ensure we're at the true base first (in case a prior run left
    # it mid-chain). This is a scratch DB, so destructive ops are fine.
    _alembic("downgrade", "base")

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, f"upgrade head failed:\n{up.stdout}\n{up.stderr}"

    down = _alembic("downgrade", "base")
    assert down.returncode == 0, f"downgrade base failed:\n{down.stdout}\n{down.stderr}"

    up2 = _alembic("upgrade", "head")
    assert up2.returncode == 0, f"second upgrade head failed:\n{up2.stdout}\n{up2.stderr}"


def test_pg_models_match_migrations():
    """After upgrade head, autogenerate must produce an EMPTY diff."""
    prep = _alembic("downgrade", "base")
    assert prep.returncode == 0
    up = _alembic("upgrade", "head")
    assert up.returncode == 0

    env = dict(os.environ, DATABASE_URL=URL, RUN_ENV="test")
    gen = subprocess.run(
        [sys.executable, "-m", "alembic", "revision", "--autogenerate",
         "--rev-id", "zz_parity_probe", "-m", "parity"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    # autogenerate ALWAYS writes a revision file; a clean model/manifest emits only
    # the no-op `pass`. We detect drift by looking for real op() calls in the probe.
    probe = (ROOT / "backend" / "alembic" / "versions").glob("*zz_parity_probe*.py")
    files = list(probe)
    try:
        if not files:
            assert False, f"parity probe not written; autogenerate errored:\n{gen.stdout}\n{gen.stderr}"
        text = files[0].read_text(encoding="utf-8")
        # A real divergence emits op() calls; a clean one has `pass` in the upgrade body.
        import re as _re

        body = _re.search(r"def upgrade\(\):.*?(?=def downgrade)", text, _re.S)
        drifted = body is not None and any(
            line.strip().startswith(("op.", "with op.")) and not line.strip().startswith(("op.bulk",))
            for line in body.group(0).splitlines()
        )
        assert not drifted, (
            "models drifted from migrations — autogenerate produced schema ops. "
            f"probe body:\n{text}\noutput:\n{gen.stdout}"
        )
    finally:
        for f in files:
            f.unlink()  # clean up the probe regardless
