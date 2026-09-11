"""A multi-page PDF goes through the same lifecycle as an image (§21, §28).

Real upload, real rendering, real OCR on every page -- nothing mocked. Two
clean Khasra scans are bound into one PDF so each page carries its own fields,
which is what proves results are attributed to the right page.
"""

import io
import json
from pathlib import Path

import pytest
from demo_users import DEO, VERIFIER
from PIL import Image

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "datasets"


def _two_page_pdf() -> bytes:
    index = json.loads((DATASETS / "metadata" / "documents.v1.json").read_text())
    clean = [d for d in index if d["difficulty"] == "clean" and d["template"] == "KHASRA_A"]
    paths = [DATASETS / d["degraded_image"] for d in clean[:2]]
    if len(paths) < 2 or not all(p.exists() for p in paths):
        pytest.skip("run scripts/generate_documents.py --profile v1 first")
    pages = [Image.open(p).convert("RGB") for p in paths]
    buffer = io.BytesIO()
    pages[0].save(buffer, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def pdf_document(client, token_for):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("khasra-bundle.pdf", _two_page_pdf(), "application/pdf")},
        data={"document_type": "KHASRA", "village_id": "LOC-VIL-01"},
        headers={"Authorization": f"Bearer {token_for(DEO)}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def processed(client, token_for, pdf_document):
    response = client.post(
        f"/api/v1/documents/{pdf_document['document_id']}/process",
        params={"synchronous": True},
        headers={"Authorization": f"Bearer {token_for(DEO)}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestUpload:
    def test_pdf_is_not_mistaken_for_a_bad_scan(self, pdf_document):
        """It used to be REJECT_QUALITY: 'could not decode image bytes'."""
        assert pdf_document["quality_recommendation"] != "REJECT_QUALITY", pdf_document
        assert "error" not in (pdf_document["quality_report"] or {})

    def test_gate_reports_every_page(self, pdf_document):
        report = pdf_document["quality_report"]
        assert report["page_count"] == 2
        assert len(report["page_scores"]) == 2
        assert report["overall_score"] == min(report["page_scores"])

    def test_each_page_is_served_as_an_image(self, client, auth, pdf_document):
        import httpx

        for number in (1, 2):
            r = client.get(
                f"/api/v1/documents/{pdf_document['document_id']}/file",
                params={"page": number}, headers=auth(VERIFIER),
            )
            assert r.status_code == 200, r.text
            assert r.json()["page_count"] == 2
            fetched = httpx.get(r.json()["url"], timeout=10)
            assert fetched.status_code == 200
            assert fetched.content[:8] == b"\x89PNG\r\n\x1a\n", "page is not a PNG"

    def test_a_page_that_does_not_exist_is_404(self, client, auth, pdf_document):
        r = client.get(
            f"/api/v1/documents/{pdf_document['document_id']}/file",
            params={"page": 3}, headers=auth(VERIFIER),
        )
        assert r.status_code == 404


class TestProcessing:
    def test_every_page_is_processed(self, processed):
        assert processed["status"] == "SUCCEEDED", processed
        assert processed["pages"] == 2
        assert processed["fields"] > 0

    def test_fields_and_text_keep_their_page(self, client, auth, pdf_document, processed):
        r = client.get(
            f"/api/v1/verifications/{pdf_document['document_id']}/workspace",
            headers=auth(VERIFIER),
        )
        assert r.status_code == 200, r.text
        workspace = r.json()
        assert [p["page_number"] for p in workspace["pages"]] == [1, 2]
        assert all(p["width"] and p["height"] for p in workspace["pages"])
        # Both pages are Khasra scans, so each must contribute its own KHASRA.
        khasra_pages = {f["page_number"] for f in workspace["fields"] if f["field"] == "KHASRA"}
        assert khasra_pages == {1, 2}, workspace["fields"]
        assert {b["page_number"] for b in workspace["ocr_blocks"]} == {1, 2}

    def test_bboxes_fit_inside_their_own_page(self, client, auth, pdf_document, processed):
        workspace = client.get(
            f"/api/v1/verifications/{pdf_document['document_id']}/workspace",
            headers=auth(VERIFIER),
        ).json()
        size = {p["page_number"]: (p["width"], p["height"]) for p in workspace["pages"]}
        for field in workspace["fields"]:
            width, height = size[field["page_number"]]
            x1, y1, x2, y2 = field["bbox"]
            assert 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height, field
