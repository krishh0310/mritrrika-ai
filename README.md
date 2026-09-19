# Mrittika AI

**Intelligent digitization for India's land records.**

Mrittika AI converts legacy land documents into AI-extracted, human-verified,
officer-approved, spatially linked digital records that authorized citizens and
officials can securely search, inspect and query through a grounded AI
assistant.

> **Every record, owner, parcel and document in this repository is synthetic.**
> It is a hackathon prototype. It holds no real citizen's land and is not
> connected to any government system.

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

```bash
# 1. Infrastructure
docker compose up -d

# 2. Python (3.12 — see pyproject.toml for why it is pinned)
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements-api.txt -r requirements-ai.txt
cp .env.example .env

# 3. Database
.venv/bin/alembic -c apps/api/alembic.ini upgrade head
.venv/bin/python scripts/seed_demo.py

# 4. API
.venv/bin/python -m uvicorn app.main:app --app-dir apps/api --port 8000

# 5. Worker (separate shell) — uploads stay queued without it
cd apps/api && ../../.venv/bin/celery -A app.worker.celery_app worker \
  --loglevel=info --concurrency=1

# 6. Web
npm install
npm run dev

# Optional: Expo citizen/field app
npm run mobile
```

Then open <http://localhost:3000> and follow **[docs/demo.md](docs/demo.md)**.

Check <http://localhost:8000/ready> first — it verifies PostGIS and pgvector are
actually present, which saves a confusing failure later.

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
`python scripts/api_keys.py create --user lrms-service@mrittika.demo --name "UP LRMS"`,
then send `X-API-Key: <key>`. The key acts as that service account.

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
.venv/bin/python -m pytest tests                  # 816 collected; 1 data-dependent skip
npm test                                          # 38 web/mobile unit tests
npm run lint && npm run typecheck                 # web + mobile
npm run build && npm run build:mobile             # production web + mobile export
npx playwright test --config apps/web/playwright.config.ts  # 17 browser e2e
.venv/bin/python -m ruff check .
```

The e2e suite is the one worth reading: `tests/e2e/lifecycle.spec.ts` follows
one document and one parcel through every hand that touches them, which is §92's
definition of done. Four disconnected screenshots would prove nothing.

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

## What this prototype does not do

Stated plainly, because a prototype that overclaims is worse than one that says
where it stops:

- Not connected to DILRMP, BhuNaksha, or any government system.
- Handwriting is detected and read by two small models trained on public
  handwriting data (IIIT-HW-Dev, DHCD, MNIST), not on land records. Every
  field on such a page goes to a verifier. Gemini can re-read the lines as an
  opt-in second opinion. See [docs/handwriting.md](docs/handwriting.md).
- No layout or language model in extraction. PP-Structure, LayoutLMv3 and
  IndicBERT are not integrated; extraction is deterministic rules.
- No blockchain. The audit trail is a SHA-256 hash chain, and the code says so.
- No accuracy claim that has not been measured.
  `scripts/evaluate_extraction.py` reports per difficulty tier; that is the only
  number to quote.
- No claim of production security or penetration testing. Authentication,
  token rotation, jurisdiction scoping, and their remaining limitations are
  documented in [security.md](docs/security.md#known-limitations).

## Licence

MIT — see [LICENSE](LICENSE).
