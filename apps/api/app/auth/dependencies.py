"""FastAPI auth dependencies (§36).

Routers declare what a caller must be allowed to do; the enforcement lives
here. A router that forgets `Depends(require(...))` grants nothing by accident,
because `current_principal` alone confers no capability.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.repositories import user_repository
from app.security.tokens import TokenError, decode_token
from app.services.auth_service import Principal, build_principal

bearer_scheme = HTTPBearer(auto_error=False)
#: Other government systems authenticate with a key instead of a login. See
#: scripts/api_keys.py and models.ApiKey.
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_api_key(key: str) -> str:
    """SHA-256 is enough here: a key is 32 random bytes, not a password."""
    return hashlib.sha256(key.encode()).hexdigest()


def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_scheme),
    session: Session = Depends(get_session),
) -> Principal:
    """Resolve the caller from their token, or from an API key.

    The token supplies only a subject id. Role, permissions and owner link are
    re-read from the database every request, so nothing the client sends
    influences authority (§12). An API key resolves to its service user and
    is then exactly as authorized as that user.
    """
    if api_key:
        from app.models import ApiKey

        row = session.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key))
        ).scalar_one_or_none()
        user = user_repository.get_by_id(session, row.user_id) if row else None
        if row is None or row.revoked_at is not None or user is None or not user.is_active:
            raise CREDENTIALS_ERROR
        row.last_used_at = datetime.now(UTC)
        session.commit()
        return build_principal(session, user)

    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_ERROR
    try:
        payload = decode_token(credentials.credentials)
    except TokenError:
        raise CREDENTIALS_ERROR from None

    user = user_repository.get_by_id(session, payload["sub"])
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR

    return build_principal(session, user)


def require(*permissions: str) -> Callable[..., Principal]:
    """Dependency factory: caller must hold ALL the named permissions."""

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        missing = [p for p in permissions if not principal.has(p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission(s): {', '.join(sorted(missing))}",
            )
        return principal

    return dependency


def require_any(*permissions: str) -> Callable[..., Principal]:
    """Dependency factory: caller must hold AT LEAST ONE of the named permissions.

    Needed wherever a broader capability subsumes a narrower one. The tehsildar
    holds `audit:view_full` but not `audit:view_limited`, so a timeline
    endpoint demanding the narrower permission locked out the role with MORE
    authority -- which is the wrong way round.
    """

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not any(principal.has(p) for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(sorted(permissions))}",
            )
        return principal

    return dependency


def require_role(*roles: str) -> Callable[..., Principal]:
    """Dependency factory: caller must hold at least one of the named roles.

    Prefer `require(...)` with a permission; use this only where the concept is
    genuinely the role itself (e.g. 'the citizen portal').
    """

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not (set(roles) & principal.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(sorted(roles))}",
            )
        return principal

    return dependency
