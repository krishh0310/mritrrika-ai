# API

The FastAPI application in `apps/api` is the only authority for web and mobile
clients. Interactive OpenAPI documentation is available at `/docs` and the
machine-readable schema at `/openapi.json` while the service is running.

## Contract

- Application routes are versioned under `/api/v1`.
- `/health`, `/ready`, and authenticated `/metrics` are unversioned operational
  endpoints.
- Authentication uses `Authorization: Bearer <access-token>`.
- Authorization is enforced by backend permissions and jurisdiction/ownership
  scope; a frontend role check never grants access.
- JSON bodies are validated by Pydantic. Uploads are multipart and validated by
  bytes, not by filename or the caller's `Content-Type`.
- Every response carries `X-Request-ID`. A syntactically safe upstream ID is
  preserved; otherwise the API creates one. Include it in support reports.
- API responses carry `Cache-Control: no-store` and baseline browser security
  headers. Production responses add HSTS.

FastAPI's existing success payloads and `{"detail": ...}` error payloads remain
stable for compatibility. Introducing a universal response envelope would
break every web, mobile, and integration consumer and is therefore deferred to
a future API version rather than retrofitted into v1.

## Route groups

| Prefix | Responsibility |
|---|---|
| `/api/v1/auth` | login, refresh-token rotation, logout, current principal |
| `/api/v1/documents` | upload, bulk upload, status, processing, signed content URLs |
| `/api/v1/verifications` | verifier queue, corrections, verification decisions |
| `/api/v1/approvals` | tehsildar approval and return flow |
| `/api/v1/citizen` | ownership-scoped land, assistant, notifications |
| `/api/v1/records` and `/api/v1/parcels` | authorized record and GIS lookup |
| `/api/v1/grievances` | citizen submission and officer resolution |
| `/api/v1/ai` | grounded query and curated feedback pool |
| `/api/v1/anomalies` | reviewable inconsistency signals |
| `/api/v1/audit` | authorized audit history and chain verification |
| `/api/v1/dashboard` | role dashboards and analytics |
| `/api/v1/integrations/lrms` | authorized LRMS outbox operations |

## Limits and failures

Upload limits and MIME allowlists come from environment settings. AI queries
have a Redis-backed per-user rate limit, per-IP rate limit, and per-user daily
quota; local single-process development uses an in-memory implementation with
the same behavior. Limit violations return HTTP 429 with `Retry-After`.

Use status codes as the stable machine contract: 401 means authentication is
missing/invalid, 403 means the principal lacks permission, 404 can deliberately
hide the existence of an out-of-scope record, 409 means workflow conflict, 422
means invalid input, and 429 means a request limit was reached. Internal errors
must be correlated through server logs rather than exposed as stack traces.

## Adding an endpoint

Keep the router responsible for HTTP parsing, dependencies, and response shape.
Put business transitions and authorization-sensitive orchestration in a named
service, and reusable entity lookup/data access in a repository. Add a Pydantic
schema for non-trivial payloads, a permission dependency at the route, and a
test for both the allowed and forbidden principal.
