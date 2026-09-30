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
