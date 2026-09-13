"""published parcels view for external GIS consumption

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-13 15:40:00.000000

GeoServer does not speak this application's authorization. It cannot evaluate
`gis:view`, it cannot scope to a tehsildar's jurisdiction, and it has no notion
of a principal at all -- it serves whatever table it is pointed at, to whoever
reaches it.

So it is never pointed at `parcels`. It is pointed at this view, which is the
authorization boundary expressed in SQL:

  * APPROVED records only. A parcel with no approved land record does not
    appear, which is the same rule §17 applies to citizen search.
  * No ownership. Not a redacted owner column -- no owner join at all. A public
    cadastral layer that carries names is a privacy incident waiting for a
    `wfs?request=GetFeature&outputFormat=csv`.
  * No confidence, no anomaly score, no document state. §17 forbids exposing
    internal AI signals outside the officer screens, and a WFS attribute table
    is the widest possible outside.

The view is the contract. Widening it is a deliberate act with a migration
attached, not a checkbox in the GeoServer admin UI.
"""
from __future__ import annotations

from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

VIEW = "gis_published_parcels"


def upgrade() -> None:
    op.execute(f"""
        CREATE OR REPLACE VIEW {VIEW} AS
        SELECT
            p.id                AS id,
            p.external_id       AS parcel_id,
            v.external_id       AS village_id,
            v.name              AS village_name,
            v.name_devanagari   AS village_name_devanagari,
            p.khasra_number     AS khasra_number,
            p.khata_number      AS khata_number,
            p.area_value        AS area_value,
            p.area_unit         AS area_unit,
            p.land_class        AS land_class,
            TRUE                AS is_synthetic,
            'DEMO / SYNTHETIC DATA'::text AS notice,
            p.geometry          AS geometry
        FROM parcels p
        JOIN locations v ON v.id = p.village_id
        WHERE p.geometry IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM land_records r
              WHERE r.parcel_id = p.id AND r.status = 'APPROVED'
          );
    """)

    # GeoServer reads the geometry_columns registry to learn a layer's type and
    # SRID. A view is not registered automatically, and without this GeoServer
    # either refuses the layer or guesses a null SRID and serves the cadastre
    # somewhere off the coast of Africa.
    op.execute(f"COMMENT ON VIEW {VIEW} IS "
               "'Approved parcels published to external GIS. No ownership. "
               "Authorization boundary -- see the migration.'")


def downgrade() -> None:
    op.execute(f"DROP VIEW IF EXISTS {VIEW}")
