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
