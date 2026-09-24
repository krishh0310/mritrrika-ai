"""A downloadable, verifiable record extract (§15, §17).

The properties that matter are about what the paper can and cannot do.

A printed extract must be checkable by anyone holding it -- otherwise the QR is
decoration. And checking it must reveal nothing: if verification replied with
the record, a photograph of somebody's paperwork would become a way to read
their holdings.

The rendering has one hard requirement too. Devanagari must be SHAPED, not just
drawn: a certificate whose conjuncts have come apart says something different
from the record it claims to reproduce.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from demo_users import CITIZEN_A, CITIZEN_B, TEHSILDAR

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.services import certificate_service as certs  # noqa: E402


def _a_parcel(client, auth, email: str) -> str:
    response = client.get("/api/v1/citizen/my-parcels", headers=auth(email))
    assert response.status_code == 200, response.text
    parcels = response.json()["parcels"]
    if not parcels:
        pytest.skip(f"{email} holds no parcels in the seeded data")
    return parcels[0]["parcel_id"]


class TestHashing:
    def test_the_same_content_hashes_the_same(self):
        content = {"parcel_id": "P-1", "holders": [{"owner": "राम"}]}
        assert certs.hash_of(content) == certs.hash_of(dict(content))

    def test_key_order_does_not_change_the_hash(self):
        a = {"parcel_id": "P-1", "khasra_number": "142/2"}
        b = {"khasra_number": "142/2", "parcel_id": "P-1"}
        assert certs.hash_of(a) == certs.hash_of(b)

    def test_a_changed_value_changes_the_hash(self):
        a = {"parcel_id": "P-1", "area_value": 1.09}
        b = {"parcel_id": "P-1", "area_value": 10.9}
        assert certs.hash_of(a) != certs.hash_of(b)

    def test_devanagari_is_hashed_as_itself(self):
        """ensure_ascii would hash escape sequences, not the text."""
        assert certs.hash_of({"owner": "राम"}) != certs.hash_of({"owner": "\\u0930"})


class TestDownload:
    def test_a_citizen_can_download_their_own_extract(self, client, auth):
        parcel = _a_parcel(client, auth, CITIZEN_A)
        response = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert response.content[:5] == b"%PDF-"

    def test_the_response_names_the_file_and_its_hash(self, client, auth):
        parcel = _a_parcel(client, auth, CITIZEN_A)
        response = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        )
        assert parcel in response.headers["content-disposition"]
        assert len(response.headers["X-Content-Hash"]) == 64

    def test_a_citizen_cannot_download_another_citizen_s_extract(self, client, auth):
        """The PDF renders data the caller can already read -- never a way round."""
        parcel = _a_parcel(client, auth, CITIZEN_A)
        response = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_B)
        )
        assert response.status_code in (403, 404), response.status_code

    def test_downloading_is_audited(self, client, auth):
        from app.db import SessionLocal
        from app.models import AuditEvent

        parcel = _a_parcel(client, auth, CITIZEN_A)
        with SessionLocal() as session:
            before = session.query(AuditEvent).filter(
                AuditEvent.action == "certificate.issued"
            ).count()

        client.get(f"/api/v1/citizen/parcels/{parcel}/certificate",
                   headers=auth(CITIZEN_A))

        with SessionLocal() as session:
            after = session.query(AuditEvent).filter(
                AuditEvent.action == "certificate.issued"
            ).count()
        assert after == before + 1


class TestVerification:
    def test_a_freshly_issued_extract_verifies(self, client, auth):
        parcel = _a_parcel(client, auth, CITIZEN_A)
        issued = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        )
        digest = issued.headers["X-Content-Hash"]

        checked = client.get(
            "/api/v1/citizen/certificates/verify",
            params={"parcel": parcel, "hash": digest},
            headers=auth(CITIZEN_A),
        )
        assert checked.status_code == 200, checked.text
        assert checked.json()["matches"] is True

    def test_a_tampered_hash_does_not_verify(self, client, auth):
        parcel = _a_parcel(client, auth, CITIZEN_A)
        checked = client.get(
            "/api/v1/citizen/certificates/verify",
            params={"parcel": parcel, "hash": "0" * 64},
            headers=auth(CITIZEN_A),
        )
        assert checked.json()["matches"] is False

    def test_verification_reveals_nothing_about_the_record(self, client, auth):
        """The property that makes a public QR safe (§17)."""
        parcel = _a_parcel(client, auth, CITIZEN_A)
        issued = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        )
        body = client.get(
            "/api/v1/citizen/certificates/verify",
            params={"parcel": parcel, "hash": issued.headers["X-Content-Hash"]},
            headers=auth(CITIZEN_A),
        ).json()
        assert set(body) == {"parcel_id", "matches", "reason", "is_synthetic"}
        for leak in ("owner", "holder", "area", "khata", "khasra"):
            assert leak not in str(body).lower(), body

    def test_someone_else_may_check_a_certificate_they_are_shown(self, client, auth):
        """Verification is the one thing a non-holder can do with an extract."""
        parcel = _a_parcel(client, auth, CITIZEN_A)
        issued = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        )
        checked = client.get(
            "/api/v1/citizen/certificates/verify",
            params={"parcel": parcel, "hash": issued.headers["X-Content-Hash"]},
            headers=auth(TEHSILDAR),
        )
        assert checked.status_code == 200
        assert checked.json()["matches"] is True

    def test_a_mismatch_is_worded_as_out_of_date_not_as_forgery(self, client, auth):
        """§34 -- a record legitimately changes when a mutation is approved."""
        parcel = _a_parcel(client, auth, CITIZEN_A)
        body = client.get(
            "/api/v1/citizen/certificates/verify",
            params={"parcel": parcel, "hash": "1" * 64},
            headers=auth(CITIZEN_A),
        ).json()
        for banned in ("forged", "fraud", "fake", "invalid"):
            assert banned not in body["reason"].lower(), body["reason"]

    def test_an_unknown_parcel_does_not_verify(self, client, auth):
        body = client.get(
            "/api/v1/citizen/certificates/verify",
            params={"parcel": "PARCEL-DOES-NOT-EXIST", "hash": "0" * 64},
            headers=auth(CITIZEN_A),
        ).json()
        assert body["matches"] is False


class TestRendering:
    def test_devanagari_is_shaped_not_boxed(self, client, auth):
        """The reason this is Pillow + libraqm rather than reportlab.

        A page of tofu boxes is still a valid PDF. Rasterising it and looking
        for ink in the right place is the only check that would notice.
        """
        from PIL import features

        assert features.check("raqm"), (
            "Pillow is not libraqm-linked; Devanagari will not shape correctly "
            "(see services/ai-worker/requirements.txt)"
        )

    def test_the_pdf_rasterises_to_a_page_with_ink(self, client, auth):
        import numpy as np
        import pypdfium2 as pdfium

        parcel = _a_parcel(client, auth, CITIZEN_A)
        pdf = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        ).content

        page = pdfium.PdfDocument(pdf)[0]
        arr = np.asarray(page.render(scale=1.0).to_pil().convert("L"))
        dark = (arr < 128).mean()
        # A blank page is ~0; a page of tofu boxes is far darker than text.
        assert 0.005 < dark < 0.25, f"unexpected ink coverage {dark:.3f}"

    def test_the_synthetic_notice_is_drawn_above_the_data(self, client, auth):
        """Checked as PIXELS, because this PDF has no text layer.

        The page is a rasterised image -- the price of shaping Devanagari with
        Pillow instead of mis-shaping it with reportlab. So the notice cannot
        be found by extracting text; it is found by looking for its red box in
        the upper third, above the first data row, where a reader who stops
        reading has already passed it.
        """
        import numpy as np
        import pypdfium2 as pdfium

        parcel = _a_parcel(client, auth, CITIZEN_A)
        pdf = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        ).content

        page = pdfium.PdfDocument(pdf)[0].render(scale=2.0).to_pil().convert("RGB")
        upper = np.asarray(page)[: page.height // 3]
        r, g, b = upper[:, :, 0].astype(int), upper[:, :, 1].astype(int), upper[:, :, 2].astype(int)
        reddish = ((r > 120) & (r - g > 60) & (r - b > 60)).sum()
        assert reddish > 200, f"no red warning box found above the data ({reddish}px)"

    def test_the_certificate_has_no_text_layer_and_that_is_known(self, client, auth):
        """Pins a real limitation so it cannot be forgotten (see docs).

        A rasterised certificate cannot be read by a screen reader, searched,
        or copied from. That is a genuine accessibility cost of correct
        Devanagari shaping, and it is recorded here rather than discovered by a
        user.
        """
        import pypdfium2 as pdfium

        parcel = _a_parcel(client, auth, CITIZEN_A)
        pdf = client.get(
            f"/api/v1/citizen/parcels/{parcel}/certificate", headers=auth(CITIZEN_A)
        ).content
        text = pdfium.PdfDocument(pdf)[0].get_textpage().get_text_range().strip()
        assert text == "", (
            "the certificate grew a text layer -- good news, but the "
            "accessibility note in docs/ and this test need updating"
        )
