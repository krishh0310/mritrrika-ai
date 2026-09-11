"""Stage 0 step 2 gate: the canonical schema, state machine and confidence rules.

The §45 worked example from the spec is used verbatim as the fixture, so if the
schema drifts away from the document everyone is building against, these fail.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

from mrittika_domain import (  # noqa: E402
    ALLOWED_TRANSITIONS,
    AreaUnit,
    BoundingBox,
    CanonicalLandRecord,
    ConfidenceBand,
    ConfidenceSignals,
    DocumentState,
    DocumentType,
    ExtractedField,
    FieldName,
    FieldStatus,
    IllegalTransitionError,
    assert_transition,
    band_for,
    can_transition,
    fuse,
)

# Spec §45, verbatim, plus the document_type/document_id the pipeline adds.
SPEC_SAMPLE = {
    "document_id": "DOC-00142",
    "parcel_id": "PARCEL-UP-DEMO-0142",
    "document_type": "KHASRA",
    "state": "Uttar Pradesh",
    "district": "Demo District",
    "tehsil": "Demo Tehsil",
    "village": "रामपुर",
    "khasra_number": "142/2",
    "khata_number": "87",
    "owners": [
        {"owner_id": "OWN-0031", "name": "राम प्रसाद सिंह", "share": "1/2"},
        {"owner_id": "OWN-0032", "name": "सीमा देवी", "share": "1/2"},
    ],
    "area": {"value": 2.75, "unit": "BIGHA", "unit_raw": "बीघा"},
    "land_class": "सिंचित",
    "record_year": "1998-99",
}


class TestCanonicalRecord:
    def test_spec_sample_validates(self):
        record = CanonicalLandRecord.model_validate(SPEC_SAMPLE)
        assert record.khasra_number == "142/2"
        assert record.village == "रामपुर"
        assert record.area.unit is AreaUnit.BIGHA
        assert record.area.unit_raw == "बीघा"
        assert len(record.owners) == 2
        assert record.document_type is DocumentType.KHASRA

    def test_round_trips_without_loss(self):
        """Serialise -> parse -> serialise must be a fixed point."""
        record = CanonicalLandRecord.model_validate(SPEC_SAMPLE)
        once = record.model_dump(mode="json", exclude_none=True)
        twice = CanonicalLandRecord.model_validate(once).model_dump(
            mode="json", exclude_none=True
        )
        assert once == twice

    def test_devanagari_survives_serialisation(self):
        """Unicode must not be mangled -- the whole dataset is Devanagari."""
        record = CanonicalLandRecord.model_validate(SPEC_SAMPLE)
        payload = record.model_dump_json()
        assert "रामपुर" in CanonicalLandRecord.model_validate_json(payload).village

    def test_marked_synthetic_by_default(self):
        """§83: nothing may be mistaken for a real citizen record."""
        assert CanonicalLandRecord.model_validate(SPEC_SAMPLE).is_synthetic is True

    def test_unknown_field_rejected(self):
        """extra='forbid' stops silent contract drift between worker and API."""
        with pytest.raises(ValueError):
            CanonicalLandRecord.model_validate({**SPEC_SAMPLE, "surprise": 1})


class TestFieldProvenance:
    def test_raw_and_normalized_both_retained(self):
        """§26: normalization must never destroy the raw OCR value."""
        f = ExtractedField(
            field=FieldName.KHASRA,
            raw_value="१४२ / २",
            normalized_value="142/2",
            ocr_confidence=0.97,
            extraction_confidence=0.94,
            final_confidence=0.95,
            bbox=BoundingBox(x1=100, y1=220, x2=250, y2=270),
            source_page=1,
            status=FieldStatus.AUTO_ACCEPTED,
            model_version="extractor-v1",
        )
        assert f.raw_value == "१४२ / २"
        assert f.normalized_value == "142/2"
        assert f.bbox.width == 150 and f.bbox.height == 50

    def test_inverted_bbox_rejected(self):
        with pytest.raises(ValueError):
            BoundingBox(x1=250, y1=0, x2=100, y2=50)

    def test_low_confidence_fields_are_surfaced(self):
        record = CanonicalLandRecord.model_validate(
            {
                **SPEC_SAMPLE,
                "fields": [
                    {"field": "KHASRA", "final_confidence": 0.95},
                    {"field": "VILLAGE", "final_confidence": 0.44},
                ],
            }
        )
        low = record.low_confidence_fields()
        assert [f.field for f in low] == [FieldName.VILLAGE]


class TestConfidenceFusion:
    def test_is_not_a_blind_average(self):
        """§8 forbids a flat mean. OCR is weighted highest, so a strong OCR
        score with a weak language signal must beat their arithmetic mean."""
        signals = ConfidenceSignals(ocr=1.0, language=0.0)
        assert fuse(signals).score > 0.5

    def test_missing_signals_do_not_penalise(self):
        """Absent evidence is not negative evidence -- weights renormalise."""
        assert fuse(ConfidenceSignals(ocr=0.9)).score == pytest.approx(0.9)

    def test_no_signals_bands_low(self):
        """A field with no evidence must route to review, not silently pass."""
        result = fuse(ConfidenceSignals())
        assert result.score == 0.0
        assert result.band is ConfidenceBand.LOW

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.95, ConfidenceBand.HIGH),
            (0.85, ConfidenceBand.HIGH),
            (0.849, ConfidenceBand.MEDIUM),
            (0.60, ConfidenceBand.MEDIUM),
            (0.599, ConfidenceBand.LOW),
            (0.0, ConfidenceBand.LOW),
        ],
    )
    def test_band_boundaries(self, score, expected):
        assert band_for(score) is expected

    def test_breakdown_is_explainable(self):
        """§68: an officer must be able to see why a field scored what it did."""
        result = fuse(ConfidenceSignals(ocr=0.9, extraction=0.8))
        assert set(result.contributions) == {"ocr", "extraction"}
        assert result.score == pytest.approx(sum(result.contributions.values()))
        assert result.version == "confidence-v1"


class TestDocumentStateMachine:
    def test_happy_path_is_walkable(self):
        path = [
            DocumentState.UPLOADED,
            DocumentState.QUALITY_CHECK,
            DocumentState.PROCESSING,
            DocumentState.AI_EXTRACTED,
            DocumentState.NEEDS_VERIFICATION,
            DocumentState.UNDER_VERIFICATION,
            DocumentState.VERIFIED,
            DocumentState.PENDING_APPROVAL,
            DocumentState.APPROVED,
        ]
        for current, target in zip(path, path[1:], strict=False):
            assert can_transition(current, target), f"{current} -> {target}"

    def test_upload_cannot_jump_to_approved(self):
        """§37 calls this out explicitly as the transition that must fail."""
        assert not can_transition(DocumentState.UPLOADED, DocumentState.APPROVED)
        with pytest.raises(IllegalTransitionError):
            assert_transition(DocumentState.UPLOADED, DocumentState.APPROVED)

    def test_verification_cannot_be_skipped(self):
        assert not can_transition(DocumentState.AI_EXTRACTED, DocumentState.APPROVED)
        assert not can_transition(DocumentState.PROCESSING, DocumentState.VERIFIED)

    def test_archived_is_terminal(self):
        assert ALLOWED_TRANSITIONS[DocumentState.ARCHIVED] == frozenset()

    def test_every_state_has_a_rule(self):
        """A state missing from the map would silently become terminal."""
        assert set(ALLOWED_TRANSITIONS) == set(DocumentState)

    def test_error_message_lists_legal_moves(self):
        with pytest.raises(IllegalTransitionError) as exc:
            assert_transition(DocumentState.UPLOADED, DocumentState.APPROVED)
        assert "QUALITY_CHECK" in str(exc.value)


def test_typescript_mirror_is_current():
    """packages/shared-types must match packages/domain.

    Generated, not hand-written, so drift is a build failure rather than a
    runtime surprise in the browser.
    """
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_shared_types.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


class TestReprocessingCannotSkipVerification:
    """§29 added NEEDS_VERIFICATION -> PROCESSING. It must not open a path to
    APPROVED that avoids a human verifier."""

    def test_every_route_to_approved_passes_under_verification(self):
        from collections import deque

        start = DocumentState.UPLOADED
        seen = {start}
        queue = deque([start])
        while queue:
            state = queue.popleft()
            for target in ALLOWED_TRANSITIONS.get(state, ()):
                if target is DocumentState.UNDER_VERIFICATION or target in seen:
                    continue
                seen.add(target)
                queue.append(target)
        assert DocumentState.APPROVED not in seen, (
            "APPROVED is reachable without passing UNDER_VERIFICATION"
        )

    def test_reprocessing_is_only_open_before_verification_starts(self):
        assert can_transition(DocumentState.NEEDS_VERIFICATION, DocumentState.PROCESSING)
        for later in (DocumentState.UNDER_VERIFICATION, DocumentState.VERIFIED,
                      DocumentState.PENDING_APPROVAL, DocumentState.APPROVED):
            assert not can_transition(later, DocumentState.PROCESSING), later
