"""Who may read the operational metrics (§74, §18).

/metrics describes workload, queue depth, failure counts and confidence
averages. That is operational intelligence about a revenue system, so the
endpoint is never public -- and the interesting case is the one added for
Prometheus, which cannot hold a JWT because it has no login and its bearer
credentials are static.

Two ways in, and the tests here are mostly about there being no third.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from demo_users import CITIZEN_A, DEO, TEHSILDAR, VERIFIER

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

TOKEN = "test-scrape-token-not-a-real-one"


@pytest.fixture
def scrape_token(monkeypatch):
    """Configure a scrape token for the duration of one test."""
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("METRICS_SCRAPE_TOKEN", TOKEN)
    yield TOKEN
    get_settings.cache_clear()


class TestPermissionPath:
    def test_the_tehsildar_may_read_metrics(self, client, auth):
        response = client.get("/metrics", headers=auth(TEHSILDAR))
        assert response.status_code == 200
        assert "mrittika_processing_queue_depth" in response.text

    @pytest.mark.parametrize("email", [CITIZEN_A, DEO, VERIFIER])
    def test_everyone_without_analytics_view_is_refused(self, client, auth, email):
        assert client.get("/metrics", headers=auth(email)).status_code == 403

    def test_an_anonymous_request_is_refused(self, client):
        assert client.get("/metrics").status_code == 401


class TestScrapeTokenPath:
    def test_the_configured_token_is_accepted(self, client, scrape_token):
        response = client.get(
            "/metrics", headers={"Authorization": f"Bearer {scrape_token}"}
        )
        assert response.status_code == 200
        assert "mrittika_" in response.text

    def test_a_wrong_token_is_refused(self, client, scrape_token):
        response = client.get(
            "/metrics", headers={"Authorization": "Bearer not-the-token"}
        )
        assert response.status_code == 401

    def test_a_token_that_is_a_prefix_is_refused(self, client, scrape_token):
        """compare_digest, so a prefix is no closer than anything else."""
        response = client.get(
            "/metrics", headers={"Authorization": f"Bearer {scrape_token[:-1]}"}
        )
        assert response.status_code == 401

    def test_with_no_token_configured_there_is_no_token_path(self, client, monkeypatch):
        """The safe default: a misconfigured scraper fails rather than
        silently publishing the exposition."""
        from app.config.settings import get_settings

        get_settings.cache_clear()
        monkeypatch.delenv("METRICS_SCRAPE_TOKEN", raising=False)
        try:
            response = client.get("/metrics", headers={"Authorization": "Bearer "})
            assert response.status_code == 401
        finally:
            get_settings.cache_clear()


class TestWhatIsExposed:
    def test_the_exposition_is_prometheus_text_format(self, client, auth):
        response = client.get("/metrics", headers=auth(TEHSILDAR))
        assert response.headers["content-type"].startswith("text/plain")
        assert "# TYPE" in response.text

    def test_no_record_content_is_exposed(self, client, auth):
        """Metrics are counts and rates -- never a name or a khasra number."""
        body = client.get("/metrics", headers=auth(TEHSILDAR)).text
        for leak in ("khasra", "owner", "@mrittika.demo", "PARCEL-"):
            assert leak.lower() not in body.lower(), leak

    def test_the_dashboard_only_queries_metrics_that_exist(self, client, auth):
        """A panel querying a metric the API never emits is an empty panel.

        Checked against the live exposition rather than a hard-coded list, so
        renaming a metric breaks this before it reaches an on-call engineer.
        """
        import json
        import re

        body = client.get("/metrics", headers=auth(TEHSILDAR)).text
        emitted = set(re.findall(r"^(mrittika_[a-z_]+)", body, re.M))
        # Histograms expose _bucket/_sum/_count suffixes that the base name
        # does not appear without.
        emitted |= {name.rsplit("_", 1)[0] for name in emitted}

        dashboard = json.loads(
            (REPO_ROOT / "infrastructure/monitoring/grafana/dashboards"
             / "pipeline-operations.json").read_text()
        )
        referenced = {
            m for panel in dashboard["panels"] for target in panel["targets"]
            for m in re.findall(r"mrittika_[a-z_]+", target["expr"])
        }
        missing = sorted(referenced - emitted)
        assert not missing, f"dashboard queries metrics the API does not emit: {missing}"
