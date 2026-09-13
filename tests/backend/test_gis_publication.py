"""The view GeoServer publishes is an authorization boundary (§17, §18).

GeoServer cannot evaluate this application's permissions. It has no principal,
cannot check `gis:view`, and cannot scope to a jurisdiction -- it serves
whatever its database role can read, to whoever reaches it. What keeps that
safe is entirely the shape of `gis_published_parcels` and the grants on the
role that reads it.

So the tests here are not about GeoServer. They pin the boundary, and they keep
passing whether or not a GeoServer container has ever been started.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.db import SessionLocal  # noqa: E402

VIEW = "gis_published_parcels"

#: Exactly what may be published. Adding to this list is a deliberate act that
#: has to change this test AND a migration -- which is the point.
PUBLISHED_COLUMNS = {
    "id", "parcel_id", "village_id", "village_name", "village_name_devanagari",
    "khasra_number", "khata_number", "area_value", "area_unit", "land_class",
    "is_synthetic", "notice", "geometry",
}


@pytest.fixture(scope="module")
def session():
    with SessionLocal() as s:
        yield s


class TestTheViewExists:
    def test_the_view_is_present(self, session):
        assert session.execute(
            text("SELECT to_regclass(:v)"), {"v": VIEW}
        ).scalar() is not None

    def test_it_publishes_something(self, session):
        assert session.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar() > 0


class TestNothingPrivateIsPublished:
    def _columns(self, session) -> set[str]:
        return {
            row[0] for row in session.execute(
                text("SELECT column_name FROM information_schema.columns "
                     "WHERE table_name = :v"),
                {"v": VIEW},
            )
        }

    def test_the_column_set_is_exactly_the_allowlist(self, session):
        """A new column reaching the public layer must break a test first."""
        assert self._columns(session) == PUBLISHED_COLUMNS

    def test_no_ownership_is_published(self, session):
        """The failure mode is one GetFeature away: outputFormat=csv."""
        leaked = [
            c for c in self._columns(session)
            if "owner" in c or "guardian" in c or "citizen" in c or "aadhaar" in c
        ]
        assert not leaked, leaked

    def test_no_internal_ai_signal_is_published(self, session):
        """§17 -- confidence and anomaly scores are officer-only."""
        leaked = [
            c for c in self._columns(session)
            if "confidence" in c or "anomaly" in c or "score" in c or "state" in c
        ]
        assert not leaked, leaked


class TestOnlyApprovedRecordsAppear:
    def test_every_published_parcel_has_an_approved_record(self, session):
        orphans = session.execute(text(f"""
            SELECT count(*) FROM {VIEW} v
            WHERE NOT EXISTS (
                SELECT 1 FROM land_records r
                WHERE r.parcel_id = v.id AND r.status = 'APPROVED'
            )
        """)).scalar()
        assert orphans == 0

    def test_parcels_without_an_approved_record_are_withheld(self, session):
        """The count must be a filter, not the whole table by coincidence."""
        withheld = session.execute(text("""
            SELECT count(*) FROM parcels p
            WHERE p.geometry IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM land_records r
                  WHERE r.parcel_id = p.id AND r.status = 'APPROVED'
              )
        """)).scalar()
        published = session.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar()
        total = session.execute(
            text("SELECT count(*) FROM parcels WHERE geometry IS NOT NULL")
        ).scalar()
        assert published + withheld == total


class TestGeometryIsUsable:
    def test_every_geometry_carries_the_pinned_srid(self, session):
        """An unset SRID makes GeoServer serve the cadastre off West Africa."""
        wrong = session.execute(
            text(f"SELECT count(*) FROM {VIEW} WHERE ST_SRID(geometry) <> 4326")
        ).scalar()
        assert wrong == 0

    def test_every_published_row_has_a_geometry(self, session):
        assert session.execute(
            text(f"SELECT count(*) FROM {VIEW} WHERE geometry IS NULL")
        ).scalar() == 0

    def test_the_synthetic_notice_travels_with_every_feature(self, session):
        """A WFS consumer must not be able to mistake this for real data."""
        assert session.execute(
            text(f"SELECT count(*) FROM {VIEW} WHERE notice IS NULL "
                 "OR is_synthetic IS NOT TRUE")
        ).scalar() == 0
