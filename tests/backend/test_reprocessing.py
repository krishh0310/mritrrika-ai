"""§29 controlled reprocessing.

Documents extracted by an older extractor had no way back: NEEDS_VERIFICATION
only led to UNDER_VERIFICATION, so a known-bad extraction (the remark line read
as an owner, 'ति' as a guardian) could only be hand-corrected field by field.
Reprocessing is allowed until a human has done any work, and never after.
"""

import json
from pathlib import Path

import pytest
from demo_users import DEO, VERIFIER

pytestmark = pytest.mark.integration

DATASETS = Path(__file__).resolve().parents[2] / "datasets"


def _clean_khasra() -> Path:
    index = json.loads((DATASETS / "metadata" / "documents.v1.json").read_text())
    doc = next(d for d in index if d["difficulty"] == "clean" and d["template"] == "KHASRA_A")
    path = DATASETS / doc["degraded_image"]
    if not path.exists():
        pytest.skip("run scripts/generate_documents.py --profile v1 first")
    return path


@pytest.fixture
def awaiting_verification(client, auth):
    with _clean_khasra().open("rb") as fh:
        upload = client.post(
            "/api/v1/documents",
            files={"file": ("khasra.jpg", fh, "image/jpeg")},
            data={"document_type": "KHASRA", "village_id": "LOC-VIL-01"},
            headers=auth(DEO),
        )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["document_id"]
    processed = client.post(
        f"/api/v1/documents/{document_id}/process",
        params={"synchronous": True}, headers=auth(DEO),
    )
    assert processed.json()["status"] == "SUCCEEDED", processed.text
    return document_id


def reprocess(client, auth, document_id, who=VERIFIER):
    return client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        params={"synchronous": True},
        json={"reason": "extractor fix"},
        headers=auth(who),
    )


def test_untouched_document_can_be_reprocessed(client, auth, awaiting_verification):
    r = reprocess(client, auth, awaiting_verification)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUCCEEDED"

    status_ = client.get(f"/api/v1/documents/{awaiting_verification}", headers=auth(VERIFIER))
    assert status_.json()["state"] == "NEEDS_VERIFICATION"


def test_reprocessing_is_audited_with_its_reason(client, auth, awaiting_verification):
    reprocess(client, auth, awaiting_verification)
    timeline = client.get(
        f"/api/v1/audit/documents/{awaiting_verification}", headers=auth(VERIFIER)
    ).json()
    events = timeline.get("events", timeline)
    requested = [e for e in events if e.get("action") == "document.reprocessing_requested"]
    assert requested, [e.get("action") for e in events]


def test_refused_once_a_field_is_corrected(client, auth, awaiting_verification):
    workspace = client.get(
        f"/api/v1/verifications/{awaiting_verification}/workspace", headers=auth(VERIFIER)
    ).json()
    field = workspace["fields"][0]
    corrected = client.patch(
        f"/api/v1/verifications/extractions/{field['extraction_id']}",
        json={"value": "corrected-by-test"}, headers=auth(VERIFIER),
    )
    assert corrected.status_code == 200, corrected.text

    r = reprocess(client, auth, awaiting_verification)
    assert r.status_code == 409
    assert "discard" in r.json()["detail"]

    # And the correction is still there.
    after = client.get(
        f"/api/v1/verifications/{awaiting_verification}/workspace", headers=auth(VERIFIER)
    ).json()
    assert any(f["corrected_value"] == "corrected-by-test" for f in after["fields"])


def test_refused_once_a_field_is_accepted(client, auth, awaiting_verification):
    workspace = client.get(
        f"/api/v1/verifications/{awaiting_verification}/workspace", headers=auth(VERIFIER)
    ).json()
    reviewable = [f for f in workspace["fields"] if f["status"] == "NEEDS_REVIEW"]
    field = (reviewable or workspace["fields"])[0]
    accepted = client.post(
        f"/api/v1/verifications/extractions/{field['extraction_id']}/approve",
        json={}, headers=auth(VERIFIER),
    )
    assert accepted.status_code == 200, accepted.text
    assert reprocess(client, auth, awaiting_verification).status_code == 409


def test_deo_cannot_reprocess(client, auth, awaiting_verification):
    """Re-running extraction is a verification decision (document:verify)."""
    assert reprocess(client, auth, awaiting_verification, who=DEO).status_code == 403
