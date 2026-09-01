# Security

The threat this system is actually built against is not an intruder. It is a
signed-in user reaching a record they are not entitled to — and every design
choice below follows from that.

## The one rule: authorization before retrieval

```
JWT → user_id → citizen_profile → owner_id → authorized parcel_ids → query
```

Never:

```
question → LLM → whole database
```

The citizen's owner identity is **derived server-side on every request**. No
endpoint accepts an `owner_id`, and none accepts a `parcel_id` without passing
it through `citizen_service.assert_can_access_parcel` first.

This matters most in the RAG path (§18). The assistant is scoped *before*
retrieval, so the model is never shown a record the caller could not already
read. Filtering the model's answer afterwards would mean the record had already
left the database.

### 404 vs 403

`assert_can_access_parcel` raises the same exception for "this parcel is not
yours" and "this parcel does not exist". Grievance reads do the same.

If the two differed, a citizen could enumerate which parcel ids exist by
comparing status codes. The refusal must not confirm the target.

## Authentication

| | |
|---|---|
| Passwords | Argon2 (`app/security/passwords.py`), with rehash-on-login when parameters change |
| Access token | short-lived JWT with a unique `jti`; carries no role or permission claims |
| Refresh token | single-use JWT; rotation and logout revocation are stored atomically in Redis |
| Failure modes | wrong password, unknown email and disabled account are **indistinguishable** to the caller |

`authenticate()` runs a dummy hash comparison when the user does not exist, so
response timing does not reveal which emails are registered.

Login failures are throttled in fixed windows by both source IP and the
IP/email pair. Production and full-compose environments share that state in
Redis; the in-memory fallback exists only for single-process local development.
A successful login clears the account-specific failure bucket.

Refresh tokens are rotated on use. Replaying a consumed token returns 401, and
logout idempotently revokes the supplied refresh token. The already-issued
access token remains usable only for its short configured lifetime.

The token carries a subject id and **nothing that grants anything**. Role,
permissions, jurisdiction and owner link are re-read from the database on every
request in `build_principal`. A forged or stale claim buys the holder nothing.

## Authorization (§36)

Server-side RBAC, expressed as permissions rather than role checks:

```python
principal: Principal = Depends(require("document:approve"))
```

A router that forgets the dependency grants nothing by accident, because
`current_principal` alone confers no capability.

Three dependency factories, and the distinction matters:

* `require(...)` — caller must hold **all** the named permissions.
* `require_any(...)` — caller must hold **at least one**. Needed wherever a
  broader capability subsumes a narrower one: the tehsildar holds
  `audit:view_full` but not `audit:view_limited`, so a timeline endpoint
  demanding the narrower permission locked out the role with *more* authority.
* `require_role(...)` — used only where the concept genuinely is the role
  itself, such as "the citizen portal".

### The frontend decides nothing

The role-selection screen (§12, §58) is navigation. It pre-fills a demo account
and changes some copy. The `AppShell` guard is a convenience so a citizen does
not load the tehsildar dashboard and watch every request 403 — it is not the
boundary.

Clicking "Tehsildar" and signing in as a citizen gets you the citizen portal,
because the server decides. There are e2e tests for exactly this.

## Upload handling (§61)

| check | how |
|---|---|
| File type | **sniffed from the bytes**, not from the extension or `Content-Type` |
| Size | capped by `max_upload_bytes` before anything is stored |
| Filename | sanitized; never used as a storage key |
| Storage key | a UUID path, so an object key cannot be guessed from a filename |
| Checksum | SHA-256 recorded at upload |

An `.exe` renamed to `.pdf` fails on content, not on extension. The declared
MIME type is cross-checked afterwards and the sniffed type always wins.

Documents are served through **short-lived presigned URLs** (900s), never as
public objects.

## Injection and validation

* **SQL** — SQLAlchemy Core/ORM throughout; no string-built SQL anywhere.
* **Input** — Pydantic at the API boundary, Zod in the web forms. Path
  parameters that reach the database carry an explicit pattern: a NUL byte in a
  parcel id previously surfaced as an unhandled `psycopg` `DataError` (HTTP
  500), and now fails validation with a 422 at the boundary.
* **CORS** — an explicit allowlist from settings, never `*`.

## Audit (§41)

Every sensitive action appends to a SHA-256 hash chain: upload, processing,
correction, verification, approval, rejection, return, download, grievance,
anomaly verdict, login.

```
event_hash = SHA256(canonical(sequence, timestamp, actor, role, action,
                              entity, before, after, reason, previous_hash))
```

Two properties worth stating precisely:

* **Tamper-evident, not tamper-proof.** Someone with write access to the
  database can rewrite the whole chain. What they cannot do is alter *one* past
  event and leave the rest verifying. `/api/v1/audit/verify` recomputes
  everything and reports what it found.
* **It is not a blockchain.** No consensus, no network, no proof of work. §41
  says not to call it one, and nothing in the UI does.

`audit_service.record` deliberately does **not** commit. The audit row lands in
the same transaction as the change it describes, so a rolled-back action cannot
leave an entry claiming it happened.

## Secrets

`.env.example` is committed; `.env` is not. No production secret is hardcoded,
and CI has no credentials in it.

The demo password lives in the seed configuration, not in source. It is a demo
password for a synthetic dataset — but it is still read from the environment so
that the *pattern* is right.

## Data

Every record, owner, parcel and document is synthetic and labelled as such
(§83). `is_synthetic` is a column on the entities that carry record content, it
is returned by the API, and the UI shows a "DEMO / SYNTHETIC DATA" marker on
every screen that displays record content.

The prototype holds no real citizen's land. It is not connected to DILRMP,
BhuNaksha, or any government system.

## Tested, not asserted

The security properties above have tests, because a security claim without one
is a hope:

| property | test |
|---|---|
| Citizen A cannot read Citizen B's parcel | `test_citizen_isolation.py`, `lifecycle.spec.ts` |
| Each role's permissions match §36 | `test_auth_rbac.py` |
| A citizen cannot reach an officer section | `lifecycle.spec.ts` |
| Grievance filing cannot enumerate parcels | `test_grievances.py` |
| An unknown parcel is indistinguishable from a forbidden one | `test_grievances.py` |
| `UPLOADED → APPROVED` is impossible | `test_canonical_schema.py`, `test_end_to_end.py` |
| The audit chain verifies after every action | `test_audit_chain.py` |
| Login failure modes are indistinguishable | `test_auth_rbac.py` |
| Replayed and logged-out refresh tokens are rejected | `test_auth_rbac.py`, `test_auth_state.py` |
| Login failures are throttled by IP and account | `test_auth_rbac.py`, `test_auth_state.py` |
| Officers cannot read or queue documents outside their jurisdiction | `test_jurisdiction_scoping.py` |
| Metrics require the analytics permission | `test_dashboards_and_metrics.py` |

## Known limitations

Honest list, because a prototype that claims to be production-secure is worse
than one that says where it stops:

* **Access tokens are not denylisted.** Logout revokes refresh capability, but
  an access token already issued remains valid until its short expiry. Immediate
  access-token revocation would require a per-request denylist lookup.
* **The local auth-state fallback is single-process.** Multi-worker execution
  must configure `AUTH_STATE_REDIS_URL`; the full Compose stack already does.
* **No penetration testing.** Nothing here has been adversarially reviewed by
  anyone but its authors.
