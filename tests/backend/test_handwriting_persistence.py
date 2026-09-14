"""Persist a synthetic provider's handwriting flag through the real API."""

from conftest import fresh_scan
from demo_users import DEO, VERIFIER
from test_end_to_end import TARGET_VILLAGE, _pick_document


def test_handwriting_flag_survives_persistence(client, auth, monkeypatch):
    from app.services import pipeline_service
    from ocr.provider import OcrResult, TextBlock

    class Engine:
        def recognize(self, image):
            return OcrResult(blocks=[
                TextBlock("खसरा संख्या", .99, (10, 50, 150, 90)),
                TextBlock("१४२", .99, (160, 50, 230, 90), is_handwritten=True),
            ], provider="synthetic-test")

    monkeypatch.setattr(pipeline_service, "get_engine", lambda: Engine())
    response = client.post(
        "/api/v1/documents",
        files={"file": ("synthetic.jpg", fresh_scan(_pick_document()), "image/jpeg")},
        data={"document_type": "KHASRA", "village_id": TARGET_VILLAGE},
        headers=auth(DEO),
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["document_id"]
    response = client.post(
        f"/api/v1/documents/{document_id}/process?synchronous=true", headers=auth(DEO),
    )
    assert response.status_code == 200, response.text
    response = client.get(
        f"/api/v1/verifications/{document_id}/workspace", headers=auth(VERIFIER),
    )
    assert response.status_code == 200, response.text
    workspace = response.json()
    assert any(b["is_handwritten"] for b in workspace["ocr_blocks"])
    assert any(f["rule"] == "SUSPECTED_HANDWRITING" for f in workspace["findings"])
    assert all(f["status"] == "NEEDS_REVIEW" for f in workspace["fields"])
