from types import SimpleNamespace

import pytest
from app.security import auth_state


@pytest.fixture(autouse=True)
def isolated_memory_state(monkeypatch):
    settings = SimpleNamespace(
        auth_state_redis_url=None,
        login_rate_limit_failures=3,
        login_rate_limit_ip_failures=10,
        login_rate_limit_window_seconds=60,
    )
    monkeypatch.setattr(auth_state, "get_settings", lambda: settings)
    auth_state.reset_memory_state()
    yield
    auth_state.reset_memory_state()


def test_failed_login_window_blocks_after_limit():
    for _ in range(3):
        auth_state.ensure_login_allowed("127.0.0.1", "person@example.test")
        auth_state.record_login_failure("127.0.0.1", "person@example.test")

    with pytest.raises(auth_state.LoginRateLimited):
        auth_state.ensure_login_allowed("127.0.0.1", "person@example.test")


def test_success_clears_only_the_account_pair():
    auth_state.record_login_failure("127.0.0.1", "person@example.test")
    auth_state.clear_login_failures("127.0.0.1", "person@example.test")
    auth_state.ensure_login_allowed("127.0.0.1", "person@example.test")


def test_refresh_token_can_only_be_consumed_once():
    expires = int(auth_state.time.time()) + 60
    auth_state.consume_refresh_token("token-id", expires)
    with pytest.raises(auth_state.RefreshTokenReplay):
        auth_state.consume_refresh_token("token-id", expires)
