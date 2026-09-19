# Delivering approved records to the state LRMS / DILRMP

An approved record is only half digitized until the state's Land Records
Management System has it. This is how a record leaves Mrittika AI, and what the
receiving system gets.

> Nothing here is connected to a live state server. The file-drop adapter
> writes to a local folder by default; the HTTP adapter posts to whatever
> `LRMS_ENDPOINT` names. Every record is synthetic and says so in its payload.

## The path

```
tehsildar approves ──► enqueue()  ──► lrms_sync_records  (PENDING)
   (same transaction)                        │
                     POST /sync ──► adapter ─┴─► DELIVERED | FAILED (retried)
```

**Queued on approval, in the same transaction.** An approved record is always
queued; a rolled-back approval never is. Approval does not wait for the state
server — a down LRMS must not block a tehsildar.

**Delivered separately, and retried.** `POST /api/v1/integrations/lrms/sync`
delivers everything due in the caller's jurisdiction (or only the records named
in `document_ids`). A failure stays `FAILED` with its error and is retried on
the next sync, up to five attempts; after that it waits for a person. Nothing is
ever marked delivered that the adapter did not see arrive. Each sync is written
to the audit chain.

**Queued once.** The outbox is keyed on the document and the SHA-256 of the
payload. Re-queueing unchanged content is a no-op; a record whose content
changes (say, after being returned and re-approved) is a new delivery.

Records approved before the outbox existed are picked up by the next sync.

## Adapters

`LRMS_ADAPTER` picks one:

| adapter | what it does | when |
|---|---|---|
| `file` (default) | writes `<record_id>.<digest16>.json` into `LRMS_OUTBOX_DIR`, via a temporary file and an atomic rename | states whose LRMS imports batches collected by an SFTP job |
| `http` | `POST`s the JSON to `LRMS_ENDPOINT`, with `Authorization: Bearer LRMS_API_TOKEN` and `Idempotency-Key: <digest>` | states exposing an ingestion API |
| `disabled` | delivers nothing; records wait in the outbox | before a state has agreed a transport |

An unknown adapter name, or `http` without an endpoint, fails every delivery
with the configuration error — visible on each record, not only in a log.

## The payload: `mrittika.ror/1`

A Record of Rights in the shape DILRMP's RoR data carries, plus provenance only
this system can supply.

```jsonc
{
  "schema": "mrittika.ror/1",
  "record_id": "DOC-00181",
  "approved_at": "2026-09-19T10:42:07.118204+00:00",
  "location": {                       // walked up from the parcel's village
    "state":    {"code": "LOC-STATE-UP", "name": "...", "name_local": "..."},
    "district": {...}, "tehsil": {...}, "village": {...}
  },
  "parcel": {
    "parcel_code": "PARCEL-UP-DEMO-0181",
    "survey_number": "142/2",         // khasra in the north, survey no. in the south
    "khata_number": "217",
    "area": {"value": 2.75, "unit": "BIGHA", "square_metres": 6955.53},
    "land_class": "..."
  },
  "holders": [                        // current ownership, from the system of record
    {"owner": "...", "owner_code": "...", "share": "1/2",
     "since": "2006-04-12", "mutation_number": "..."}
  ],
  "source_document": {
    "document_type": "KHASRA", "record_year": "1998-99",
    "sha256": "…",                    // the scanned file, as uploaded
    "as_recorded": [                  // what the page says, after verification
      {"field": "AREA", "value": "2.5", "row": null, "verified_by_human": true}
    ]
  },
  "provenance": {
    "system": "mrittika-ai",
    "approval_audit_hash": "…",       // the audit-chain event of the approval
    "is_synthetic": true
  }
}
```

Two things let the receiver check the record without trusting the sender: the
`sha256` of the source scan, and `approval_audit_hash`, which is the hash of the
approval event in this system's tamper-evident audit chain.

`holders` comes from the ownership records, `as_recorded` from the verified
page. They are delivered side by side rather than merged, because when they
disagree that disagreement is itself information for the receiving office.

**Location codes are this system's ids.** A real deployment maps them to LGD
(Local Government Directory) codes in one function, `_location` in
`lrms_service.py`; the mapping is per state and this prototype's villages are
synthetic.

## API

All three need `integration:sync` (tehsildar) and are scoped to the caller's
jurisdiction.

| | |
|---|---|
| `GET  /api/v1/integrations/lrms/sync` | counts by status, records approved but not yet queued, the latest deliveries |
| `POST /api/v1/integrations/lrms/sync` | queue anything missing, then deliver; body `{"limit": 100, "document_ids": [...]}`, both optional |
| `GET  /api/v1/integrations/lrms/records/{document_id}` | one approved record exactly as delivered, with its digest — for a state system that prefers to pull |

The analytics page shows the same queue with a **Sync now** button.
