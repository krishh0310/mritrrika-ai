"""Grievance lifecycle and authorization (§19, §36).

The interesting assertions are the negative ones: a citizen must not be able to
file against a parcel they do not hold, read someone else's grievance, or drive
the review workflow.
"""

from __future__ import annotations

import pytest
from demo_users import CITIZEN_A, CITIZEN_B, DEO, TEHSILDAR, VERIFIER


def _my_parcel(client, auth, email: str) -> str:
    response = client.get("/api/v1/citizen/my-parcels", headers=auth(email))
    assert response.status_code == 200
    parcels = response.json()["parcels"]
    assert parcels, f"{email} has no seeded parcels"
    return parcels[0]["parcel_id"]


def _file(client, auth, email: str, **form) -> object:
    payload = {"issue_type": "INCORRECT_AREA", "description": "Recorded area looks wrong."}
    payload.update(form)
    return client.post("/api/v1/grievances", headers=auth(email), data=payload)


class TestFiling:
    def test_citizen_can_file_against_own_parcel(self, client, auth):
        parcel_id = _my_parcel(client, auth, CITIZEN_A)
        response = _file(client, auth, CITIZEN_A, parcel_id=parcel_id)
        assert response.status_code == 201, response.text

        body = response.json()
        assert body["grievance_id"].startswith("GRV-")
        assert body["status"] == "SUBMITTED"
        assert body["parcel_id"] == parcel_id
        assert body["is_synthetic"] is True

    def test_citizen_can_file_without_a_parcel(self, client, auth):
        response = _file(
            client, auth, CITIZEN_A,
            issue_type="DOCUMENT_NOT_FOUND",
            description="I cannot find my 1998 record.",
        )
        assert response.status_code == 201
        assert response.json()["parcel_id"] is None

    def test_citizen_cannot_file_against_another_citizens_parcel(self, client, auth):
        """§62 -- and the refusal must not confirm the parcel exists."""
        other_parcel = _my_parcel(client, auth, CITIZEN_B)
        response = _file(client, auth, CITIZEN_A, parcel_id=other_parcel)
        assert response.status_code == 403

    def test_unknown_parcel_is_indistinguishable_from_forbidden(self, client, auth):
        response = _file(client, auth, CITIZEN_A, parcel_id="PARCEL-DOES-NOT-EXIST")
        assert response.status_code == 403

    def test_unknown_issue_type_is_rejected(self, client, auth):
        response = _file(client, auth, CITIZEN_A, issue_type="NOT_A_REAL_TYPE")
        assert response.status_code == 422

    def test_blank_description_is_rejected(self, client, auth):
        response = _file(client, auth, CITIZEN_A, description="   ")
        assert response.status_code == 422

    @pytest.mark.parametrize("email", [DEO, VERIFIER, TEHSILDAR])
    def test_officers_cannot_file_grievances(self, client, auth, email):
        """§36 -- grievance submission is Citizen-only."""
        assert _file(client, auth, email).status_code == 403


class TestReading:
    def test_me_returns_only_the_callers_own(self, client, auth):
        _file(client, auth, CITIZEN_A)
        _file(client, auth, CITIZEN_B)

        response = client.get("/api/v1/grievances/me", headers=auth(CITIZEN_A))
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == len(body["grievances"])

        b_response = client.get("/api/v1/grievances/me", headers=auth(CITIZEN_B))
        a_ids = {g["grievance_id"] for g in body["grievances"]}
        b_ids = {g["grievance_id"] for g in b_response.json()["grievances"]}
        assert not (a_ids & b_ids), "citizens are seeing each other's grievances"

    def test_citizen_cannot_read_another_citizens_grievance(self, client, auth):
        created = _file(client, auth, CITIZEN_B).json()["grievance_id"]
        response = client.get(f"/api/v1/grievances/{created}", headers=auth(CITIZEN_A))
        # 404 not 403: a citizen must not learn which grievance ids exist.
        assert response.status_code == 404

    def test_citizen_cannot_see_the_review_queue(self, client, auth):
        assert client.get("/api/v1/grievances", headers=auth(CITIZEN_A)).status_code == 403

    def test_tehsildar_sees_the_review_queue(self, client, auth):
        _file(client, auth, CITIZEN_A)
        response = client.get("/api/v1/grievances", headers=auth(TEHSILDAR))
        assert response.status_code == 200
        assert response.json()["count"] >= 1

    def test_verifier_has_limited_review_access(self, client, auth):
        """§36 gives the verifier `grievance:review_limited` -- read, not decide."""
        assert client.get("/api/v1/grievances", headers=auth(VERIFIER)).status_code == 200


class TestLifecycle:
    def test_tehsildar_advances_a_grievance(self, client, auth):
        grievance_id = _file(client, auth, CITIZEN_A).json()["grievance_id"]

        response = client.post(
            f"/api/v1/grievances/{grievance_id}/status",
            headers=auth(TEHSILDAR),
            json={"status": "UNDER_REVIEW"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "UNDER_REVIEW"

        response = client.post(
            f"/api/v1/grievances/{grievance_id}/status",
            headers=auth(TEHSILDAR),
            json={"status": "RESOLVED", "note": "Area corrected in mutation 44."},
        )
        assert response.status_code == 200
        assert response.json()["resolution_note"] == "Area corrected in mutation 44."

    def test_a_closed_grievance_cannot_be_reopened(self, client, auth):
        grievance_id = _file(client, auth, CITIZEN_A).json()["grievance_id"]
        for target in ("UNDER_REVIEW", "RESOLVED"):
            client.post(
                f"/api/v1/grievances/{grievance_id}/status",
                headers=auth(TEHSILDAR), json={"status": target},
            )
        response = client.post(
            f"/api/v1/grievances/{grievance_id}/status",
            headers=auth(TEHSILDAR), json={"status": "UNDER_REVIEW"},
        )
        assert response.status_code == 409

    def test_submitted_cannot_jump_straight_to_resolved(self, client, auth):
        grievance_id = _file(client, auth, CITIZEN_A).json()["grievance_id"]
        response = client.post(
            f"/api/v1/grievances/{grievance_id}/status",
            headers=auth(TEHSILDAR), json={"status": "RESOLVED"},
        )
        assert response.status_code == 409

    def test_citizen_cannot_change_their_own_grievance_status(self, client, auth):
        grievance_id = _file(client, auth, CITIZEN_A).json()["grievance_id"]
        response = client.post(
            f"/api/v1/grievances/{grievance_id}/status",
            headers=auth(CITIZEN_A), json={"status": "RESOLVED"},
        )
        assert response.status_code == 403

    def test_verifier_cannot_close_a_grievance(self, client, auth):
        """Limited review is read-only; only `grievance:review` decides (§36)."""
        grievance_id = _file(client, auth, CITIZEN_A).json()["grievance_id"]
        response = client.post(
            f"/api/v1/grievances/{grievance_id}/status",
            headers=auth(VERIFIER), json={"status": "REJECTED"},
        )
        assert response.status_code == 403


class TestAudit:
    def test_filing_appends_to_the_audit_chain(self, client, auth):
        grievance_id = _file(client, auth, CITIZEN_A).json()["grievance_id"]
        response = client.get("/api/v1/audit/verify", headers=auth(TEHSILDAR))
        assert response.status_code == 200
        assert response.json()["valid"] is True, (
            f"chain broke after filing {grievance_id}"
        )
