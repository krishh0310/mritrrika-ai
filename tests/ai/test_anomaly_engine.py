"""Anomaly rules and the Isolation Forest (§7, §34).

The rules are pure functions over `RecordFeatures`, so they are tested directly
rather than through the API. The properties that matter are that each rule
fires only on its own condition, that every flag carries checkable evidence,
and that no user-facing string accuses anyone of anything.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from anomaly import analyse, evaluable_types  # noqa: E402
from anomaly.detector import (  # noqa: E402
    MIN_CORPUS,
    REPORT_THRESHOLD,
    SKLEARN_AVAILABLE,
    IsolationForestDetector,
)
from anomaly.features import (  # noqa: E402
    FEATURE_NAMES,
    OwnershipSpan,
    RecordFeatures,
    feature_vector,
)
from anomaly.rules import (  # noqa: E402
    ALL_ANOMALY_TYPES,
    ANOMALY_RULES,
    DOCUMENT_DEPENDENT,
    area_jump,
    duplicate_parcel,
    invalid_chronology,
    location_mismatch,
    missing_mutation,
    repeated_modification,
    run_all,
    unusual_ownership_change,
)


def a_record(**overrides) -> RecordFeatures:
    """A clean, unremarkable parcel. Every test perturbs one thing."""
    defaults = dict(
        parcel_id="PARCEL-UP-DEMO-0142",
        has_document=True,
        khasra_number="142/2",
        village_id="VIL-001",
        document_village_id="VIL-001",
        area_value=2.75,
        previous_area_value=2.75,
        record_year=1998,
        current_year=2024,
        ownership_spans=[
            OwnershipSpan("OWN-1", 0.5, date(1998, 1, 1), None),
            OwnershipSpan("OWN-2", 0.5, date(1998, 1, 1), None),
        ],
        mutation_dates=[date(2006, 4, 1)],
        duplicate_parcel_ids=[],
        correction_count=0,
        confidences=[0.95, 0.91],
    )
    defaults.update(overrides)
    return RecordFeatures(**defaults)


class TestCleanRecord:
    def test_a_consistent_record_raises_nothing(self):
        assert run_all(a_record()) == []

    def test_every_rule_returns_none_on_a_clean_record(self):
        record = a_record()
        assert [rule(record) for rule in ANOMALY_RULES] == [None] * len(ANOMALY_RULES)


class TestAreaJump:
    def test_fires_above_the_threshold(self):
        signal = area_jump(a_record(previous_area_value=2.5, area_value=25.0))
        assert signal is not None
        assert signal.anomaly_type == "AREA_JUMP"
        assert signal.evidence["ratio"] == pytest.approx(10.0)

    def test_ignores_a_modest_change(self):
        assert area_jump(a_record(previous_area_value=2.5, area_value=3.0)) is None

    def test_fires_on_a_shrink_as_well_as_a_growth(self):
        assert area_jump(a_record(previous_area_value=25.0, area_value=2.5)) is not None

    def test_no_previous_area_means_no_comparison(self):
        assert area_jump(a_record(previous_area_value=None, area_value=99.0)) is None


class TestChronology:
    def test_out_of_order_mutations_are_flagged(self):
        signal = invalid_chronology(
            a_record(mutation_dates=[date(2019, 1, 1), date(2006, 1, 1)])
        )
        assert signal is not None
        assert signal.evidence["out_of_order_mutations"]

    def test_an_ownership_span_ending_before_it_starts_is_flagged(self):
        signal = invalid_chronology(
            a_record(ownership_spans=[
                OwnershipSpan("OWN-1", 1.0, date(2010, 1, 1), date(2005, 1, 1))
            ])
        )
        assert signal is not None
        assert signal.evidence["inverted_ownership_spans"]

    def test_a_date_violation_scores_maximally(self):
        """It is a fact, not a likelihood -- there is nothing to be unsure of."""
        signal = invalid_chronology(
            a_record(mutation_dates=[date(2019, 1, 1), date(2006, 1, 1)])
        )
        assert signal.score == 1.0


class TestDuplicateParcel:
    def test_a_shared_khasra_is_flagged(self):
        signal = duplicate_parcel(a_record(duplicate_parcel_ids=["PARCEL-UP-DEMO-0999"]))
        assert signal is not None
        assert signal.evidence["other_parcels"] == ["PARCEL-UP-DEMO-0999"]

    def test_the_parcel_itself_does_not_count_as_a_duplicate(self):
        record = a_record(duplicate_parcel_ids=["PARCEL-UP-DEMO-0142"])
        assert duplicate_parcel(record) is None


class TestMissingMutation:
    def test_unexplained_ownership_changes_are_flagged(self):
        signal = missing_mutation(a_record(
            ownership_spans=[
                OwnershipSpan("OWN-1", 1.0, date(1998, 1, 1), date(2006, 1, 1)),
                OwnershipSpan("OWN-2", 1.0, date(2006, 1, 1), date(2015, 1, 1)),
                OwnershipSpan("OWN-3", 1.0, date(2015, 1, 1), None),
            ],
            mutation_dates=[],
        ))
        assert signal is not None
        assert signal.evidence["unexplained"] == 2

    def test_co_owners_from_one_event_are_not_two_changes(self):
        """A jointly-held parcel has two spans but only one transfer.

        Counting spans instead of distinct start dates flagged half the seeded
        cadastre as having an unexplained transfer.
        """
        jointly_held = a_record(
            ownership_spans=[
                OwnershipSpan("OWN-1", 0.5, date(2006, 1, 1), None),
                OwnershipSpan("OWN-2", 0.5, date(2006, 1, 1), None),
            ],
            mutation_dates=[date(2006, 1, 1)],
        )
        assert jointly_held.ownership_change_count == 0
        assert missing_mutation(jointly_held) is None

    def test_changes_matched_by_mutations_are_not_flagged(self):
        assert missing_mutation(a_record(
            ownership_spans=[
                OwnershipSpan("OWN-1", 1.0, date(1998, 1, 1), date(2006, 1, 1)),
                OwnershipSpan("OWN-2", 1.0, date(2006, 1, 1), None),
            ],
            mutation_dates=[date(2006, 1, 1)],
        )) is None


class TestLocationMismatch:
    def test_a_document_from_another_village_is_flagged(self):
        signal = location_mismatch(a_record(document_village_id="VIL-999"))
        assert signal is not None
        assert signal.evidence["parcel_village_id"] == "VIL-001"

    def test_an_unlinked_document_cannot_mismatch(self):
        assert location_mismatch(a_record(document_village_id=None)) is None


class TestRepeatedModification:
    def test_a_high_mutation_rate_is_flagged(self):
        signal = repeated_modification(a_record(
            record_year=2020, current_year=2024,
            mutation_dates=[date(2021, 1, 1)] * 8,
        ))
        assert signal is not None
        assert signal.evidence["rate_per_year"] > 1.0

    def test_a_long_quiet_history_is_not_flagged(self):
        assert repeated_modification(a_record(
            record_year=1960, current_year=2024,
            mutation_dates=[date(1990, 1, 1), date(2005, 1, 1), date(2019, 1, 1)],
        )) is None


class TestOwnershipShares:
    def test_shares_that_do_not_total_one_are_flagged(self):
        signal = unusual_ownership_change(a_record(ownership_spans=[
            OwnershipSpan("OWN-1", 0.5, date(1998, 1, 1), None),
            OwnershipSpan("OWN-2", 0.25, date(1998, 1, 1), None),
        ]))
        assert signal is not None
        assert signal.evidence["share_total"] == 0.75

    def test_historical_spans_do_not_count_toward_the_current_total(self):
        """A closed span is not a current holding, so it must not inflate it."""
        assert unusual_ownership_change(a_record(ownership_spans=[
            OwnershipSpan("OWN-0", 1.0, date(1990, 1, 1), date(1998, 1, 1)),
            OwnershipSpan("OWN-1", 0.5, date(1998, 1, 1), None),
            OwnershipSpan("OWN-2", 0.5, date(1998, 1, 1), None),
        ])) is None


class TestWording:
    """§34 -- a flag describes an inconsistency, never an accusation."""

    FORBIDDEN = ("fraud", "fraudulent", "forged", "criminal", "illegal", "fake")

    def _all_signals(self):
        return (
            run_all(a_record(previous_area_value=2.5, area_value=40.0))
            + run_all(a_record(mutation_dates=[date(2019, 1, 1), date(2006, 1, 1)]))
            + run_all(a_record(duplicate_parcel_ids=["PARCEL-X"]))
            + run_all(a_record(document_village_id="VIL-999"))
        )

    def test_no_signal_accuses_anyone(self):
        for signal in self._all_signals():
            lowered = signal.explanation.lower()
            for word in self.FORBIDDEN:
                assert word not in lowered, f"{signal.anomaly_type} says {word!r}"

    def test_every_signal_carries_evidence(self):
        for signal in self._all_signals():
            assert signal.evidence, f"{signal.anomaly_type} has no evidence (§68)"

    def test_every_signal_recommends_investigation(self):
        for signal in self._all_signals():
            assert "investigation recommended" in signal.explanation.lower()


class TestFeatureVector:
    def test_vector_matches_the_declared_names(self):
        assert len(feature_vector(a_record())) == len(FEATURE_NAMES)

    def test_mutation_rate_is_normalised_by_age(self):
        old = a_record(record_year=1960, current_year=2020,
                       mutation_dates=[date(2000, 1, 1)] * 6)
        young = a_record(record_year=2018, current_year=2020,
                         mutation_dates=[date(2019, 1, 1)] * 6)
        assert young.mutations_per_year > old.mutations_per_year


class TestDetector:
    def test_reports_unavailable_before_fitting(self):
        detector = IsolationForestDetector()
        assert detector.available is False
        assert detector.score(a_record()) is None
        assert detector.unavailable_reason

    def test_a_tiny_corpus_does_not_produce_a_model(self):
        """Fitting on five parcels would call almost anything an outlier."""
        detector = IsolationForestDetector()
        assert detector.fit([a_record() for _ in range(5)]) is False
        assert detector.available is False
        assert str(MIN_CORPUS) in detector.unavailable_reason

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
    def test_fits_on_an_adequate_corpus(self):
        detector = IsolationForestDetector()
        corpus = [a_record(area_value=2.5 + i * 0.01) for i in range(MIN_CORPUS + 20)]
        assert detector.fit(corpus) is True
        assert detector.available is True

        score = detector.score(a_record())
        assert score is not None
        assert 0.0 <= score <= 1.0

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
    def test_a_far_outlier_scores_above_a_typical_record(self):
        detector = IsolationForestDetector()
        corpus = [a_record(area_value=2.5 + i * 0.01) for i in range(MIN_CORPUS + 20)]
        detector.fit(corpus)

        typical = detector.score(a_record(area_value=2.6))
        extreme = detector.score(a_record(area_value=5000.0, mutation_dates=[]))
        assert extreme > typical

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
    def test_only_sufficiently_unusual_records_become_signals(self):
        detector = IsolationForestDetector()
        detector.fit([a_record(area_value=2.5 + i * 0.01) for i in range(MIN_CORPUS + 20)])
        signal = detector.signal(a_record(area_value=2.6))
        assert signal is None or signal.score >= REPORT_THRESHOLD


class TestEngine:
    def test_rules_run_without_a_detector(self):
        """§82 -- the rules engine must not depend on the optional model."""
        signals = analyse(a_record(previous_area_value=2.5, area_value=25.0), None)
        assert [s.anomaly_type for s in signals] == ["AREA_JUMP"]

    def test_signals_are_ordered_by_score(self):
        signals = analyse(
            a_record(
                previous_area_value=2.5, area_value=40.0,
                mutation_dates=[date(2019, 1, 1), date(2006, 1, 1)],
            ),
            None,
        )
        assert [s.score for s in signals] == sorted(
            (s.score for s in signals), reverse=True
        )

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
    def test_an_outlier_score_is_suppressed_when_a_rule_already_fired(self):
        """"Also unusual" adds noise on top of "these dates run backwards"."""
        detector = IsolationForestDetector()
        detector.fit([a_record(area_value=2.5 + i * 0.01) for i in range(MIN_CORPUS + 20)])

        signals = analyse(
            a_record(area_value=5000.0, previous_area_value=2.5), detector
        )
        assert all(s.anomaly_type != "UNUSUAL_PATTERN" for s in signals)


class TestEvaluableTypes:
    """A pass that cannot judge a rule must not close that rule's flags."""

    def test_a_document_pass_can_evaluate_everything(self):
        assert evaluable_types(a_record(has_document=True)) == ALL_ANOMALY_TYPES

    def test_a_parcel_only_pass_excludes_document_dependent_rules(self):
        types = evaluable_types(a_record(has_document=False))
        assert types == ALL_ANOMALY_TYPES - DOCUMENT_DEPENDENT
        assert "LOCATION_MISMATCH" not in types
        assert "MISSING_MUTATION" in types

    def test_every_rule_name_appears_in_the_type_set(self):
        """A rule whose type is missing here would never be reconcilable."""
        produced = {
            signal.anomaly_type
            for record in (
                a_record(previous_area_value=2.5, area_value=40.0),
                a_record(mutation_dates=[date(2019, 1, 1), date(2006, 1, 1)]),
                a_record(duplicate_parcel_ids=["PARCEL-X"]),
                a_record(document_village_id="VIL-999"),
                a_record(ownership_spans=[
                    OwnershipSpan("OWN-1", 0.5, date(1998, 1, 1), None),
                ]),
            )
            for signal in run_all(record)
        }
        assert produced <= ALL_ANOMALY_TYPES


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
def test_failed_refit_does_not_reuse_previous_corpus():
    detector = IsolationForestDetector()
    assert detector.fit([a_record(area_value=2.5 + i * 0.01) for i in range(40)])
    assert not detector.fit([a_record()])
    assert not detector.available
    assert detector.score(a_record()) is None
