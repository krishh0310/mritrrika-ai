"""A document is checked against the records it claims to describe (§33, §34).

The existing validation rules ask whether a value is well-formed. A page can
satisfy every one of them and still describe a parcel that does not exist, in
a village it does not belong to, claiming several times the land the cadastre
records. These checks ask the other question.

What must hold: a finding reports a disagreement, never resolves one. It never
rewrites a value, never accuses anyone, and never fires on a field the
extractor simply did not find -- that is already reported as MISSING, and
saying it also fails to match the cadastre is the same fact twice.
"""

import sys
from pathlib import Path

import pytest
from demo_users import VERIFIER

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.services import cross_reference_service as xref  # noqa: E402


class _Parcel:
    def __init__(self, khasra="140", khata="164", area=0.89, unit="HECTARE"):
        self.khasra_number = khasra
        self.khata_number = khata
        self.area_value = area
        self.area_unit = unit
        self.geometry = None


class _Location:
    def __init__(self, name="Rampur", devanagari="रामपुर", external_id="LOC-VIL-01"):
        self.name = name
        self.name_devanagari = devanagari
        self.external_id = external_id
        self.id = "vil-1"
        self.level = "VILLAGE"
        self.parent_id = None


class TestVillage:
    def test_a_matching_devanagari_name_produces_no_finding(self):
        assert xref.check_village({"VILLAGE": "रामपुर"}, _Location()) == []

    def test_a_matching_latin_name_produces_no_finding(self):
        assert xref.check_village({"VILLAGE": "Rampur"}, _Location()) == []

    def test_normalisation_ignores_spacing_and_punctuation(self):
        assert xref.check_village({"VILLAGE": " रामपुर। "}, _Location()) == []

    def test_a_different_village_is_flagged(self):
        findings = xref.check_village({"VILLAGE": "सीतापुर"}, _Location())
        assert len(findings) == 1
        assert findings[0].field == "VILLAGE"

    def test_a_missing_village_produces_no_finding(self):
        """Already reported as MISSING; saying it twice is noise."""
        assert xref.check_village({}, _Location()) == []


class TestKhata:
    def test_a_matching_khata_produces_no_finding(self):
        assert xref.check_khata({"KHATA": "164"}, _Parcel()) == []

    def test_a_different_khata_is_flagged(self):
        assert len(xref.check_khata({"KHATA": "999"}, _Parcel())) == 1

    def test_no_parcel_means_no_finding(self):
        assert xref.check_khata({"KHATA": "164"}, None) == []


class TestArea:
    def test_an_equal_area_produces_no_finding(self):
        assert xref.check_area({"AREA": "0.89", "AREA_UNIT": "HECTARE"}, _Parcel()) == []

    def test_rounding_on_the_page_is_tolerated(self):
        assert xref.check_area({"AREA": "0.95", "AREA_UNIT": "HECTARE"}, _Parcel()) == []

    def test_a_threefold_difference_is_flagged(self):
        findings = xref.check_area({"AREA": "3.0", "AREA_UNIT": "HECTARE"}, _Parcel())
        assert len(findings) == 1
        assert findings[0].evidence["severe"] is True

    def test_units_are_converted_before_comparing(self):
        """0.89 hectare is ~3.52 bigha; stating it in bigha must not flag."""
        parcel = _Parcel(area=0.89, unit="HECTARE")
        assert xref.check_area({"AREA": "3.52", "AREA_UNIT": "BIGHA"}, parcel) == []

    def test_a_missing_unit_is_assumed_and_the_assumption_is_recorded(self):
        findings = xref.check_area({"AREA": "9.0"}, _Parcel())
        assert len(findings) == 1
        assert findings[0].evidence["unit_assumed"] is True

    def test_a_non_numeric_area_is_left_to_the_format_rules(self):
        assert xref.check_area({"AREA": "काफी", "AREA_UNIT": "BIGHA"}, _Parcel()) == []

    def test_an_unconvertible_unit_produces_no_guess(self):
        """Never invent a conversion factor."""
        assert xref.check_area({"AREA": "2", "AREA_UNIT": "KANAL"}, _Parcel()) == []


class TestWording:
    """§34: a finding describes a disagreement, it does not accuse."""

    @pytest.mark.parametrize("banned", ["fraud", "fake", "forged", "false", "illegal"])
    def test_no_finding_accuses_anyone(self, banned):
        produced = (
            xref.check_village({"VILLAGE": "सीतापुर"}, _Location())
            + xref.check_khata({"KHATA": "999"}, _Parcel())
            + xref.check_area({"AREA": "9.0", "AREA_UNIT": "HECTARE"}, _Parcel())
        )
        assert produced
        for finding in produced:
            assert banned not in finding.message.lower(), finding.message

    def test_every_finding_carries_checkable_evidence(self):
        for finding in xref.check_area({"AREA": "9.0", "AREA_UNIT": "HECTARE"}, _Parcel()):
            assert finding.evidence
            assert finding.check
            assert finding.severity in ("info", "warning")


class TestThroughTheWorkspace:
    def test_the_verifier_workspace_carries_cross_reference_findings(
        self, client, auth, uploaded_for_xref
    ):
        body = client.get(
            f"/api/v1/verifications/{uploaded_for_xref}/workspace",
            headers=auth(VERIFIER),
        ).json()
        assert "cross_reference" in body
        assert isinstance(body["cross_reference"], list)

    def test_cross_reference_is_kept_apart_from_format_findings(
        self, client, auth, uploaded_for_xref
    ):
        """Merging them would invite fixing the page to match the reference."""
        body = client.get(
            f"/api/v1/verifications/{uploaded_for_xref}/workspace",
            headers=auth(VERIFIER),
        ).json()
        assert body["cross_reference"] is not body["findings"]
        for row in body["cross_reference"]:
            assert "check" in row and "rule" not in row


@pytest.fixture(scope="module")
def uploaded_for_xref(client, token_for):
    """A processed document, so the workspace has extractions to check."""
    import json

    from conftest import fresh_scan
    from demo_users import DEO

    index = json.loads(
        (REPO_ROOT / "datasets" / "metadata" / "documents.v1.json").read_text()
    )
    clean = next((d for d in index if d["difficulty"] == "clean"), None)
    if clean is None:
        pytest.skip("run scripts/generate_documents.py --profile v1 first")
    path = REPO_ROOT / "datasets" / clean["degraded_image"]
    if not path.exists():
        pytest.skip("run scripts/generate_documents.py --profile v1 first")

    upload = client.post(
        "/api/v1/documents",
        files={"file": ("xref.jpg", fresh_scan(path), "image/jpeg")},
        data={"document_type": "KHASRA", "village_id": "LOC-VIL-01"},
        headers={"Authorization": f"Bearer {token_for(DEO)}"},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["document_id"]
    client.post(
        f"/api/v1/documents/{document_id}/process",
        params={"synchronous": True},
        headers={"Authorization": f"Bearer {token_for(DEO)}"},
    )
    return document_id
