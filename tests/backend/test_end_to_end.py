"""§73 -- the full lifecycle, on ONE document, through the real API.

    DEO upload -> quality gate -> AI pipeline -> extraction
    -> Verifier correction -> verification submitted
    -> Tehsildar approval -> Citizen sees the parcel
    -> ownership/mutation history -> audit trail

Nothing here is mocked. The same document_id and parcel_id are followed end to
end, which is the property §92 defines as done.
"""

import json
from pathlib import Path

import pytest
from conftest import fresh_scan
from demo_users import CITIZEN_A, CITIZEN_B, DEO, TEHSILDAR, VERIFIER

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "datasets"

#: A parcel citizen A holds, so approval becomes visible to a real citizen.
TARGET_PARCEL = "PARCEL-UP-DEMO-0181"
TARGET_VILLAGE = "LOC-VIL-02"


def _pick_document() -> Path:
    """A clean page, so the chain exercises the happy path deterministically.

    Degraded pages are covered by the quality and extraction test suites; using
    one here would make the E2E test measure OCR accuracy rather than
    integration.
    """
    index = json.loads((DATASETS / "metadata" / "documents.slice1.json").read_text())
    clean = [d for d in index if d["difficulty"] == "clean"]
    if not clean:
        pytest.skip("no clean documents generated")
    return DATASETS / clean[0]["degraded_image"]


