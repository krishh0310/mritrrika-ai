"""Stage 1 steps 6-7 gate: rendering, degradation, annotation and splitting.

The defect that matters most here is an annotation that does not describe the
image it is attached to. Because ground truth is generated BEFORE rendering
(§44), such a dataset trains and evaluates against text the page does not
contain -- and it presents as poor model accuracy, not as a data bug.
"""

import json
import random
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "datasets"
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "services" / "dataset-generator"))

from degradation.engine import perspective, rescale, rotate  # noqa: E402
from degradation.profiles import DIFFICULTY_MIX, TIERS, degrade  # noqa: E402
from mrittika_domain.dataset_paths import (  # noqa: E402
    SPLIT_NAMES,
    active_profile,
    index_path,
    split_path,
)
from rendering.canvas import RecordingCanvas  # noqa: E402
from templates.base import DocumentContext  # noqa: E402
from templates.layouts import TEMPLATES  # noqa: E402

SAMPLE_CTX = DocumentContext(
    document_id="DOC-TEST",
    parcel_id="PARCEL-UP-DEMO-0142",
    state="उत्तर प्रदेश",
    district="डेमो जिला",
    tehsil="डेमो तहसील",
    village="रामपुर",
    khasra_number="142/2",
    khata_number="87",
    area_value=2.75,
    area_unit_raw="बीघा",
    land_class="सिंचित",
    record_year="1998-99",
    owners=[("राम प्रसाद सिंह", "1/2"), ("सीमा देवी", "1/2")],
    guardian="स्व. मोहन सिंह",
    mutation_number="44",
    mutation_type="उत्तराधिकार",
    mutation_date="12/04/2006",
    previous_owners=["राम प्रसाद सिंह"],
)


