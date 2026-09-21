# Mrittika AI

**A human-in-the-loop platform for digitizing India's land records.**

Mrittika AI turns scanned land documents into structured, spatially linked
records. AI performs quality checks, OCR, extraction, validation and anomaly
detection; authorized staff verify the result before an officer approves it.
Citizens can then search their own approved holdings, inspect parcel history and
ask questions through a grounded assistant.

> **Prototype boundary:** every record, owner, parcel and document is synthetic.
> This repository is a hackathon prototype. It stores no real citizen data and
> is not connected to DILRMP, BhuNaksha or any other government system.

## At a glance

| Area | Current implementation |
|---|---|
| Web | Next.js officer workstations and citizen portal |
| API | FastAPI, PostgreSQL, PostGIS, pgvector and Redis |
| AI pipeline | OpenCV, PaddleOCR, layout detection, deterministic extraction, validation and anomaly detection |
| Mobile | Expo citizen and field-capture app |
| Geospatial | PostGIS cadastre data with optional GeoServer publication |
| Integrations | Mock LRMS/DILRMP connectors and API-key access |
| Security model | Role-based access, jurisdiction scoping, audit hash chain and retrieval authorization |

The project is designed to demonstrate an accountable workflow, not to replace
an official land-records system.

---

## What it does

A scanned Khasra page enters at one end and leaves as an approved record of
rights, with the same `document_id` and `parcel_id` travelling the whole way:

```
DEO uploads  →  quality gate  →  OpenCV  →  PaddleOCR  →  layout  →  extraction
   →  normalization  →  confidence  →  validation  →  anomaly detection
   →  verifier corrects  →  tehsildar approves  →  citizen sees their parcel
   →  map, ownership history, grounded AI answer, verifiable audit trail
```

Four roles, strictly separated and enforced server-side:

| | Citizen | DEO | Verifier | Tehsildar |
|---|---|---|---|---|
| Search approved records | ✓ | ✓ | ✓ | ✓ |
| View own holdings | ✓ | | | |
| Upload and process | | ✓ | | |
| Correct extraction | | | ✓ | |
| Final approval | | | | ✓ |
| Internal anomaly scores | | | ✓ | ✓ |

## Quick start

### Prerequisites

- Docker Desktop with Compose
- Node.js 20+ and npm
- Python 3.12
- Git

The Python version is pinned because the AI and document-processing dependencies
are tested against it. Apple Silicon users can use
`/opt/homebrew/bin/python3.12` when it is available; otherwise use the Python
3.12 executable on their PATH.

```bash
# Clone and enter the repository
git clone https://github.com/krishh0310/mritrrika-ai.git
cd mritrrika-ai

# Install JavaScript workspace dependencies
npm install

# Start PostgreSQL/PostGIS, Redis, MinIO and pg_featureserv
docker compose up -d

# Create the Python environment and install API + AI dependencies
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements-api.txt -r requirements-ai.txt
cp .env.example .env

# Apply migrations and load the synthetic demo data
.venv/bin/alembic -c apps/api/alembic.ini upgrade head
.venv/bin/python scripts/seed_demo.py

# Start the API
.venv/bin/python -m uvicorn app.main:app --app-dir apps/api --port 8000

# In a second shell, start the AI worker
cd apps/api && ../../.venv/bin/celery -A app.worker.celery_app worker \
  --loglevel=info --concurrency=1

# In a third shell, start the web app
npm run dev

# Optional: start the Expo app
npm run mobile
```

Open <http://localhost:3000> and follow **[docs/demo.md](docs/demo.md)** for the
role-by-role walkthrough. The API health endpoint is available at
<http://localhost:8000/ready>; it checks that PostGIS and pgvector are present.

To stop local infrastructure:

```bash
docker compose down
```

Add `-v` only when you intentionally want to delete the local database, object
storage and cache volumes.

### Demo accounts

All share one password from the seed configuration (`demo_change_me` by
default).

| role | email |
|---|---|
| Citizen | `ram31@mrittika.demo` |
| Citizen (second) | `seema32@mrittika.demo` |
| Data Entry Operator | `deo@mrittika.demo` |
| Verifier / Lekhpal | `lekhpal@mrittika.demo` |
| Tehsildar | `tehsildar@mrittika.demo` |
| State Revenue Officer (read-only, Uttar Pradesh) | `state@mrittika.demo` |
| Central Ministry Officer (read-only, all states) | `central@mrittika.demo` |
| Survey Department (read-only, map and inconsistencies) | `survey@mrittika.demo` |
| Research Institution (anonymised export only) | `research@mrittika.demo` |

