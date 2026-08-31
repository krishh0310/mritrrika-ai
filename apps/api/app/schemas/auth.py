"""Auth request/response shapes."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    # NOTE: there is deliberately no `role` field. The role-selection screen
    # (§12/§58) is navigation only; authority comes from the user record.


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]
    jurisdiction_id: str | None = None
    #: Present for citizens only, and informational -- the server never accepts
    #: this value back as an input (§62).
    owner_id: str | None = None
    is_synthetic: bool = True
