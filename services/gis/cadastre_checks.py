"""Geometric invariants for the generated cadastre (step 5 gate).

Overlapping parcels are the failure that matters: two plots claiming the same
ground is exactly the real-world defect this product exists to surface, so the
synthetic data must not contain it by accident. Gaps, by contrast, are legal --
real cadastres have lanes, ponds and unrecorded strips.
"""

from __future__ import annotations

from shapely import wkt
from shapely.geometry import Polygon

#: Slivers below this are float noise from clipping, not real overlap.
OVERLAP_TOLERANCE_SQM = 1.0

#: How far a parcel may stray outside its village boundary before it counts.
OUTSIDE_TOLERANCE_SQM = 1.0


def _polygons(parcels) -> dict[str, Polygon]:
    return {
        p.parcel_id: wkt.loads(p.geometry_wkt)
        for p in parcels
        if p.geometry_wkt
    }


def check_every_parcel_has_geometry(world) -> list[str]:
    return [
        f"{p.parcel_id}: no geometry"
        for p in world.parcels
        if not p.geometry_wkt
    ]


def check_geometries_valid(world) -> list[str]:
    problems = []
    for parcel_id, poly in _polygons(world.parcels).items():
        if not poly.is_valid:
            problems.append(f"{parcel_id}: invalid geometry")
        elif poly.is_empty:
            problems.append(f"{parcel_id}: empty geometry")
        elif poly.area <= 0:
            problems.append(f"{parcel_id}: non-positive area")
    return problems


def check_no_overlaps(world) -> list[str]:
    """No two parcels may claim the same ground.

    Compared in the WGS84 frame, so the tolerance is converted from square
    metres using the local degree scale rather than guessed.
    """
    problems = []
    polys = _polygons(world.parcels)
    by_village: dict[str, list[str]] = {}
    for p in world.parcels:
        if p.geometry_wkt:
            by_village.setdefault(p.village_id, []).append(p.parcel_id)

    # deg^2 -> m^2 at ~26.8N. Used only to size the noise tolerance.
    sqdeg_to_sqm = (111_320.0 ** 2) * 0.893

    for parcel_ids in by_village.values():
        for i, a_id in enumerate(parcel_ids):
            for b_id in parcel_ids[i + 1:]:
                inter = polys[a_id].intersection(polys[b_id])
                if inter.is_empty:
                    continue
                overlap_sqm = inter.area * sqdeg_to_sqm
                if overlap_sqm > OVERLAP_TOLERANCE_SQM:
                    problems.append(
                        f"{a_id} overlaps {b_id} by {overlap_sqm:.1f} m2"
                    )
    return problems


def check_within_village_boundary(world, boundaries: dict[str, Polygon]) -> list[str]:
    """Every parcel must lie inside the village that claims it."""
    problems = []
    sqdeg_to_sqm = (111_320.0 ** 2) * 0.893
    for parcel in world.parcels:
        if not parcel.geometry_wkt:
            continue
        boundary = boundaries.get(parcel.village_id)
        if boundary is None:
            problems.append(f"{parcel.parcel_id}: no boundary for {parcel.village_id}")
            continue
        poly = wkt.loads(parcel.geometry_wkt)
        outside = poly.difference(boundary)
        if not outside.is_empty and outside.area * sqdeg_to_sqm > OUTSIDE_TOLERANCE_SQM:
            problems.append(
                f"{parcel.parcel_id}: {outside.area * sqdeg_to_sqm:.1f} m2 lies "
                f"outside village {parcel.village_id}"
            )
    return problems


def check_area_matches_geometry(world, tolerance: float = 0.05) -> list[str]:
    """Recorded area and polygon area must agree.

    They are the same number by construction, so a mismatch means the geometry
    and the record drifted apart -- which would show a citizen a plot whose map
    footprint contradicts their document.
    """
    from parcel_generator.voronoi_cadastre import SQM_PER_UNIT

    problems = []
    sqdeg_to_sqm = (111_320.0 ** 2) * 0.893
    for parcel in world.parcels:
        if not parcel.geometry_wkt:
            continue
        poly = wkt.loads(parcel.geometry_wkt)
        geom_units = (poly.area * sqdeg_to_sqm) / SQM_PER_UNIT[parcel.area_unit.value]
        if abs(geom_units - parcel.area_value) > max(tolerance, parcel.area_value * 0.02):
            problems.append(
                f"{parcel.parcel_id}: recorded {parcel.area_value} "
                f"{parcel.area_unit.value} vs geometry {geom_units:.2f}"
            )
    return problems


def check_areas_are_plausible(world) -> list[str]:
    """Catch degenerate slivers that are geometrically valid but absurd."""
    problems = []
    for parcel in world.parcels:
        if parcel.area_value <= 0:
            problems.append(f"{parcel.parcel_id}: area {parcel.area_value}")
        if parcel.area_unit.value == "BIGHA" and parcel.area_value > 100:
            problems.append(
                f"{parcel.parcel_id}: implausible {parcel.area_value} bigha"
            )
    return problems
