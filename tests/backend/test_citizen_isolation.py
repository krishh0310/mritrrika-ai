"""§72 -- THE non-negotiable security gate.

Citizen A must never reach Citizen B's private parcel data, through any
endpoint, by any parameter, in any encoding.

This file is deliberately adversarial. It does not merely check the happy path
works; it tries the specific attacks that a naive implementation permits:
supplying someone else's owner_id, guessing parcel ids, probing 403-vs-404 to
enumerate, and reading internal fields that citizens must never see (§17).
"""

import pytest
from demo_users import CITIZEN_A, CITIZEN_B, DEO, TEHSILDAR, VERIFIER

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def parcels_of(client, token_for):
    """Each citizen's own parcel ids, read from their own session."""
    cache: dict[str, list[str]] = {}

    def _get(email: str) -> list[str]:
        if email not in cache:
            r = client.get(
                "/api/v1/citizen/my-parcels",
                headers={"Authorization": f"Bearer {token_for(email)}"},
            )
            assert r.status_code == 200, r.text
            cache[email] = [p["parcel_id"] for p in r.json()["parcels"]]
        return cache[email]

    return _get


class TestSetupIsMeaningful:
    """If the two citizens shared parcels, every isolation test below would
    pass vacuously."""

    def test_both_citizens_hold_land(self, parcels_of):
        assert parcels_of(CITIZEN_A), "citizen A holds nothing"
        assert parcels_of(CITIZEN_B), "citizen B holds nothing"

    def test_their_holdings_are_disjoint(self, parcels_of):
        overlap = set(parcels_of(CITIZEN_A)) & set(parcels_of(CITIZEN_B))
        assert not overlap, f"citizens share parcels {overlap}"

    def test_dashboards_differ(self, client, auth):
        a = client.get("/api/v1/citizen/dashboard", headers=auth(CITIZEN_A)).json()
        b = client.get("/api/v1/citizen/dashboard", headers=auth(CITIZEN_B)).json()
        assert a["citizen_name"] != b["citizen_name"]
        assert (a["parcel_count"], a["total_area"]) != (b["parcel_count"], b["total_area"])


class TestOwnAccessWorks:
    def test_citizen_a_can_read_own_parcels(self, client, auth, parcels_of):
        for parcel_id in parcels_of(CITIZEN_A):
            r = client.get(f"/api/v1/citizen/parcels/{parcel_id}", headers=auth(CITIZEN_A))
            assert r.status_code == 200, f"{parcel_id}: {r.status_code}"

    def test_citizen_b_can_read_own_parcels(self, client, auth, parcels_of):
        for parcel_id in parcels_of(CITIZEN_B):
            r = client.get(f"/api/v1/citizen/parcels/{parcel_id}", headers=auth(CITIZEN_B))
            assert r.status_code == 200, f"{parcel_id}: {r.status_code}"


class TestCrossCitizenAccessIsRefused:
    """The core of §72."""

    def test_a_cannot_read_b_parcel_detail(self, client, auth, parcels_of):
        for parcel_id in parcels_of(CITIZEN_B):
            r = client.get(f"/api/v1/citizen/parcels/{parcel_id}", headers=auth(CITIZEN_A))
            assert r.status_code == 403, f"LEAK: A read B's {parcel_id}"

    def test_b_cannot_read_a_parcel_detail(self, client, auth, parcels_of):
        for parcel_id in parcels_of(CITIZEN_A):
            r = client.get(f"/api/v1/citizen/parcels/{parcel_id}", headers=auth(CITIZEN_B))
            assert r.status_code == 403, f"LEAK: B read A's {parcel_id}"

    def test_a_cannot_read_b_ownership_history(self, client, auth, parcels_of):
        for parcel_id in parcels_of(CITIZEN_B):
            r = client.get(
                f"/api/v1/citizen/parcels/{parcel_id}/ownership-history",
                headers=auth(CITIZEN_A),
            )
            assert r.status_code == 403, f"LEAK: A read history of {parcel_id}"

    def test_a_cannot_query_historical_owners_of_b_parcel(self, client, auth, parcels_of):
        """The 'who owned this in 1998' path must be scoped too."""
        for parcel_id in parcels_of(CITIZEN_B):
            r = client.get(
                f"/api/v1/citizen/parcels/{parcel_id}/owners-on",
                params={"on": "1998-12-31"},
                headers=auth(CITIZEN_A),
            )
            assert r.status_code == 403, f"LEAK: A read 1998 owners of {parcel_id}"

    def test_refused_responses_carry_no_parcel_data(self, client, auth, parcels_of):
        """A 403 must not leak the very data it refuses."""
        target = parcels_of(CITIZEN_B)[0]
        body = client.get(
            f"/api/v1/citizen/parcels/{target}", headers=auth(CITIZEN_A)
        ).text
        for leaked in ("khasra", "area_value", "land_class", "owner"):
            assert leaked not in body.lower(), f"403 body leaked {leaked!r}"


