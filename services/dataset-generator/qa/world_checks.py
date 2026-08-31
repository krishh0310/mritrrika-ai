"""Invariant checks on the generated structured world (§52).

These are the Stage 1 gate. They exist because a corrupt ownership timeline is
invisible until very late -- it surfaces as a citizen seeing the wrong parcel,
or the RAG assistant confidently citing a wrong owner. Cheaper to catch here.

Every check returns a list of human-readable problems; empty means clean.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from fractions import Fraction

from mrittika_domain import SyntheticWorld


def check_shares_sum_to_one(world: SyntheticWorld) -> list[str]:
    """At every date where ownership changes, active shares must total exactly 1.

    Checked at each interval boundary rather than sampling dates, because an
    off-by-one in interval closing shows up only on the pivot date itself.
    """
    problems: list[str] = []
    by_parcel: dict[str, list] = defaultdict(list)
    for record in world.ownership:
        by_parcel[record.parcel_id].append(record)

    for parcel_id, records in by_parcel.items():
        pivots: set[date] = set()
        for r in records:
            pivots.add(r.valid_from)
            if r.valid_to is not None:
                pivots.add(r.valid_to)
        for when in sorted(pivots):
            active = [r for r in records if r.covers(when)]
            if not active:
                problems.append(f"{parcel_id}: no active ownership on {when}")
                continue
            total = sum((r.share_fraction for r in active), Fraction(0))
            if total != 1:
                holders = ", ".join(f"{r.owner_id}={r.share}" for r in active)
                problems.append(
                    f"{parcel_id}: shares total {total} (not 1) on {when} [{holders}]"
                )
    return problems


def check_no_overlaps_or_gaps(world: SyntheticWorld) -> list[str]:
    """A parcel's ownership timeline must be continuous once it starts."""
    problems: list[str] = []
    by_parcel: dict[str, list] = defaultdict(list)
    for record in world.ownership:
        by_parcel[record.parcel_id].append(record)

    for parcel_id, records in by_parcel.items():
        # Group intervals by their (valid_from, valid_to) span; co-owners share one.
        spans = sorted({(r.valid_from, r.valid_to) for r in records})
        for (_, end), (next_start, _) in zip(spans, spans[1:], strict=False):
            if end is None:
                problems.append(
                    f"{parcel_id}: an open-ended interval is followed by another "
                    f"starting {next_start}"
                )
                continue
            expected = (end.toordinal() + 1) == next_start.toordinal()
            if not expected:
                problems.append(
                    f"{parcel_id}: timeline break -- interval ends {end} but next "
                    f"begins {next_start}"
                )
    return problems


def check_mutation_chronology(world: SyntheticWorld) -> list[str]:
    """Mutations must be dated sanely and ordered within a parcel (§52)."""
    problems: list[str] = []
    by_parcel: dict[str, list] = defaultdict(list)
    for mutation in world.mutations:
        by_parcel[mutation.parcel_id].append(mutation)

    for parcel_id, mutations in by_parcel.items():
        mutations.sort(key=lambda m: m.effective_date)
        for m in mutations:
            if m.registration_date and m.registration_date < m.effective_date:
                problems.append(
                    f"{m.mutation_id}: registered {m.registration_date} before "
                    f"taking effect {m.effective_date}"
                )
            if not m.new_owner_ids:
                problems.append(f"{m.mutation_id}: mutation transfers to nobody")
        for earlier, later in zip(mutations, mutations[1:], strict=False):
            if earlier.effective_date == later.effective_date:
                problems.append(
                    f"{parcel_id}: two mutations share effective date "
                    f"{earlier.effective_date}"
                )
    return problems


def check_referential_integrity(world: SyntheticWorld) -> list[str]:
    """Every foreign key in the payload must resolve."""
    problems: list[str] = []
    owner_ids = {o.owner_id for o in world.owners}
    parcel_ids = {p.parcel_id for p in world.parcels}
    location_ids = {loc.location_id for loc in world.locations}
    mutation_ids = {m.mutation_id for m in world.mutations}

    for p in world.parcels:
        if p.village_id not in location_ids:
            problems.append(f"{p.parcel_id}: unknown village {p.village_id}")

    for r in world.ownership:
        if r.owner_id not in owner_ids:
            problems.append(f"{r.ownership_id}: unknown owner {r.owner_id}")
        if r.parcel_id not in parcel_ids:
            problems.append(f"{r.ownership_id}: unknown parcel {r.parcel_id}")
        if r.mutation_id and r.mutation_id not in mutation_ids:
            problems.append(f"{r.ownership_id}: unknown mutation {r.mutation_id}")

    for m in world.mutations:
        if m.parcel_id not in parcel_ids:
            problems.append(f"{m.mutation_id}: unknown parcel {m.parcel_id}")
        for oid in (*m.previous_owner_ids, *m.new_owner_ids):
            if oid not in owner_ids:
                problems.append(f"{m.mutation_id}: unknown owner {oid}")

    for u in world.users:
        if u.owner_id and u.owner_id not in owner_ids:
            problems.append(f"{u.user_id}: unknown owner {u.owner_id}")
        if u.jurisdiction_id and u.jurisdiction_id not in location_ids:
            problems.append(f"{u.user_id}: unknown jurisdiction {u.jurisdiction_id}")

    for lr in world.land_records:
        if lr.parcel_id not in parcel_ids:
            problems.append(f"{lr.record_id}: unknown parcel {lr.parcel_id}")

    return problems


def check_unique_ids(world: SyntheticWorld) -> list[str]:
    """Duplicate ids would silently collapse rows at seed time."""
    problems: list[str] = []
    groups = {
        "location": [x.location_id for x in world.locations],
        "owner": [x.owner_id for x in world.owners],
        "parcel": [x.parcel_id for x in world.parcels],
        "ownership": [x.ownership_id for x in world.ownership],
        "mutation": [x.mutation_id for x in world.mutations],
        "land_record": [x.record_id for x in world.land_records],
        "user": [x.user_id for x in world.users],
    }
    for label, ids in groups.items():
        seen, dupes = set(), set()
        for i in ids:
            (dupes if i in seen else seen).add(i)
        for d in sorted(dupes):
            problems.append(f"duplicate {label} id: {d}")
    return problems


ALL_CHECKS = (
    ("unique ids", check_unique_ids),
    ("referential integrity", check_referential_integrity),
    ("ownership shares sum to 1", check_shares_sum_to_one),
    ("timeline continuity", check_no_overlaps_or_gaps),
    ("mutation chronology", check_mutation_chronology),
)


def run_all(world: SyntheticWorld) -> dict[str, list[str]]:
    """Run every check. Returns {check name: problems}."""
    return {label: fn(world) for label, fn in ALL_CHECKS}
