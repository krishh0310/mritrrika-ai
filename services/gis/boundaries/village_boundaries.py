"""Synthetic village boundaries (§53).

Coordinates are plausible for the Uttar Pradesh plains so a basemap renders
sensibly behind the cadastre, but every boundary here is invented. Nothing
corresponds to a real village, and every generated feature carries
is_synthetic=True plus a DEMO marker (§83).

Geometry is built in a LOCAL METRE frame (east/north offsets from an origin)
and only converted to WGS84 at the end. Doing the maths in metres keeps
computed areas exact; computing area from raw degrees would be wrong by the
cosine of the latitude and would quietly corrupt every recorded area.
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, replace

from shapely.geometry import Polygon

#: UP pucca bigha. Regional definitions vary; this is the value the prototype
#: uses everywhere, and it is recorded alongside the figure so it is auditable.
SQM_PER_BIGHA = 2529.285
SQM_PER_HECTARE = 10_000.0
SQM_PER_ACRE = 4046.86

#: Mean metres per degree of latitude. Longitude is scaled by cos(lat).
METRES_PER_DEGREE_LAT = 111_320.0


@dataclass(frozen=True)
class VillageSite:
    """Where a synthetic village sits, and how big it is."""

    village_id: str
    name_devanagari: str
    origin_lon: float
    origin_lat: float
    radius_m: float = 900.0


#: Typical smallholding used to size a village to its parcel count.
MEAN_PARCEL_BIGHA = 3.0


def radius_for(parcel_count: int, mean_bigha: float = MEAN_PARCEL_BIGHA) -> float:
    """Radius that makes a village hold `parcel_count` plots of a sane size.

    Without this the boundary and the recorded areas disagree wildly -- a
    900 m village divided into 20 plots gives ~49 bigha each, against recorded
    areas of 0.5-8 bigha. Deriving the radius keeps map and record coherent.
    """
    total_sqm = parcel_count * mean_bigha * SQM_PER_BIGHA
    return math.sqrt(total_sqm / math.pi)


#: Slice-1 sites. Placed ~700 m apart so both villages sit in one map view
#: with a lane between them rather than overlapping.
VILLAGE_SITES: dict[str, VillageSite] = {
    "LOC-VIL-01": VillageSite("LOC-VIL-01", "रामपुर", 80.9000, 26.8000, radius_for(20)),
    "LOC-VIL-02": VillageSite("LOC-VIL-02", "मुड़ियाकला", 80.9055, 26.8040, radius_for(20)),
    "LOC-VIL-03": VillageSite("LOC-VIL-03", "बरगदही", 80.9110, 26.7960, radius_for(20)),
    "LOC-VIL-04": VillageSite("LOC-VIL-04", "सोनवर्षा", 80.8945, 26.8055, radius_for(20)),
}


def site_for(village_id: str, parcel_count: int) -> VillageSite | None:
    """The registered site, resized to actually hold `parcel_count` plots.

    The radius baked into VILLAGE_SITES is only a default for the slice-1 size.
    Sizing must follow the parcel count the world actually generated: a village
    sized for 20 plots but tessellated into 40 gives cells half the recorded
    area, and pinning a parcel back to its recorded figure then grows it over
    its neighbours. Deriving the radius here keeps map and record coherent at
    every profile size.
    """
    site = VILLAGE_SITES.get(village_id)
    if site is None:
        return None
    return replace(site, radius_m=radius_for(parcel_count))


def metres_to_wgs84(x_m: float, y_m: float, site: VillageSite) -> tuple[float, float]:
    """Local ENU metres -> (lon, lat). Accurate enough over a ~2 km village."""
    lat = site.origin_lat + (y_m / METRES_PER_DEGREE_LAT)
    lon = site.origin_lon + (
        x_m / (METRES_PER_DEGREE_LAT * math.cos(math.radians(site.origin_lat)))
    )
    return lon, lat


def build_boundary(site: VillageSite, seed: int, vertices: int = 26) -> Polygon:
    """An irregular closed boundary in local metres.

    A perturbed circle rather than a real outline: convex enough that Voronoi
    clipping behaves, irregular enough that the map does not look synthetic in
    the wrong way (a perfect circle reads as obviously fake).
    """
    rng = random.Random(seed)
    points: list[tuple[float, float]] = []
    for i in range(vertices):
        angle = (2 * math.pi * i) / vertices
        # Smooth low-frequency wobble plus a little noise.
        wobble = 1.0 + 0.13 * math.sin(3 * angle + seed % 7) + rng.uniform(-0.05, 0.05)
        r = site.radius_m * wobble
        points.append((r * math.cos(angle), r * math.sin(angle)))
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return polygon


def stable_seed(base_seed: int, key: str) -> int:
    """Derive a per-village seed deterministically.

    Python's builtin hash() is randomised per process for str (PYTHONHASHSEED),
    so `base_seed + hash(village_id)` silently produces a DIFFERENT cadastre on
    every run. crc32 is stable across processes and interpreter versions, which
    is what "same seed reproduces the same world" requires.
    """
    return (base_seed + zlib.crc32(key.encode("utf-8"))) % (2**31)
