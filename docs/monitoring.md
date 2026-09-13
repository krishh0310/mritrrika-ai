# Operational monitoring

Prometheus scrapes the API; Grafana draws it. Nine panels covering the
pipeline's health, for whoever is on call.

This is **not** the tehsildar's analytics screen. That one answers "how is the
digitisation programme going"; this one answers "is the system working right
now". A DEO saying uploads are not processing is a queue-depth question, not an
approval-rate question.

## The exposition already existed

`/metrics` has emitted Prometheus text format since before this was set up —
HTTP counters, a latency histogram, queue depth, failure counts, stage
latencies, confidence and correction rates. What was missing was something to
scrape it and somewhere to look.

| metric | what it answers |
|---|---|
| `mrittika_processing_queue_depth` | is the worker consuming? A flat non-zero line means it is not |
| `mrittika_documents_by_state` | where work is piling up |
| `mrittika_ai_failures_total` | pipeline defects, as distinct from bad scans |
| `mrittika_http_errors_total` | the API breaking, as distinct from a document failing |
| `mrittika_http_request_duration_seconds` | p50 / p95 latency |
| `mrittika_stage_latency_seconds` | where a page spends its time |
| `mrittika_average_confidence` | a leading indicator of verifier workload |
| `mrittika_correction_rate` | how often a verifier had to change a value — the honest measure of whether the model is helping |
| `mrittika_verification_seconds` | how long a document sits with a verifier |

`tests/backend/test_metrics_access.py` asserts every metric the dashboard
queries is one the API actually emits, checked against the **live** exposition
rather than a hard-coded list. Renaming a metric breaks a test before it
reaches an on-call engineer staring at an empty panel.

## Prometheus cannot hold a JWT

That is the whole reason `/metrics` grew a second way in. Prometheus has no
login and its bearer credentials are static, so the endpoint accepts either:

* an officer holding `analytics:view` — as before; or
* a static scrape token, compared with `hmac.compare_digest` so an early-exit
  comparison cannot leak the token's length and prefix to anyone timing the
  response.

**With `METRICS_SCRAPE_TOKEN` unset there is no token path at all.** That is
the safe default: a misconfigured scraper fails to authenticate rather than
silently publishing workload and queue depth to whoever asks.

The token is mounted into Prometheus from a gitignored file rather than written
into `prometheus.yml`, which is committed. A committed credential is a leaked
credential.

## Standing it up

```bash
# 1. A token, and a file for Prometheus to read it from
python -c "import secrets; print(secrets.token_urlsafe(32))"   # -> $TOKEN
mkdir -p .monitoring && printf '%s' "$TOKEN" > .monitoring/scrape-token

# 2. The API needs the same token
METRICS_SCRAPE_TOKEN="$TOKEN" \
  .venv/bin/python -m uvicorn app.main:app --app-dir apps/api --port 8000

# 3. Prometheus + Grafana. docker-compose.yml MUST come first -- see below.
GRAFANA_ADMIN_PASSWORD='...' docker compose \
  -f docker-compose.yml \
  -f infrastructure/docker/compose.monitoring.yml up -d prometheus grafana
```

Grafana at <http://127.0.0.1:3001>, Prometheus at <http://127.0.0.1:9090>. Both
bind to localhost: an exposed Prometheus is a description of the system's
behaviour handed to anyone who asks.

Two footguns, both hit while setting this up:

* **Pass `docker-compose.yml` first.** Compose resolves relative volume paths
  against the project directory — the directory of the *first* `-f` file — not
  against the file that declares them. Paths in the overlay are therefore
  written relative to the repo root, and running the overlay alone resolves
  them two levels too high and fails with a permission error on `/Users`.
* **`host.docker.internal`.** The API and worker run natively rather than in
  the compose network, because paddlepaddle has no reliable linux/arm64 wheel
  (see [architecture.md](architecture.md)). The `extra_hosts` entry supplies
  that name on Linux, where Docker does not provide it automatically. In a
  deployment where the API is containerised, this becomes its service name.

## Verified working

Not just configured — the chain was run end to end:

```
Prometheus targets:  mrittika-api  up
Query via Grafana:   mrittika_documents_by_state -> 12 series (QUALITY_CHECK=105)
Scrape-token auth:   correct 200, wrong 401, absent 401
```

Grafana's datasource and dashboard are **provisioned from files**, not clicked
in the UI — a datasource configured by hand lives only in that container's
volume and is lost with it.

## What is NOT done

| | status |
|---|---|
| Alerting rules | not written — the dashboard shows, it does not page |
| Worker-side metrics | not exposed; queue depth is read from the database, not from Celery |
| Log aggregation (Loki or equivalent) | not set up |
| Tracing | not instrumented |
| Long-term storage | 15-day local retention only |
| Superset | not used — the business-analytics screen already lives in the application |
