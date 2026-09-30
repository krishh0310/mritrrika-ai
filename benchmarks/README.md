# Benchmarks

From the repository root, run `.venv/bin/python benchmarks/benchmark.py --output benchmarks/results.json`. `baseline.json` is the captured pre-remediation 10-call profile; `results.json` is the measured current run. Workload, complexity, and limits are documented in [performance.md](../docs/performance.md).

## Local image/PDF OCR pipeline

```bash
.venv/bin/python benchmarks/document_pipeline.py --detector server --languages hi --repeats 1 --output /tmp/server.json
.venv/bin/python benchmarks/document_pipeline.py --detector mobile --languages hi --repeats 1 --output /tmp/mobile.json
.venv/bin/python benchmarks/compare_pipeline.py /tmp/server.json /tmp/mobile.json --min-f1 0.9 --max-memory-mib 4096 --output /tmp/operating-points.json
.venv/bin/python -m impact /tmp/mobile.json --pipeline
```

Install the AI/dataset dependencies and configured Indic fonts first. Models must be cached or downloaded by PaddleOCR. Run sequentially on an otherwise idle machine. Supported fixture languages: hi, te, ta, kn; committed measurements cover Hindi only. See the script's `--help` for arguments. Captured before/after reports are in `document-pipeline/`; before reports precede the merged-label extraction fix. Environment, workload hashes, per-stage observations and limitations are included. The comparator rejects differing workloads/environments and failed runs. This is a local synthetic development benchmark, not an API/load test or held-out ML evaluation.
