"""Vector search over approved records, in pgvector (§10)."""

from __future__ import annotations

import pytest
from demo_users import CITIZEN_A, RESEARCHER

pytestmark = pytest.mark.integration


def search(client, auth, q, email=CITIZEN_A):
    response = client.get("/api/v1/records/semantic-search", params={"q": q},
                          headers=auth(email))
    assert response.status_code == 200, response.text
    return response.json()["results"]


def described(parcel_id: str) -> str:
    """A description of a parcel in the words its record uses."""
    from app.db import SessionLocal
    from app.models import Parcel

    with SessionLocal() as s:
        p = s.query(Parcel).filter(Parcel.external_id == parcel_id).one()
        return f"Mudiyakala khasra {p.khasra_number} khata {p.khata_number}"


def test_the_nearest_record_comes_first(client, auth):
    top = search(client, auth, described("PARCEL-UP-DEMO-0181"))[0]
    assert top["parcel_id"] == "PARCEL-UP-DEMO-0181"


def test_it_tolerates_a_misspelt_place(client, auth):
    """OCR and transliteration mangle names; shared spelling still ranks."""
    results = search(client, auth, "Mudiyakla")
    assert results[0]["village_id"] == "LOC-VIL-02"


def test_it_returns_public_fields_only(client, auth):
    row = search(client, auth, "irrigated")[0]
    assert set(row) == {
        "parcel_id", "khasra_number", "khata_number", "village", "village_id",
        "area_value", "area_unit", "land_class", "similarity", "is_synthetic",
    }


def test_owner_names_are_never_indexed(client):
    from app.db import SessionLocal
    from app.models import Embedding, Owner

    with SessionLocal() as s:
        names = [o.name for o in s.query(Owner).all()]
        contents = [e.content for e in s.query(Embedding).all()]
    assert contents
    assert not [n for n in names for c in contents if n in c]


def test_only_approved_records_are_found(client, auth):
    from app.db import SessionLocal
    from app.models import LandRecord, Parcel

    with SessionLocal() as s:
        record = s.query(LandRecord).join(Parcel).filter(
            Parcel.external_id == "PARCEL-UP-DEMO-0181").first()
        record.status = "PENDING"
        s.commit()
    try:
        ids = [r["parcel_id"] for r in
               search(client, auth, described("PARCEL-UP-DEMO-0181"))]
        assert "PARCEL-UP-DEMO-0181" not in ids
    finally:
        with SessionLocal() as s:
            s.merge(record).status = "APPROVED"
            s.commit()


def test_it_needs_the_public_search_permission(client, auth):
    response = client.get("/api/v1/records/semantic-search", params={"q": "x y"},
                          headers=auth(RESEARCHER))
    assert response.status_code == 403
