"""AI usage limits protect the expensive provider boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.security import auth_state


@pytest.fixture(autouse=True)
def isolated_limits(monkeypatch):
    settings = SimpleNamespace(
        auth_state_redis_url=None,
        ai_query_rate_limit_user=2,
        ai_query_rate_limit_ip=3,
        ai_query_rate_limit_window_seconds=60,
        ai_query_daily_quota=10,
    )
    monkeypatch.setattr(auth_state, "get_settings", lambda: settings)
    auth_state.reset_memory_state()
    yield
    auth_state.reset_memory_state()


def test_user_limit_returns_retry_delay():
    auth_state.consume_ai_query("user-a", "127.0.0.1")
    auth_state.consume_ai_query("user-a", "127.0.0.1")

    with pytest.raises(auth_state.AiRateLimited) as error:
        auth_state.consume_ai_query("user-a", "127.0.0.1")

    assert 1 <= error.value.retry_after <= 60


def test_ip_limit_spans_users():
    auth_state.consume_ai_query("user-a", "127.0.0.1")
    auth_state.consume_ai_query("user-b", "127.0.0.1")
    auth_state.consume_ai_query("user-c", "127.0.0.1")

    with pytest.raises(auth_state.AiRateLimited):
        auth_state.consume_ai_query("user-d", "127.0.0.1")
