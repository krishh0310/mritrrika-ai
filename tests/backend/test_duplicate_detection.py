"""Duplicate detection at upload (§22, §34).

The distinction under test is the whole point of the feature: identical bytes
are refused, a page that merely *looks* like another is accepted and flagged.
Collapsing the two would either wave through real double-entry or block the
rescan an operator was just told to perform.
"""

import io
import json
import os
from pathlib import Path

import numpy as np
import pytest
from demo_users import DEO, VERIFIER
from PIL import Image

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "datasets"

#: Unique per test run; see _clean_page.
_RUN_SEED = int.from_bytes(os.urandom(3), "big")

import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.services import duplicate_service  # noqa: E402


def _clean_page(offset: int = 0) -> bytes:
    """A corpus page made byte-unique for this test run.

    The seeded demo database already holds the corpus verbatim, so uploading a
    page straight from disk is itself an exact duplicate -- which is the
    feature working, but leaves no way to test the FIRST upload. A small block
    of deterministic noise in one corner changes the bytes without changing
    what the page is.
    """
    index = json.loads((DATASETS / "metadata" / "documents.v1.json").read_text())
    clean = [d for d in index if d["difficulty"] == "clean"]
    if len(clean) <= offset:
        pytest.skip("run scripts/generate_documents.py --profile v1 first")
    path = DATASETS / clean[offset]["degraded_image"]
    if not path.exists():
        pytest.skip("run scripts/generate_documents.py --profile v1 first")

    image = Image.open(path).convert("RGB")
    arr = np.asarray(image).copy()
    # Seeded per RUN, not per test: the demo database persists between runs, so
    # a fixed seed would make the second run's "first upload" a duplicate of
    # the first run's -- the tests would pass once and fail forever after.
    patch = np.random.RandomState(_RUN_SEED + offset).randint(
        0, 255, (12, 12, 3), dtype=np.uint8
    )
    arr[:12, :12] = patch
    buffer = io.BytesIO()
    Image.fromarray(arr).save(buffer, "JPEG", quality=95)
    return buffer.getvalue()


