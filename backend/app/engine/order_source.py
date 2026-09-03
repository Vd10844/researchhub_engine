"""Dev/standalone order source for the engine.

The engine needs order context (address, county, state, parcel_id) to run
research. In the parent repo this data comes from ``app/modules/orders``
(``Order`` + ``OrderAddress``). This module is the engine's self-contained
stand-in so the standalone repo is runnable end-to-end on a fresh database:

  - ``Order``   — minimal ``orders`` table mirroring the parent's columns
    (same table name and column names so the parent's Alembic FK targets
    from revision 0001 resolve; the parent's real models replace this
    model wholesale at integration).
  - ``order_provider`` — the production callable injected into
    ``ResearchService``; reads ``Order`` and returns ``OrderData``.
  - ``seed_dev_order`` — idempotent dev seeding for the local E2E.

Integration note: swap ``order_provider`` for a reader over the parent's
models; the signature ``(order_id, tenant_id) -> OrderData`` stays.
"""
from __future__ import annotations

import uuid
from typing import ClassVar

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SessionLocal
from app.db.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin
from app.engine.service import OrderData


class Order(Base, TimestampMixin, AuditMixin, SoftDeleteMixin):
    """Stand-in for the parent's orders table (dev/standalone E2E)."""

    __tablename__ = "orders"
    __versioned__: ClassVar[dict] = {}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True, comment="Tenant isolation key."
    )
    order_number: Mapped[str | None] = mapped_column(
        nullable=True, comment="Human-facing order number."
    )

    address_line_1: Mapped[str] = mapped_column(nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(nullable=True)
    city: Mapped[str | None] = mapped_column(nullable=True)
    state: Mapped[str | None] = mapped_column(nullable=True)
    zip_code: Mapped[str | None] = mapped_column(nullable=True)
    county: Mapped[str | None] = mapped_column(nullable=True)
    parcel_id: Mapped[str | None] = mapped_column(nullable=True)
    lat: Mapped[float | None] = mapped_column(nullable=True)
    lon: Mapped[float | None] = mapped_column(nullable=True)
    survey_type: Mapped[str | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order {self.id} {self.address_line_1!r}>"


class Tenant(Base, TimestampMixin):
    """Stand-in for the parent's tenants table (dev/standalone E2E)."""

    __tablename__ = "tenants"
    __versioned__: ClassVar[dict] = {}


def order_provider(order_id: uuid.UUID, tenant_id: uuid.UUID) -> OrderData | None:
    """Production order provider: read a live ``orders`` row from the DB.

    Replaced at parent integration by a reader over ``app/modules/orders``
    (same columns). Tests monkeypatch ``app.engine.adapters.order_provider``
    so this path is only exercised by real deployments + the E2E.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(Order)
            .filter(
                Order.id == order_id,
                Order.tenant_id == tenant_id,
                Order.deleted_at.is_(None),
            )
            .first()
        )
        if row is None:
            return None
        return OrderData(
            id=row.id,
            address_line_1=row.address_line_1,
            address_line_2=row.address_line_2,
            city=row.city,
            state=row.state,
            zip_code=row.zip_code,
            county=row.county,
            parcel_id=row.parcel_id,
            lat=row.lat,
            lon=row.lon,
            survey_type=row.survey_type,
        )
    finally:
        db.close()


def seed_dev_order(
    db,
    *,
    tenant_id: uuid.UUID | None = None,
    address_line_1: str = "123 Main St",
    address_line_2: str | None = None,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
    county: str | None = None,
    parcel_id: str | None = None,
    survey_type: str | None = None,
) -> Order:
    """Insert (or return an existing) dev ``orders`` row for the E2E."""
    if tenant_id is None:
        tenant_id = uuid.uuid4()
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id)
        .first()
    )
    if tenant is None:
        db.add(Tenant(id=tenant_id))
        db.commit()
    row = (
        db.query(Order)
        .filter(
            Order.tenant_id == tenant_id,
            Order.address_line_1 == address_line_1,
            Order.deleted_at.is_(None),
        )
        .first()
    )
    if row is None:
        row = Order(
            tenant_id=tenant_id,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            state=state,
            zip_code=zip_code,
            county=county,
            parcel_id=parcel_id,
            survey_type=survey_type,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row
