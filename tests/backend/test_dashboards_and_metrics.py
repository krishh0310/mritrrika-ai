"""Role dashboards, analytics and the metrics endpoint (§20, §27, §31, §74).

The cards themselves are aggregates over seeded state, so these tests assert
shape and authorization rather than exact counts -- the counts move as other
tests file grievances and process documents.
"""

from __future__ import annotations

import pytest
from demo_users import CITIZEN_A, DEO, TEHSILDAR, VERIFIER

DEO_CARDS = {
    "uploaded_today", "processing", "completed", "needs_verification",
    "quality_rejected", "failed",
}
VERIFIER_CARDS = {
    "assigned", "needs_review", "low_confidence", "medium_confidence",
    "anomaly_flagged", "completed_today",
}
TEHSILDAR_CARDS = {
    "pending_approval", "approved_today", "returned", "potential_inconsistencies",
    "average_ai_confidence", "average_verification_seconds", "digitization_progress",
    "extraction_accuracy",
}


class TestDeoDashboard:
    def test_returns_every_card_in_the_spec(self, client, auth):
        response = client.get("/api/v1/dashboard/deo", headers=auth(DEO))
        assert response.status_code == 200
        body = response.json()
        assert set(body["cards"]) == DEO_CARDS
        assert all(isinstance(v, int) for v in body["cards"].values())

    def test_includes_recent_documents(self, client, auth):
        body = client.get("/api/v1/dashboard/deo", headers=auth(DEO)).json()
        assert isinstance(body["recent_documents"], list)
        for document in body["recent_documents"]:
            assert document["document_id"].startswith("DOC-")
            assert "state" in document

    @pytest.mark.parametrize("email", [CITIZEN_A, VERIFIER, TEHSILDAR])
    def test_requires_the_upload_permission(self, client, auth, email):
        assert client.get("/api/v1/dashboard/deo", headers=auth(email)).status_code == 403


class TestVerifierDashboard:
    def test_returns_every_card_in_the_spec(self, client, auth):
        response = client.get("/api/v1/dashboard/verifier", headers=auth(VERIFIER))
        assert response.status_code == 200
        assert set(response.json()["cards"]) == VERIFIER_CARDS

    def test_confidence_bands_do_not_overlap(self, client, auth):
        """A task counted as low must not also be counted as medium (§8)."""
        cards = client.get(
            "/api/v1/dashboard/verifier", headers=auth(VERIFIER)
        ).json()["cards"]
        assert cards["low_confidence"] + cards["medium_confidence"] <= cards["needs_review"]

    @pytest.mark.parametrize("email", [CITIZEN_A, DEO, TEHSILDAR])
    def test_requires_the_verify_permission(self, client, auth, email):
        response = client.get("/api/v1/dashboard/verifier", headers=auth(email))
        assert response.status_code == 403


class TestTehsildarDashboard:
    def test_returns_every_card_in_the_spec(self, client, auth):
        response = client.get("/api/v1/dashboard/tehsildar", headers=auth(TEHSILDAR))
        assert response.status_code == 200
        assert set(response.json()["cards"]) == TEHSILDAR_CARDS

    def test_digitization_progress_is_a_fraction(self, client, auth):
        cards = client.get(
            "/api/v1/dashboard/tehsildar", headers=auth(TEHSILDAR)
        ).json()["cards"]
        assert 0.0 <= cards["digitization_progress"] <= 1.0

    @pytest.mark.parametrize("email", [CITIZEN_A, DEO, VERIFIER])
    def test_requires_the_approve_permission(self, client, auth, email):
        response = client.get("/api/v1/dashboard/tehsildar", headers=auth(email))
        assert response.status_code == 403


class TestAnalytics:
    def test_returns_distributions(self, client, auth):
        response = client.get("/api/v1/dashboard/analytics", headers=auth(TEHSILDAR))
        assert response.status_code == 200
        body = response.json()
        for key in (
            "documents_by_state", "documents_by_type", "confidence_bands",
            "anomalies_by_type", "workload",
        ):
            assert key in body, f"missing {key}"
        assert set(body["confidence_bands"]) == {"HIGH", "MEDIUM", "LOW"}

    @pytest.mark.parametrize("email", [CITIZEN_A, DEO, VERIFIER])
    def test_analytics_is_tehsildar_only(self, client, auth, email):
        """§36 grants `analytics:view` to the tehsildar alone."""
        response = client.get("/api/v1/dashboard/analytics", headers=auth(email))
        assert response.status_code == 403


class TestObservability:
    def test_health_needs_no_token(self, client):
        assert client.get("/health").status_code == 200

    def test_metrics_requires_analytics_permission(self, client, auth):
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers=auth(CITIZEN_A)).status_code == 403

    def test_metrics_is_prometheus_text(self, client, auth):
        response = client.get("/metrics", headers=auth(TEHSILDAR))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")

        body = response.text
        for metric in (
            "mrittika_http_requests_total",
            "mrittika_http_request_duration_seconds_bucket",
            "mrittika_processing_queue_depth",
            "mrittika_average_confidence",
            "mrittika_documents_by_state",
            "mrittika_correction_rate",
        ):
            assert metric in body, f"{metric} missing from /metrics"

    def test_every_metric_has_help_and_type(self, client, auth):
        """Malformed exposition silently breaks a scraper, so check the form."""
        body = client.get("/metrics", headers=auth(TEHSILDAR)).text
        helps = {line.split()[2] for line in body.splitlines() if line.startswith("# HELP")}
        types = {line.split()[2] for line in body.splitlines() if line.startswith("# TYPE")}
        assert helps == types, f"HELP/TYPE mismatch: {helps ^ types}"

    def test_request_counter_advances(self, client, auth):
        def total() -> int:
            return sum(
                int(line.rsplit(" ", 1)[1])
                for line in client.get("/metrics", headers=auth(TEHSILDAR)).text.splitlines()
                if line.startswith("mrittika_http_requests_total{")
            )

        before = total()
        client.get("/health")
        assert total() > before

    def test_histogram_buckets_are_cumulative(self, client, auth):
        body = client.get("/metrics", headers=auth(TEHSILDAR)).text
        counts = [
            int(line.rsplit(" ", 1)[1])
            for line in body.splitlines()
            if line.startswith("mrittika_http_request_duration_seconds_bucket")
        ]
        assert counts == sorted(counts), "bucket counts must be non-decreasing"
