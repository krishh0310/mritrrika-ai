# Architecture assessment

Assessment date: 2026-09-19

This assessment was written before the production-hardening changes described
below. The repository already has a coherent modular-monolith architecture; a
directory rewrite would add migration risk without improving the runtime
boundaries.

## Executive summary

Mrittika AI is a monorepo containing a Next.js web application, an Expo mobile
application, one authoritative FastAPI backend, a Celery AI worker, PostgreSQL
with PostGIS and pgvector, Redis, and S3-compatible object storage. Offline
dataset and GIS generators are deliberately outside the request path.

The codebase is substantially aligned with the requested target architecture:
API routes are versioned, controllers are thin, business rules live in
services, core queries are isolated in repositories or domain services,
authorization is enforced server-side, expensive inference is queued, binary
files are kept out of PostgreSQL, and predictions retain model provenance.

The safest restructuring is therefore incremental hardening, not moving files
to match a generic template. Existing public routes, database migrations,
model identifiers, storage keys, and UI flows must remain stable.

## Current architecture and data flow

```text
Browser / Expo
      |
      | HTTPS + bearer JWT
      v
Next.js / mobile client
      |
      | /api/v1/*
      v
FastAPI routers -> auth/RBAC -> services -> repositories/domain logic
      |                                  |
      |                                  +-> PostgreSQL/PostGIS/pgvector
      |                                  +-> MinIO object storage
      |                                  +-> external notification/LLM adapters
      v
Redis broker -> Celery worker -> quality/OCR/layout/extraction/validation
                                      |
                                      +-> model registry + persisted provenance
```

An uploaded document is byte-sniffed and size checked, stored under a UUID
object key, represented by metadata in PostgreSQL, and queued for processing.
The worker rasterizes and evaluates quality, runs OCR and extraction, validates
and scores results, persists raw and normalized values with model versions, and
routes uncertain work to human verification. Approval, publication, citizen
retrieval, grievances, and audit events remain backend-controlled.

Authentication uses Argon2 password hashes, short-lived access JWTs, rotating
single-use refresh JWTs, and Redis-backed replay/rate-limit state. JWT claims do
not grant roles: users, roles, permissions, jurisdiction, and citizen ownership
are resolved from PostgreSQL for each request. The web client keeps tokens in
session storage and uses one API client; frontend role checks affect rendering
only.

## Stack and dependency boundaries

| Area | Current implementation |
|---|---|
| Web | Next.js 16, React 19, TypeScript, TanStack Query, React Hook Form, Zod |
| Mobile | Expo/React Native, React Navigation, TanStack Query, Secure Store |
| API | FastAPI, Pydantic, SQLAlchemy 2, Alembic, Psycopg |
| Data | PostgreSQL 16, PostGIS, pgvector |
| Queue/cache | Redis and Celery |
| Storage | MinIO/S3 through boto3; PostgreSQL stores metadata and keys only |
| AI/ML | PaddleOCR/Gemini OCR, deterministic extraction/layout, optional learned models, scikit-learn anomaly detector |
| Delivery | Docker Compose, component Dockerfiles, GitHub Actions |
| Testing | Pytest, Vitest, Playwright, Ruff, TypeScript, ESLint |

Python application dependencies are split between API and AI-worker requirement
files. JavaScript packages are npm workspaces. Many Python ranges are broad,
which is convenient for development but not reproducible enough for a
production release; a tested lock/constraints artifact is still required.

## Database assessment

The relational model correctly separates identity, geography, documents,
workflow, ownership history, AI output, integrations, notifications, and the
audit chain. Migrations define primary and foreign keys, uniqueness rules, and
indexes for the principal lookup paths. Ownership is temporal and normalized;
large binaries are not placed in database rows. PostGIS and pgvector presence
is checked by readiness.

Remaining work before real-data production includes restore-tested encrypted
backups, retention rules, row-level security as defense in depth, migration
rollback rehearsals, query/load profiling, and a review of check constraints
for enum-like status and score/range columns. These should be driven by real
deployment and query evidence rather than speculative schema churn.

## AI/ML assessment

The worker is a separate logical service with bounded Celery task execution,
late acknowledgement, worker-loss requeueing, stale-job recovery, validation,
confidence bands, human review, and persisted model versions. The registry
truthfully distinguishes pretrained models, deterministic rules, heuristics,
and uncalibrated formulas. Provider failures degrade safely instead of
fabricating successful output.

Production gaps are model-artifact signing, immutable dataset/version lineage,
calibrated confidence thresholds, representative real-script evaluation,
drift monitoring, and an explicit promotion/rollback process. The current
registry is appropriate for the prototype and should not be replaced by a
network service until artifact volume or multi-team ownership requires one.

## Security and reliability assessment

Existing strengths:

- explicit CORS allowlist and server-side permissions/jurisdiction checks;
- Argon2 passwords, refresh rotation/replay prevention, and login throttling;
- parameterized ORM access and Pydantic boundary validation;
- byte-level MIME detection, upload limits, UUID object keys, checksums, and
  short-lived signed downloads;
- transaction-coupled, hash-chained audit events;
- liveness, readiness, authenticated Prometheus metrics, queue recovery, and
  safe provider fallbacks;
- secrets excluded from version control and an environment template committed.

Prioritized gaps:

| Priority | Gap | Decision |
|---|---|---|
| P0 | Requests have no correlation identifier and API responses lack baseline security headers | Add one small middleware and tests without changing response bodies |
| P0 | Production configuration can start with local/demo infrastructure defaults | Add startup validation for production-only invariants |
| P1 | Readiness validates PostgreSQL extensions but not Redis/object storage | Add checks when production dependencies are configured; keep local development usable |
| P1 | CI lacked dependency vulnerability checks | Added npm/Python audits and pull-request dependency review; repository secret scanning still depends on platform configuration |
| P1 | Error bodies use FastAPI's stable `detail` shape but do not yet expose typed application error codes | Introduce compatibly, endpoint by endpoint; do not break every client in one pass |
| P2 | Access tokens cannot be immediately revoked | Accept short TTL for the prototype; add denylisting only for a real revocation requirement |
| P2 | No proven restore, load, penetration, or disaster-recovery exercise | Deployment work, not a code-only claim |

## Scalability and separation of concerns

The API is stateless apart from external stores and can scale horizontally.
CPU/memory-heavy inference is already moved off HTTP. PostgreSQL is the source
of truth, Redis contains ephemeral coordination state, and object storage owns
binary data. The primary scaling risks are OCR worker memory, external-provider
quotas, unmeasured database query plans, and Redis/MinIO/PostgreSQL deployment
availability—not the monolith boundary.

Some services query SQLAlchemy directly instead of using a repository for every
aggregate. This is acceptable where the service is already the single owner of
that query; manufacturing one-method repository wrappers would add ceremony
without reducing coupling. Shared identity/ownership lookup code already uses
repositories where reuse and authorization make the boundary valuable.

## Change plan

1. Preserve the modular monolith, all `/api/v1` contracts, schema history,
   model identifiers, integrations, and current UI behavior.
2. Add request correlation, safe response headers, and structured access logs.
3. Reject unsafe production configuration at startup while leaving local/test
   defaults intact.
4. Extend targeted tests and CI security checks.
5. Add the missing API/database/AI documentation entry points and update the
   existing deployment/security guidance.

The intentionally deferred items above remain explicit technical debt. They
need deployment evidence, policy decisions, or representative data and should
not be simulated with extra services or placeholder abstractions.
