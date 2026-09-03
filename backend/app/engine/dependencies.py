"""Auth/tenant dependencies for the research router.

Resolves the actor + tenant for a request.

Two modes:
  - Production: validate a Cognito JWT from the ``Authorization: Bearer``
    header (``COGNITO_*`` settings set). The actor id is the JWT ``sub``
    claim; the tenant id is resolved from the ``custom:tenant_id`` claim.
  - Local/dev: fall back to self-asserted ``X-Actor-Id`` / ``X-Tenant-Id``
    headers when no Cognito pool is configured, so the contract stays
    testable end-to-end without AWS.

During integration into the parent repo this can be swapped wholesale for
``app/modules/identity/dependencies.py`` (``get_current_user`` +
``get_current_tenant_id``); the signatures below are the seam.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

_bearer = HTTPBearer(auto_error=False)


def _jwt_auth_enabled() -> bool:
    return bool(
        settings.COGNITO_USER_POOL_ID
        and settings.COGNITO_REGION
        and settings.COGNITO_ISSUER
    )


def get_actor_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
) -> uuid.UUID:
    """Actor (user) id — Cognito JWT ``sub`` in production, header in dev."""
    # ---- production: validate the Cognito JWT ----------------------
    if _jwt_auth_enabled():
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.COGNITO_CLIENT_ID or "",
                algorithms=["RS256", "HS256"],
                issuer=settings.COGNITO_ISSUER,
                audience=settings.COGNITO_AUDIENCE,
            )
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from None
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
        request.state.cognito_payload = payload
        try:
            return uuid.UUID(sub)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid 'sub' in token") from None

    # ---- local/dev: header passthrough ------------------------------
    if not x_actor_id:
        raise HTTPException(status_code=401, detail="Missing X-Actor-Id")
    try:
        return uuid.UUID(x_actor_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Actor-Id") from None


def get_tenant_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> uuid.UUID:
    """Tenant id — Cognito ``custom:tenant_id`` claim in production, header in dev."""
    # ---- production: resolve tenant from the validated JWT ---------
    if _jwt_auth_enabled():
        payload = getattr(request.state, "cognito_payload", None)
        if payload is None:
            raise HTTPException(status_code=401, detail="Token not validated")
        tenant = payload.get("custom:tenant_id") or payload.get("tenant_id")
        if not tenant:
            raise HTTPException(status_code=401, detail="Token missing tenant claim")
        try:
            return uuid.UUID(str(tenant))
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid tenant id in token") from None

    # ---- local/dev: header passthrough ------------------------------
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-Id")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Tenant-Id") from None
