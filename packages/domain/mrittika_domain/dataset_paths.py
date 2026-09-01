"""Where dataset artifacts live, and which profile is the active one.

Every generated artifact is namespaced by profile -- `world.v1.json`,
`documents.v1.json`, `parcels.v1.geojson`. The split files were the exception,
written as bare `train.jsonl`, and that inconsistency had a real consequence:
generating a second profile silently overwrote the first profile's splits while
leaving its index in place, so the two disagreed about which documents existed.

Namespacing them removes the failure mode. `active_profile` then lets scripts
and tests agree on which profile to read without hardcoding a name.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Repo root, from this file's location inside packages/domain.
REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS = REPO_ROOT / "datasets"

SPLIT_NAMES = ("train", "val", "test")

#: Read when set, so CI and a developer with several profiles on disk can pin
#: one explicitly.
PROFILE_ENV_VAR = "MRITTIKA_DATASET_PROFILE"


def index_path(profile: str) -> Path:
    return DATASETS / "metadata" / f"documents.{profile}.json"


def world_path(profile: str) -> Path:
    return DATASETS / "metadata" / f"world.{profile}.json"


def split_path(name: str, profile: str) -> Path:
    return DATASETS / "splits" / f"{name}.{profile}.jsonl"


def available_profiles() -> list[str]:
    """Profiles that have a document index on disk, largest last."""
    metadata = DATASETS / "metadata"
    if not metadata.is_dir():
        return []

    found = [
        path.stem.removeprefix("documents.")
        for path in metadata.glob("documents.*.json")
    ]
    # Sorted by index size so `active_profile` prefers the richest corpus --
    # a test asserting a difficulty distribution wants the larger sample.
    return sorted(found, key=lambda p: index_path(p).stat().st_size)


def active_profile() -> str | None:
    """The profile scripts and tests should read.

    An explicit env var wins. Otherwise the largest generated profile, so a
    developer who has just widened the dataset does not have to re-point
    anything. None when nothing has been generated.
    """
    pinned = os.environ.get(PROFILE_ENV_VAR)
    if pinned:
        return pinned

    profiles = available_profiles()
    return profiles[-1] if profiles else None


__all__ = [
    "DATASETS", "PROFILE_ENV_VAR", "REPO_ROOT", "SPLIT_NAMES",
    "active_profile", "available_profiles", "index_path", "split_path",
    "world_path",
]
