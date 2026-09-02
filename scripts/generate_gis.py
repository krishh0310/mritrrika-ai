#!/usr/bin/env python
"""Generate the synthetic cadastre and link it to the structured world (step 5).

Reads datasets/metadata/world.<profile>.json, tessellates each village into one
polygon per parcel, writes the geometry back onto the parcels and emits GeoJSON.

    python scripts/generate_gis.py --profile slice1

Recorded areas are recomputed from the geometry so the map and the document
agree -- except for parcels pinned by the spec's worked examples, whose cells
are scaled to the stated figure instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "services" / "gis"))

from boundaries.village_boundaries import (  # noqa: E402
    SQM_PER_BIGHA,
    site_for,
    metres_to_wgs84,
    stable_seed,
)
from mrittika_domain import SyntheticWorld  # noqa: E402
from parcel_generator.voronoi_cadastre import (  # noqa: E402
    build_village_cadastre,
    sqm_to_unit,
)

METADATA_DIR = REPO_ROOT / "datasets" / "metadata"
GIS_DIR = REPO_ROOT / "datasets" / "gis"

#: Parcels whose recorded area is fixed by a spec worked example (§45).
PINNED_BIGHA = {"PARCEL-UP-DEMO-0142": 2.75}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="slice1")
    args = parser.parse_args()

    world_path = METADATA_DIR / f"world.{args.profile}.json"
    if not world_path.exists():
        print(
            f"{world_path.relative_to(REPO_ROOT)} not found -- run "
            f"scripts/generate_dataset.py --profile {args.profile} first",
            file=sys.stderr,
        )
        return 1

    world = SyntheticWorld.model_validate_json(world_path.read_text())
    by_id = {p.parcel_id: p for p in world.parcels}

    features: list[dict] = []
    boundary_features: list[dict] = []
    all_cells = []

    villages = [loc for loc in world.locations if loc.level == "VILLAGE"]
    for village in villages:
        parcel_ids = sorted(
            p.parcel_id for p in world.parcels if p.village_id == village.location_id
        )

        # Size the boundary to the parcels this world actually put here, not to
        # a default baked in at slice-1 scale.
        site = site_for(village.location_id, len(parcel_ids))
        if site is None:
            print(f"no site defined for {village.location_id}", file=sys.stderr)
            return 1
        pinned = {
            pid: bigha * SQM_PER_BIGHA
            for pid, bigha in PINNED_BIGHA.items()
            if pid in parcel_ids
        }

        boundary, cells = build_village_cadastre(
            site,
            parcel_ids,
            seed=stable_seed(world.seed, village.location_id),
            pinned_areas_sqm=pinned,
        )
        all_cells.extend(cells)

        boundary_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [list(metres_to_wgs84(x, y, site)) for x, y in boundary.exterior.coords]
                    ],
                },
                "properties": {
                    "village_id": village.location_id,
                    "name": village.name,
                    "name_devanagari": village.name_devanagari,
                    "is_synthetic": True,
                    "notice": "DEMO / SYNTHETIC DATA",
                },
            }
        )

        for cell in cells:
            parcel = by_id[cell.parcel_id]
            # Geometry is authoritative for area, so map and record agree.
            parcel.area_value = round(sqm_to_unit(cell.area_sqm, parcel.area_unit.value), 2)
            parcel.geometry_wkt = cell.polygon_wgs84.wkt

            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(
                        json.dumps(
                            {
                                "type": "Polygon",
                                "coordinates": [
                                    [list(c) for c in cell.polygon_wgs84.exterior.coords]
                                ],
                            }
                        )
                    ),
                    "properties": {
                        "parcel_id": parcel.parcel_id,
                        "khasra_number": parcel.khasra_number,
                        "khata_number": parcel.khata_number,
                        "village_id": parcel.village_id,
                        "area_value": parcel.area_value,
                        "area_unit": parcel.area_unit.value,
                        "area_sqm": round(cell.area_sqm, 1),
                        "land_class": parcel.land_class,
                        "is_synthetic": True,
                        "notice": "DEMO / SYNTHETIC DATA",
                    },
                }
            )

    print(f"tessellated {len(villages)} villages into {len(all_cells)} parcels")

    GIS_DIR.mkdir(parents=True, exist_ok=True)
    (GIS_DIR / f"parcels.{args.profile}.geojson").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False, indent=1,
        )
    )
    (GIS_DIR / f"villages.{args.profile}.geojson").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": boundary_features},
            ensure_ascii=False, indent=1,
        )
    )
    world_path.write_text(world.model_dump_json(indent=2))

    print(f"wrote {(GIS_DIR / f'parcels.{args.profile}.geojson').relative_to(REPO_ROOT)}")
    print(f"wrote {(GIS_DIR / f'villages.{args.profile}.geojson').relative_to(REPO_ROOT)}")
    print(f"updated {world_path.relative_to(REPO_ROOT)} with geometry + areas")

    demo = by_id.get("PARCEL-UP-DEMO-0142")
    if demo:
        print(f"\ndemo parcel {demo.parcel_id}: {demo.area_value} {demo.area_unit.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
