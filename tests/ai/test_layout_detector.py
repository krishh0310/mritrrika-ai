"""Layout region detection and the extraction scoping it enables (§6, §82).

Two things are worth guarding here, and neither is "does YOLO work".

First, the fallback contract. This detector is optional by construction: the
weights are a gitignored binary, and ultralytics need not be installed at all.
Every one of those paths must leave extraction running exactly as it did
before the detector existed. A vision model that cannot load may cost accuracy;
it may never cost correctness.

Second, the scoping rule. Regions are allowed to DROP a page-metadata value
that was read from inside a table, and allowed to do nothing else. They may not
rewrite a value, may not invent one, and may not touch a field that legitimately
appears as a table column.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from extraction.field_extractor import (  # noqa: E402
    HEADER_ONLY_FIELDS,
    ExtractedValue,
    _crosses_a_table_boundary,
    extract,
)
from layout import LayoutDetector, LayoutRegion, build_default_detector  # noqa: E402
from ocr.provider import TextBlock  # noqa: E402


def region(kind="table", box=(100, 400, 1100, 800), conf=0.9) -> LayoutRegion:
    return LayoutRegion(type=kind, bbox=box, confidence=conf)


def value(field: str, box) -> ExtractedValue:
    return ExtractedValue(
        field=field, raw_value="x", bbox=box,
        ocr_confidence=0.9, extraction_confidence=0.9, source_block_index=0,
    )


class TestFallbackContract:
    """§82: unavailable must mean inert, never broken."""

    def test_missing_weights_reports_unavailable(self, tmp_path):
        detector = LayoutDetector(tmp_path / "nope.pt")
        assert detector.available is False
        assert "no weights" in detector.unavailable_reason

    def test_missing_weights_detects_nothing_rather_than_raising(self, tmp_path):
        assert LayoutDetector(tmp_path / "nope.pt").detect("anything.png") == []

    def test_default_detector_is_constructible_without_weights(self):
        """Importing and building it must never be what breaks a worker."""
        detector = build_default_detector()
        assert detector.detect("anything.png") == []

    def test_unavailable_reason_is_none_only_when_loaded(self, tmp_path):
        detector = LayoutDetector(tmp_path / "nope.pt")
        assert detector.available is False
        assert detector.unavailable_reason is not None


class TestRegionGeometry:
    def test_contains_accepts_a_box_inside(self):
        assert region().contains((200, 500, 300, 550))

    def test_contains_rejects_a_box_outside(self):
        assert not region().contains((200, 100, 300, 150))

    def test_contains_allows_rounding_slack(self):
        assert region(box=(100, 400, 1100, 800)).contains((97, 397, 300, 500))

    def test_to_dict_is_json_shaped(self):
        assert region().to_dict() == {
            "type": "table", "bbox": [100, 400, 1100, 800], "confidence": 0.9,
        }


class TestScopingRule:
    def test_header_only_field_inside_a_table_is_dropped(self):
        assert _crosses_a_table_boundary(value("VILLAGE", (200, 500, 300, 550)), [region()])

    def test_header_only_field_outside_a_table_is_kept(self):
        assert not _crosses_a_table_boundary(value("VILLAGE", (200, 100, 300, 150)), [region()])

    @pytest.mark.parametrize("field", ["KHASRA", "AREA", "LAND_CLASS"])
    def test_fields_that_are_also_table_columns_are_never_scoped(self, field):
        """These appear 167 times as cells. Scoping them would delete truth."""
        assert not _crosses_a_table_boundary(value(field, (200, 500, 300, 550)), [region()])
        assert field not in HEADER_ONLY_FIELDS

    def test_a_header_region_never_drops_anything(self):
        header = region(kind="header", box=(0, 0, 1200, 900))
        assert not _crosses_a_table_boundary(value("VILLAGE", (200, 500, 300, 550)), [header])

    @pytest.mark.parametrize("field", ["OWNER", "GUARDIAN", "SHARE"])
    def test_table_column_fields_are_not_header_only(self, field):
        assert field not in HEADER_ONLY_FIELDS


class TestExtractIsUnchangedWithoutRegions:
    """The detector is additive. No regions must mean the previous behaviour."""

    def _blocks(self) -> list[TextBlock]:
        return [
            TextBlock("ग्राम", 0.95, (100, 100, 180, 130)),
            TextBlock("रामपुर", 0.95, (200, 100, 300, 130)),
            TextBlock("खसरा सं", 0.95, (100, 160, 200, 190)),
            TextBlock("१४०", 0.95, (220, 160, 270, 190)),
        ]

    def test_none_and_empty_regions_agree(self):
        blocks = self._blocks()
        without = extract(blocks)
        empty = extract(blocks, regions=[])
        assert [(v.field, v.raw_value) for v in without.values] == \
               [(v.field, v.raw_value) for v in empty.values]

    def test_regions_elsewhere_on_the_page_change_nothing(self):
        blocks = self._blocks()
        far = [region(box=(0, 900, 1200, 1100))]
        assert [(v.field, v.raw_value) for v in extract(blocks, regions=far).values] == \
               [(v.field, v.raw_value) for v in extract(blocks).values]

    def test_a_table_over_the_village_drops_only_that_field(self):
        blocks = self._blocks()
        covering = [region(box=(50, 50, 1200, 400))]
        before = {v.field for v in extract(blocks).values}
        after = {v.field for v in extract(blocks, regions=covering).values}
        assert "VILLAGE" in before
        assert "VILLAGE" not in after
        # KHASRA is a legitimate table column, so it survives the same region.
        assert ("KHASRA" in before) == ("KHASRA" in after)


class TestModelConfig:
    """The base model is named in one place and inference stays opt-in."""

    def test_the_base_model_is_yolo11n(self):
        from config.cv_config import YOLO_MODEL

        assert YOLO_MODEL == "yolo11n.pt"

    def test_training_defaults_to_the_configured_base(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "train_layout_detector", REPO_ROOT / "scripts" / "train_layout_detector.py")
        source = spec.loader.get_source("train_layout_detector")
        assert 'default=YOLO_MODEL' in source
        assert "yolov8n.pt" not in source

    def test_inference_loads_the_configured_checkpoint(self):
        from config.cv_config import LAYOUT_CHECKPOINT
        from layout.detector import DEFAULT_WEIGHTS

        assert LAYOUT_CHECKPOINT in DEFAULT_WEIGHTS.parts

    def test_the_detector_is_off_unless_use_yolo_is_set(self, monkeypatch):
        sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
        from app.config.settings import get_settings
        from app.services import pipeline_service

        monkeypatch.setattr(get_settings(), "use_yolo", False)
        assert pipeline_service.get_layout_detector() is None
