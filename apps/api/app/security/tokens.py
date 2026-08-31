"""JWT issue/verify (§61).

The token carries the user id and nothing security-relevant beyond it. Roles
are re-read from the database on every request rather than trusted from the
token, so a revoked role takes effect immediately and a forged claim buys
nothing (§12: never trust frontend role selection).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config.settings import get_settings

ACCESS = "access"
REFRESH = "refresh"


class TokenError(Exception):
    """Raised for any invalid, expired or wrong-type token."""


def _create(subject: str, token_type: str, expires: timedelta,
            extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    return _create(
        user_id, ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
        extra,
    )


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    return _create(user_id, REFRESH, timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str = ACCESS) -> dict[str, Any]:
    """Decode and validate. Raises TokenError on anything suspect.

    The algorithm is pinned to the configured one: accepting the token's own
    `alg` header would allow the classic 'alg: none' and HS/RS confusion
    attacks.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise TokenError(
            f"expected a {expected_type} token, got {payload.get('type')!r}"
        )
    return payload
