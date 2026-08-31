"""Load the generated cadastre into PostGIS and verify it there (§53).

Shapely's notion of validity is not PostGIS's, and SRID handling is easy to get
silently wrong (a polygon with no SRID computes an "area" in square degrees,
which looks like a plausible small number and is meaningless). So geometry is
round-tripped through the database and checked with ST_IsValid / ST_Area
before anything downstream trusts it.

The production tables are created by Alembic in Stage 2. This module loads into
a clearly-named staging table so the two never collide.
"""

from __future__ import annotations

import os

import psycopg

STAGING_TABLE = "cadastre_staging"

WGS84 = 4326


def connection_string() -> str:
    return os.environ.get(
        "DATABASE_URL_PSYCOPG",
        "postgresql://{u}:{p}@{h}:{port}/{db}".format(
            u=os.environ.get("POSTGRES_USER", "mrittika"),
            p=os.environ.get("POSTGRES_PASSWORD", "change_me_locally"),
            h=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            db=os.environ.get("POSTGRES_DB", "mrittika"),
        ),
    )


DDL = f"""
DROP TABLE IF EXISTS {STAGING_TABLE};
CREATE TABLE {STAGING_TABLE} (
    parcel_id     text PRIMARY KEY,
    village_id    text NOT NULL,
    khasra_number text NOT NULL,
    area_value    double precision NOT NULL,
    area_unit     text NOT NULL,
    is_synthetic  boolean NOT NULL DEFAULT true,
    geom          geometry(Polygon, {WGS84}) NOT NULL
);
CREATE INDEX {STAGING_TABLE}_geom_idx ON {STAGING_TABLE} USING GIST (geom);
CREATE INDEX {STAGING_TABLE}_village_idx ON {STAGING_TABLE} (village_id);
"""


def load(parcels, conn_str: str | None = None) -> int:
    """Create the staging table and insert every parcel that has geometry."""
    rows = [
        (
            p.parcel_id,
            p.village_id,
            p.khasra_number,
            p.area_value,
            p.area_unit.value,
            p.is_synthetic,
            p.geometry_wkt,
        )
        for p in parcels
        if p.geometry_wkt
    ]
    with psycopg.connect(conn_str or connection_string(), autocommit=True) as conn:
        conn.execute(DDL)
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {STAGING_TABLE} "
                "(parcel_id, village_id, khasra_number, area_value, area_unit, "
                " is_synthetic, geom) "
                f"VALUES (%s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, {WGS84}))",
                rows,
            )
    return len(rows)


def verify(conn_str: str | None = None) -> dict[str, object]:
    """Ask PostGIS -- not shapely -- whether the cadastre is sound."""
    with psycopg.connect(conn_str or connection_string()) as conn:
        invalid = conn.execute(
            f"SELECT parcel_id, ST_IsValidReason(geom) FROM {STAGING_TABLE} "
            "WHERE NOT ST_IsValid(geom)"
        ).fetchall()

        # ::geography gives true metres, independent of the projection.
        overlaps = conn.execute(
            f"""
            SELECT a.parcel_id, b.parcel_id,
                   ST_Area(ST_Intersection(a.geom, b.geom)::geography)
            FROM {STAGING_TABLE} a
            JOIN {STAGING_TABLE} b
              ON a.parcel_id < b.parcel_id
             AND a.village_id = b.village_id
             AND ST_Intersects(a.geom, b.geom)
            WHERE ST_Area(ST_Intersection(a.geom, b.geom)::geography) > 1.0
            """
        ).fetchall()

        stats = conn.execute(
            f"""
            SELECT count(*),
                   round(min(ST_Area(geom::geography))::numeric, 1),
                   round(max(ST_Area(geom::geography))::numeric, 1),
                   round(sum(ST_Area(geom::geography))::numeric, 1)
            FROM {STAGING_TABLE}
            """
        ).fetchone()

        srids = conn.execute(
            f"SELECT DISTINCT ST_SRID(geom) FROM {STAGING_TABLE}"
        ).fetchall()

    return {
        "invalid": invalid,
        "overlaps": overlaps,
        "count": stats[0],
        "min_sqm": float(stats[1]),
        "max_sqm": float(stats[2]),
        "total_sqm": float(stats[3]),
        "srids": [r[0] for r in srids],
    }
