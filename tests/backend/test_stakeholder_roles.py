"""Read-only stakeholders: state and central oversight, survey, research.

They see progress at their own level of the hierarchy, can change nothing, and
research institutions get parcel data with nothing that identifies a person or
a plot.
"""

from __future__ import annotations

import csv
import io

import pytest
from demo_users import (
    CENTRAL_OFFICER,
    RESEARCHER,
    STAKEHOLDERS,
    STATE_OFFICER,
    SURVEYOR,
    TEHSILDAR,
)

pytestmark = pytest.mark.integration

#: Anything that changes a record, a document or what the model learns.
WRITES = {
    "document:upload", "document:start_processing", "extraction:correct",
    "document:verify", "document:approve", "document:reject", "document:return",
    "integration:sync", "grievance:review",
}


def me(client, auth, email):
    response = client.get("/api/v1/auth/me", headers=auth(email))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("email", STAKEHOLDERS)
def test_stakeholders_hold_no_write_permission(client, auth, email):
    assert not WRITES & set(me(client, auth, email)["permissions"])


@pytest.mark.parametrize("email", [STATE_OFFICER, CENTRAL_OFFICER, SURVEYOR])
def test_only_research_can_export(client, auth, email):
    assert client.get("/api/v1/research/export.csv", headers=auth(email)).status_code == 403


def progress(client, auth, email):
    response = client.get("/api/v1/dashboard/analytics", headers=auth(email))
    assert response.status_code == 200, response.text
    return response.json()["progress_by_location"]


def test_central_oversight_compares_states(client, auth):
    report = progress(client, auth, CENTRAL_OFFICER)
    assert report["levels"][:2] == ["COUNTRY", "STATE"]
    states = {r["name"] for r in report["rows"] if r["level"] == "STATE"}
    assert states == {"Uttar Pradesh", "Bihar"}


def test_a_state_officer_sees_only_their_state(client, auth):
    report = progress(client, auth, STATE_OFFICER)
    assert report["levels"][0] == "STATE"
    assert {r["name"] for r in report["rows"] if r["level"] == "STATE"} == {"Uttar Pradesh"}


def test_the_tehsildar_still_sees_only_their_district(client, auth):
    report = progress(client, auth, TEHSILDAR)
    assert "Bihar" not in {r["name"] for r in report["rows"]}


def test_a_stakeholder_cannot_decide_what_the_model_learns(client, auth):
    response = client.post("/api/v1/ai/feedback/any/review",
                           json={"decision": "ACCEPTED"}, headers=auth(STATE_OFFICER))
    assert response.status_code == 403


@pytest.fixture(scope="module")
def export(client, token_for):
    response = client.get("/api/v1/research/export.csv",
                          headers={"Authorization": f"Bearer {token_for(RESEARCHER)}"})
    assert response.status_code == 200, response.text
    return response.text


class TestResearchExport:
    def test_it_is_a_csv_of_exactly_the_anonymised_columns(self, export):
        from app.services.dashboard_service import RESEARCH_COLUMNS

        reader = csv.DictReader(io.StringIO(export))
        assert tuple(reader.fieldnames) == RESEARCH_COLUMNS
        assert sum(1 for _ in reader) > 0

    def test_it_names_no_person_and_no_plot(self, export):
        from app.db import SessionLocal
        from app.models import Owner

        with SessionLocal() as session:
            names = [o.name for o in session.query(Owner).all()]
        assert "PARCEL-" not in export
        assert not [n for n in names if n in export]

    def test_areas_are_coarsened(self, export):
        for row in csv.DictReader(io.StringIO(export)):
            if row["area_sqm"]:
                assert int(row["area_sqm"]) % 100 == 0

    def test_it_covers_both_states(self, export):
        states = {row["state"] for row in csv.DictReader(io.StringIO(export))}
        assert states == {"Uttar Pradesh", "Bihar"}

    def test_an_export_is_audited(self, client, auth):
        from app.db import SessionLocal
        from app.models import AuditEvent

        def count():
            with SessionLocal() as session:
                return session.query(AuditEvent).filter(
                    AuditEvent.action == "research.export").count()

        before = count()
        client.get("/api/v1/research/export.csv", headers=auth(RESEARCHER))
        assert count() == before + 1
