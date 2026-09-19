"""PostGIS-side verification of the cadastre (step 5 gate, integration half).

Shapely's validity is not PostGIS's, and an unset SRID silently turns ST_Area
into square degrees -- a small plausible-looking number that is meaningless.
These checks ask the database directly.

Requires the infra stack:  docker compose up -d
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "services" / "gis"))

pytestmark = pytest.mark.integration

WORLD_PATH = REPO_ROOT / "datasets" / "metadata" / "world.slice1.json"


@pytest.fixture(scope="module")
def verified():
    psycopg = pytest.importorskip("psycopg")
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    from mrittika_domain import SyntheticWorld
    from spatial_linker.postgis_loader import connection_string, load, verify

    if not WORLD_PATH.exists():
        pytest.skip("generate the world and cadastre first")

    try:
        psycopg.connect(connection_string(), connect_timeout=3).close()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"postgres unavailable ({exc}); run: docker compose up -d")

    world = SyntheticWorld.model_validate_json(WORLD_PATH.read_text())
    load(world.parcels)
    return {**verify(), "expected": len(world.parcels)}


def test_all_geometries_valid_in_postgis(verified):
    assert verified["invalid"] == [], verified["invalid"][:5]


def test_no_overlapping_parcels_in_postgis(verified):
    """Measured in true metres via ::geography, not degrees."""
    assert verified["overlaps"] == [], verified["overlaps"][:5]


def test_srid_is_set_uniformly(verified):
    """An unset SRID makes every downstream area silently wrong."""
    assert verified["srids"] == [4326]


def test_all_parcels_loaded(verified):
    assert verified["count"] == verified["expected"]


def test_areas_are_smallholding_sized(verified):
    """Sanity bound in real square metres: no slivers, no implausible estates."""
    assert verified["min_sqm"] > 500, verified["min_sqm"]
    assert verified["max_sqm"] < 60_000, verified["max_sqm"]