def _ink_bounds(image: Image.Image, threshold: int = 140):
    arr = np.array(image.convert("L"))
    ys, xs = np.where(arr < threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


class TestRendering:
    @pytest.mark.parametrize("template", sorted(TEMPLATES))
    def test_template_renders_and_annotates(self, template):
        _, render = TEMPLATES[template]
        page = render(SAMPLE_CTX)
        assert page.value_regions(), f"{template} annotated no values"
        assert page.layout_boxes, f"{template} recorded no layout regions"

    @pytest.mark.parametrize("template", sorted(TEMPLATES))
    def test_every_recorded_box_contains_ink(self, template):
        """The bbox must describe where the text actually is."""
        _, render = TEMPLATES[template]
        page = render(SAMPLE_CTX)
        arr = np.array(page.image.convert("L"), dtype=np.float32)
        for region in page.value_regions():
            x1, y1, x2, y2 = region.bbox
            crop = arr[y1:y2 + 1, x1:x2 + 1]
            assert crop.size > 0, f"{region.field}: empty crop"
            assert crop.min() < 160, f"{region.field}: box holds no dark pixels"

    def test_devanagari_digits_carry_a_normalized_form(self):
        """The page shows १४२/२; the extractor must be graded on 142/2."""
        page = TEMPLATES["KHASRA_A"][1](SAMPLE_CTX)
        khasra = next(r for r in page.value_regions() if r.field == "KHASRA")
        assert khasra.text == "१४२/२"
        assert khasra.normalized == "142/2"

    def test_synthetic_notice_is_present(self):
        """§83 -- every page must be unmistakably marked."""
        page = TEMPLATES["KHASRA_A"][1](SAMPLE_CTX)
        assert any("SYNTHETIC" in r.text for r in page.regions)

    def test_templates_differ_structurally(self):
        """Layouts must not be near-identical, or the extractor can memorise
        one arrangement and appear to generalise."""
        signatures = set()
        for _, render in TEMPLATES.values():
            page = render(SAMPLE_CTX)
            khasra = next(
                (r for r in page.value_regions() if r.field == "KHASRA"), None
            )
            signatures.add(khasra.bbox if khasra else None)
        assert len(signatures) > 1


class TestGeometricTransformsMoveBoxes:
    """§48: if geometry changes, annotations must change with it."""

    def _prepare(self):
        c = RecordingCanvas(700, 300, background="white")
        region = c.text((180, 120), "खसरा १४२/२", size=40)
        return c.image, region.bbox

    @pytest.mark.parametrize("angle", [3.0, -7.0, 12.0])
    def test_rotation_box_tracks_the_ink(self, angle):
        image, box = self._prepare()
        rotated, moved = rotate(image, [box], angle, fill="white")
        actual = _ink_bounds(rotated)
        x1, y1, x2, y2 = moved[0]
        assert x1 <= actual[0] and y1 <= actual[1], "box does not cover the ink"
        assert x2 >= actual[2] and y2 >= actual[3], "box does not cover the ink"

    def test_rotation_actually_moves_the_box(self):
        image, box = self._prepare()
        _, moved = rotate(image, [box], 12.0, fill="white")
        assert moved[0] != box

    @pytest.mark.parametrize("strength", [0.04, 0.09])
    def test_perspective_box_tracks_the_ink(self, strength):
        image, box = self._prepare()
        warped, moved = perspective(
            image, [box], strength, random.Random(3), fill="white"
        )
        actual = _ink_bounds(warped)
        x1, y1, x2, y2 = moved[0]
        assert x1 <= actual[0] + 2 and y1 <= actual[1] + 2
        assert x2 >= actual[2] - 2 and y2 >= actual[3] - 2

    def test_rescale_preserves_geometry(self):
        image, box = self._prepare()
        _, moved = rescale(image, [box], 0.5)
        assert moved[0] == box


class TestDegradationProfiles:
    def test_mix_sums_to_one(self):
        assert sum(DIFFICULTY_MIX.values()) == pytest.approx(1.0)

    @pytest.mark.parametrize("tier", sorted(TIERS))
    def test_every_tier_produces_a_valid_page(self, tier):
        page = TEMPLATES["KHASRA_A"][1](SAMPLE_CTX)
        boxes = [r.bbox for r in page.regions]
        result = degrade(page.image, boxes, tier, random.Random(7))
        assert result.applied, f"{tier} applied nothing"
        assert len(result.boxes) == len(boxes)
        w, h = result.image.size
        for x1, y1, x2, y2 in result.boxes:
            assert 0 <= x1 <= x2 <= w and 0 <= y1 <= y2 <= h

    def test_harder_tiers_apply_more(self):
        page = TEMPLATES["KHASRA_A"][1](SAMPLE_CTX)
        boxes = [r.bbox for r in page.regions]
        clean = degrade(page.image, boxes, "clean", random.Random(1))
        extreme = degrade(page.image, boxes, "extreme", random.Random(1))
        assert len(extreme.applied) >= len(clean.applied)

    def test_degradation_is_deterministic(self):
        page = TEMPLATES["KHASRA_A"][1](SAMPLE_CTX)
        boxes = [r.bbox for r in page.regions]
        a = degrade(page.image, boxes, "hard", random.Random(11))
        b = degrade(page.image, boxes, "hard", random.Random(11))
        assert a.boxes == b.boxes
        assert a.applied == b.applied

    def test_parameters_are_recorded(self):
        """§49: a sample must be traceable to how it was produced."""
        page = TEMPLATES["KHASRA_A"][1](SAMPLE_CTX)
        result = degrade(page.image, [r.bbox for r in page.regions], "hard",
                         random.Random(2))
        assert all("op" in entry for entry in result.applied)


# ── generated-artefact checks (skip if the set has not been built) ──────────
#
# Read whichever profile is active rather than a hardcoded name. Pinning these
# to `slice1` meant generating a larger profile left the index and the splits
# describing different corpora, and the tests failed on the mismatch rather
# than on anything being wrong.


@pytest.fixture(scope="module")
def profile():
    active = active_profile()
    if active is None:
        pytest.skip("run scripts/generate_documents.py")
    return active


@pytest.fixture(scope="module")
def index(profile):
    path = index_path(profile)
    if not path.exists():
        pytest.skip(f"run scripts/generate_documents.py --profile {profile}")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def splits(profile):
    paths = {n: split_path(n, profile) for n in SPLIT_NAMES}
    if not all(p.exists() for p in paths.values()):
        pytest.skip(f"run scripts/split_dataset.py --profile {profile}")
    return {
        n: [json.loads(line) for line in p.read_text().splitlines() if line]
        for n, p in paths.items()
    }


class TestGeneratedSet:
    def test_every_field_box_contains_ink(self, index):
        """Compared against the LOCAL background: uneven illumination makes a
        global page mean the wrong reference."""
        offenders = []
        for doc in index:
            arr = np.array(
                Image.open(DATASETS / doc["degraded_image"]).convert("L"),
                dtype=np.float32,
            )
            h, w = arr.shape
            ann = json.loads((DATASETS / doc["annotation"]).read_text())
            for f in ann["fields"]:
                x1, y1, x2, y2 = f["bbox"]
                crop = arr[y1:y2 + 1, x1:x2 + 1]
                ring = arr[max(0, y1 - 18):min(h, y2 + 19),
                           max(0, x1 - 18):min(w, x2 + 19)]
                if crop.size == 0 or ring.size == 0:
                    offenders.append((doc["document_id"], f["field"], "empty"))
                    continue
                if crop.mean() / np.percentile(ring, 85) > 0.995:
                    offenders.append((doc["document_id"], f["field"], "no ink"))
        assert not offenders, offenders[:5]

    def test_annotations_stay_inside_the_image(self, index):
        for doc in index:
            ann = json.loads((DATASETS / doc["annotation"]).read_text())
            w, h = ann["width"], ann["height"]
            for f in ann["fields"]:
                x1, y1, x2, y2 = f["bbox"]
                assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h, (
                    f"{doc['document_id']}/{f['field']} {f['bbox']} vs {w}x{h}"
                )

    def test_all_three_templates_are_represented(self, index):
        assert {d["template"] for d in index} == set(TEMPLATES)


class TestLayoutAnnotation:
    """§48 again, for the structural regions.

    Layout boxes used to be written in canvas coordinates while the annotation
    recorded the POST-degradation size. Every tier rotates, warps and rescales,
    so those boxes described a page that was never saved -- and because no test
    read them, a region detector trained on this corpus would have learned
    misaligned targets rather than a visible defect.
    """

    def test_layout_boxes_stay_inside_the_image(self, index):
        for doc in index:
            ann = json.loads((DATASETS / doc["annotation"]).read_text())
            w, h = ann["width"], ann["height"]
            for box in ann["layout"]:
                x1, y1, x2, y2 = box["bbox"]
                assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h, (
                    f"{doc['document_id']}/{box['type']} {box['bbox']} vs {w}x{h}"
                )

    def test_table_cells_fall_inside_a_table_region(self, index):
        """The invariant the canvas-coordinate bug broke.

        Cell boxes travel through degradation; the table region that encloses
        them must travel the same way or it stops enclosing them. A few pixels
        of slack absorbs the rounding in the corner-bounds arithmetic.
        """
        slack = 6
        offenders = []
        for doc in index:
            ann = json.loads((DATASETS / doc["annotation"]).read_text())
            regions = [b["bbox"] for b in ann["layout"] if b["type"] == "table"]
            if not regions:
                continue
            for cell in ann["tables"]:
                cx1, cy1, cx2, cy2 = cell["bbox"]
                inside = any(
                    rx1 - slack <= cx1 and ry1 - slack <= cy1
                    and cx2 <= rx2 + slack and cy2 <= ry2 + slack
                    for rx1, ry1, rx2, ry2 in regions
                )
                if not inside:
                    offenders.append((doc["document_id"], cell["bbox"], regions))
        assert not offenders, offenders[:3]

    def test_every_page_carries_layout_ground_truth(self, index):
        """The four annotation views live in one file; none may quietly empty."""
        missing = [d["document_id"] for d in index
                   if not json.loads((DATASETS / d["annotation"]).read_text())["layout"]]
        assert not missing, missing[:5]


class TestSplitIntegrity:
    def test_no_group_spans_two_splits(self, splits):
        """§51 -- the check the whole split exists to satisfy."""
        for key in ("group", "parcel_family", "base_document_id"):
            seen: dict[str, str] = {}
            for name, docs in splits.items():
                for doc in docs:
                    value = doc[key]
                    assert seen.get(value, name) == name, (
                        f"{key} {value} in both {seen[value]} and {name}"
                    )
                    seen[value] = name

    def test_ratios_are_close_to_target(self, splits):
        total = sum(len(v) for v in splits.values())
        assert abs(len(splits["train"]) / total - 0.70) < 0.10
        assert abs(len(splits["val"]) / total - 0.15) < 0.10
        assert abs(len(splits["test"]) / total - 0.15) < 0.10

    def test_every_difficulty_appears_in_every_split(self, splits):
        """§65 reports per-tier accuracy; a missing tier is unmeasurable."""
        for name, docs in splits.items():
            present = {d["difficulty"] for d in docs}
            assert present == set(DIFFICULTY_MIX), f"{name} has only {present}"

    def test_splits_cover_the_index_exactly(self, splits, index):
        split_ids = {d["document_id"] for docs in splits.values() for d in docs}
        assert split_ids == {d["document_id"] for d in index}
