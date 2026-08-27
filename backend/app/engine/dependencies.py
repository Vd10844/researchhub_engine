"""Auth/tenant dependencies for the research router.

PLACEHOLDER implementation: resolves the actor + tenant from headers so the
contract is testable end-to-end. During integration into the parent repo,
replace the bodies with ``app/modules/identity/dependencies.py``
(``get_current_user`` + ``get_current_tenant_id``). The signatures stay.
"""
from __future__ import annotations

import uuid

from fastapi import Header, HTTPException


def get_actor_id(x_actor_id: str | None = Header(default=None, alias="X-Actor-Id")) -> uuid.UUID:
    """Actor (user) id. Parent resolves this from a Cognito JWT."""
    if not x_actor_id:
        raise HTTPException(status_code=401, detail="Missing X-Actor-Id")
    try:
        return uuid.UUID(x_actor_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Actor-Id")


def get_tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")) -> uuid.UUID:
    """Tenant id. Parent resolves this from auth/session middleware."""
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-Id")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Tenant-Id")