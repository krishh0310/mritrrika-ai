"""Corrections become curated retraining candidates (§30, §67).

The table these rows land in has existed since the initial schema with nothing
writing to it. Two properties matter now that something does.

The ranking must put a CONFIDENT wrong answer above an unsure one. That is the
whole point of the pool: a field returned at 0.97 that a verifier had to
rewrite is a systematic error the model cannot see, while a field returned at
0.30 and rewritten is the confidence engine working exactly as designed.

And nothing may retrain automatically. Every row arrives unreviewed, and
readiness is a report a human reads, not a trigger.
"""

import pytest
from demo_users import DEO, TEHSILDAR, VERIFIER

pytestmark = pytest.mark.integration

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.services import feedback_service  # noqa: E402


class TestRanking:
    def test_confident_and_wrong_outranks_unsure_and_wrong(self):
        confident = feedback_service.classify(0.97, "राम")[1]
        unsure = feedback_service.classify(0.30, "राम")[1]
        assert confident > unsure

    def test_more_confident_and_wrong_ranks_higher_still(self):
        assert feedback_service.classify(0.99, "x")[1] > \
               feedback_service.classify(0.86, "x")[1]

    def test_confident_band_is_labelled(self):
        assert feedback_service.classify(0.95, "x")[0] == \
               feedback_service.CONFIDENT_BUT_WRONG

    def test_unsure_band_is_labelled(self):
        assert feedback_service.classify(0.20, "x")[0] == \
               feedback_service.UNCERTAIN_AND_WRONG

    def test_an_empty_prediction_is_a_miss_not_a_wrong_answer(self):
        reason, _ = feedback_service.classify(0.9, "   ")
        assert reason == feedback_service.MISSED_ENTIRELY

    def test_absent_confidence_does_not_crash_the_ranking(self):
        reason, score = feedback_service.classify(None, "x")
        assert reason == feedback_service.MODERATE_MISS
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize("confidence", [0.0, 0.3, 0.55, 0.7, 0.85, 0.99, 1.0])
    def test_every_score_stays_in_range(self, confidence):
        _, score = feedback_service.classify(confidence, "x")
        assert 0.0 <= score <= 1.0


class TestNothingRetrainsItself:
    """§67: the pool is a proposal, never a trigger."""

    def test_readiness_reports_rather_than_acts(self, client, auth):
        response = client.get("/api/v1/ai/feedback", headers=auth(TEHSILDAR))
        assert response.status_code == 200, response.text
        readiness = response.json()["readiness"]
        assert set(readiness) >= {"reviewed", "pending_review", "threshold",
                                  "ready_to_retrain"}
        assert isinstance(readiness["ready_to_retrain"], bool)

    def test_unreviewed_rows_never_count_towards_readiness(self, client, auth):
        body = client.get("/api/v1/ai/feedback", headers=auth(TEHSILDAR)).json()
        reviewed_rows = [r for r in body["pool"] if r["reviewed"]]
        assert body["readiness"]["reviewed"] >= len(reviewed_rows) - len(body["pool"])
        assert body["readiness"]["reviewed"] <= \
               body["readiness"]["reviewed"] + body["readiness"]["pending_review"]


class TestAccess:
    def test_a_citizen_cannot_read_the_pool(self, client, auth):
        from demo_users import CITIZEN_A
        assert client.get(
            "/api/v1/ai/feedback", headers=auth(CITIZEN_A)
        ).status_code == 403

    def test_a_deo_cannot_read_the_pool(self, client, auth):
        assert client.get("/api/v1/ai/feedback", headers=auth(DEO)).status_code == 403

    def test_a_verifier_can(self, client, auth):
        assert client.get(
            "/api/v1/ai/feedback", headers=auth(VERIFIER)
        ).status_code == 200

    def test_the_pool_never_returns_corrected_values(self, client, auth):
        body = client.get("/api/v1/ai/feedback", headers=auth(TEHSILDAR)).json()
        for row in body["pool"]:
            assert "corrected_value" not in row
            assert "model_prediction" not in row
