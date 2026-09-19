"""Authentication endpoints (§55)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import current_principal
from app.db import get_session
from app.repositories import user_repository
from app.schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from app.security.auth_state import (
    LoginRateLimited,
    RefreshTokenReplay,
    clear_login_failures,
    consume_refresh_token,
    ensure_login_allowed,
    record_login_failure,
    revoke_refresh_token,
)
from app.security.tokens import REFRESH, TokenError, decode_token
from app.services.auth_service import (
    AuthenticationError,
    Principal,
    authenticate,
    issue_tokens,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    try:
        ensure_login_allowed(client_ip, payload.email)
    except LoginRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    try:
        user = authenticate(session, payload.email, payload.password)
    except AuthenticationError:
        record_login_failure(client_ip, payload.email)
        # One message for every failure mode: wrong password, unknown email and
        # disabled account must be indistinguishable to the caller.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None
    clear_login_failures(client_ip, payload.email)
    return TokenResponse(**issue_tokens(user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, session: Session = Depends(get_session)) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type=REFRESH)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from None

    try:
        consume_refresh_token(claims["jti"], claims["exp"])
    except RefreshTokenReplay:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has already been used",
        ) from None

    user = user_repository.get_by_id(session, claims["sub"])
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user"
        )
    return TokenResponse(**issue_tokens(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest) -> Response:
    try:
        claims = decode_token(payload.refresh_token, expected_type=REFRESH)
    except TokenError:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    revoke_refresh_token(claims["jti"], claims["exp"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(current_principal)) -> MeResponse:
    return MeResponse(
        user_id=principal.user.external_id,
        email=principal.user.email,
        full_name=principal.user.full_name,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
        jurisdiction_id=principal.jurisdiction_id,
        owner_id=principal.owner_id,
    )


@router.put("/push-token", status_code=status.HTTP_204_NO_CONTENT)
def set_push_token(
    token: str | None = Body(
        None, embed=True, max_length=255, pattern=r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]+\]$"
    ),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> Response:
    """Register this phone for push notifications; null (or no token) clears it.

    Only an Expo push token is accepted: anything else stored here would be
    sent to Expo on every notification and rejected every time.
    """
    principal.user.push_token = token
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