Other government systems call the API with a key rather than a login:

```bash
.venv/bin/python scripts/api_keys.py create \
  --user lrms-service@mrittika.demo --name "UP LRMS"
```

Send the returned key in `X-API-Key`. It acts as the configured service account.

Two citizens exist so ownership isolation can be demonstrated rather than
described.

## Repository layout

```
apps/
  api/                FastAPI — the single authoritative backend
  web/                Next.js — officer workstations and the citizen portal
  mobile/             Expo — citizen access and field capture
services/
  ai-worker/          quality, preprocessing, OCR, extraction, validation, anomaly
  dataset-generator/  synthetic records → templates → rendering → degradation
  gis/                village boundaries, Voronoi cadastre, PostGIS loading
packages/
  domain/             canonical record, confidence fusion, state machine
  ui/                 shared interface vocabulary
  shared-types/       generated from packages/domain — do not hand-edit
datasets/             generated data, annotations, splits, QA reports
models/               model configuration and version registry
scripts/              reproducible admin commands
tests/                backend, AI, dataset, integration, e2e
docs/                 architecture, data model, AI pipeline, security, demo
```

Why each directory exists is documented in
**[docs/architecture.md](docs/architecture.md)**.

## Documentation

| | |
|---|---|
| [architecture.md](docs/architecture.md) | system shape, runtime topology, why each directory exists |
| [architecture-assessment.md](docs/architecture-assessment.md) | audited current state, prioritized gaps, incremental change plan |
| [api.md](docs/api.md) | API contracts, route groups, limits, extension rules |
| [database.md](docs/database.md) | migration workflow and production database requirements |
| [ai-ml.md](docs/ai-ml.md) | AI operating contract, query protection, model promotion |
| [data-model.md](docs/data-model.md) | the schema, and why ownership is not a column |
| [ai-pipeline.md](docs/ai-pipeline.md) | each stage, its fallback, and what it may claim |
| [security.md](docs/security.md) | authorization before retrieval, and known limitations |
| [demo.md](docs/demo.md) | the walkthrough, step by step |
| [gis-integration.md](docs/gis-integration.md) | WMS/WFS publication, and why GeoServer never sees ownership |
| [lrms-integration.md](docs/lrms-integration.md) | delivering approved Records of Rights to the state LRMS / DILRMP |
| [existing-system-study.md](docs/existing-system-study.md) | the manual process today, its pain points, and what Mrittika can claim to improve |
| [dilrmp-integration.md](docs/dilrmp-integration.md) | DILRMP / LRMS connectors, field mapping, and why they run in mock mode |
| [asyncapi.yaml](docs/asyncapi.yaml) | AsyncAPI 2.6 contract for `record.approved` and `record.flagged` events |
| [deployment.md](docs/deployment.md) | the intended production target, and the distance from it |
| [i18n.md](docs/i18n.md) | Hindi and English, and why record values are never translated |
| [monitoring.md](docs/monitoring.md) | Prometheus and Grafana over the pipeline |
| [dossier.html](docs/dossier.html) | the full technical report — every model and why, all measured results, including the two that failed |

## Tests

```bash
.venv/bin/python -m pytest tests
.venv/bin/python -m ruff check .
npm test                                          # web + mobile unit tests
npm run lint
npm run typecheck
npm run build && npm run build:mobile
npm run e2e                                       # browser end-to-end tests
```

The end-to-end suite is the best place to understand the product workflow:
`tests/e2e/lifecycle.spec.ts` follows one document and one parcel through every
role that touches them. Test counts are intentionally omitted because they
change as the prototype evolves.

## Regenerating the dataset

Two size profiles (§42: 50 → 500 → ~2000):

| profile | villages | parcels | pages |
|---|---|---|---|
| `slice1` | 2 | 40 | 50 |
| `v1` | 4 | 80 | 500 |

```bash
P=v1
.venv/bin/python scripts/generate_dataset.py   --profile $P
.venv/bin/python scripts/generate_documents.py --profile $P --count 500
.venv/bin/python scripts/generate_gis.py       --profile $P
.venv/bin/python scripts/split_dataset.py      --profile $P
.venv/bin/python scripts/verify_dataset.py     --profile $P
```

Every artifact is namespaced by profile, splits included. Tests read whichever
profile is active — the largest generated one, or `MRITTIKA_DATASET_PROFILE`
when it is set.

