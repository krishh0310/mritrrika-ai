"""Stage 1 gate: the synthetic structured world (steps 3-4).

A corrupt ownership timeline is invisible until very late -- it surfaces as a
citizen seeing someone else's land, or the AI assistant confidently citing the
wrong owner. These run the invariants directly against a freshly built world.
"""

import sys
from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "services" / "dataset-generator"))

from mrittika_domain import Role, SyntheticWorld  # noqa: E402
from qa.world_checks import ALL_CHECKS  # noqa: E402
from records.world_builder import (  # noqa: E402
    DEMO_OWNER_A,
    DEMO_OWNER_B,
    DEMO_PARCEL,
    WorldBuilder,
    WorldSpec,
)


@pytest.fixture(scope="module")
def world() -> SyntheticWorld:
    return WorldBuilder(WorldSpec()).build()


@pytest.mark.parametrize("label,check", ALL_CHECKS, ids=[label for label, _ in ALL_CHECKS])
def test_invariant(world, label, check):
    problems = check(world)
    assert not problems, f"{label}: " + "; ".join(problems[:5])


def test_generation_is_deterministic():
    """Same seed must give the same world, or the demo is not reproducible."""
    a = WorldBuilder(WorldSpec(seed=4242)).build()
    b = WorldBuilder(WorldSpec(seed=4242)).build()
    assert a.model_dump_json() == b.model_dump_json()


def test_different_seeds_give_different_worlds():
    a = WorldBuilder(WorldSpec(seed=1)).build()
    b = WorldBuilder(WorldSpec(seed=2)).build()
    assert a.model_dump_json() != b.model_dump_json()


class TestDemoTimeline:
    """The §40 worked example, which demo step 24 asks about directly."""

    def test_1998_sole_owner(self, world):
        active = world.ownership_for(DEMO_PARCEL, date(1998, 12, 31))
        assert [(o.owner_id, o.share) for o in active] == [(DEMO_OWNER_A, "1/1")]

    def test_2006_inheritance_splits_in_half(self, world):
        active = world.ownership_for(DEMO_PARCEL, date(2006, 12, 31))
        assert {(o.owner_id, o.share) for o in active} == {
            (DEMO_OWNER_A, "1/2"),
            (DEMO_OWNER_B, "1/2"),
        }

    def test_2019_sale_consolidates(self, world):
        active = world.ownership_for(DEMO_PARCEL, date(2019, 12, 31))
        assert [(o.owner_id, o.share) for o in active] == [(DEMO_OWNER_B, "1/1")]

    def test_mutations_are_numbered_as_specified(self, world):
        muts = sorted(
            (m for m in world.mutations if m.parcel_id == DEMO_PARCEL),
            key=lambda m: m.effective_date,
        )
        assert [m.mutation_number for m in muts] == ["44", "101"]

    def test_share_sum_holds_on_the_pivot_dates(self, world):
        """Off-by-one interval closing shows up only on the transition date."""
        for pivot in (date(2006, 4, 12), date(2019, 9, 3)):
            active = world.ownership_for(DEMO_PARCEL, pivot)
            assert sum((o.share_fraction for o in active), Fraction(0)) == 1


class TestCitizenSeparation:
    """Groundwork for the §72 isolation test: the two demo citizens must
    genuinely differ, otherwise that test could pass vacuously."""

    def test_both_citizens_hold_land(self, world):
        today = date.today()
        for owner_id in (DEMO_OWNER_A, DEMO_OWNER_B):
            assert world.parcels_for_owner(owner_id, today), f"{owner_id} holds nothing"

    def test_dashboards_are_disjoint(self, world):
        today = date.today()
        a = set(world.parcels_for_owner(DEMO_OWNER_A, today))
        b = set(world.parcels_for_owner(DEMO_OWNER_B, today))
        assert not (a & b), f"citizens share parcels {a & b}"

    def test_each_citizen_has_several_parcels(self, world):
        """'My Land' should be a list, not a single row."""
        today = date.today()
        assert len(world.parcels_for_owner(DEMO_OWNER_A, today)) >= 2
        assert len(world.parcels_for_owner(DEMO_OWNER_B, today)) >= 2

    def test_demo_parcel_is_currently_owner_b(self, world):
        """After the 2019 sale, the demo parcel belongs to सीमा देवी."""
        assert DEMO_PARCEL in world.parcels_for_owner(DEMO_OWNER_B, date.today())
        assert DEMO_PARCEL not in world.parcels_for_owner(DEMO_OWNER_A, date.today())


class TestDemoUsers:
    def test_all_four_roles_exist(self, world):
        assert {u.role for u in world.users} == set(Role)

    def test_citizens_link_to_owners_officers_do_not(self, world):
        for u in world.users:
            if u.role is Role.CITIZEN:
                assert u.owner_id and not u.jurisdiction_id
            else:
                assert u.jurisdiction_id and not u.owner_id

    def test_emails_are_unique(self, world):
        emails = [u.email for u in world.users]
        assert len(emails) == len(set(emails))


class TestSyntheticLabelling:
    def test_everything_is_marked_synthetic(self, world):
        """§83: nothing may be mistaken for a real citizen record."""
        assert all(o.is_synthetic for o in world.owners)
        assert all(p.is_synthetic for p in world.parcels)
        assert all(r.is_synthetic for r in world.land_records)


class TestSpecAlignment:
    """The §45/§46 worked examples name concrete ids -- they must be real."""

    def test_demo_parcel_matches_spec_sample(self, world):
        parcel = next(p for p in world.parcels if p.parcel_id == DEMO_PARCEL)
        assert parcel.khasra_number == "142/2"
        assert parcel.khata_number == "87"
        assert parcel.area_value == 2.75
        assert parcel.area_unit_raw == "बीघा"
        assert parcel.land_class == "सिंचित"

    def test_parcel_0181_from_spec_46_exists(self, world):
        assert any(p.parcel_id == "PARCEL-UP-DEMO-0181" for p in world.parcels)

    def test_demo_parcel_is_in_rampur(self, world):
        """§45 places the sample record in रामपुर."""
        parcel = next(p for p in world.parcels if p.parcel_id == DEMO_PARCEL)
        village = next(loc for loc in world.locations if loc.location_id == parcel.village_id)
        assert village.name_devanagari == "रामपुर"
