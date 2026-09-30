"""Benchmark fixtures must be deterministic, correctly shaped, and decodable."""

import hashlib

import pytest
from ingest.rasterize import decode_pages

from benchmarks.document_pipeline import corpus, summary


def test_fixture_formats_page_counts_and_workload_hashes():
    documents = corpus(["hi"])
    assert len(documents) == 4
    assert {c["format"] for c, _ in documents} == {"PNG", "PDF"}
    assert {c["quality"] for c, _ in documents} == {"clean", "blurred"}
    for config, payload in documents:
        assert hashlib.sha256(payload).hexdigest() == config["sha256"]
        assert len(decode_pages(payload)) == config["pages"]
    assert [c["sha256"] for c, _ in documents] == [c["sha256"] for c, _ in corpus(["hi"])]


def test_percentiles_report_sample_size_and_empty_measurements():
    measured = summary([0.001, 0.002, 0.003, 0.004, 0.005])
    assert measured == {"count": 5, "p50_ms": 3.0, "p95_ms": 4.8, "p99_ms": 4.96}
    assert summary([])["p99_ms"] is None
    assert measured["p99_ms"] >= measured["p95_ms"] >= measured["p50_ms"]
    assert summary([0.003])["p99_ms"] == pytest.approx(3.0)
