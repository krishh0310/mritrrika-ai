"""Authentication endpoints (§55)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import current_principal
from app.db import get_session
from app.repositories import user_repository
from app.schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from app.security.tokens import REFRESH, TokenError, decode_token
from app.services.auth_service import (
    AuthenticationError,
    Principal,
    authenticate,
    issue_tokens,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    try:
        user = authenticate(session, payload.email, payload.password)
    except AuthenticationError:
        # One message for every failure mode: wrong password, unknown email and
        # disabled account must be indistinguishable to the caller.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None
    return TokenResponse(**issue_tokens(user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, session: Session = Depends(get_session)) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type=REFRESH)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from None

    user = user_repository.get_by_id(session, claims["sub"])
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user"
        )
    return TokenResponse(**issue_tokens(user))


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
