# AI and ML operations

The detailed pipeline, measured experiments, and fallback behavior are in
[ai-pipeline.md](ai-pipeline.md). This document defines the operating contract
around that pipeline.

## Request and inference flow

```text
API authorization -> object metadata -> Redis/Celery job -> worker
  -> byte/raster validation -> quality -> OCR -> layout/extraction
  -> normalization -> validation/confidence -> anomaly signals
  -> PostgreSQL result + model version -> human review -> approved record
```

The frontend never calls a private model provider. Expensive document inference
runs in a worker with soft/hard time limits, late acknowledgement, worker-loss
redelivery, and stale-job recovery. The grounded assistant retrieves only rows
already authorized for the caller; optional LLM phrasing is not the source of
record facts.

AI query traffic is protected by three counters shared through Redis in a
multi-instance deployment:

- `AI_QUERY_RATE_LIMIT_USER` per `AI_QUERY_RATE_LIMIT_WINDOW_SECONDS`;
- `AI_QUERY_RATE_LIMIT_IP` per the same window;
- `AI_QUERY_DAILY_QUOTA` per user.

The API returns HTTP 429 and `Retry-After` before retrieval or provider use when
a limit is exhausted.

## Model registry and provenance

`models/registry/model_versions.json` is the source registry loaded into the
`model_versions` table. Every extraction/anomaly result stores the exact model
or rule version that produced it. Registry entries must state what actually
runs and distinguish pretrained models, fine-tuned artifacts, deterministic
rules, heuristics, and uncalibrated scores.

A production promotion record should add immutable artifact checksum, dataset
version, training code revision, training date, evaluation cohort, precision,
recall, F1, calibration/thresholds, approver, activation time, and rollback
target. Do not mark a model active until those values come from a reproducible
evaluation; placeholders are worse than an explicit missing measurement.

## Safe deployment rules

- Keep provider/model secrets server-side.
- Validate size, type, dimensions/page count, and rasterization before model
  execution; reject decompression bombs and pathological documents.
- Bound provider and worker execution time; retries must be bounded and used
  only for transient failures.
- Persist raw input provenance and raw/normalized outputs separately.
- Route low-confidence, invalid, degraded, or anomalous output to human review.
- Log latency, failure category, provider, and model version without document
  content or credentials.
- Promote and roll back by registry/config change, never by silently replacing
  an artifact behind an existing version.

Current prototype debt is explicit: confidence is not calibrated on a
representative production corpus, learned extraction experiments are not the
default path, and model artifacts are not signed. A standalone network model
registry is not warranted until multiple deployment teams or artifact volume
make the file/database registry insufficient.