@pytest.fixture(scope="module")
def uploaded(client, token_for):
    """Step 1: the DEO uploads a real scan."""
    image = _pick_document()
    if not image.exists():
        pytest.skip("run scripts/generate_documents.py first")

    # Uploaded as fresh bytes: the demo database is seeded from this same
    # corpus, so the file as it sits on disk is already stored and upload
    # refuses it as an exact duplicate (§22).
    response = client.post(
        "/api/v1/documents",
        files={"file": (image.name, fresh_scan(image), "image/jpeg")},
        data={
            "document_type": "KHASRA",
            "village_id": TARGET_VILLAGE,
            "record_year": "1998-99",
            "khasra_number": "142/2",
            "parcel_id": TARGET_PARCEL,
        },
        headers={"Authorization": f"Bearer {token_for(DEO)}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestStep1Upload:
    def test_document_created(self, uploaded):
        assert uploaded["document_id"].startswith("DOC-")

    def test_quality_gate_ran_immediately(self, uploaded):
        """§22 -- assessed on upload, before any model runs."""
        assert uploaded["quality_recommendation"] in {
            "PROCESS", "PROCESS_WITH_WARNING", "RESCAN_RECOMMENDED", "REJECT_QUALITY"
        }
        assert uploaded["quality_report"]["blur_score"] is not None
        assert uploaded["quality_score"] > 0

    def test_state_advanced_past_upload(self, uploaded):
        assert uploaded["state"] in {"QUALITY_CHECK", "RESCAN_REQUIRED"}

    def test_citizens_cannot_upload(self, client, auth):
        with _pick_document().open("rb") as fh:
            r = client.post(
                "/api/v1/documents",
                files={"file": ("x.jpg", fh, "image/jpeg")},
                data={"document_type": "KHASRA"},
                headers=auth(CITIZEN_A),
            )
        assert r.status_code == 403

    def test_upload_without_a_location_says_what_is_missing(self, client, auth):
        """It used to claim the (unselected) location was outside jurisdiction."""
        with _pick_document().open("rb") as fh:
            r = client.post(
                "/api/v1/documents",
                files={"file": ("x.jpg", fh, "image/jpeg")},
                data={"document_type": "KHASRA"},
                headers=auth(DEO),
            )
        assert r.status_code == 422
        assert "choose the village" in r.json()["detail"].lower()

    def test_disguised_executable_is_rejected(self, client, auth):
        """§61 -- type comes from sniffing bytes, not the declared header."""
        r = client.post(
            "/api/v1/documents",
            files={"file": ("payload.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")},
            data={"document_type": "KHASRA", "village_id": "LOC-VIL-01"},
            headers=auth(DEO),
        )
        assert r.status_code == 415


class TestStep2Processing:
    def test_pipeline_runs_and_extracts(self, client, auth, uploaded):
        document_id = uploaded["document_id"]
        r = client.post(
            f"/api/v1/documents/{document_id}/process",
            params={"synchronous": True},
            headers=auth(DEO),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "SUCCEEDED", body
        assert body["fields"] > 0, "pipeline extracted nothing"

    def test_status_reports_completion(self, client, auth, uploaded):
        r = client.get(
            f"/api/v1/documents/{uploaded['document_id']}/status", headers=auth(DEO)
        )
        assert r.json()["status"] == "SUCCEEDED"
        assert r.json()["progress"] == 100

    def test_document_awaits_verification(self, client, auth, uploaded):
        r = client.get(f"/api/v1/documents/{uploaded['document_id']}", headers=auth(DEO))
        assert r.json()["state"] in {"NEEDS_VERIFICATION", "UNDER_VERIFICATION"}


class TestStep3Verification:
    def test_document_is_in_the_queue(self, client, auth, uploaded):
        r = client.get("/api/v1/verifications", headers=auth(VERIFIER))
        assert r.status_code == 200
        assert uploaded["document_id"] in {t["document_id"] for t in r.json()["tasks"]}

    def test_workspace_carries_boxes_and_confidence(self, client, auth, uploaded):
        """§28 -- clicking a field must be able to zoom the source region."""
        r = client.get(
            f"/api/v1/verifications/{uploaded['document_id']}/workspace",
            headers=auth(VERIFIER),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fields"], "workspace has no fields"
        assert body["ocr_blocks"], "workspace has no OCR blocks"
        for field in body["fields"]:
            assert len(field["bbox"]) == 4 and all(v is not None for v in field["bbox"])
            assert field["model_version"], "field has no model version (§64)"
            assert field["confidence_breakdown"], "no confidence explanation (§68)"

    def test_correction_preserves_the_model_prediction(self, client, auth, uploaded):
        """§26 -- normalization and correction never destroy raw OCR."""
        workspace = client.get(
            f"/api/v1/verifications/{uploaded['document_id']}/workspace",
            headers=auth(VERIFIER),
        ).json()
        target = workspace["fields"][0]

        r = client.patch(
            f"/api/v1/verifications/extractions/{target['extraction_id']}",
            json={"value": "CORRECTED-BY-TEST", "reason": "e2e"},
            headers=auth(VERIFIER),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["corrected_value"] == "CORRECTED-BY-TEST"
        assert body["raw_value"] == target["raw_value"], "raw OCR was overwritten!"
        assert body["status"] == "VERIFIER_CORRECTED"

    def test_cannot_submit_while_fields_need_review(self, client, auth, uploaded):
        """Guard: submitting with unreviewed fields defeats the queue."""
        workspace = client.get(
            f"/api/v1/verifications/{uploaded['document_id']}/workspace",
            headers=auth(VERIFIER),
        ).json()
        if not any(f["status"] == "NEEDS_REVIEW" for f in workspace["fields"]):
            pytest.skip("no low-confidence fields on this page")
        r = client.post(
            f"/api/v1/verifications/{uploaded['document_id']}/submit",
            json={"note": "premature"}, headers=auth(VERIFIER),
        )
        assert r.status_code == 409

    def test_submit_after_reviewing_everything(self, client, auth, uploaded):
        workspace = client.get(
            f"/api/v1/verifications/{uploaded['document_id']}/workspace",
            headers=auth(VERIFIER),
        ).json()
        for field in workspace["fields"]:
            if field["status"] == "NEEDS_REVIEW":
                client.post(
                    f"/api/v1/verifications/extractions/{field['extraction_id']}/approve",
                    headers=auth(VERIFIER),
                )
        r = client.post(
            f"/api/v1/verifications/{uploaded['document_id']}/submit",
            json={"note": "verified in e2e"}, headers=auth(VERIFIER),
        )
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "PENDING_APPROVAL"

    def test_tehsildar_cannot_correct_extractions(self, client, auth, uploaded):
        """Separation of duties (§36)."""
        workspace = client.get(
            f"/api/v1/verifications/{uploaded['document_id']}/workspace",
            headers=auth(VERIFIER),
        ).json()
        r = client.patch(
            f"/api/v1/verifications/extractions/{workspace['fields'][0]['extraction_id']}",
            json={"value": "x"}, headers=auth(TEHSILDAR),
        )
        assert r.status_code == 403


class TestStep4Approval:
    def test_document_is_in_the_approval_queue(self, client, auth, uploaded):
        r = client.get("/api/v1/approvals", headers=auth(TEHSILDAR))
        assert uploaded["document_id"] in {d["document_id"] for d in r.json()["documents"]}

    def test_verifier_cannot_approve(self, client, auth, uploaded):
        r = client.post(
            f"/api/v1/approvals/{uploaded['document_id']}/approve",
            json={"reason": "should not work"}, headers=auth(VERIFIER),
        )
        assert r.status_code == 403

    def test_tehsildar_approves(self, client, auth, uploaded):
        r = client.post(
            f"/api/v1/approvals/{uploaded['document_id']}/approve",
            json={"reason": "approved in e2e"}, headers=auth(TEHSILDAR),
        )
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "APPROVED"


class TestStep5CitizenAccess:
    def test_owner_sees_the_parcel(self, client, auth):
        r = client.get("/api/v1/citizen/my-parcels", headers=auth(CITIZEN_A))
        assert TARGET_PARCEL in {p["parcel_id"] for p in r.json()["parcels"]}

    def test_other_citizen_still_cannot(self, client, auth):
        """Approval must not widen anyone else's access."""
        r = client.get(f"/api/v1/citizen/parcels/{TARGET_PARCEL}", headers=auth(CITIZEN_B))
        assert r.status_code == 403

    def test_ownership_history_is_available(self, client, auth):
        r = client.get(
            f"/api/v1/citizen/parcels/{TARGET_PARCEL}/ownership-history",
            headers=auth(CITIZEN_A),
        )
        assert r.status_code == 200
        assert r.json()["history"], "no ownership history"

    def test_historical_owner_query(self, client, auth):
        """Demo step 24: 'who was the recorded owner in 1998?'"""
        r = client.get(
            "/api/v1/citizen/parcels/PARCEL-UP-DEMO-0142/owners-on",
            params={"on": "1998-12-31"}, headers=auth(CITIZEN_B),
        )
        assert r.status_code == 200, r.text
        owners = r.json()["owners"]
        assert owners, "no owner recorded for 1998"
        assert owners[0]["owner"] == "राम प्रसाद सिंह"


class TestStep6AuditTrail:
    def test_timeline_covers_the_whole_lifecycle(self, client, auth, uploaded):
        r = client.get(
            f"/api/v1/audit/documents/{uploaded['document_id']}", headers=auth(TEHSILDAR)
        )
        assert r.status_code == 200
        actions = [e["action"] for e in r.json()["events"]]
        for expected in (
            "document.upload", "document.quality_check",
            "document.processing_started", "document.processing_completed",
            "extraction.corrected", "document.verified", "document.approved",
        ):
            assert expected in actions, f"{expected} missing from audit trail: {actions}"

    def test_events_are_chained(self, client, auth, uploaded):
        events = client.get(
            f"/api/v1/audit/documents/{uploaded['document_id']}", headers=auth(TEHSILDAR)
        ).json()["events"]
        assert all(e["event_hash"] and e["previous_hash"] for e in events)

    def test_chain_verifies(self, client, auth):
        r = client.get("/api/v1/audit/verify", headers=auth(TEHSILDAR))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["valid"] is True, body["problems"][:5]
        assert body["mechanism"] == "sha256-hash-chain"

    def test_citizens_cannot_read_the_audit_trail(self, client, auth, uploaded):
        r = client.get(
            f"/api/v1/audit/documents/{uploaded['document_id']}", headers=auth(CITIZEN_A)
        )
        assert r.status_code == 403
