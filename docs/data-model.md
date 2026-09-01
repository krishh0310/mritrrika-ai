# Data model

The shape of the database, and the two or three decisions in it that everything
else depends on.

## The one that matters: ownership is not a column

A parcel has **no owner column**. It is tempting — `parcels.owner_name` is one
join fewer on every query — and it makes the system unable to answer the
question land records exist to answer: *who held this in 1998?*

```
OWNER ──< OWNERSHIP_RECORD >── PARCEL
                │
                └── MUTATION
```

An `ownership_records` row is a **time-bounded interest**:

| column | meaning |
|---|---|
| `owner_id` | who |
| `parcel_id` | what |
| `share` | how much, as the fraction written on the document (`"1/2"`) |
| `valid_from` | when it began |
| `valid_to` | when it ended — **`NULL` means "current"** |
| `mutation_id` | the transfer that caused it, where one is on file |

"Who holds this now" is `valid_to IS NULL`. "Who held it on 1998-06-01" is
`valid_from <= date AND (valid_to IS NULL OR valid_to > date)`. Both are the
same index.

`share` is a **string**, not a float. `1/3` is not `0.333`, and rounding a
recorded share changes its legal meaning. The anomaly engine parses it with
`fractions.Fraction` when it needs arithmetic (`anomaly_service._share_as_float`)
and never writes the result back.

## parcel_id is the join key

§11 calls `parcel_id` the most important identifier in the project, and the
schema takes that literally. It is what links:

```
GIS polygon ─ khasra ─ land record ─ owner ─ ownership history
     └─ mutations ─ documents ─ OCR blocks ─ extractions ─ verification ─ audit
```

Every table that participates in the lifecycle reaches a parcel in one or two
hops. That is what makes the §92 vertical slice a single connected story rather
than six screens that happen to show similar numbers.

## Tables

### Identity and access

| table | holds |
|---|---|
| `users` | login identity, password hash, active flag |
| `roles`, `permissions`, `role_permissions`, `user_roles` | the §36 matrix, as data |
| `citizen_profiles` | the **user → owner** link that makes §62 enforceable |

`citizen_profiles` is the whole of the citizen isolation guarantee. A citizen's
`owner_id` is reachable only from their own user row, so
`citizen_service.my_parcel_ids` can derive their holdings from a session and
from nothing the client sends.

### Geography and land

| table | holds |
|---|---|
| `locations` | state → district → tehsil → village, self-referencing |
| `parcels` | khasra, khata, area, land class, PostGIS `POLYGON` (SRID 4326) |
| `owners` | a person who can hold land — **distinct from `users`**; most owners have no login |
| `ownership_records` | the time-bounded interests above |
| `mutations` | recorded transfers (§40) |
| `land_records` | a record-of-rights row tying a parcel to a record year |

The parcel geometry pins `srid=4326` explicitly. An unset SRID makes `ST_Area`
return square degrees, which looks like a plausible number and is wrong.

### Documents and the pipeline

| table | holds |
|---|---|
| `documents` | one scan: state, storage key, quality report, DEO-supplied metadata |
| `document_pages` | per-page render and dimensions |
| `processing_jobs` | one pipeline run — stage, progress, status, error |
| `ocr_blocks` | recognised text with confidence, bbox, script, reading order |
| `extractions` | one row per field, with the full §26 provenance |
| `field_corrections` | what a verifier changed, and away from what |

`documents` keeps the DEO's declared metadata (`declared_khasra`,
`declared_khata`) in separate columns from anything the AI later read. They are
different kinds of claim and the validation engine compares them
(`check_against_declared`).

**`extractions` is where §26 lives.** Each row carries `raw_value`,
`normalized_value`, `corrected_value` and a computed `effective_value`, plus
four confidence components and their fusion. Normalization never overwrites
`raw_value`; correction never overwrites `normalized_value`. That is what the
provenance strip in the UI renders, and what makes an approved record auditable
back to the pixels it came from.

### Workflow

| table | holds |
|---|---|
| `verification_tasks` | the queue, with denormalised `lowest_confidence` and `anomaly_count` |
| `verification_actions` | what a verifier did |
| `approval_actions` | a tehsildar's decision and reason |
| `validation_findings` | §33 deterministic rule outcomes, per document |
| `anomaly_flags` | §34 pattern flags, per parcel, with evidence |
| `grievances` | §19 citizen-raised issues |

`verification_tasks.lowest_confidence` is denormalised deliberately: the queue
sorts by it on every load, and computing it from `extractions` per row turns the
list into a correlated subquery.

`anomaly_flags` hang off the **parcel**, not the document. An area jump is a
property of the record's history; the document is just where it was noticed.

### AI and audit

| table | holds |
|---|---|
| `model_versions` | the §64 registry — every prediction records which version made it |
| `embeddings` | pgvector column for semantic retrieval |
| `ai_feedback` | corrections marked as retraining candidates (§67) |
| `audit_events` | the §41 hash chain |
| `notifications` | per-user messages |

## The audit chain

`audit_events` is append-only and each row carries:

```
event_hash = SHA256(canonical(sequence, timestamp, actor, action,
                              entity, before, after, reason, previous_hash))
```

Altering any past event changes its hash, which breaks `previous_hash` on every
event after it. `/api/v1/audit/verify` recomputes the whole chain and reports
what it found.

This is a **hash chain**, not a blockchain — no distributed consensus, no
network, no proof of work. §41 is explicit about not calling it one, and the UI
says "hash chain" everywhere.

Two rules the service enforces:

* `audit_service.record` **does not commit**. The audit row lands in the same
  transaction as the change it describes, so a rolled-back action cannot leave
  an entry claiming it happened.
* `actor_id` is the user's primary key, not their external id — it is a real
  foreign key, so an audit row cannot name a user who never existed.

## Document states

The §37 machine lives in `packages/domain/state_machine.py` as data, so the API
and any other consumer enforce the same graph:

```
UPLOADED → QUALITY_CHECK → PROCESSING → AI_EXTRACTED → NEEDS_VERIFICATION
  → UNDER_VERIFICATION → VERIFIED → PENDING_APPROVAL → APPROVED → ARCHIVED
```

with `RESCAN_REQUIRED` and `REJECTED` reachable from most points, and
`RESCAN_REQUIRED → UPLOADED` closing the loop for a re-scan.

`UPLOADED → APPROVED` is not in the table, so it cannot happen — regardless of
which endpoint is called or what a client sends.

## Identifiers

Two id columns on most tables, on purpose:

* `id` — a UUID primary key, used for every foreign key.
* `external_id` — the human-readable handle (`DOC-00142`, `PARCEL-UP-DEMO-0142`,
  `GRV-00001`), unique and indexed, and the only one that appears in a URL or on
  screen.

Officers quote external ids at each other; the database joins on UUIDs. Mixing
the two is how you end up with a sequential primary key an attacker can walk.
