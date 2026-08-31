"""Generate a synthetic cadastre by Voronoi tessellation (§53).

    village boundary -> seeded points -> Voronoi cells -> clip -> regularise
    -> assign parcel_id -> link khasra / owner / record

Everything is computed in local metres and converted to WGS84 only on output,
so the recorded area of a plot and the area of its polygon agree. The
`parcel_id` is the join key that ties the polygon to the khasra number, the
land record, the ownership chain and the documents (§11).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from boundaries.village_boundaries import (
    SQM_PER_ACRE,
    SQM_PER_BIGHA,
    SQM_PER_HECTARE,
    VillageSite,
    build_boundary,
    metres_to_wgs84,
)
from shapely import voronoi_polygons
from shapely.affinity import scale as affine_scale
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.geometry.base import BaseGeometry

SQM_PER_UNIT = {
    "BIGHA": SQM_PER_BIGHA,
    "HECTARE": SQM_PER_HECTARE,
    "ACRE": SQM_PER_ACRE,
    "BISWA": SQM_PER_BIGHA / 20.0,
    "SQUARE_METRE": 1.0,
}


@dataclass
class CadastreCell:
    """One generated plot, before it is attached to a Parcel."""

    parcel_id: str
    village_id: str
    polygon_m: Polygon      # local metres
    polygon_wgs84: Polygon  # lon/lat
    area_sqm: float


def _seed_points(boundary: Polygon, count: int, rng: random.Random) -> list[Point]:
    """Scatter `count` points inside the boundary by rejection sampling.

    A Poisson-ish minimum spacing is enforced so cells come out reasonably
    even; pure uniform sampling produces slivers that look wrong on a map and
    make the 'plot too small to be real' case dominate.
    """
    minx, miny, maxx, maxy = boundary.bounds
    # Spacing target: cells should tile the boundary roughly evenly.
    min_spacing = 0.55 * (boundary.area / count) ** 0.5

    points: list[Point] = []
    attempts = 0
    max_attempts = count * 4000
    while len(points) < count and attempts < max_attempts:
        attempts += 1
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if not boundary.contains(p):
            continue
        if any(p.distance(q) < min_spacing for q in points):
            continue
        points.append(p)

    if len(points) < count:
        # Relax spacing rather than loop forever; still deterministic.
        while len(points) < count and attempts < max_attempts * 2:
            attempts += 1
            p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
            if boundary.contains(p) and all(p.distance(q) > 1.0 for q in points):
                points.append(p)

    if len(points) < count:
        raise RuntimeError(
            f"could only place {len(points)}/{count} seed points in the village "
            f"boundary; the boundary is too small for this parcel count"
        )
    return points


def _cells_for_points(
    points: list[Point], boundary: Polygon
) -> list[Polygon]:
    """Voronoi cells, clipped to the boundary, in the same order as `points`.

    shapely returns cells in an arbitrary order, so each cell is matched back
    to the seed point it contains. Without that mapping, parcel ids would be
    attached to the wrong polygons -- which would look fine on a map and be
    completely wrong.
    """
    regions = voronoi_polygons(MultiPoint(points), extend_to=boundary.envelope)
    cells: list[Polygon | None] = [None] * len(points)

    for region in regions.geoms:
        for i, p in enumerate(points):
            if cells[i] is None and region.contains(p):
                clipped = region.intersection(boundary)
                cells[i] = _largest_polygon(clipped)
                break

    missing = [i for i, c in enumerate(cells) if c is None or c.is_empty]
    if missing:
        raise RuntimeError(f"no Voronoi cell resolved for seed points {missing}")
    return cells  # type: ignore[return-value]


def _largest_polygon(geom: BaseGeometry) -> Polygon:
    """Clipping can yield a MultiPolygon; keep the main body."""
    if geom.geom_type == "Polygon":
        return geom
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        polys = [g for g in geom.geoms if g.geom_type == "Polygon" and not g.is_empty]
        if polys:
            return max(polys, key=lambda g: g.area)
    raise ValueError(f"cannot reduce {geom.geom_type} to a polygon")


def _regularise(polygon: Polygon, boundary: Polygon, tolerance_m: float = 1.5) -> Polygon:
    """Simplify jagged clip artefacts, then re-clip to the village boundary.

    Simplifying moves vertices, so a cell that was exactly clipped to the
    boundary can end up a metre or two outside it. Re-intersecting afterwards
    is what keeps "every parcel lies inside its village" true; without it a
    handful of plots spill over by ~10-25 m2.
    """
    simplified = polygon.simplify(tolerance_m, preserve_topology=True)
    if not simplified.is_valid:
        simplified = simplified.buffer(0)
    if simplified.is_empty:
        return polygon
    reclipped = simplified.intersection(boundary)
    if reclipped.is_empty:
        return polygon
    return _largest_polygon(reclipped)


def scale_to_area(polygon: Polygon, target_sqm: float) -> Polygon:
    """Scale a polygon about its centroid so its area equals `target_sqm`.

    Used only to pin the demo parcel to the exact figure the §45 sample and the
    rendered document both state. Shrinking one cell leaves a sliver gap
    against its neighbours, which is geometrically fine (gaps are legal in a
    cadastre; overlaps are not).
    """
    if polygon.area <= 0:
        raise ValueError("cannot scale a zero-area polygon")
    factor = (target_sqm / polygon.area) ** 0.5
    return affine_scale(polygon, xfact=factor, yfact=factor, origin="centroid")


def build_village_cadastre(
    site: VillageSite,
    parcel_ids: list[str],
    seed: int,
    pinned_areas_sqm: dict[str, float] | None = None,
) -> tuple[Polygon, list[CadastreCell]]:
    """Tessellate one village into a cell per parcel id.

    Returns (boundary in local metres, cells). Cells are returned in the same
    order as `parcel_ids`.
    """
    rng = random.Random(seed)
    boundary = build_boundary(site, seed=seed)
    points = _seed_points(boundary, len(parcel_ids), rng)
    raw_cells = _cells_for_points(points, boundary)

    pinned = pinned_areas_sqm or {}
    cells: list[CadastreCell] = []
    for parcel_id, cell in zip(parcel_ids, raw_cells, strict=True):
        polygon = _regularise(cell, boundary)
        if parcel_id in pinned:
            polygon = scale_to_area(polygon, pinned[parcel_id])
        wgs = Polygon(
            [metres_to_wgs84(x, y, site) for x, y in polygon.exterior.coords]
        )
        cells.append(
            CadastreCell(
                parcel_id=parcel_id,
                village_id=site.village_id,
                polygon_m=polygon,
                polygon_wgs84=wgs,
                area_sqm=polygon.area,
            )
        )
    return boundary, cells


def sqm_to_unit(area_sqm: float, unit: str) -> float:
    """Convert a computed area into the unit written on the record."""
    return area_sqm / SQM_PER_UNIT[unit]
