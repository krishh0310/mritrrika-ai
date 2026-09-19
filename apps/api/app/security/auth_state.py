"""Distributed login throttling and refresh-token replay protection.

Docker/production uses Redis so every API worker shares one security state.
Development without ``AUTH_STATE_REDIS_URL`` uses the same semantics in memory;
that keeps tests and the offline demo usable without pretending a per-process
store is suitable for a multi-worker deployment.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from app.config.settings import get_settings

_lock = threading.Lock()
_attempts: dict[str, tuple[int, float]] = {}
_usage: dict[str, tuple[int, float]] = {}
_consumed_tokens: dict[str, float] = {}


@dataclass
class LoginRateLimited(Exception):
    retry_after: int


class RefreshTokenReplay(Exception):
    pass


@dataclass
class AiRateLimited(Exception):
    retry_after: int


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redis():
    url = get_settings().auth_state_redis_url
    if not url:
        return None
    from redis import Redis

    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _attempt_keys(client_ip: str, email: str) -> tuple[tuple[str, int], ...]:
    settings = get_settings()
    normalized_email = email.strip().casefold()
    return (
        (f"auth:fail:ip:{_digest(client_ip)}", settings.login_rate_limit_ip_failures),
        (
            f"auth:fail:pair:{_digest(f'{client_ip}|{normalized_email}')}",
            settings.login_rate_limit_failures,
        ),
    )


def ensure_login_allowed(client_ip: str, email: str) -> None:
    """Reject a key whose fixed failure window is already exhausted."""
    backend = _redis()
    now = time.monotonic()
    for key, limit in _attempt_keys(client_ip, email):
        if backend is not None:
            value = backend.get(key)
            if value is not None and int(value) >= limit:
                raise LoginRateLimited(max(1, backend.ttl(key)))
            continue
        with _lock:
            count, expires = _attempts.get(key, (0, 0.0))
            if expires <= now:
                _attempts.pop(key, None)
            elif count >= limit:
                raise LoginRateLimited(max(1, int(expires - now)))


def record_login_failure(client_ip: str, email: str) -> None:
    settings = get_settings()
    backend = _redis()
    now = time.monotonic()
    for key, _limit in _attempt_keys(client_ip, email):
        if backend is not None:
            count = backend.incr(key)
            if count == 1:
                backend.expire(key, settings.login_rate_limit_window_seconds)
            continue
        with _lock:
            count, expires = _attempts.get(key, (0, 0.0))
            if expires <= now:
                count = 0
                expires = now + settings.login_rate_limit_window_seconds
            _attempts[key] = (count + 1, expires)


def clear_login_failures(client_ip: str, email: str) -> None:
    """Clear only the account/IP pair after a successful authentication."""
    pair_key = _attempt_keys(client_ip, email)[1][0]
    backend = _redis()
    if backend is not None:
        backend.delete(pair_key)
        return
    with _lock:
        _attempts.pop(pair_key, None)


def consume_refresh_token(jti: str, expires_at: int) -> None:
    """Atomically mark a refresh token used; a second use is a replay."""
    ttl = max(1, expires_at - int(time.time()))
    key = f"auth:refresh:used:{_digest(jti)}"
    backend = _redis()
    if backend is not None:
        if not backend.set(key, "1", ex=ttl, nx=True):
            raise RefreshTokenReplay
        return

    now = time.time()
    with _lock:
        for token, expiry in list(_consumed_tokens.items()):
            if expiry <= now:
                _consumed_tokens.pop(token, None)
        if key in _consumed_tokens:
            raise RefreshTokenReplay
        _consumed_tokens[key] = float(expires_at)


def revoke_refresh_token(jti: str, expires_at: int) -> None:
    """Idempotently prevent a refresh token from being used after sign-out."""
    try:
        consume_refresh_token(jti, expires_at)
    except RefreshTokenReplay:
        pass


def consume_ai_query(user_id: str, client_ip: str) -> None:
    """Consume per-user, per-IP and daily AI allowance atomically per key."""
    settings = get_settings()
    limits = (
        (
            f"ai:minute:user:{_digest(user_id)}",
            settings.ai_query_rate_limit_user,
            settings.ai_query_rate_limit_window_seconds,
        ),
        (
            f"ai:minute:ip:{_digest(client_ip)}",
            settings.ai_query_rate_limit_ip,
            settings.ai_query_rate_limit_window_seconds,
        ),
        (
            f"ai:day:user:{_digest(user_id)}",
            settings.ai_query_daily_quota,
            86_400,
        ),
    )
    backend = _redis()
    now = time.monotonic()

    for key, limit, window in limits:
        if backend is not None:
            count = backend.incr(key)
            if count == 1:
                backend.expire(key, window)
            if count > limit:
                raise AiRateLimited(max(1, backend.ttl(key)))
            continue

        with _lock:
            count, expires = _usage.get(key, (0, 0.0))
            if expires <= now:
                count, expires = 0, now + window
            count += 1
            _usage[key] = (count, expires)
            if count > limit:
                raise AiRateLimited(max(1, int(expires - now)))


def reset_memory_state() -> None:
    """Test helper; production Redis state is deliberately untouched."""
    with _lock:
        _attempts.clear()
        _usage.clear()
        _consumed_tokens.clear()
