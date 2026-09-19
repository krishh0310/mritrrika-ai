"""Suspected handwriting reaches the reviewer with detail, not just a flag."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from demo_users import VERIFIER
from staged_documents import Field, delete, stage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ai-worker"))

from ocr.handwriting import routing_meta  # noqa: E402

pytestmark = pytest.mark.integration

HANDWRITTEN = (300, 400, 520, 440)
QUALITY = {"blur_score": 0.9, "skew_score": 0.6, "contrast_score": 0.6}


class TestRoutingMeta:
    def test_fields_inside_handwritten_regions_are_named(self):
        meta = routing_meta(
            blocks=[((80, 100, 260, 134), False), (HANDWRITTEN, True),
                    ((300, 150, 400, 184), False), ((90, 500, 330, 530), False)],
            fields=[("OWNER", (310, 405, 510, 435)), ("KHASRA", (300, 150, 400, 184)),
                    ("AREA", (320, 420, 380, 438)), ("VILLAGE", (80, 100, 260, 134))],
            quality=QUALITY,
        )
        assert meta["affected_fields"] == ["area", "owner"]
        assert meta["coverage_pct"] == 0.25
        assert meta["confidence"] == pytest.approx(0.7)

    def test_nothing_flagged_is_none(self):
        assert routing_meta([((0, 0, 9, 9), False)], [("OWNER", (0, 0, 9, 9))], QUALITY) is None

    def test_pipeline_results_map_ocr_boxes_back_before_overlapping(self):
        from app.services.pipeline_service import handwriting_meta_for

        halve = lambda b: tuple(v // 2 for v in b)  # noqa: E731 - prepared = 2x original
        result = SimpleNamespace(
            original_bbox=halve,
            ocr=SimpleNamespace(blocks=[
                SimpleNamespace(bbox=(600, 800, 1040, 880), is_handwritten=True),
                SimpleNamespace(bbox=(160, 200, 520, 268), is_handwritten=False)]),
            fields=[SimpleNamespace(field="MUTATION", bbox=(310, 405, 510, 435))],
        )
        meta = handwriting_meta_for([result], QUALITY)
        assert meta["affected_fields"] == ["mutation_number"]


@pytest.fixture
def two_documents(client):
    from app.db import SessionLocal

    with SessionLocal() as s:
        written = stage(s, [Field("OWNER", "राम", 0.4, (310, 405, 510, 435))])
        printed = stage(s, [Field("OWNER", "सीमा", 0.4, (310, 405, 510, 435))])
        written.handwriting_meta = routing_meta(
            [(HANDWRITTEN, True), ((0, 0, 50, 20), False)],
            [("OWNER", (310, 405, 510, 435))], QUALITY)
        s.commit()
        yield written.external_id, printed.external_id
        delete(s, written, printed)


def test_the_queue_filters_to_handwritten(client, auth, two_documents):
    written, printed = two_documents
    ids = {t["document_id"] for t in client.get(
        "/api/v1/verifications", params={"handwritten": "true"}, headers=auth(VERIFIER)
    ).json()["tasks"]}
    assert written in ids and printed not in ids
    assert all(t["handwriting_meta"] for t in client.get(
        "/api/v1/verifications", params={"handwritten": "true"}, headers=auth(VERIFIER)
    ).json()["tasks"])


def test_the_record_carries_the_meta_and_null_when_printed(client, auth, two_documents):
    written, printed = two_documents
    body = client.get(f"/api/v1/records/{written}", headers=auth(VERIFIER)).json()
    assert body["handwriting_meta"]["affected_fields"] == ["owner"]
    body = client.get(f"/api/v1/records/{printed}", headers=auth(VERIFIER)).json()
    assert "handwriting_meta" in body and body["handwriting_meta"] is None


def test_semantic_search_is_not_captured_by_the_record_route(client, auth):
    response = client.get("/api/v1/records/semantic-search", params={"q": "khasra"},
                          headers=auth(VERIFIER))
    assert response.status_code == 200 and "results" in response.json()
