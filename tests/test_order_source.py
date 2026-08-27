"""Tests for the dev/standalone order source + doc-type validation.

``order_provider`` runs against the global SessionLocal (StaticPool in-memory
SQLite here), so it shares the ``test_db`` fixture's database — the same
pattern the service tests use.
"""
from __future__ import annotations

import uuid

import pytest

# Register the dev Order model on Base.metadata BEFORE create_all runs.
import app.engine.order_source  # noqa: F401
from app.engine.adapters import STEP_TO_DOC_TYPE
from app.engine.errors import InvalidDocTypesError
from app.engine.order_source import Order, order_provider, seed_dev_order
from app.engine.service import OrderData, ResearchService

TENANT = uuid.UUID("f0000000-0000-0000-0000-000000000001")
TENANT_2 = uuid.UUID("f0000000-0000-0000-0000-000000000002")
ACTOR = uuid.UUID("f0000000-0000-0000-0000-000000000003")
OTHER_ORDER = uuid.UUID("f0000000-0000-0000-0000-0000000000aa")


def test_seed_creates_row_and_provider_returns_order_data(test_db):
    order = seed_dev_order(
        test_db,
        tenant_id=TENANT,
        address_line_1="123 Main St",
        city="Lakeland",
        state="FL",
        county="Polk",
        parcel_id="262828612000000060",
        survey_type="Location Survey",
    )

    data = order_provider(order.id, TENANT)
    assert isinstance(data, OrderData)
    assert data.id == order.id
    assert data.address_line_1 == "123 Main St"
    assert data.city == "Lakeland"
    assert data.state == "FL"
    assert data.county == "Polk"
    assert data.parcel_id == "262828612000000060"
    assert data.survey_type == "Location Survey"


def test_provider_scopes_by_tenant(test_db):
    order = seed_dev_order(test_db, tenant_id=TENANT, address_line_1="9 Elm St")
    assert order_provider(order.id, TENANT_2) is None
    assert order_provider(uuid.uuid4(), TENANT) is None


def test_seed_is_idempotent_per_tenant_and_address(test_db):
    a = seed_dev_order(test_db, tenant_id=TENANT, address_line_1="5 Oak Ave")
    b = seed_dev_order(test_db, tenant_id=TENANT, address_line_1="5 Oak Ave")
    assert a.id == b.id
    rows = (
        test_db.query(Order)
        .filter(Order.tenant_id == TENANT)
        .count()
    )
    assert rows == 1


# ------------------------------------------------------------------ doc-type validation


def test_doc_type_aliases_normalized_to_canonical(test_db):
    svc = ResearchService(
        order_provider=lambda oid, tid: OrderData(id=oid, address_line_1="1 Main St")
    )
    job = svc.create_job(
        test_db,
        tenant_id=TENANT,
        actor_id=ACTOR,
        order_id=OTHER_ORDER,
        doc_types=["FLOOD", "PARCEL_RECORD", "deed", "benchmarks"],
        idempotency_key=None,
    )
    assert job.requested_doc_types == [
        "FEMA_FLOOD_ZONE_FIRM",
        "PARCEL_RECORD",
        "DEED_SUBJECT_PARCEL",
        "NGS_CONTROL",
    ]


def test_unknown_doc_types_rejected(test_db):
    svc = ResearchService(
        order_provider=lambda oid, tid: OrderData(id=oid, address_line_1="1 Main St")
    )
    with pytest.raises(InvalidDocTypesError):
        svc.create_job(
            test_db,
            tenant_id=TENANT,
            actor_id=ACTOR,
            order_id=OTHER_ORDER,
            doc_types=["NOT_A_DOC_TYPE"],
            idempotency_key=None,
        )


def test_every_step_key_maps_to_canonical_doc_type(test_db):
    svc = ResearchService(
        order_provider=lambda oid, tid: OrderData(id=oid, address_line_1="1 Main St")
    )
    aliases = list(STEP_TO_DOC_TYPE.keys()) + [s.upper() for s in STEP_TO_DOC_TYPE]
    job = svc.create_job(
        test_db,
        tenant_id=TENANT,
        actor_id=ACTOR,
        order_id=OTHER_ORDER,
        doc_types=aliases,
        idempotency_key=None,
    )
    assert set(job.requested_doc_types) == set(STEP_TO_DOC_TYPE.values())