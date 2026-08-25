"""Demo seeding — one realistic order so the QuickPlot UI has something to open on a
fresh install. Idempotent: re-seeding returns the existing order instead of duplicating it.

This is a convenience for the POC/demo, not part of the product surface. Point it at a real
Florida address so "Start Research" actually exercises the live pipeline.
"""
from __future__ import annotations

import datetime

from sqlalchemy import select

from ..db import SessionLocal
from . import research
from .locker import audit
from .models import Order, _now, iso

SEED_ORDER_NO = "123-45"


def _days(n: int) -> datetime.datetime:
    return _now() + datetime.timedelta(days=n)


def seed(org_id: str = "default", actor: str = "Olivia Reed") -> dict:
    with SessionLocal() as s:
        existing = s.execute(
            select(Order).where(Order.org_id == org_id, Order.order_no == SEED_ORDER_NO)
        ).scalars().first()
        if existing:
            return {"created": False, "order": existing.as_dict()}

        o = Order(
            org_id=org_id,
            order_no=SEED_ORDER_NO,
            title="Oakmont Elevation",
            order_type="Boundary Survey",
            survey_type="Residential Land Survey",
            stage="placed",
            research_state="not_started",
            # A real, resolvable parcel in a fully-wired county, verified end to end:
            # the parcel, appraiser record card, plat, FEMA flood and NGS control all
            # auto-fetch for this address, so "Start Research" demonstrates the real pipeline.
            address="1015 E Palmetto St, Lakeland, FL 33801",
            city="Lakeland", county="Polk", county_fips="12105", state="FL", postal="33801",
            parcel_id="242819216500002011",
            client={"name": "Aron Smith", "role": "Realtor",
                    "email": "aron@mail.com", "phone": "+1 123 456 7980"},
            access_contact={"name": "John Doe", "phone": "+1 987 654 3210"},
            buyer_owner="Mary Joe",
            lender="SBI Bank",
            title_company="Dan Surveyors",
            underwriter="ICICI",
            client_notes="Lender needs the flood determination and the recorded plat with the "
                         "survey. Confirm the rear easement before the field visit.",
            legal_description="Lot 11, Block 2, of the recorded subdivision plat for this "
                              "parcel, Public Records of Polk County, Florida. Confirmed "
                              "against the plat auto-fetched from the Clerk.",
            scope_tags=["Structures / Improvements", "Easements"],
            received_at=_days(-3),
            due_at=_days(4),
            created_by=actor,
            researcher="Owen Ranford",
        )
        now = _now()
        o.stage_dates = {"created": iso(now - datetime.timedelta(days=3)),
                         "placed": iso(now - datetime.timedelta(days=3))}
        s.add(o)
        s.flush()
        audit(s, org_id=org_id, order_id=o.id, scope="order", action="order_created",
              title="Order created",
              subtitle="Residential Land Survey · 123-45 — routed to the assigned team.",
              actor=actor)
        audit(s, org_id=org_id, order_id=o.id, scope="order",
              action="order_details_captured", title="Order details captured",
              subtitle="Client, property, scope and team recorded on intake.", actor=actor)
        audit(s, org_id=org_id, order_id=o.id, scope="order", action="quote_sent",
              title="Quote sent",
              subtitle="$2,485.00 · 10 line items sent to aron@mail.com.", actor=actor)
        research.ensure_sources(s, o)
        s.commit()
        return {"created": True, "order": o.as_dict()}
