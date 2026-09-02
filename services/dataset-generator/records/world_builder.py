"""Build the synthetic structured world: locations, owners, parcels, ownership
history, mutations and demo logins (Stage 1, steps 3-4).

Order matters. Spec §44 is absolute: **structured ground truth exists BEFORE
any document is rendered.** Nothing here looks at an image, and nothing
downstream may derive a label by OCRing a generated image.

Two invariants are maintained by construction rather than checked afterwards:

  1. Active ownership shares for a parcel sum to exactly 1 on every date.
     Enforced by doing all share arithmetic in `Fraction`, never float.
  2. Ownership intervals for a parcel never overlap and never gap: closing a
     record and opening its successor happen in the same operation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

from mrittika_domain import (
    AreaUnit,
    DocumentType,
    LandRecord,
    Location,
    Mutation,
    MutationType,
    Owner,
    OwnershipRecord,
    Parcel,
    Role,
    SyntheticUser,
    SyntheticWorld,
)

from . import names as pools

# The two demo citizens are fixed, not random: the §70 demo script and the §72
# isolation test both refer to them by name and must stay stable across runs.
DEMO_OWNER_A = "OWN-0031"  # राम प्रसाद सिंह -- holds several parcels
DEMO_OWNER_B = "OWN-0032"  # सीमा देवी      -- co-owner, then sole owner
DEMO_PARCEL = "PARCEL-UP-DEMO-0142"  # the parcel the whole demo follows


@dataclass
class WorldSpec:
    """Size knobs. Slice 1 stays deliberately small (see the build plan)."""

    seed: int = 20260831
    villages: int = 2
    parcels_per_village: int = 20
    extra_owners: int = 24


class WorldBuilder:
    def __init__(self, spec: WorldSpec) -> None:
        self.spec = spec
        self.rng = random.Random(spec.seed)
        self._mutation_seq = 0
        self._ownership_seq = 0

    # ── ids ──────────────────────────────────────────────────────────────
    def _next_ownership_id(self) -> str:
        self._ownership_seq += 1
        return f"OWNS-{self._ownership_seq:05d}"

    def _next_mutation_id(self) -> str:
        self._mutation_seq += 1
        return f"MUT-{self._mutation_seq:05d}"

    # ── locations ────────────────────────────────────────────────────────
    def build_locations(self) -> list[Location]:
        state = Location(
            location_id="LOC-STATE-UP",
            name=pools.STATE[1],
            name_devanagari=pools.STATE[0],
            level="STATE",
        )
        district = Location(
            location_id="LOC-DIST-DEMO",
            name=pools.DISTRICT[1],
            name_devanagari=pools.DISTRICT[0],
            level="DISTRICT",
            parent_id=state.location_id,
        )
        tehsil = Location(
            location_id="LOC-TEH-DEMO",
            name=pools.TEHSIL[1],
            name_devanagari=pools.TEHSIL[0],
            level="TEHSIL",
            parent_id=district.location_id,
        )
        if self.spec.villages > len(pools.VILLAGES):
            # Silently truncating makes a profile lie about its own size: v1
            # asked for 4 villages, got 2, and every downstream count was half
            # what the profile advertised.
            raise ValueError(
                f"profile asks for {self.spec.villages} villages but only "
                f"{len(pools.VILLAGES)} names are defined in pools.VILLAGES"
            )
        villages = [
            Location(
                location_id=f"LOC-VIL-{i:02d}",
                name=latin,
                name_devanagari=deva,
                level="VILLAGE",
                parent_id=tehsil.location_id,
            )
            for i, (deva, latin) in enumerate(pools.VILLAGES[: self.spec.villages], 1)
        ]
        return [state, district, tehsil, *villages]

    # ── owners ───────────────────────────────────────────────────────────
    def build_owners(self) -> list[Owner]:
        owners = [
            Owner(owner_id=DEMO_OWNER_A, name="राम प्रसाद सिंह", guardian_name="स्व. मोहन सिंह"),
            Owner(owner_id=DEMO_OWNER_B, name="सीमा देवी", guardian_name="राम प्रसाद सिंह"),
        ]
        used = {o.name for o in owners}
        n = 33
        while len(owners) < self.spec.extra_owners + 2:
            feminine = self.rng.random() < 0.4
            given = self.rng.choice(
                pools.GIVEN_NAMES_FEMININE if feminine else pools.GIVEN_NAMES_MASCULINE
            )
            surname = (
                "देवी" if feminine and self.rng.random() < 0.5
                else self.rng.choice(pools.SURNAMES)
            )
            name = f"{given} {surname}"
            if name in used:
                continue
            used.add(name)
            owners.append(
                Owner(
                    owner_id=f"OWN-{n:04d}",
                    name=name,
                    guardian_name=(
                        f"{self.rng.choice(pools.GIVEN_NAMES_MASCULINE)} "
                        f"{self.rng.choice(pools.SURNAMES)}"
                    ),
                )
            )
            n += 1
        return owners

    # ── parcels ──────────────────────────────────────────────────────────
    def build_parcels(self, villages: list[Location]) -> list[Parcel]:
        parcels: list[Parcel] = []
        # Base 140 with 40 per village puts khasra 142 in the first village
        # (रामपुर, matching the §45 sample) and 181 in the second, so the demo
        # parcel ids named in §45/§46 are real rather than aspirational.
        khasra_base = 140
        for v_index, village in enumerate(villages):
            for i in range(self.spec.parcels_per_village):
                khasra_n = khasra_base + v_index * 40 + i
                # Roughly a third of plots are sub-divided, as in real records.
                khasra = (
                    f"{khasra_n}/{self.rng.randint(1, 3)}"
                    if self.rng.random() < 0.35 else str(khasra_n)
                )
                unit = AreaUnit.BIGHA if self.rng.random() < 0.8 else AreaUnit.HECTARE
                area = (
                    round(self.rng.uniform(0.5, 8.0), 2)
                    if unit is AreaUnit.BIGHA
                    else round(self.rng.uniform(0.1, 2.5), 2)
                )
                parcels.append(
                    Parcel(
                        parcel_id=f"PARCEL-UP-DEMO-{khasra_n:04d}",
                        village_id=village.location_id,
                        khasra_number=khasra,
                        khata_number=str(self.rng.randint(10, 240)),
                        area_value=area,
                        area_unit=unit,
                        area_unit_raw=pools.AREA_UNITS_RAW[unit.value],
                        land_class=self.rng.choice(pools.LAND_CLASSES),
                    )
                )

        # Pin the demo parcel so the §70 script and §45 sample line up exactly.
        demo = next(p for p in parcels if p.parcel_id == DEMO_PARCEL)
        demo.khasra_number = "142/2"
        demo.khata_number = "87"
        demo.area_value = 2.75
        demo.area_unit = AreaUnit.BIGHA
        demo.area_unit_raw = "बीघा"
        demo.land_class = "सिंचित"
        return parcels

    # ── ownership + mutations ────────────────────────────────────────────
    def _open(
        self,
        parcel_id: str,
        owner_id: str,
        share: Fraction,
        start: date,
        mutation_id: str | None,
    ) -> OwnershipRecord:
        return OwnershipRecord(
            ownership_id=self._next_ownership_id(),
            owner_id=owner_id,
            parcel_id=parcel_id,
            share=f"{share.numerator}/{share.denominator}",
            valid_from=start,
            valid_to=None,
            mutation_id=mutation_id,
        )

    def _close_all(
        self, records: list[OwnershipRecord], parcel_id: str, on: date
    ) -> list[OwnershipRecord]:
        """Close every open interest on a parcel the day before `on`.

        Closing at `on - 1 day` rather than `on` keeps intervals half-open, so
        the successor's valid_from == `on` produces neither a gap nor an
        overlap. Without this the share-sum invariant breaks on the pivot date.
        """
        closed = []
        for r in records:
            if r.parcel_id == parcel_id and r.valid_to is None:
                r.valid_to = on - timedelta(days=1)
                r.status = "SUPERSEDED"
                closed.append(r)
        return closed

    def build_demo_history(
        self, ownership: list[OwnershipRecord], mutations: list[Mutation]
    ) -> None:
        """The §40 worked timeline, on the parcel the demo follows.

            1998  राम प्रसाद सिंह  1/1
              -> 2006, mutation 44 (inheritance): + सीमा देवी, 1/2 each
              -> 2019, mutation 101 (sale):        सीमा देवी 1/1

        Hard-coded because demo step 24 asks "who was the recorded owner in
        1998?" and the answer must be stable across regenerations.
        """
        ownership.append(
            self._open(DEMO_PARCEL, DEMO_OWNER_A, Fraction(1), date(1998, 7, 1), None)
        )

        m44_date = date(2006, 4, 12)
        self._close_all(ownership, DEMO_PARCEL, m44_date)
        m44 = Mutation(
            mutation_id=self._next_mutation_id(),
            parcel_id=DEMO_PARCEL,
            mutation_number="44",
            mutation_type=MutationType.INHERITANCE,
            effective_date=m44_date,
            registration_date=m44_date + timedelta(days=21),
            previous_owner_ids=[DEMO_OWNER_A],
            new_owner_ids=[DEMO_OWNER_A, DEMO_OWNER_B],
        )
        mutations.append(m44)
        ownership.append(
            self._open(DEMO_PARCEL, DEMO_OWNER_A, Fraction(1, 2), m44_date, m44.mutation_id)
        )
        ownership.append(
            self._open(DEMO_PARCEL, DEMO_OWNER_B, Fraction(1, 2), m44_date, m44.mutation_id)
        )

        m101_date = date(2019, 9, 3)
        self._close_all(ownership, DEMO_PARCEL, m101_date)
        m101 = Mutation(
            mutation_id=self._next_mutation_id(),
            parcel_id=DEMO_PARCEL,
            mutation_number="101",
            mutation_type=MutationType.SALE,
            effective_date=m101_date,
            registration_date=m101_date + timedelta(days=14),
            previous_owner_ids=[DEMO_OWNER_A, DEMO_OWNER_B],
            new_owner_ids=[DEMO_OWNER_B],
        )
        mutations.append(m101)
        ownership.append(
            self._open(DEMO_PARCEL, DEMO_OWNER_B, Fraction(1), m101_date, m101.mutation_id)
        )

    def build_history(
        self, parcels: list[Parcel], owners: list[Owner]
    ) -> tuple[list[OwnershipRecord], list[Mutation]]:
        ownership: list[OwnershipRecord] = []
        mutations: list[Mutation] = []
        pool = [o.owner_id for o in owners]

        self.build_demo_history(ownership, mutations)

        for parcel in parcels:
            if parcel.parcel_id == DEMO_PARCEL:
                continue

            start = date(self.rng.randint(1992, 2002), self.rng.randint(1, 12), 1)
            holders: list[tuple[str, Fraction]]
            if self.rng.random() < 0.25:
                a, b = self.rng.sample(pool, 2)
                holders = [(a, Fraction(1, 2)), (b, Fraction(1, 2))]
            else:
                holders = [(self.rng.choice(pool), Fraction(1))]

            for owner_id, share in holders:
                ownership.append(
                    self._open(parcel.parcel_id, owner_id, share, start, None)
                )

            # 0-2 later mutations, always chronologically after `start`.
            when = start
            for _ in range(self.rng.choice([0, 0, 1, 1, 2])):
                gap = self.rng.randint(3, 12)
                when = date(when.year + gap, self.rng.randint(1, 12), self.rng.randint(1, 28))
                if when.year > 2024:
                    break
                holders = self._apply_mutation(
                    parcel.parcel_id, holders, when, pool, ownership, mutations
                )

        # Give the two demo citizens a second parcel each, so "My Land" shows a
        # list rather than a single row, and so the §72 isolation test has a
        # parcel on each side that the other must not reach.
        known = {p.parcel_id for p in parcels}
        self._grant(ownership, known, "PARCEL-UP-DEMO-0181", DEMO_OWNER_A, date(2011, 2, 14))
        self._grant(ownership, known, "PARCEL-UP-DEMO-0190", DEMO_OWNER_B, date(2015, 6, 9))

        return ownership, mutations

    def _grant(
        self,
        ownership: list[OwnershipRecord],
        known_parcels: set[str],
        parcel_id: str,
        owner_id: str,
        when: date,
    ) -> None:
        """Hand a whole parcel to one owner, superseding whoever held it.

        Fails loudly on an unknown parcel: a silent dangling grant would leave
        a demo citizen with a parcel that does not exist, which surfaces much
        later as an empty 'My Land' page with no obvious cause.
        """
        if parcel_id not in known_parcels:
            raise ValueError(
                f"cannot grant unknown parcel {parcel_id} to {owner_id}; "
                f"check the khasra numbering in build_parcels()"
            )
        # The parcel may already carry randomly generated mutations that run
        # past `when`. Closing those at an earlier date would invert their
        # interval, so the grant is pushed to the day after the last event.
        latest = max(
            (r.valid_from for r in ownership if r.parcel_id == parcel_id),
            default=None,
        )
        effective = when if latest is None else max(when, latest + timedelta(days=1))
        self._close_all(ownership, parcel_id, effective)
        ownership.append(self._open(parcel_id, owner_id, Fraction(1), effective, None))

    def _apply_mutation(
        self,
        parcel_id: str,
        holders: list[tuple[str, Fraction]],
        when: date,
        pool: list[str],
        ownership: list[OwnershipRecord],
        mutations: list[Mutation],
    ) -> list[tuple[str, Fraction]]:
        """Transform the holder set, preserving sum(share) == 1 exactly."""
        previous = [oid for oid, _ in holders]

        if len(holders) == 1 and self.rng.random() < 0.5:
            # Inheritance / gift: sole owner becomes two co-owners.
            heir = self.rng.choice([o for o in pool if o != holders[0][0]])
            new_holders = [(holders[0][0], Fraction(1, 2)), (heir, Fraction(1, 2))]
            mtype = MutationType.INHERITANCE
        elif len(holders) > 1:
            # Partition/sale: one co-owner consolidates the whole parcel.
            keeper = self.rng.choice(holders)[0]
            new_holders = [(keeper, Fraction(1))]
            mtype = MutationType.PARTITION
        else:
            # Outright sale to a new party.
            buyer = self.rng.choice([o for o in pool if o != holders[0][0]])
            new_holders = [(buyer, Fraction(1))]
            mtype = MutationType.SALE

        self._close_all(ownership, parcel_id, when)
        mutation = Mutation(
            mutation_id=self._next_mutation_id(),
            parcel_id=parcel_id,
            mutation_number=str(self.rng.randint(10, 400)),
            mutation_type=mtype,
            effective_date=when,
            registration_date=when + timedelta(days=self.rng.randint(7, 60)),
            previous_owner_ids=previous,
            new_owner_ids=[oid for oid, _ in new_holders],
        )
        mutations.append(mutation)
        for owner_id, share in new_holders:
            ownership.append(
                self._open(parcel_id, owner_id, share, when, mutation.mutation_id)
            )
        return new_holders

    # ── records + users ──────────────────────────────────────────────────
    def build_land_records(self, parcels: list[Parcel]) -> list[LandRecord]:
        types = [
            DocumentType.KHASRA,
            DocumentType.KHATAUNI,
            DocumentType.MUTATION_REGISTER,
        ]
        records = []
        for i, parcel in enumerate(parcels, 1):
            year_start = self.rng.choice([1995, 1998, 2003, 2010, 2016])
            records.append(
                LandRecord(
                    record_id=f"LR-UP-{i:06d}",
                    parcel_id=parcel.parcel_id,
                    document_type=types[i % len(types)],
                    record_year=f"{year_start}-{str(year_start + 1)[-2:]}",
                )
            )
        return records

    def build_users(self, owners: list[Owner]) -> list[SyntheticUser]:
        by_id = {o.owner_id: o for o in owners}
        return [
            SyntheticUser(
                user_id="USR-C-0031",
                role=Role.CITIZEN,
                name=by_id[DEMO_OWNER_A].name,
                email="ram31@mrittika.demo",
                owner_id=DEMO_OWNER_A,
            ),
            SyntheticUser(
                user_id="USR-C-0032",
                role=Role.CITIZEN,
                name=by_id[DEMO_OWNER_B].name,
                email="seema32@mrittika.demo",
                owner_id=DEMO_OWNER_B,
            ),
            SyntheticUser(
                user_id="USR-D-0001",
                role=Role.DEO,
                name="अनिल कुमार",
                email="deo@mrittika.demo",
                jurisdiction_id="LOC-TEH-DEMO",
            ),
            SyntheticUser(
                user_id="USR-V-0001",
                role=Role.VERIFIER,
                name="सुनीता शर्मा",
                email="lekhpal@mrittika.demo",
                jurisdiction_id="LOC-TEH-DEMO",
            ),
            SyntheticUser(
                user_id="USR-T-0001",
                role=Role.TEHSILDAR,
                name="राजेश मिश्रा",
                email="tehsildar@mrittika.demo",
                jurisdiction_id="LOC-DIST-DEMO",
            ),
        ]

    # ── entry point ──────────────────────────────────────────────────────
    def build(self) -> SyntheticWorld:
        locations = self.build_locations()
        villages = [loc for loc in locations if loc.level == "VILLAGE"]
        owners = self.build_owners()
        parcels = self.build_parcels(villages)
        ownership, mutations = self.build_history(parcels, owners)
        return SyntheticWorld(
            seed=self.spec.seed,
            locations=locations,
            owners=owners,
            parcels=parcels,
            ownership=ownership,
            mutations=mutations,
            land_records=self.build_land_records(parcels),
            users=self.build_users(owners),
        )
