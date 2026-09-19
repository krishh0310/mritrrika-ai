"""Email and push notification channels, and API keys for other systems."""

from __future__ import annotations

import secrets
from types import SimpleNamespace

import pytest
from demo_users import CITIZEN_A, DEO

pytestmark = pytest.mark.integration

SETTINGS = SimpleNamespace(
    smtp_host="smtp.example", smtp_sender="noreply@mrittika.demo", smtp_port=587,
    smtp_username=None, smtp_password=None, smtp_starttls=True,
    expo_push_enabled=True, expo_access_token=None,
)


def template():
    from app.services.notification_service import TEMPLATES

    return TEMPLATES["record_approved"]


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def send_message(self, message):
        FakeSMTP.sent.append(message)


class TestEmailAndPush:
    def test_email_carries_the_lock_screen_safe_text(self, monkeypatch):
        import smtplib

        from app.services.notification_service import EmailProvider

        FakeSMTP.sent = []
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        delivery = EmailProvider("smtp.example", "noreply@x").send(
            "ram@x", template(), {"reference": "DOC-1"})
        assert delivery.delivered and delivery.channel == "email"
        message = FakeSMTP.sent[0]
        assert message["To"] == "ram@x"
        assert "DOC-1" in message.get_content()

    def test_expo_rejection_in_a_200_body_is_not_a_delivery(self, monkeypatch):
        import httpx
        from app.services.notification_service import ExpoPushProvider, NotificationError

        monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
            200, json={"data": {"status": "error", "message": "DeviceNotRegistered"}},
            request=httpx.Request("POST", "https://exp.host")))
        with pytest.raises(NotificationError, match="DeviceNotRegistered"):
            ExpoPushProvider().send("ExponentPushToken[x]", template(), {"reference": "D"})

    def test_both_channels_go_out_and_a_failure_is_reported_not_raised(self, monkeypatch):
        import smtplib

        import httpx
        from app.services.notification_service import extra_channels

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
            503, json={}, request=httpx.Request("POST", "https://exp.host")))
        user = SimpleNamespace(email="ram@x", push_token="ExponentPushToken[abc]")
        results = {d.channel: d.delivered for d in
                   extra_channels(user, template(), {"reference": "D"}, settings=SETTINGS)}
        assert results == {"email": True, "push": False}

    def test_nothing_is_attempted_when_unconfigured(self):
        from app.services.notification_service import extra_channels

        off = SimpleNamespace(**{**vars(SETTINGS), "smtp_host": None})
        user = SimpleNamespace(email="ram@x", push_token=None)
        assert extra_channels(user, template(), {"reference": "D"}, settings=off) == []


class TestPushTokenEndpoint:
    def test_register_and_clear(self, client, auth):
        from app.db import SessionLocal
        from app.models import User

        def stored():
            with SessionLocal() as s:
                return s.query(User).filter(User.email == CITIZEN_A).one().push_token

        token = "ExponentPushToken[abc123]"
        assert client.put("/api/v1/auth/push-token", json={"token": token},
                          headers=auth(CITIZEN_A)).status_code == 204
        assert stored() == token
        client.put("/api/v1/auth/push-token", json={"token": None}, headers=auth(CITIZEN_A))
        assert stored() is None

    def test_anything_but_an_expo_token_is_refused(self, client, auth):
        response = client.put("/api/v1/auth/push-token", json={"token": "hello"},
                              headers=auth(CITIZEN_A))
        assert response.status_code == 422


@pytest.fixture
def api_key(client):
    """A live key for the LRMS service account, removed afterwards."""
    from app.auth.dependencies import hash_api_key
    from app.db import SessionLocal
    from app.models import ApiKey, User

    key = "mk_" + secrets.token_urlsafe(32)
    with SessionLocal() as s:
        user = s.query(User).filter(User.email == "lrms-service@mrittika.demo").one()
        row = ApiKey(name="test", prefix=key[:11], key_hash=hash_api_key(key), user_id=user.id)
        s.add(row)
        s.commit()
        row_id = row.id
    yield key, row_id
    with SessionLocal() as s:
        s.query(ApiKey).filter(ApiKey.id == row_id).delete()
        s.commit()


class TestApiKeys:
    def test_a_key_acts_as_its_service_user(self, client, api_key):
        me = client.get("/api/v1/auth/me", headers={"X-API-Key": api_key[0]}).json()
        assert me["roles"] == ["INTEGRATION"]
        assert "integration:sync" in me["permissions"]

    def test_it_can_use_the_lrms_api_and_nothing_else(self, client, api_key):
        headers = {"X-API-Key": api_key[0]}
        assert client.get("/api/v1/integrations/lrms/sync", headers=headers).status_code == 200
        assert client.get("/api/v1/dashboard/deo", headers=headers).status_code == 403

    def test_use_is_recorded(self, client, api_key):
        from app.db import SessionLocal
        from app.models import ApiKey

        client.get("/api/v1/auth/me", headers={"X-API-Key": api_key[0]})
        with SessionLocal() as s:
            assert s.get(ApiKey, api_key[1]).last_used_at is not None

    def test_a_wrong_key_is_refused(self, client):
        response = client.get("/api/v1/auth/me", headers={"X-API-Key": "mk_nope"})
        assert response.status_code == 401

    def test_a_revoked_key_is_refused(self, client, api_key):
        from datetime import UTC, datetime

        from app.db import SessionLocal
        from app.models import ApiKey

        with SessionLocal() as s:
            s.get(ApiKey, api_key[1]).revoked_at = datetime.now(UTC)
            s.commit()
        assert client.get("/api/v1/auth/me",
                          headers={"X-API-Key": api_key[0]}).status_code == 401

    def test_bearer_login_still_works(self, client, auth):
        assert client.get("/api/v1/auth/me", headers=auth(DEO)).status_code == 200
