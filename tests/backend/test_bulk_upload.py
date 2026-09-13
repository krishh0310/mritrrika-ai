"""A DEO uploads a tray of scans in one request (§21).

The property under test is that partial success works, because partial success
is what actually happens. A day's scanning routinely contains a page already
filed, a page that is not an image, and thirty-seven that are fine. If the
batch failed as a unit, the operator would re-upload everything to fix one
file; if it succeeded as a unit, the two bad pages would vanish silently.

The other property is that batching takes no shortcut. Every file goes through
the same upload path as a single upload -- same quality gate, same duplicate
check, same audit event -- because a bulk fast-path is exactly where the
per-document guarantees would quietly stop applying.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import numpy as np
import pytest
from conftest import fresh_scan
from demo_users import CITIZEN_A, DEO
from PIL import Image

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "datasets"

_RUN_SALT = int.from_bytes(os.urandom(3), "big")


def _clean_pages(count: int) -> list[bytes]:
    index = json.loads((DATASETS / "metadata" / "documents.v1.json").read_text())
    clean = [d for d in index if d["difficulty"] == "clean"]
    paths = [DATASETS / d["degraded_image"] for d in clean[:count]]
    if len(paths) < count or not all(p.exists() for p in paths):
        pytest.skip("run scripts/generate_documents.py --profile v1 first")
    return [fresh_scan(p) for p in paths]


def _post(client, auth, files: list[tuple[str, bytes]], **form):
    payload = {"document_type": "KHASRA", "village_id": "LOC-VIL-01"}
    payload.update(form)
    return client.post(
        "/api/v1/documents/batch",
        files=[("files", (name, data, "image/jpeg")) for name, data in files],
        data=payload,
        headers=auth(DEO),
    )


class TestHappyPath:
    def test_a_tray_of_scans_is_accepted(self, client, auth):
        pages = _clean_pages(3)
        response = _post(client, auth, [(f"p{i}.jpg", d) for i, d in enumerate(pages)])
        assert response.status_code == 207, response.text

        body = response.json()
        assert body["counts"]["submitted"] == 3
        assert body["counts"]["accepted"] == 3
        assert body["counts"]["rejected"] == 0

    def test_every_accepted_file_gets_its_own_document(self, client, auth):
        pages = _clean_pages(3)
        body = _post(
            client, auth, [(f"q{i}.jpg", d) for i, d in enumerate(pages)]
        ).json()
        ids = {row["document_id"] for row in body["accepted"]}
        assert len(ids) == 3

    def test_batched_uploads_run_the_quality_gate_like_single_ones(self, client, auth):
        """No bulk fast-path: the §22 verdict is present on every document."""
        pages = _clean_pages(2)
        body = _post(
            client, auth, [(f"r{i}.jpg", d) for i, d in enumerate(pages)]
        ).json()
        for row in body["accepted"]:
            assert row.get("quality_recommendation")


class TestPartialSuccess:
    def test_one_bad_file_does_not_lose_the_good_ones(self, client, auth):
        pages = _clean_pages(2)
        files = [("good-1.jpg", pages[0]),
                 ("not-an-image.jpg", b"MZ\x90\x00 this is not a scan"),
                 ("good-2.jpg", pages[1])]
        body = _post(client, auth, files).json()

        assert body["counts"]["accepted"] == 2
        assert body["counts"]["rejected"] == 1
        assert body["rejected"][0]["code"] == "UNSUPPORTED_TYPE"

    def test_a_duplicate_inside_the_batch_is_reported_not_fatal(self, client, auth):
        """The same page twice in one tray -- an ordinary scanning slip."""
        page = _clean_pages(1)[0]
        body = _post(client, auth, [("a.jpg", page), ("a-again.jpg", page)]).json()

        assert body["counts"]["accepted"] == 1
        assert body["counts"]["rejected"] == 1
        rejection = body["rejected"][0]
        assert rejection["code"] == "DUPLICATE"
        # Naming the original is the point: an operator who cannot find it will
        # upload a renamed copy instead.
        assert rejection["existing_document"] == body["accepted"][0]["document_id"]

    def test_every_rejection_says_which_file_and_why(self, client, auth):
        body = _post(client, auth, [("broken.jpg", b"not an image at all")]).json()
        rejection = body["rejected"][0]
        assert rejection["filename"] == "broken.jpg"
        assert rejection["reason"]
        assert rejection["code"]

    def test_rescan_needed_is_counted_apart_from_rejected(self, client, auth):
        """Stored-but-poor and never-stored are different problems."""
        body = _post(client, auth, [("ok.jpg", _clean_pages(1)[0])]).json()
        assert "needs_rescan" in body["counts"]
        assert body["counts"]["rejected"] == 0


class TestLimitsAndAccess:
    def test_a_batch_over_the_limit_is_refused_whole(self, client, auth):
        from app.routers.documents import MAX_BATCH_FILES

        tiny = io.BytesIO()
        Image.fromarray(
            np.full((40, 40, 3), 255, dtype=np.uint8)
        ).save(tiny, "JPEG")
        files = [(f"f{i}.jpg", tiny.getvalue()) for i in range(MAX_BATCH_FILES + 1)]
        response = _post(client, auth, files)
        assert response.status_code == 413, response.status_code

    def test_a_batch_without_a_village_is_refused(self, client, auth):
        response = _post(client, auth, [("x.jpg", _clean_pages(1)[0])], village_id="")
        assert response.status_code == 422

    def test_a_citizen_cannot_bulk_upload(self, client, auth):
        response = client.post(
            "/api/v1/documents/batch",
            files=[("files", ("x.jpg", b"x", "image/jpeg"))],
            data={"document_type": "KHASRA", "village_id": "LOC-VIL-01"},
            headers=auth(CITIZEN_A),
        )
        assert response.status_code == 403
