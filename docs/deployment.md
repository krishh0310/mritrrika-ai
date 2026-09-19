# Deployment

This is a hackathon prototype holding synthetic data. Nothing here has been
through a security audit, a load test, or an STQC evaluation. What follows is
the intended production target and the honest distance from it.

## Intended target: NIC MeghRaj

Land records are covered by the Government of India's data-localisation
expectations, and the Digital India Land Records Modernisation Programme
(DILRMP) is run through NIC infrastructure. So the target is **NIC MeghRaj**
(the National Cloud), not a commercial hyperscaler, for reasons that are
regulatory rather than technical:

* **Residency.** Records of rights are state revenue data. It stays on
  government-controlled infrastructure inside India.
* **Empanelment.** State revenue departments consume services through NIC or
  MeitY-empanelled providers; a deployment outside that list is not procurable
  however well it runs.
* **Integration.** DILRMP, BhuNaksha and the state's existing RoR systems are
  already inside that network. An integration across a public-internet boundary
  is a larger security surface than one inside it.

A MeitY-empanelled commercial cloud in an Indian region is the fallback if NIC
capacity is unavailable. A non-Indian region is not an option.

## What the stack needs

| component | what it needs | notes |
|---|---|---|
| API (FastAPI) | 2 vCPU, 4 GB | stateless, scale horizontally |
| Worker (Celery) | 4 vCPU, 8 GB+ | PaddleOCR's server detector peaks near 19 GB across a long-lived process; the worker recycles deliberately |
| Postgres 16 | PostGIS + pgvector | managed, with PITR |
| Redis | 1 GB | broker and auth state |
| Object storage | S3-compatible | MinIO locally; NIC object storage in production |
| Web (Next.js) | 1 vCPU, 2 GB | or a static/edge deployment |
| GeoServer | 2 vCPU, 4 GB | optional; see [gis-integration.md](gis-integration.md) |

**Architecture constraint that survives the move:** the worker runs natively on
macOS-arm64 during development because paddlepaddle has no reliable linux/arm64
wheel. In production it runs on **x86_64 Linux**, where it does build. Do not
plan an arm64 production fleet without re-testing the OCR stack first.

## Notifications

Both channels are template-based, and that is a regulatory constraint rather
than an API detail:

* **WhatsApp Business Cloud API** — a business-initiated message needs a
  template approved by Meta. Free-form text only works inside a 24-hour window
  after the user writes first, which never happens in this flow.
* **SMS in India** — TRAI's DLT regime requires each transactional template to
  be registered against a principal entity. A message sent without a valid DLT
  template ID is **accepted by the gateway and dropped by the operator**: a
  delivery failure that looks exactly like a success. The provider here refuses
  to send rather than report one.

So going live is not a matter of setting credentials. Every template in
`TEMPLATES` must first be registered with Meta and on the DLT portal, and its
identifiers recorded there.

With no credentials set, the dispatcher records the attempt and the in-app
notification is still written. Nothing in the workflow depends on a gateway
being reachable.

**No notification carries record content.** They are read on lock screens, in
households that may contain the other party to a land dispute. Every template
says that something changed and that the reader should sign in; none names a
person, a khasra number, or an area. `tests/backend/test_notifications.py`
enforces that on every template.

## Before this could carry a real record

Ordered by how load-bearing each one is.

1. **A security audit and an STQC evaluation.** Neither has happened.
2. **Authentication fit for revenue staff** — the current JWT + Argon2 login has
   no MFA, no session revocation list beyond refresh-token reuse detection, and
   no integration with any government identity provider.
3. **The bigha problem.** `SQM_PER_BIGHA` is the Uttar Pradesh pucca bigha,
   hard-coded. A bigha differs by state and sometimes by district. Any real
   deployment must make this configurable per revenue circle, or every area
   comparison outside UP is wrong.
4. **Per-state templates.** The extractor is anchored to the label vocabulary
   of three synthetic UP templates. A different state's Khasra needs its own
   labels and its own evaluation run.
5. **Real accuracy figures.** Every number in this repository is measured on
   synthetic pages. Extraction F1 is **0.59** on the synthetic val split, and
   nothing about that transfers to scanned 1950s registers.
6. **Retention, deletion and consent.** No policy is implemented. Documents and
   extractions are kept indefinitely.
7. **Load testing.** None performed. The known pressure point is worker memory
   under OCR, not request throughput.

## Operational notes

* **Production configuration fails closed.** Set `ENVIRONMENT=production` only
  with a 32+ character JWT secret, non-demo database/object-store credentials,
  `AUTH_STATE_REDIS_URL`, TLS-enabled object storage, and non-local HTTPS CORS
  origins. The API refuses to start if any invariant is missing.
* **Migrations** run as a separate step before the API starts, never on API
  boot — two replicas starting at once would race.
* **The worker recycles** after heavy tasks by design. Do not raise
  `WORKER_CONCURRENCY` above 1 without re-measuring memory: two PaddleOCR
  models in one process is the fastest way to exhaust a container.
* **GeoServer binds to localhost** in the compose overlay. It has no notion of
  this application's authorization and must sit behind an authenticating proxy
  before it is exposed.
* **Backups** must cover Postgres *and* object storage. A database restored
  without its documents leaves every record pointing at a missing scan.
* **Client IPs** for login and AI abuse limits come from the ASGI server's
  trusted proxy handling. The ingress must replace forwarded-IP headers and
  Uvicorn must trust only that ingress; never accept client-supplied forwarding
  headers from the public internet.

The full Compose file is a demo/development topology and intentionally uses
`ENVIRONMENT=docker`. A production deployment must supply its own secrets,
TLS ingress, managed backing services, backup policy, and
`ENVIRONMENT=production`; changing only the Compose environment label is not a
production deployment.