Ground truth exists **before** rendering — it is never derived by OCRing the
generated image. Splits happen before augmentation and are grouped by base
document, so a clean page and its degraded clone cannot land on opposite sides
of the train/test line.

## Background

Land records support property ownership, taxation, land acquisition, dispute
resolution and infrastructure planning. Across India, many historical records
still exist as handwritten registers, scanned documents, maps, cadastral records
and legacy PDF files maintained at different administrative levels.

An intelligent digitization system can improve data quality while accelerating
the modernization of land administration. Mrittika AI addresses this need with
an AI-assisted workflow that combines document processing, structured
extraction, validation, human review, geospatial context and accountable
approval.

## Study description

The proposed system extracts structured information from scanned land records,
handwritten documents, maps and legacy PDF files. It uses OCR, computer vision,
document classification and language-aware processing to identify printed and
handwritten content, then maps the result to land-record fields such as:

- Landowner and ownership details
- Survey, khasra, khata and plot numbers
- Plot area and land classification
- Village, tehsil and district
- Mutation and registration information
- Parcel geometry, ownership history and related records

Every extraction carries confidence and provenance information. Low-confidence
fields are routed to a verifier, while an authorized officer approves the final
record. This preserves a human decision point where a model should not guess.

## Scope of study

| Scope area | What the system provides | Current prototype status |
|---|---|---|
| Document ingestion | Upload and process scanned images, PDFs and generated records | Implemented |
| OCR and handwriting | Printed-text OCR, script routing, handwriting detection and reading | Implemented with verifier review |
| Multilingual processing | Hindi/English workflows with Indic-script support and translation fallbacks | Implemented for supported scripts |
| Field extraction | Structured owner, parcel, location, area, mutation and registration fields | Implemented |
| Validation | Business rules, confidence scoring, duplicate detection and anomaly flags | Implemented |
| Human verification | Field-level correction, review queues and approval workflow | Implemented |
| GIS and cadastre | Parcel geometry, map views, spatial checks and inconsistency reporting | Implemented with PostGIS |
| Dashboards | Processing volume, accuracy, validation status, pending work, errors and geographic progress | Implemented |
| Search and assistant | Authorized record search and grounded answers over approved records | Implemented |
| LRMS/DILRMP exchange | API contracts and mock connectors for approved-record delivery | Integration-ready; external systems are not connected |
| Secure repository | Document metadata, role-based access, jurisdiction scoping and audit history | Implemented for the prototype |
| Learning loop | Feedback export and retraining workflow for future model improvement | Implemented as an experimental workflow |

## Problems addressed

Legacy records are difficult to digitize because of poor image quality,
inconsistent layouts, faded or damaged pages, multiple regional languages and
handwritten annotations. Manual data entry is slow and error-prone, and
inconsistent records make it harder to verify ownership, maintain reliable
databases, connect land information systems and deliver citizen services.

Mrittika AI addresses these problems by combining automated processing with
confidence-aware review. It preserves the source document, records how each
field was produced, flags conflicts and gives authorized users a traceable path
from upload to approved record.

## Expected solution and capabilities

The platform is designed to reduce manual effort while improving the accuracy,
reliability and transparency of digital land records. Its main capabilities are:

1. Multilingual recognition for supported Indian scripts and English.
2. Extraction from scanned PDFs, images, handwritten pages and historical
   documents.
3. Classification into predefined land-record fields.
4. Rule-based validation, duplicate detection, anomaly detection and spatial
   consistency checks.
5. Confidence scores that identify uncertain fields and records.
6. Human-assisted verification for low-confidence or conflicting values.
7. Feedback export and retraining workflows that support continuous improvement.
8. GIS, cadastral-map and parcel-history views backed by PostGIS.
9. Integration contracts and mock LRMS/DILRMP connectors for approved records.
10. Secure document storage with metadata, role-based access and audit trails.
11. Interactive dashboards for document volume, extraction quality, validation
    status, pending verification, error statistics and state/district progress.
12. APIs for government applications and digital-governance integrations.

The workflow supports distinct citizen, data-entry, verifier, tehsildar and
read-only institutional roles. Citizens see only authorized holdings; staff see
the work and jurisdiction required for their role; final approval remains with
the designated officer.

The prototype does not claim production deployment, government connectivity or
unmeasured accuracy. Handwriting models are trained on public handwriting data,
and uncertain handwritten fields are sent to verification. See
[docs/handwriting.md](docs/handwriting.md), [docs/security.md](docs/security.md)
and [docs/deployment.md](docs/deployment.md) for the implementation boundaries.

## Licence

MIT — see [LICENSE](LICENSE).
