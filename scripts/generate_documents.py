#!/usr/bin/env python
"""Render, annotate and degrade the document set (Stage 1, step 6).

    python scripts/generate_documents.py --profile slice1 --count 50

Ground truth already exists in datasets/metadata/world.<profile>.json; this
only produces pixels from it and carries the labels through degradation (§44).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "services" / "dataset-generator"))

from degradation.profiles import DIFFICULTY_MIX  # noqa: E402
from document_pipeline import generate_document  # noqa: E402
from mrittika_domain import SyntheticWorld  # noqa: E402
from templates.layouts import TEMPLATES  # noqa: E402

DATASETS = REPO_ROOT / "datasets"

#: Report order, easiest first. Taken from the mix itself so the two can never
#: name a different set of tiers.
DIFFICULTY_TIERS = list(DIFFICULTY_MIX)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="slice1")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--save-clean", action="store_true", default=True)
    args = parser.parse_args()

    world_path = DATASETS / "metadata" / f"world.{args.profile}.json"
    if not world_path.exists():
        print(f"missing {world_path}; run scripts/generate_dataset.py", file=sys.stderr)
        return 1
    world = SyntheticWorld.model_validate_json(world_path.read_text())

    rng = random.Random(world.seed ^ 0x5EED)
    parcels = sorted(world.parcels, key=lambda p: p.parcel_id)
    mutations_by_parcel: dict[str, list] = {}
    for m in world.mutations:
        mutations_by_parcel.setdefault(m.parcel_id, []).append(m)

    clean_dir = DATASETS / "generated" / "clean"
    degraded_dir = DATASETS / "generated" / "degraded"
    # One file per page holds all four annotation views -- fields, ocr, layout
    # and tables -- because they describe the same render and must never drift
    # apart. Sibling ocr/, layout/ and tables/ directories used to be created
    # here and never written, which read as missing ground truth when it was
    # actually present inline under those keys of each fields/ file.
    ann_dir = DATASETS / "annotations" / "fields"
    for d in (clean_dir, degraded_dir, ann_dir):
        d.mkdir(parents=True, exist_ok=True)

    template_names = list(TEMPLATES)
    index: list[dict] = []
    difficulties: Counter[str] = Counter()
    templates_used: Counter[str] = Counter()

    for i in range(args.count):
        parcel = parcels[i % len(parcels)]
        template = template_names[i % len(template_names)]

        mutation = None
        if template == "MUTATION_REGISTER_A":
            candidates = mutations_by_parcel.get(parcel.parcel_id)
            if not candidates:
                template = "KHASRA_A"
            else:
                mutation = rng.choice(candidates)

        as_of = mutation.effective_date if mutation else __import__("datetime").date.today()
        document_id = f"DOC-{i + 1:05d}"

        doc = generate_document(
            world, parcel, template, document_id, rng, as_of, mutation=mutation
        )

        doc.degraded_image.save(degraded_dir / f"{document_id}.jpg", quality=95)
        if args.save_clean:
            doc.clean_image.save(clean_dir / f"{document_id}.png")
        (ann_dir / f"{document_id}.json").write_text(
            json.dumps(doc.annotation.to_dict(), ensure_ascii=False, indent=1)
        )

        difficulties[doc.difficulty] += 1
        templates_used[doc.template] += 1
        index.append(
            {
                "document_id": document_id,
                "parcel_id": doc.parcel_id,
                "template": doc.template,
                "template_family": doc.template_family,
                "parcel_family": doc.parcel_family,
                "base_document_id": doc.base_document_id,
                "document_type": doc.document_type,
                "difficulty": doc.difficulty,
                "degraded_image": f"generated/degraded/{document_id}.jpg",
                "clean_image": f"generated/clean/{document_id}.png",
                "annotation": f"annotations/fields/{document_id}.json",
                "field_count": len(doc.annotation.fields),
            }
        )

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{args.count}")

    (DATASETS / "metadata" / f"documents.{args.profile}.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1)
    )

    print(f"\ngenerated {len(index)} documents")
    print("  templates:  " + ", ".join(f"{k}={v}" for k, v in sorted(templates_used.items())))
    total = len(index)
    print("  difficulty: " + ", ".join(
        f"{k}={v} ({v / total:.0%})" for k, v in
        sorted(
            difficulties.items(),
            key=lambda kv: DIFFICULTY_TIERS.index(kv[0]),
        )
    ))
    print(f"  mean fields/page: {sum(d['field_count'] for d in index) / total:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
