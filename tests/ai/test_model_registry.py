"""§64 / §69 — the model registry describes only what runs.

It used to list PP-Structure layout detection, a LayoutLMv3 "wired behind the
same interface", and an IndicBERT extraction assist. No code referenced any of
them. The pipeline's "layout" stage was likewise a progress message with no
work behind it. These tests keep both from coming back.
"""

import importlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

REGISTRY = json.loads((REPO_ROOT / "models" / "registry" / "model_versions.json").read_text())

#: provider -> the code that implements it. A provider missing from this map,
#: or naming a symbol that does not import, fails the test.
IMPLEMENTATIONS = {
    "paddleocr": [("ocr.provider", "PaddleOcrProvider")],
    "geometry-rules": [("extraction.field_extractor", "extract_table_rows")],
    "rules": [("extraction.field_extractor", "extract")],
    "weighted-fusion": [("mrittika_domain.confidence", "fuse")],
    "rules+isolation-forest": [
        ("anomaly.rules", None),
        ("anomaly.detector", "IsolationForestDetector"),
    ],
}

#: Named in the spec, not integrated. They may appear only in `notes`, and
#: only alongside the words "not integrated".
UNINTEGRATED = ("PP-Structure", "LayoutLM", "IndicBERT", "TrOCR", "MuRIL")


@pytest.mark.parametrize("entry", REGISTRY["versions"], ids=lambda e: e["name"])
def test_every_provider_names_real_code(entry):
    assert entry["provider"] in IMPLEMENTATIONS, (
        f"{entry['name']}: provider {entry['provider']!r} has no known implementation"
    )
    for module_name, symbol in IMPLEMENTATIONS[entry["provider"]]:
        module = importlib.import_module(module_name)
        if symbol:
            assert hasattr(module, symbol), f"{module_name}.{symbol} does not exist"


@pytest.mark.parametrize("entry", REGISTRY["versions"], ids=lambda e: e["name"])
def test_unintegrated_models_are_never_described_as_running(entry):
    for name in UNINTEGRATED:
        assert name.lower() not in entry["description"].lower(), (
            f"{entry['name']} describes {name} as part of what runs"
        )
        if name.lower() in entry["notes"].lower():
            assert "not integrated" in entry["notes"].lower(), (
                f"{entry['name']} mentions {name} without saying it is not integrated"
            )


def test_seed_loads_the_registry_rather_than_a_copy():
    """A hard-coded copy in seed_demo.py had drifted and repeated the false claims."""
    source = (REPO_ROOT / "scripts" / "seed_demo.py").read_text()
    assert "MODEL_VERSIONS = [" not in source
    assert "model_versions.json" in source


def test_layout_stage_does_work_before_extraction(monkeypatch):
    """The 'layout' progress stage must be followed by real layout work."""
    import extraction_pipeline as pipeline
    from ocr.provider import OcrResult, TextBlock

    events: list[str] = []
    real_table_rows = pipeline.extract_table_rows

    def spy_table_rows(blocks):
        events.append("table-rows")
        return real_table_rows(blocks)

    monkeypatch.setattr(pipeline, "extract_table_rows", spy_table_rows)

    class FixedEngine:
        """Stands in for OCR only; every later stage is the real code."""

        def recognize(self, image):
            return OcrResult(
                blocks=[TextBlock("खसरा संख्या", 0.95, (80, 100, 260, 140)),
                        TextBlock("१४२/२", 0.93, (300, 100, 400, 140))],
                provider="paddle",
            )

    page = np.full((1200, 1240, 3), 245, np.uint8)
    ok, png = cv2.imencode(".png", page)
    assert ok

    pipeline.run(
        png.tobytes(),
        FixedEngine(),
        progress=lambda stage, percent, message: events.append(stage),
    )

    assert "layout" in events and "extraction" in events
    between = events[events.index("layout") + 1:events.index("extraction")]
    assert between == ["table-rows"], f"nothing ran during the layout stage: {events}"
