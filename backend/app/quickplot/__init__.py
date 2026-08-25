"""QuickPlot — the Mapperty-styled order + research hub layer (API v2).

Importing this package registers the ORM models on `db.Base`, so `db.init_db()` creates the
`qp_*` tables. `router` is mounted by app.main.
"""
from . import models  # noqa: F401 — import for the side effect of registering the tables
from .router import router  # noqa: F401

__all__ = ["models", "router"]
