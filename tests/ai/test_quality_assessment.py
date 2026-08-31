"""§22 quality gate.

The gate's job is to catch pages not worth processing WITHOUT discarding the
hard-but-readable ones that the verification workflow exists to handle. Both
failure directions are tested.
"""

import json
import statistics as st
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "datasets"
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from quality.assessment import (  # noqa: E402
    assess,
    assess_bytes,
    measure_blur,
    measure_skew,
    recommend,
)

TIERS = ("clean", "moderate", "hard", "extreme")


def _page(text: str = "MRITTIKA", size=(900, 1200)) -> np.ndarray:
    img = np.full((size[1], size[0], 3), 250, dtype=np.uint8)
    for i in range(6):
        cv2.putText(img, text, (60, 160 + i * 150), cv2.FONT_HERSHEY_SIMPLEX,
                    2.2, (20, 20, 20), 4)
    return img


class TestBlur:
    def test_blurred_page_scores_lower_than_sharp(self):
        sharp = _page()
        blurred = cv2.GaussianBlur(sharp, (15, 15), 0)
        assert measure_blur(cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY))[0] < \
               measure_blur(cv2.cvtColor(sharp, cv2.COLOR_BGR2GRAY))[0]

    def test_impulse_noise_does_not_read_as_sharpness(self):
        """Regression: raw Laplacian variance ranked the noisiest tier as the
        SHARPEST. Denoising must happen before the measurement."""
        sharp = cv2.cvtColor(_page(), cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(sharp, (15, 15), 0)

        noisy = blurred.copy()
        rng = np.random.default_rng(0)
        mask = rng.random(noisy.shape)
        noisy[mask < 0.01] = 0
        noisy[mask > 0.99] = 255

        # Adding noise to a blurred page must not make it look sharp.
        assert measure_blur(noisy)[0] < measure_blur(sharp)[0]


class TestSkew:
    @pytest.mark.parametrize("angle", [-6.0, -3.0, 0.0, 2.5, 5.0])
    def test_recovers_a_known_rotation(self, angle):
        """Magnitude AND sign.

        Two regressions guarded here: minAreaRect over all ink returned ~-90
        deg for near-upright pages, and the projection method initially
        returned the CORRECTION angle rather than the page's rotation -- which
        would make a deskew step double the tilt instead of removing it.
        """
        page = cv2.cvtColor(_page(), cv2.COLOR_BGR2GRAY)
        h, w = page.shape
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(page, matrix, (w, h), borderValue=250)

        measured, _ = measure_skew(rotated)
        assert abs(measured - angle) < 1.5, (
            f"expected ~{angle} deg, measured {measured} deg "
            f"(sign inverted?)"
        )

    def test_upright_page_reports_near_zero(self):
        measured, score = measure_skew(cv2.cvtColor(_page(), cv2.COLOR_BGR2GRAY))
        assert abs(measured) <= 1.0
        assert score > 0.85


class TestRecommendation:
    def test_vocabulary_matches_the_spec(self):
        allowed = {"PROCESS", "PROCESS_WITH_WARNING", "RESCAN_RECOMMENDED",
                   "REJECT_QUALITY"}
        for overall in (0.05, 0.25, 0.4, 0.5, 0.75, 0.95):
            assert recommend(overall, 0.5, 1.0) in allowed

    def test_unreadable_page_is_rejected(self):
        assert recommend(0.05, 0.01, 1.0) == "REJECT_QUALITY"

    def test_good_page_is_processed(self):
        assert recommend(0.9, 0.95, 1.0) == "PROCESS"

    def test_blank_page_does_not_crash(self):
        blank = np.full((800, 600, 3), 255, dtype=np.uint8)
        assert assess(blank).recommended_action in {
            "PROCESS", "PROCESS_WITH_WARNING", "RESCAN_RECOMMENDED", "REJECT_QUALITY"
        }

    def test_undecodable_bytes_raise_cleanly(self):
        with pytest.raises(ValueError):
            assess_bytes(b"not an image")


@pytest.fixture(scope="module")
def by_tier():
    index_path = DATASETS / "metadata" / "documents.slice1.json"
    if not index_path.exists():
        pytest.skip("run scripts/generate_documents.py")
    index = json.loads(index_path.read_text())
    scored: dict[str, list] = {}
    for tier in TIERS:
        scored[tier] = [
            assess_bytes((DATASETS / d["degraded_image"]).read_bytes())
            for d in index
            if d["difficulty"] == tier
        ]
    return scored


class TestAgainstTheRealSet:
    def test_clean_pages_are_always_processed(self, by_tier):
        for report in by_tier["clean"]:
            assert report.recommended_action == "PROCESS", report.to_dict()

    def test_clean_scores_above_moderate_above_severe(self, by_tier):
        """The gross ordering must hold.

        'hard' and 'extreme' are NOT required to separate from each other:
        their degradation ranges overlap, and with a small sample the two are
        legitimately tied. Demanding a strict order there would be fitting to
        noise.
        """
        mean = {t: st.mean(r.overall_score for r in by_tier[t]) for t in TIERS}
        assert mean["clean"] > mean["moderate"]
        assert mean["moderate"] > max(mean["hard"], mean["extreme"])

    def test_severe_pages_are_never_silently_accepted(self, by_tier):
        """A badly degraded page must carry a warning so the operator knows."""
        for tier in ("hard", "extreme"):
            for report in by_tier[tier]:
                assert report.recommended_action != "PROCESS", (
                    f"{tier} page passed with no warning: {report.to_dict()}"
                )

    def test_readable_pages_are_not_thrown_away(self, by_tier):
        """Regression: an earlier calibration rejected 94% of the 'hard' tier,
        which would have removed exactly the cases the Verifier handles."""
        rejected = sum(
            1 for tier in TIERS for r in by_tier[tier]
            if r.recommended_action == "REJECT_QUALITY"
        )
        total = sum(len(by_tier[t]) for t in TIERS)
        assert rejected / total < 0.10, f"{rejected}/{total} pages rejected"

    def test_measured_skew_tracks_the_applied_rotation(self, by_tier):
        """Clean pages were rotated at most 0.4 deg; hard pages up to 5."""
        clean = st.mean(abs(r.skew_angle) for r in by_tier["clean"])
        hard = st.mean(abs(r.skew_angle) for r in by_tier["hard"])
        assert clean < 1.0, clean
        assert hard > clean
