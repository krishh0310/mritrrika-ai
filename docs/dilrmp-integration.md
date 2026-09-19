# DILRMP and state LRMS connectors

How an approved record reaches the national Digital India Land Records
Modernization Programme (DILRMP) and a state Land Records Management System,
and why the prototype runs both in mock mode.

## 1. Record of Rights fields and their source

Built by `dilrmp_connector.ror_fields()` from the same Record of Rights the
LRMS outbox delivers (`lrms_service.ror_payload`), so there is one mapping.

| RoR field | Mrittika source |
|---|---|
| `khata_number` | `parcels.khata_number` |
| `khasra_number` | `parcels.khasra_number` (the survey number in southern states) |
| `owner_name` | current `ownership_records` holders' `owners.name`, `; `-joined |
| `area_hectares` | `parcels.area_value` in `parcels.area_unit`, converted via `mrittika_domain.area` |
| `mutation_number` | the latest `mutations.mutation_number` behind a current holding |
| `tehsil_code` / `district_code` / `state_code` | `locations.external_id` walked up from the parcel's village |

DILRMP sends the fields as XML (`<RecordOfRights>` with one element per field);
the LRMS connector sends the same fields as JSON. **The element names are this
system's mapping, not a published NIC schema** -- none was available to
validate against -- and the location codes are internal ids, where a real
deployment maps them to LGD codes. Both are to be confirmed with the receiving
state.

## 2. Endpoints

| connector | call | method and path | auth header |
|---|---|---|---|
| DILRMP | `push_record(record_id)` | `POST {DILRMP_ENDPOINT}/ror`, `Content-Type: application/xml` | `X-API-Key: {DILRMP_API_KEY}` |
| DILRMP | `fetch_cadastre(survey_number)` | `GET {DILRMP_ENDPOINT}/cadastre/{survey_number}` -> GeoJSON | `X-API-Key` |
| LRMS | `push_record(record_id)` | `POST {LRMS_ENDPOINT}/mutations`, JSON | `Authorization: Bearer {LRMS_API_KEY}` |
| LRMS | `fetch_record(record_id)` | `GET {LRMS_ENDPOINT}/mutations/{record_id}` | Bearer |

`dilrmp_connector.push_record` runs after every tehsildar approval, **after the
approval has committed**: an unreachable server can neither delay nor undo it.
Every attempt -- `mock`, `delivered` or `failed`, with the error -- is a row in
`integration_log`. `GET /api/v1/integrations/status` (Tehsildar, State Officer,
Central Ministry) returns both connectors' health and last five attempts.

## 3. Environment

| variable | default | effect when unset |
|---|---|---|
| `DILRMP_ENDPOINT` | unset | mock mode: payload built, nothing sent, receipt `MOCK-{record_id}` |
| `DILRMP_API_KEY` | unset | sent empty |
| `LRMS_ENDPOINT` | unset | mock mode (also switches the LRMS outbox's `http` adapter) |
| `LRMS_API_KEY` | unset | sent empty |

## 4. Why there is no live connection

DILRMP has no public sandbox. API access to a state's land records is granted
per state under a memorandum of understanding with its revenue department, and
a hackathon prototype holds none. So both connectors run in mock mode by
design: they build exactly what they would send, log every attempt, and report
`"connected": false` with the reason -- never a fabricated success. Pointing
the two endpoint variables at a real service switches them to live without a
code change.

## 5. Event-driven integration

For a subscription model rather than push/pull, the `record.approved` and
`record.flagged` event contract is in [asyncapi.yaml](asyncapi.yaml), served at
`/api/v1/integrations/asyncapi.yaml`.
