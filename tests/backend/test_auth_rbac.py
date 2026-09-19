"""Stage 2 step 9 gate: authentication and the §36 authorization matrix."""

import pytest
from demo_users import (
    ALL_USERS,
    CITIZEN_A,
    CITIZEN_B,
    DEMO_PASSWORD,
    DEO,
    TEHSILDAR,
    VERIFIER,
)

pytestmark = pytest.mark.integration


class TestAuthentication:
    def test_valid_login_returns_tokens(self, client):
        r = client.post("/api/v1/auth/login",
                        json={"email": CITIZEN_A, "password": DEMO_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert body["access_token"] and body["refresh_token"]
        assert body["token_type"] == "bearer"

    def test_wrong_password_is_rejected(self, client):
        r = client.post("/api/v1/auth/login",
                        json={"email": CITIZEN_A, "password": "not-the-password"})
        assert r.status_code == 401

    def test_unknown_email_and_wrong_password_are_indistinguishable(self, client):
        """Response must not reveal which emails are registered."""
        unknown = client.post("/api/v1/auth/login",
                              json={"email": "nobody@mrittika.demo", "password": "x"})
        wrong = client.post("/api/v1/auth/login",
                            json={"email": CITIZEN_A, "password": "x"})
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]

    def test_password_never_appears_in_any_response(self, client, auth):
        r = client.get("/api/v1/auth/me", headers=auth(CITIZEN_A))
        assert "password" not in r.text.lower()
        assert "argon2" not in r.text.lower()

    def test_endpoints_require_a_token(self, client):
        assert client.get("/api/v1/citizen/my-parcels").status_code == 401

    def test_garbage_token_is_rejected(self, client):
        r = client.get("/api/v1/citizen/my-parcels",
                       headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401

    def test_refresh_token_cannot_be_used_as_access_token(self, client):
        """Token-type confusion must be blocked."""
        login = client.post("/api/v1/auth/login",
                            json={"email": CITIZEN_A, "password": DEMO_PASSWORD})
        refresh = login.json()["refresh_token"]
        r = client.get("/api/v1/citizen/my-parcels",
                       headers={"Authorization": f"Bearer {refresh}"})
        assert r.status_code == 401

    def test_refresh_issues_a_working_access_token(self, client):
        login = client.post("/api/v1/auth/login",
                            json={"email": CITIZEN_A, "password": DEMO_PASSWORD})
        r = client.post("/api/v1/auth/refresh",
                        json={"refresh_token": login.json()["refresh_token"]})
        assert r.status_code == 200
        token = r.json()["access_token"]
        assert client.get("/api/v1/citizen/my-parcels",
                          headers={"Authorization": f"Bearer {token}"}).status_code == 200

    def test_refresh_token_is_single_use(self, client):
        login = client.post("/api/v1/auth/login",
                            json={"email": CITIZEN_A, "password": DEMO_PASSWORD})
        refresh = login.json()["refresh_token"]
        assert client.post("/api/v1/auth/refresh",
                           json={"refresh_token": refresh}).status_code == 200
        assert client.post("/api/v1/auth/refresh",
                           json={"refresh_token": refresh}).status_code == 401

    def test_logout_revokes_refresh_token(self, client):
        login = client.post("/api/v1/auth/login",
                            json={"email": CITIZEN_A, "password": DEMO_PASSWORD})
        refresh = login.json()["refresh_token"]
        assert client.post("/api/v1/auth/logout",
                           json={"refresh_token": refresh}).status_code == 204
        assert client.post("/api/v1/auth/refresh",
                           json={"refresh_token": refresh}).status_code == 401

    def test_failed_logins_are_rate_limited(self, client):
        from app.security.auth_state import reset_memory_state

        reset_memory_state()
        try:
            payload = {"email": "limited@mrittika.demo", "password": "wrong"}
            for _ in range(5):
                assert client.post("/api/v1/auth/login", json=payload).status_code == 401
            response = client.post("/api/v1/auth/login", json=payload)
            assert response.status_code == 429
            assert int(response.headers["Retry-After"]) >= 1
        finally:
            reset_memory_state()


class TestRoleAssignment:
    @pytest.mark.parametrize(
        "email,expected_role",
        [
            (CITIZEN_A, "CITIZEN"),
            (CITIZEN_B, "CITIZEN"),
            (DEO, "DEO"),
            (VERIFIER, "VERIFIER"),
            (TEHSILDAR, "TEHSILDAR"),
        ],
    )
    def test_role_comes_from_the_user_record(self, client, auth, email, expected_role):
        r = client.get("/api/v1/auth/me", headers=auth(email))
        assert r.status_code == 200
        assert r.json()["roles"] == [expected_role]

    def test_login_accepts_no_role_field(self, client):
        """§12 -- the role-selection screen is navigation only.

        A client claiming to be a TEHSILDAR must still be issued whatever role
        the database says. The field is ignored (extra input, not honoured).
        """
        r = client.post(
            "/api/v1/auth/login",
            json={"email": CITIZEN_A, "password": DEMO_PASSWORD, "role": "TEHSILDAR"},
        )
        assert r.status_code == 200
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        )
        assert me.json()["roles"] == ["CITIZEN"], "frontend-declared role was honoured!"

    def test_officers_have_a_jurisdiction_citizens_do_not(self, client, auth):
        for email in (DEO, VERIFIER, TEHSILDAR):
            assert client.get("/api/v1/auth/me",
                              headers=auth(email)).json()["jurisdiction_id"]
        for email in (CITIZEN_A, CITIZEN_B):
            assert client.get("/api/v1/auth/me",
                              headers=auth(email)).json()["jurisdiction_id"] is None


class TestPermissionMatrix:
    """§36, encoded. Each row is (permission, roles that must hold it)."""

    MATRIX = {
        "parcel:view_own": {CITIZEN_A, CITIZEN_B},
        "grievance:create": {CITIZEN_A, CITIZEN_B},
        "document:upload": {DEO},
        "document:enter_metadata": {DEO},
        "extraction:correct": {VERIFIER},
        "document:verify": {VERIFIER},
        "document:approve": {TEHSILDAR},
        "document:reject": {TEHSILDAR},
        "audit:view_full": {TEHSILDAR},
        "analytics:view": {TEHSILDAR},
        "integration:sync": {TEHSILDAR},
        # Shared across every role.
        "record:search_public": set(ALL_USERS),
        "gis:view": set(ALL_USERS),
    }

    @pytest.mark.parametrize("permission,holders", sorted(MATRIX.items()))
    def test_permission_is_held_by_exactly_the_right_roles(
        self, client, auth, permission, holders
    ):
        for email in ALL_USERS:
            granted = set(
                client.get("/api/v1/auth/me", headers=auth(email)).json()["permissions"]
            )
            should_have = email in holders
            assert (permission in granted) is should_have, (
                f"{email} {'should' if should_have else 'must not'} have {permission}"
            )

    def test_citizens_cannot_upload(self, client, auth):
        me = client.get("/api/v1/auth/me", headers=auth(CITIZEN_A)).json()
        assert "document:upload" not in me["permissions"]

    def test_no_role_can_both_verify_and_approve(self, client, auth):
        """Separation of duties: the verifier must not be the approver (§2)."""
        for email in ALL_USERS:
            perms = set(
                client.get("/api/v1/auth/me", headers=auth(email)).json()["permissions"]
            )
            assert not ({"document:verify", "document:approve"} <= perms), (
                f"{email} can both verify and approve"
            )


class TestOperationalEndpoints:
    def test_health(self, client):
        assert client.get("/health").json()["status"] == "ok"

    def test_ready_reports_extensions(self, client):
        body = client.get("/ready").json()
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["postgis"] == "ok"
        assert body["checks"]["pgvector"] == "ok"
        assert body["ready"] is True

    def test_ready_is_200_when_ready(self, client):
        assert client.get("/ready").status_code == 200

    def test_not_ready_is_a_503_not_a_200(self, client, monkeypatch):
        """Health checks read the status code; a 200 hid a dead database."""
        import app.main as main

        def unreachable():
            raise ConnectionError("database down")

        monkeypatch.setattr(main.engine, "connect", unreachable)
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["ready"] is False
