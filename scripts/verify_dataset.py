#!/usr/bin/env python
"""Dataset QA (Stage 1, step 7 -- §52).

Checks the generated document set is internally consistent and, above all,
free of split leakage. Writes a report and a visual contact sheet.

    python scripts/verify_dataset.py --profile slice1
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "datasets"
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

TARGET_MIX = {"clean": 0.20, "moderate": 0.35, "hard": 0.30, "extreme": 0.15}
MIX_TOLERANCE = 0.15  # absolute, generous at slice-1 sample sizes


def load_splits(profile: str) -> dict[str, list[dict]]:
    splits = {}
    for name in ("train", "val", "test"):
        path = DATASETS / "splits" / f"{name}.{profile}.jsonl"
        if not path.exists():
            return {}
        splits[name] = [json.loads(line) for line in path.read_text().splitlines() if line]
    return splits


def check_no_split_leakage(splits) -> list[str]:
    """THE critical check (§51).

    No group -- parcel, base document or template instance -- may appear in
    more than one split. A parcel straddling train and test lets a model score
    by recalling owner names it has already seen.
    """
    problems = []
    for key in ("group", "parcel_family", "base_document_id"):
        seen: dict[str, str] = {}
        for split_name, docs in splits.items():
            for doc in docs:
                value = doc.get(key)
                if value is None:
                    continue
                if value in seen and seen[value] != split_name:
                    problems.append(
                        f"{key} {value!r} appears in both {seen[value]} and {split_name}"
                    )
                seen[value] = split_name
    return sorted(set(problems))


def check_files_exist(docs) -> list[str]:
    problems = []
    for doc in docs:
        for key in ("degraded_image", "annotation"):
            if not (DATASETS / doc[key]).exists():
                problems.append(f"{doc['document_id']}: missing {doc[key]}")
    return problems


def check_annotations(docs) -> list[str]:
    problems = []
    for doc in docs:
        path = DATASETS / doc["annotation"]
        if not path.exists():
            continue
        try:
            ann = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            problems.append(f"{doc['document_id']}: invalid JSON ({exc})")
            continue

        w, h = ann["width"], ann["height"]
        if not ann["fields"]:
            problems.append(f"{doc['document_id']}: no field annotations")

        for f in ann["fields"]:
            x1, y1, x2, y2 = f["bbox"]
            if x2 <= x1 or y2 <= y1:
                problems.append(f"{doc['document_id']}/{f['field']}: degenerate bbox")
            if not (0 <= x1 < w and 0 <= y1 < h and 0 < x2 <= w and 0 < y2 <= h):
                problems.append(
                    f"{doc['document_id']}/{f['field']}: bbox {f['bbox']} outside "
                    f"{w}x{h}"
                )
            for key in ("raw_value", "normalized_value"):
                text = f.get(key) or ""
                if text != unicodedata.normalize("NFC", text):
                    problems.append(
                        f"{doc['document_id']}/{f['field']}: {key} is not NFC-normalised"
                    )
    return problems


def check_unique_ids(docs) -> list[str]:
    counts = Counter(d["document_id"] for d in docs)
    return [f"duplicate document_id {k}" for k, v in counts.items() if v > 1]


def check_parcel_links(docs, world) -> list[str]:
    known = {p.parcel_id for p in world.parcels}
    return [
        f"{d['document_id']}: unknown parcel {d['parcel_id']}"
        for d in docs
        if d["parcel_id"] not in known
    ]


def check_difficulty_mix(docs) -> list[str]:
    total = len(docs)
    mix = Counter(d["difficulty"] for d in docs)
    problems = []
    for tier, target in TARGET_MIX.items():
        actual = mix[tier] / total if total else 0.0
        if abs(actual - target) > MIX_TOLERANCE:
            problems.append(
                f"difficulty {tier}: {actual:.0%} vs target {target:.0%} "
                f"(tolerance {MIX_TOLERANCE:.0%})"
            )
    return problems


def check_every_tier_in_every_split(splits) -> list[str]:
    """§65 reports accuracy per tier, so a tier missing from a split is
    unmeasurable there."""
    problems = []
    for name, docs in splits.items():
        present = {d["difficulty"] for d in docs}
        for tier in TARGET_MIX:
            if tier not in present:
                problems.append(f"split {name} contains no '{tier}' documents")
    return problems


def contact_sheet(docs, out: Path, columns: int = 8, thumb: int = 190) -> None:
    from PIL import Image, ImageDraw

    sample = docs[: columns * 5]
    rows = (len(sample) + columns - 1) // columns
    cell_h = int(thumb * 1.42) + 22
    sheet = Image.new("RGB", (columns * thumb, rows * cell_h), "#FDF6E3")
    draw = ImageDraw.Draw(sheet)
    for i, doc in enumerate(sample):
        img = Image.open(DATASETS / doc["degraded_image"])
        img.thumbnail((thumb - 8, int(thumb * 1.42) - 8))
        x = (i % columns) * thumb + 4
        y = (i // columns) * cell_h + 4
        sheet.paste(img, (x, y))
        draw.text((x, y + int(thumb * 1.42) - 2),
                  f"{doc['document_id'][-5:]} {doc['difficulty'][:4]}", fill="#1A1A1A")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="slice1")
    args = parser.parse_args()

    from mrittika_domain import SyntheticWorld

    index_path = DATASETS / "metadata" / f"documents.{args.profile}.json"
    world_path = DATASETS / "metadata" / f"world.{args.profile}.json"
    if not index_path.exists() or not world_path.exists():
        print("generate the world and documents first", file=sys.stderr)
        return 1

    docs = json.loads(index_path.read_text())
    world = SyntheticWorld.model_validate_json(world_path.read_text())
    splits = load_splits(args.profile)

    checks: list[tuple[str, list[str]]] = [
        ("files exist", check_files_exist(docs)),
        ("annotations valid", check_annotations(docs)),
        ("unique document ids", check_unique_ids(docs)),
        ("parcel links resolve", check_parcel_links(docs, world)),
        ("difficulty mix on target", check_difficulty_mix(docs)),
    ]
    if splits:
        checks.append(("NO SPLIT LEAKAGE", check_no_split_leakage(splits)))
        checks.append(("every tier in every split", check_every_tier_in_every_split(splits)))
    else:
        print("(no splits found -- run scripts/split_dataset.py)")

    failed = False
    print(f"QA for profile '{args.profile}': {len(docs)} documents\n")
    for label, problems in checks:
        if problems:
            failed = True
            print(f"  FAIL  {label}: {len(problems)}")
            for p in problems[:6]:
                print(f"          - {p}")
            if len(problems) > 6:
                print(f"          ... and {len(problems) - 6} more")
        else:
            print(f"  ok    {label}")

    reports = DATASETS / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    sheet_path = reports / f"contact_sheet.{args.profile}.png"
    contact_sheet(docs, sheet_path)

    report = {
        "profile": args.profile,
        "documents": len(docs),
        "difficulty": dict(Counter(d["difficulty"] for d in docs)),
        "templates": dict(Counter(d["template"] for d in docs)),
        "splits": {k: len(v) for k, v in splits.items()},
        "checks": {label: problems for label, problems in checks},
        "passed": not failed,
    }
    (reports / f"qa.{args.profile}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )

    print(f"\nwrote {sheet_path.relative_to(REPO_ROOT)}")
    print(f"wrote {(reports / f'qa.{args.profile}.json').relative_to(REPO_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
