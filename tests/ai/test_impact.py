"""The impact report must calculate deltas from inputs and reject mismatches."""

import pytest

from impact import ImpactReporter


def test_report_uses_measured_times():
    current = {"iterations": 10, "blocks_per_page": 150, "total_seconds": 1.0}
    baseline = {"iterations": 10, "blocks_per_page": 150, "total_seconds": 2.0}
    report = ImpactReporter(current, baseline).report()
    assert report["seconds_saved"] == 1.0
    assert report["throughput_gain_pct"] == 100.0
    with pytest.raises(ValueError):
        ImpactReporter(current, baseline | {"blocks_per_page": 100}).report()


def test_pipeline_impact_uses_observations_without_inventing_human_savings():
    from impact.reporter import pipeline_metrics

    report = {
        "scope": "synthetic local pipeline", "peak_process_rss_mib": 1000,
        "observations": [{"total_seconds": 2.0, "fields": 4, "review_fields": 3,
                          "empty_pages": 0, "error": None}],
    }
    metrics = pipeline_metrics(report)
    assert metrics["successful_documents_per_second"] == 0.5
    assert metrics["flagged_fraction_of_extracted_fields"] == 0.75
    assert metrics["human_review_seconds_saved"] is None
    with pytest.raises(ValueError):
        pipeline_metrics(report | {"observations": []})
    report["observations"][0]["total_seconds"] = float("nan")
    with pytest.raises(ValueError):
        pipeline_metrics(report)
