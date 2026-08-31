#!/usr/bin/env python
"""Split the document set without leakage (Stage 1, step 7 -- §51).

70 / 15 / 15, split by GROUP rather than by document.

The grouping key is the parcel. Two documents of the same parcel share the
owner names, khasra number, village, area and land class -- so putting one in
train and the other in test lets a model score well by memorising values it has
already seen. That is the classic way to report an accuracy figure that
evaporates on real data, and §51 calls it out explicitly.

Splitting happens on the BASE documents, before augmentation, so a clean page
and its degraded clone can never land on opposite sides.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "datasets"

RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}


def split_groups(groups: dict[str, list[dict]], seed: int) -> dict[str, str]:
    """Assign whole groups to splits, balancing BOTH size and difficulty.

    Balancing on document count alone is not enough. §65 requires accuracy to
    be reported per difficulty tier, so a tier that is absent from test is
    simply unmeasurable -- and with groups kept whole that happens easily
    (a count-only greedy left test with zero 'hard' pages).

    So each group is placed into whichever split minimises the combined
    imbalance afterwards: overall size deficit plus per-tier deficit. Groups
    are never broken, so the leakage guarantee is unaffected.
    """
    tiers = ("clean", "moderate", "hard", "extreme")
    total = sum(len(v) for v in groups.values())
    tier_totals = Counter(
        doc["difficulty"] for docs in groups.values() for doc in docs
    )

    quota = {name: ratio * total for name, ratio in RATIOS.items()}
    tier_quota = {
        name: {t: RATIOS[name] * tier_totals[t] for t in tiers} for name in RATIOS
    }

    assigned = {name: 0 for name in RATIOS}
    assigned_tiers = {name: Counter() for name in RATIOS}
    placement: dict[str, str] = {}

    rng = random.Random(seed)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rng.shuffle(ordered)
    ordered.sort(key=lambda kv: -len(kv[1]))

    def imbalance(name: str, docs: list[dict]) -> float:
        """Squared shortfall if `docs` went to `name` -- lower is better."""
        size_gap = (quota[name] - (assigned[name] + len(docs))) / max(quota[name], 1e-9)
        score = size_gap ** 2
        group_tiers = Counter(d["difficulty"] for d in docs)
        for t in tiers:
            target = tier_quota[name][t]
            if target <= 0:
                continue
            gap = (target - (assigned_tiers[name][t] + group_tiers[t])) / target
            # Weighted above size so an empty tier is avoided first.
            score += 1.6 * (gap ** 2)
        return score

    for group_key, docs in ordered:
        # Prefer the split that is furthest BEHIND -- i.e. largest positive gap.
        best = min(
            RATIOS,
            key=lambda name: -sum(
                max(0.0, (tier_quota[name][t] - assigned_tiers[name][t]))
                for t in tiers
                if Counter(d["difficulty"] for d in docs)[t]
            )
            - max(0.0, quota[name] - assigned[name]) * 0.35,
        )
        placement[group_key] = best
        assigned[best] += len(docs)
        assigned_tiers[best].update(d["difficulty"] for d in docs)

    return placement


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="slice1")
    parser.add_argument("--seed", type=int, default=20260831)
    args = parser.parse_args()

    index_path = DATASETS / "metadata" / f"documents.{args.profile}.json"
    if not index_path.exists():
        print(f"missing {index_path}; run scripts/generate_documents.py", file=sys.stderr)
        return 1
    index = json.loads(index_path.read_text())

    groups: dict[str, list[dict]] = defaultdict(list)
    for doc in index:
        groups[doc["parcel_family"]].append(doc)

    placement = split_groups(groups, args.seed)

    out_dir = DATASETS / "splits"
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    per_split: dict[str, list[dict]] = {name: [] for name in RATIOS}

    for group_key, docs in groups.items():
        target = placement[group_key]
        for doc in docs:
            entry = dict(doc)
            entry["split"] = target
            entry["group"] = group_key
            per_split[target].append(entry)
            counts[target] += 1

    for name, entries in per_split.items():
        entries.sort(key=lambda d: d["document_id"])
        with (out_dir / f"{name}.jsonl").open("w") as fh:
            for entry in entries:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = sum(counts.values())
    print(f"split {total} documents across {len(groups)} parcel groups")
    for name in RATIOS:
        share = counts[name] / total
        print(f"  {name:5s} {counts[name]:4d} ({share:.0%}, target {RATIOS[name]:.0%})")

    # Difficulty should be represented in every split, or test scores mean
    # something different from train scores.
    print("\ndifficulty per split:")
    for name in RATIOS:
        mix = Counter(d["difficulty"] for d in per_split[name])
        print(f"  {name:5s} " + ", ".join(f"{k}={mix[k]}" for k in
              ("clean", "moderate", "hard", "extreme")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
