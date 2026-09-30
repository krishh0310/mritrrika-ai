# Performance

Measurements use CPython 3.12 on the development machine, one process, a deterministic synthetic 150-block OCR page. OCR, network, and database latency are excluded. Reproduce current results with `.venv/bin/python benchmarks/benchmark.py --output benchmarks/results.json`.

| Workload | Before | After | Method |
|---|---:|---:|---|
| Ten repeated 150-block scalar extractions | 5.385 s | 0.1265 s | `cProfile`; baseline captured before edits in `benchmarks/baseline.json` |
| Thirty varied 150-block pages | — | 31.743 ms median, 33.304 ms p95 | `time.perf_counter`; `benchmarks/results.json` |

The repeated-page speedup reflects cache reuse. The varied-page figure is the better estimate for a stream of distinct documents. Neither number predicts full upload latency, which is dominated by OCR and storage.

## Core work and bounds

| Algorithm | Complexity / bound | Note |
|---|---|---|
| Scalar field extraction | O(F × B × V + F × B log B) for F fields, B blocks, V label variants | Each block/field score is computed once per page; bounded cross-page cache avoids repeated OCR labels. The previous neighbor scan reclassified labels repeatedly. |
| Owner/share table extraction | O(B²) worst case from line grouping | Typical forms have tens of blocks; optimize after a measured corpus shows this is hot. |
| Parcel lookup | O(log P) common exact match with indexed `(village_id, khasra_number)`; O(P) fallback | P is parcels in a village. Fallback retains punctuation-tolerant matching on misses. |
| Exact document duplicate | O(1) indexed digest lookup after O(bytes) SHA-256 | The near-duplicate branch only runs when exact lookup misses. |
| Near duplicate scan | O(D) over candidate hashes | D is candidate documents. Use an approximate index if the corpus makes this hot. |
| Map viewport | Spatial index query plus at most 200 returned parcels | See `search_service.MAX_RESULTS`. |
| S3 I/O | Bounded by 5 s connect and 30 s read timeout | One cached boto3 client with a 20-connection pool per process. |

The API's SQLAlchemy engine already pools connections and pre-pings stale ones. OCR and handwriting models are lazily loaded once per worker process. Upload processing is queued through Celery so the request does not wait for model inference.

## Real OCR pipeline: measured development corpus

Raw observations and environment versions are in [`benchmarks/document-pipeline/`](../benchmarks/document-pipeline/). Each run used the same four synthetic Hindi documents (six pages): clean and blurred scans, PNG and two-page PDF, four expected fields per page. One repeat per workload on macOS arm64, Python 3.12.14, PaddleOCR 3.7.0, Paddle 3.3.1. Font and document hashes are recorded.

| Detector / extraction | p50 document ms | p95 ms | p99 ms | Documents/s | Peak RSS MiB | Field F1 | Failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| Server / before | 10622.916 | 15132.380 | 15141.948 | 0.09820 | 16043.03 | 0.4000 | 0/4 |
| Server / after | 10577.812 | 15301.038 | 15344.185 | 0.09807 | 15386.47 | 1.0000 | 0/4 |
| Mobile / before | 2438.471 | 3334.059 | 3339.937 | 0.41263 | 1959.33 | 0.2857 | 0/4 |
| Mobile / after | 2393.768 | 3284.949 | 3290.281 | 0.41860 | 1964.31 | 0.9167 | 0/4 |

Profiling exposed merged label:value blocks being rejected by the label-length guard. The shared extractor now scores the explicit label prefix and preserves its attached value. This improves this regression corpus's extraction quality; it does not demonstrate a material OCR latency improvement. The mobile detector offers a latency/memory trade-off at lower measured field accuracy. The production detector default is unchanged.

Model cold loads after the fix were 11.761 s (server) and 11.976 s (mobile). Warm model access reuses the loaded instance; this is not warm inference latency. Per-stage raw timings cover decoding, preprocessing, OCR, layout, extraction, normalization, validation and confidence. Peak RSS includes fixture generation and models. Four documents cannot establish reliable tail latency. This development corpus is neither held-out evaluation nor evidence of real-scan accuracy. API response, queue wait, database, object storage and concurrent backpressure remain unmeasured by this harness.

The offline Pareto selector is O(C²) for C measured configurations. It preserves accuracy and memory constraints and abstains when none qualify; it is intended for a small configuration sweep. See [benchmark commands](../benchmarks/README.md).
