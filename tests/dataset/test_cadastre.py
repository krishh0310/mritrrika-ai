"""Stage 1 step 5 gate: the synthetic cadastre.

Overlapping parcels are the defect that matters most here. Two plots claiming
the same ground is precisely the real-world problem this product exists to
surface, so the synthetic data must never contain it by accident.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from shapely.geometry import Polygon

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "services" / "gis"))
sys.path.insert(0, str(REPO_ROOT / "services" / "dataset-generator"))

import cadastre_checks as checks  # noqa: E402
from boundaries.village_boundaries import (  # noqa: E402
    SQM_PER_BIGHA,
    VILLAGE_SITES,
    build_boundary,
    metres_to_wgs84,
    radius_for,
    stable_seed,
)
from mrittika_domain import SyntheticWorld  # noqa: E402
from parcel_generator.voronoi_cadastre import (  # noqa: E402
    build_village_cadastre,
    scale_to_area,
)

WORLD_PATH = REPO_ROOT / "datasets" / "metadata" / "world.slice1.json"


@pytest.fixture(scope="module")
def world() -> SyntheticWorld:
    if not WORLD_PATH.exists():
        pytest.skip("run scripts/generate_dataset.py then scripts/generate_gis.py")
    return SyntheticWorld.model_validate_json(WORLD_PATH.read_text())


@pytest.fixture(scope="module")
def boundaries(world) -> dict[str, Polygon]:
    """Rebuild village boundaries in WGS84, exactly as the generator did."""
    return {
        vid: Polygon(
            [
                metres_to_wgs84(x, y, site)
                for x, y in build_boundary(
                    site, seed=stable_seed(world.seed, vid)
                ).exterior.coords
            ]
        )
        for vid, site in VILLAGE_SITES.items()
    }


class TestGeometricInvariants:
    def test_every_parcel_has_geometry(self, world):
        assert not checks.check_every_parcel_has_geometry(world)

    def test_geometries_are_valid(self, world):
        assert not checks.check_geometries_valid(world)

    def test_no_two_parcels_overlap(self, world):
        problems = checks.check_no_overlaps(world)
        assert not problems, "; ".join(problems[:5])

    def test_parcels_lie_inside_their_village(self, world, boundaries):
        problems = checks.check_within_village_boundary(world, boundaries)
        assert not problems, "; ".join(problems[:5])

    def test_recorded_area_matches_polygon(self, world):
        problems = checks.check_area_matches_geometry(world)
        assert not problems, "; ".join(problems[:5])

    def test_areas_are_plausible(self, world):
        assert not checks.check_areas_are_plausible(world)


class TestDeterminism:
    def test_stable_seed_is_process_independent(self):
        """Regression: builtin hash() on str is randomised per process, so
        seeding from it produced a different cadastre on every run."""
        gis_path = str(REPO_ROOT / "services" / "gis")
        code = (
            f"import sys; sys.path.insert(0, {gis_path!r});"
            "from boundaries.village_boundaries import stable_seed;"
            "print(stable_seed(20260831, 'LOC-VIL-01'))"
        )
        runs = {
            subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                env={"PYTHONHASHSEED": str(seed), "PATH": "/usr/bin:/bin"},
            ).stdout.strip()
            for seed in ("0", "1", "12345")
        }
        assert len(runs) == 1, f"stable_seed varies with PYTHONHASHSEED: {runs}"

    def test_same_seed_gives_same_cadastre(self):
        site = VILLAGE_SITES["LOC-VIL-01"]
        ids = [f"P-{i}" for i in range(12)]
        _, a = build_village_cadastre(site, ids, seed=99)
        _, b = build_village_cadastre(site, ids, seed=99)
        assert [c.polygon_m.wkt for c in a] == [c.polygon_m.wkt for c in b]

    def test_cells_are_returned_in_parcel_id_order(self):
        """Cells must map to the seed point they contain, not shapely's order.

        A mismatch would attach parcel ids to the wrong polygons -- which looks
        completely fine on a map and is completely wrong.
        """
        site = VILLAGE_SITES["LOC-VIL-01"]
        ids = [f"P-{i}" for i in range(10)]
        _, cells = build_village_cadastre(site, ids, seed=5)
        assert [c.parcel_id for c in cells] == ids


class TestAreaPinning:
    def test_scale_to_area_hits_the_target(self):
        square = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        scaled = scale_to_area(square, 2500.0)
        assert scaled.area == pytest.approx(2500.0, rel=1e-9)

    def test_demo_parcel_matches_the_spec_figure(self, world):
        """§45 states 2.75 बीघा; the map and the document must not disagree."""
        demo = next(p for p in world.parcels if p.parcel_id == "PARCEL-UP-DEMO-0142")
        assert demo.area_value == pytest.approx(2.75, abs=0.01)
        assert demo.area_unit.value == "BIGHA"


class TestVillageSizing:
    def test_radius_scales_with_parcel_count(self):
        assert radius_for(80) > radius_for(20)

    def test_village_holds_plausible_smallholdings(self):
        """A village sized for 20 plots should average a few bigha, not fifty."""
        site = VILLAGE_SITES["LOC-VIL-01"]
        boundary = build_boundary(site, seed=7)
        mean_bigha = (boundary.area / 20) / SQM_PER_BIGHA
        assert 1.0 < mean_bigha < 8.0, f"mean plot {mean_bigha:.1f} bigha"


class TestSpatialLinking:
    def test_parcel_id_joins_geometry_to_the_record(self, world):
        """§11: parcel_id is the key tying polygon to khasra to ownership."""
        geo_ids = {p.parcel_id for p in world.parcels if p.geometry_wkt}
        owned_ids = {o.parcel_id for o in world.ownership}
        assert owned_ids <= geo_ids, f"ownership without geometry: {owned_ids - geo_ids}"

    def test_every_village_has_parcels(self, world):
        villages = {loc.location_id for loc in world.locations if loc.level == "VILLAGE"}
        with_parcels = {p.village_id for p in world.parcels}
        assert villages == with_parcels
