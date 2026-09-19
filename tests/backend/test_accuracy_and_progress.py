"""Live extraction accuracy and geographic digitization progress (§11, §31).

Accuracy is asserted on documents staged under their own model version, so
the figure for that version is exactly the documents this test made -- the
shared database's other documents cannot move it. Progress is asserted as a
difference before and after, for the same reason.
"""

from __future__ import annotations

import uuid

import pytest
from demo_users import TEHSILDAR, VERIFIER
from staged_documents import (
    PARCEL,
    Field,
    approve,
    delete,
    finish_verification,
    principal,
    stage,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def session(client):
    from app.db import SessionLocal

    with SessionLocal() as s:
        yield s


@pytest.fixture
def version():
    """A model version no other document carries."""
    return f"x-test-{uuid.uuid4().hex[:8]}"


def fields(*extra: Field) -> list[Field]:
    return [
        Field("VILLAGE", "मुड़ियाकला", 0.96),
        Field("KHASRA", "142/2", 0.91),
        Field("AREA", "2.75", 0.58),
        *extra,
    ]


def accuracy_for(session, version: str) -> dict | None:
    from app.services import dashboard_service

    report = dashboard_service.extraction_accuracy(session, principal(session, TEHSILDAR))
    return next((r for r in report["by_model_version"] if r["model_version"] == version),
                None)


class TestExtractionAccuracy:
    def test_a_correction_counts_against_the_ai(self, session, version):
        document = stage(session, fields(), model_version=version)
        try:
            finish_verification(session, document, VERIFIER, corrections={"AREA": "2.5"})
            row = accuracy_for(session, version)
            assert (row["reviewed"], row["correct"]) == (3, 2)
            assert row["accuracy"] == pytest.approx(2 / 3, abs=1e-4)
        finally:
            delete(session, document)

    def test_correcting_to_the_same_value_is_not_an_error(self, session, version):
        document = stage(session, fields(), model_version=version)
        try:
            finish_verification(session, document, VERIFIER,
                                corrections={"KHASRA": " 142/2 "})
            assert accuracy_for(session, version)["accuracy"] == 1.0
        finally:
            delete(session, document)

    def test_a_document_still_in_verification_is_not_evidence(self, session, version):
        """AUTO_ACCEPTED on a page nobody has opened is unverified, not correct."""
        document = stage(session, fields(), model_version=version)
        try:
            assert accuracy_for(session, version) is None
        finally:
            delete(session, document)

    def test_an_illegible_field_is_not_judged(self, session, version):
        document = stage(
            session, fields(Field("OWNER", "?", 0.2, status="ILLEGIBLE")),
            model_version=version,
        )
        try:
            finish_verification(session, document, VERIFIER)
            assert accuracy_for(session, version)["reviewed"] == 3
        finally:
            delete(session, document)

    def test_the_tehsildar_dashboard_shows_it(self, client, auth):
        body = client.get("/api/v1/dashboard/tehsildar", headers=auth(TEHSILDAR)).json()
        accuracy = body["cards"]["extraction_accuracy"]
        assert accuracy is None or 0.0 <= accuracy <= 1.0
        assert isinstance(body["totals"]["accuracy_fields_reviewed"], int)

    def test_analytics_breaks_it_down_by_field(self, client, auth):
        report = client.get("/api/v1/dashboard/analytics",
                            headers=auth(TEHSILDAR)).json()["extraction_accuracy"]
        assert report["fields_reviewed"] == report["fields_correct"] + \
            report["fields_corrected"]
        assert sum(r["reviewed"] for r in report["by_field"]) == report["fields_reviewed"]


def progress(session, email=TEHSILDAR) -> dict:
    from app.services import dashboard_service

    return dashboard_service.progress_by_location(session, principal(session, email))


def row(report: dict, location_id: str) -> dict:
    return next(r for r in report["rows"] if r["location_id"] == location_id)


class TestProgressByLocation:
    def test_every_level_of_the_jurisdiction_is_reported(self, session):
        report = progress(session)
        # The demo tehsildar holds a district.
        assert report["levels"] == ["DISTRICT", "TEHSIL", "VILLAGE"]
        assert {r["level"] for r in report["rows"]} == set(report["levels"])

    def test_parents_are_the_sum_of_their_children(self, session):
        report = progress(session)
        for parent in (r for r in report["rows"] if r["level"] != "VILLAGE"):
            children = [r for r in report["rows"] if r["parent_id"] == parent["location_id"]]
            for key in ("documents", "approved", "parcels", "parcels_digitized"):
                assert parent[key] == sum(c[key] for c in children), (parent["name"], key)

    def test_stages_partition_the_documents(self, session):
        for r in progress(session)["rows"]:
            staged = sum(r[stage] for stage in progress(session)["stages"])
            assert staged <= r["documents"]

    def test_an_approval_moves_its_village_and_every_ancestor(self, session):
        from app.models import Location, Parcel
        from sqlalchemy import select

        village = session.execute(
            select(Location).join(Parcel, Parcel.village_id == Location.id)
            .where(Parcel.external_id == PARCEL)
        ).scalar_one()
        tehsil = session.get(Location, village.parent_id)
        district = session.get(Location, tehsil.parent_id)
        ids = [village.external_id, tehsil.external_id, district.external_id]

        before = progress(session)
        document = stage(session, fields())
        try:
            finish_verification(session, document, VERIFIER)
            approve(session, document, TEHSILDAR)
            after = progress(session)
            for location_id in ids:
                assert row(after, location_id)["documents"] == \
                    row(before, location_id)["documents"] + 1
                assert row(after, location_id)["approved"] == \
                    row(before, location_id)["approved"] + 1
        finally:
            delete(session, document)

    def test_a_tehsil_officer_gets_no_district_row(self, session):
        """A district row built from one tehsil's numbers would read as a
        district-wide figure. The verifier holds a tehsil."""
        report = progress(session, VERIFIER)
        assert "DISTRICT" not in report["levels"]
        assert report["levels"][0] == "TEHSIL"

    def test_analytics_includes_it(self, client, auth):
        body = client.get("/api/v1/dashboard/analytics", headers=auth(TEHSILDAR)).json()
        assert body["progress_by_location"]["rows"]
