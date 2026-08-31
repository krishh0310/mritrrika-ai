"""FastAPI auth dependencies (§36).

Routers declare what a caller must be allowed to do; the enforcement lives
here. A router that forgets `Depends(require(...))` grants nothing by accident,
because `current_principal` alone confers no capability.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.repositories import user_repository
from app.security.tokens import TokenError, decode_token
from app.services.auth_service import Principal, build_principal

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> Principal:
    """Resolve the caller from their token.

    The token supplies only a subject id. Role, permissions and owner link are
    re-read from the database every request, so nothing the client sends
    influences authority (§12).
    """
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