class TestForgedIdentityIsIgnored:
    """§62 -- the server derives owner identity; it never accepts one."""

    def test_owner_id_query_parameter_is_ignored(self, client, auth, token_for):
        """`?owner_id=` must not widen or change the caller's scope."""
        baseline = client.get("/api/v1/citizen/my-parcels", headers=auth(CITIZEN_A)).json()

        b_owner = client.get("/api/v1/auth/me", headers=auth(CITIZEN_B)).json()["owner_id"]
        forged = client.get(
            "/api/v1/citizen/my-parcels",
            params={"owner_id": b_owner},
            headers=auth(CITIZEN_A),
        ).json()

        assert forged == baseline, "owner_id parameter changed the caller's scope!"

    def test_owner_id_in_body_is_ignored(self, client, auth):
        b_owner = client.get("/api/v1/auth/me", headers=auth(CITIZEN_B)).json()["owner_id"]
        baseline = client.get("/api/v1/citizen/dashboard", headers=auth(CITIZEN_A)).json()
        forged = client.request(
            "GET", "/api/v1/citizen/dashboard",
            json={"owner_id": b_owner}, headers=auth(CITIZEN_A),
        ).json()
        assert forged == baseline

    def test_another_users_token_grants_only_their_own_scope(
        self, client, auth, parcels_of
    ):
        """Sanity: the isolation is per-token, not global."""
        a_parcel = parcels_of(CITIZEN_A)[0]
        assert client.get(
            f"/api/v1/citizen/parcels/{a_parcel}", headers=auth(CITIZEN_A)
        ).status_code == 200
        assert client.get(
            f"/api/v1/citizen/parcels/{a_parcel}", headers=auth(CITIZEN_B)
        ).status_code == 403


class TestNoEnumeration:
    def test_unknown_parcel_is_indistinguishable_from_unauthorized(
        self, client, auth, parcels_of
    ):
        """403 for both, so a citizen cannot map which parcel ids exist."""
        unauthorized = client.get(
            f"/api/v1/citizen/parcels/{parcels_of(CITIZEN_B)[0]}", headers=auth(CITIZEN_A)
        )
        nonexistent = client.get(
            "/api/v1/citizen/parcels/PARCEL-UP-DEMO-9999", headers=auth(CITIZEN_A)
        )
        assert unauthorized.status_code == nonexistent.status_code == 403
        assert unauthorized.json()["detail"] == nonexistent.json()["detail"]

    @pytest.mark.parametrize(
        "probe",
        [
            "PARCEL-UP-DEMO-0142%00",          # NUL byte -- once reached psycopg as a 500
            "' OR '1'='1",                      # SQL metacharacters
            "%2e%2e%2fPARCEL-UP-DEMO-0181",     # encoded traversal
            "<script>alert(1)</script>",
            "PARCEL-UP-DEMO-0142%0A",          # encoded newline (raw one cannot be sent)
            "A" * 200,                          # length
        ],
    )
    def test_malformed_parcel_ids_never_succeed(self, client, auth, probe):
        """Malformed input must be refused cleanly -- never a 500, never a hit."""
        r = client.get(f"/api/v1/citizen/parcels/{probe}", headers=auth(CITIZEN_A))
        assert r.status_code in (403, 404, 422), f"probe {probe!r} returned {r.status_code}"
        assert r.status_code < 500, f"probe {probe!r} caused a server error"

    def test_path_traversal_cannot_bypass_authorization(self, client, auth, parcels_of):
        """A traversal segment normalises to a plain lookup -- which must STILL
        be authorized. Pointed at B's parcel, A must be refused."""
        target = parcels_of(CITIZEN_B)[0]
        r = client.get(
            f"/api/v1/citizen/parcels/PARCEL-UP-DEMO-0181/../{target}",
            headers=auth(CITIZEN_A),
        )
        assert r.status_code == 403, f"traversal reached B's parcel: {r.status_code}"


class TestInternalFieldsAreHidden:
    """§17 -- citizens must never see pipeline internals."""

    FORBIDDEN_KEYS = (
        "raw_value", "ocr_confidence", "extraction_confidence", "final_confidence",
        "confidence_breakdown", "anomaly", "verification_note", "model_version",
        "password_hash", "storage_key",
    )

    def test_parcel_detail_exposes_no_internals(self, client, auth, parcels_of):
        body = client.get(
            f"/api/v1/citizen/parcels/{parcels_of(CITIZEN_A)[0]}", headers=auth(CITIZEN_A)
        ).text.lower()
        for key in self.FORBIDDEN_KEYS:
            assert key not in body, f"citizen response exposed {key!r}"

    def test_my_parcels_exposes_no_internals(self, client, auth):
        body = client.get("/api/v1/citizen/my-parcels", headers=auth(CITIZEN_A)).text.lower()
        for key in self.FORBIDDEN_KEYS:
            assert key not in body, f"citizen response exposed {key!r}"

    def test_responses_are_marked_synthetic(self, client, auth):
        """§83 -- no screenshot may be mistaken for real citizen data."""
        assert client.get(
            "/api/v1/citizen/my-parcels", headers=auth(CITIZEN_A)
        ).json()["is_synthetic"] is True


class TestOfficersCannotUseCitizenPortal:
    """Officers have their own routes; 'My Land' is not one of them (§36)."""

    @pytest.mark.parametrize("email", [DEO, VERIFIER, TEHSILDAR])
    def test_officer_denied_my_parcels(self, client, auth, email):
        assert client.get("/api/v1/citizen/my-parcels", headers=auth(email)).status_code == 403

    @pytest.mark.parametrize("email", [DEO, VERIFIER, TEHSILDAR])
    def test_officer_denied_citizen_dashboard(self, client, auth, email):
        assert client.get("/api/v1/citizen/dashboard", headers=auth(email)).status_code == 403
