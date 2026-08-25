"""Shared pytest fixtures for the QuickPlot API suite.

Every test runs against a throwaway SQLite database and a throwaway blob store, so the
suite never touches the developer's real jobs/ or evidence/ directories. The env vars are
set *before* app.config is imported, because that module resolves paths at import time.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="qp_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["QP_STORAGE_ROOT"] = str(_TMP / "blob")
os.environ["SURVEY_JOBS_DIR"] = str(_TMP / "jobs")
os.environ["SURVEY_EVIDENCE_DIR"] = str(_TMP / "evidence")
os.environ["QP_DEFAULT_ORG"] = "default"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def api(client):
    """A thin wrapper that always sends the tenant + actor headers."""

    class Api:
        H = {"X-Org-Id": "default", "X-Actor": "QA Bot"}

        def get(self, path, **kw):
            return client.get("/api/v2" + path, headers=self.H, **kw)

        def post(self, path, **kw):
            return client.post("/api/v2" + path, headers=self.H, **kw)

        def patch(self, path, **kw):
            return client.patch("/api/v2" + path, headers=self.H, **kw)

        def delete(self, path, **kw):
            return client.delete("/api/v2" + path, headers=self.H, **kw)

        def as_org(self, org):
            other = Api()
            other.H = {"X-Org-Id": org, "X-Actor": "Other Tenant"}
            return other

    return Api()


MINIMAL_ORDER = {
    "order_no": "T-100",
    "title": "Test Order",
    "address": "1015 E Palmetto St, Lakeland, FL 33801",
    "city": "Lakeland", "county": "Polk", "county_fips": "12105", "state": "FL",
}


@pytest.fixture
def order(api):
    """A freshly created order, unique per test."""
    import uuid

    body = {**MINIMAL_ORDER, "order_no": "T-" + uuid.uuid4().hex[:6]}
    r = api.post("/orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


PDF_BYTES = (b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\n2 0 obj<</Type /Page>>endobj\n"
             b"trailer<</Root 1 0 R>>\n%%EOF")


@pytest.fixture
def doc(api, order):
    """One uploaded, typed, unlocked document on `order`."""
    r = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("Deed.pdf", PDF_BYTES, "application/pdf")},
                 data={"doc_type": "deed"})
    assert r.status_code == 201, r.text
    return r.json()["documents"][0]


ALL_CHECKS = {"legible": True, "matches_parcel": True, "source_recorded": True}