def _rescan(data: bytes) -> bytes:
    """The same page through a second, slightly different scan.

    Brightness, contrast and JPEG quality change; the content does not. This is
    what a genuine rescan looks like, and it must NOT be refused.
    """
    image = Image.open(io.BytesIO(data)).convert("RGB")
    arr = np.asarray(image).astype(np.float32)
    arr = np.clip(arr * 1.06 + 8, 0, 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(arr).save(buffer, "JPEG", quality=72)
    return buffer.getvalue()


def _upload(client, token_for, data: bytes, name: str):
    return client.post(
        "/api/v1/documents",
        files={"file": (name, data, "image/jpeg")},
        data={"document_type": "KHASRA", "village_id": "LOC-VIL-01"},
        headers={"Authorization": f"Bearer {token_for(DEO)}"},
    )


class TestPerceptualHash:
    """Unit-level: the hash must be stable, comparable and brightness-robust."""

    def test_hash_is_sixteen_hex_characters(self):
        image = np.random.RandomState(0).randint(0, 255, (200, 180, 3), dtype=np.uint8)
        digest = duplicate_service.perceptual_hash(image)
        assert len(digest) == 16
        int(digest, 16)

    def test_identical_images_hash_identically(self):
        image = np.random.RandomState(1).randint(0, 255, (200, 180, 3), dtype=np.uint8)
        assert duplicate_service.perceptual_hash(image) == \
               duplicate_service.perceptual_hash(image.copy())

    def test_brightness_shift_barely_moves_the_hash(self):
        """The reason dHash was chosen over aHash."""
        image = np.random.RandomState(2).randint(20, 200, (200, 180, 3), dtype=np.uint8)
        brighter = np.clip(image.astype(np.int16) + 40, 0, 255).astype(np.uint8)
        distance = duplicate_service.hamming_distance(
            duplicate_service.perceptual_hash(image),
            duplicate_service.perceptual_hash(brighter),
        )
        assert distance <= duplicate_service.NEAR_DUPLICATE_DISTANCE

    def test_unrelated_images_are_far_apart(self):
        a = np.random.RandomState(3).randint(0, 255, (200, 180, 3), dtype=np.uint8)
        b = np.random.RandomState(4).randint(0, 255, (200, 180, 3), dtype=np.uint8)
        distance = duplicate_service.hamming_distance(
            duplicate_service.perceptual_hash(a), duplicate_service.perceptual_hash(b)
        )
        assert distance > duplicate_service.NEAR_DUPLICATE_DISTANCE

    def test_hamming_distance_of_a_hash_with_itself_is_zero(self):
        assert duplicate_service.hamming_distance("a1b2c3d4e5f60718", "a1b2c3d4e5f60718") == 0

    def test_grayscale_input_is_accepted(self):
        grey = np.random.RandomState(5).randint(0, 255, (200, 180), dtype=np.uint8)
        assert len(duplicate_service.perceptual_hash(grey)) == 16


class TestExactDuplicate:
    def test_the_same_bytes_twice_is_refused(self, client, token_for):
        data = _clean_page(0)
        first = _upload(client, token_for, data, "scan.jpg")
        assert first.status_code == 201, first.text

        second = _upload(client, token_for, data, "scan-renamed.jpg")
        assert second.status_code == 409, second.text

    def test_the_refusal_names_the_existing_document(self, client, token_for):
        data = _clean_page(1)
        first = _upload(client, token_for, data, "a.jpg")
        assert first.status_code == 201, first.text
        existing = first.json()["document_id"]

        second = _upload(client, token_for, data, "b.jpg")
        assert second.status_code == 409
        assert existing in second.json()["detail"]
        assert second.headers["X-Existing-Document"] == existing

    def test_a_refused_upload_stores_nothing(self, client, token_for):
        """A rejected duplicate must not leave a second row behind."""
        data = _clean_page(2)
        assert _upload(client, token_for, data, "x.jpg").status_code == 201
        before = client.get(
            "/api/v1/documents", headers={"Authorization": f"Bearer {token_for(DEO)}"}
        )
        assert _upload(client, token_for, data, "y.jpg").status_code == 409
        after = client.get(
            "/api/v1/documents", headers={"Authorization": f"Bearer {token_for(DEO)}"}
        )
        if before.status_code == 200 and after.status_code == 200:
            assert len(after.json()) == len(before.json())


class TestNearDuplicate:
    def test_a_rescan_is_accepted_not_refused(self, client, token_for):
        """The case that must never become a 409."""
        original = _clean_page(3)
        assert _upload(client, token_for, original, "orig.jpg").status_code == 201
        again = _upload(client, token_for, _rescan(original), "rescan.jpg")
        assert again.status_code == 201, again.text

    def test_a_rescan_is_flagged_for_an_officer(self, client, token_for):
        original = _clean_page(4)
        assert _upload(client, token_for, original, "o2.jpg").status_code == 201
        second = _upload(client, token_for, _rescan(original), "r2.jpg")
        assert second.status_code == 201, second.text

        document_id = second.json()["document_id"]
        flags = client.get(
            "/api/v1/anomalies",
            params={"status": "OPEN", "limit": 500},
            headers={"Authorization": f"Bearer {token_for(VERIFIER)}"},
        )
        assert flags.status_code == 200, flags.text
        mine = [
            f for f in flags.json()["flags"]
            if f.get("document") == document_id or f.get("document_id") == document_id
        ]
        assert mine, (
            "the resemblance flag is not reachable through the officer's "
            f"anomaly list for {document_id}"
        )
        assert {f["anomaly_type"] for f in mine} == {"DUPLICATE_DOCUMENT"}


class TestWording:
    """§34: a flag describes a resemblance, never an accusation."""

    def test_the_explanation_accuses_nobody(self):
        class _Doc:
            id = "1"
            parcel_id = None
            external_id = "DOC-1"

        class _Session:
            def add(self, _):
                pass

        flag = duplicate_service.record_resemblance(
            _Session(), _Doc(), [(_Doc(), 2)]
        )
        text = flag.explanation.lower()
        for banned in ("fraud", "fake", "forged", "duplicate entry", "cheat"):
            assert banned not in text, text
        assert "resembles" in text

    def test_no_matches_produces_no_flag(self):
        class _Session:
            def add(self, _):
                raise AssertionError("nothing should be added")

        assert duplicate_service.record_resemblance(_Session(), object(), []) is None
