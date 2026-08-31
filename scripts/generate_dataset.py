#!/usr/bin/env python
"""Generate the synthetic structured world (Stage 1, steps 3-4).

Ground truth first: this writes structured records, ownership history and
mutations. Document images are rendered FROM this payload in a later step and
never the other way round (§44).

    python scripts/generate_dataset.py --profile slice1
    python scripts/generate_dataset.py --profile slice1 --check-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "services" / "dataset-generator"))

from qa.world_checks import run_all  # noqa: E402
from records.world_builder import WorldBuilder, WorldSpec  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "datasets" / "metadata"

#: Named size profiles. Slice 1 is deliberately small so the whole §92 chain
#: can be made real before the dataset is widened (§42: 50 -> 500 -> ~2000).
PROFILES = {
    "slice1": WorldSpec(villages=2, parcels_per_village=20, extra_owners=24),
    "v1": WorldSpec(villages=4, parcels_per_village=40, extra_owners=80),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="slice1", choices=sorted(PROFILES))
    parser.add_argument("--seed", type=int, default=None, help="override the profile seed")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="build and validate but do not write output",
    )
    args = parser.parse_args()

    spec = PROFILES[args.profile]
    if args.seed is not None:
        spec = WorldSpec(
            seed=args.seed,
            villages=spec.villages,
            parcels_per_village=spec.parcels_per_village,
            extra_owners=spec.extra_owners,
        )

    print(f"building profile '{args.profile}' (seed {spec.seed})")
    world = WorldBuilder(spec).build()

    print(
        f"  locations={len(world.locations)} owners={len(world.owners)} "
        f"parcels={len(world.parcels)} ownership={len(world.ownership)} "
        f"mutations={len(world.mutations)} records={len(world.land_records)} "
        f"users={len(world.users)}"
    )

    print("\nvalidating:")
    results = run_all(world)
    failed = False
    for label, problems in results.items():
        if problems:
            failed = True
            print(f"  FAIL  {label}: {len(problems)} problem(s)")
            for p in problems[:8]:
                print(f"          - {p}")
            if len(problems) > 8:
                print(f"          ... and {len(problems) - 8} more")
        else:
            print(f"  ok    {label}")

    if failed:
        print("\nrefusing to write an invalid world", file=sys.stderr)
        return 1

    if args.check_only:
        print("\ncheck-only: nothing written")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"world.{args.profile}.json"
    out.write_text(world.model_dump_json(indent=2))
    print(f"\nwrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
