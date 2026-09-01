"""Officer permissions never expand beyond the officer's location subtree."""

import pytest
from demo_users import VERIFIER
from sqlalchemy import select

pytestmark = pytest.mark.integration


def test_verifier_cannot_read_or_queue_another_villages_document(client, auth):
    from app.db import SessionLocal
    from app.models import Document, Location, Parcel, User, VerificationTask

    with SessionLocal() as session:
        verifier = session.execute(select(User).where(User.email == VERIFIER)).scalar_one()
        original_jurisdiction = verifier.jurisdiction_id
        own_village = session.execute(
            select(Location).where(Location.external_id == "LOC-VIL-01")
        ).scalar_one()
        outside_village = session.execute(
            select(Location).where(Location.external_id == "LOC-VIL-02")
        ).scalar_one()
        outside_document = session.execute(
            select(Document)
            .outerjoin(Parcel, Parcel.id == Document.parcel_id)
            .where(
                (Document.village_id == outside_village.id)
                | (Parcel.village_id == outside_village.id)
            )
            .limit(1)
        ).scalar_one()
        verifier.jurisdiction_id = own_village.id
        session.commit()

    try:
        response = client.get(
            f"/api/v1/documents/{outside_document.external_id}", headers=auth(VERIFIER)
        )
        assert response.status_code == 404

        queue = client.get("/api/v1/verifications", headers=auth(VERIFIER))
        assert queue.status_code == 200
        queued_ids = {item["document_id"] for item in queue.json()["tasks"]}

        with SessionLocal() as session:
            outside_task_ids = set(
                session.execute(
                    select(Document.external_id)
                    .join(VerificationTask, VerificationTask.document_id == Document.id)
                    .outerjoin(Parcel, Parcel.id == Document.parcel_id)
                    .where(
                        (Document.village_id == outside_village.id)
                        | (Parcel.village_id == outside_village.id)
                    )
                ).scalars()
            )
        assert not (queued_ids & outside_task_ids)
    finally:
        with SessionLocal() as session:
            verifier = session.execute(select(User).where(User.email == VERIFIER)).scalar_one()
            verifier.jurisdiction_id = original_jurisdiction
            session.commit()


def test_officer_without_jurisdiction_has_no_document_scope(client, auth):
    from app.db import SessionLocal
    from app.models import Document, User

    with SessionLocal() as session:
        verifier = session.execute(select(User).where(User.email == VERIFIER)).scalar_one()
        original_jurisdiction = verifier.jurisdiction_id
        document_id = session.execute(select(Document.external_id).limit(1)).scalar_one()
        verifier.jurisdiction_id = None
        session.commit()

    try:
        response = client.get(f"/api/v1/documents/{document_id}", headers=auth(VERIFIER))
        assert response.status_code == 404

        queue = client.get("/api/v1/verifications", headers=auth(VERIFIER))
        assert queue.status_code == 200
        assert queue.json()["count"] == 0
    finally:
        with SessionLocal() as session:
            verifier = session.execute(select(User).where(User.email == VERIFIER)).scalar_one()
            verifier.jurisdiction_id = original_jurisdiction
            session.commit()
