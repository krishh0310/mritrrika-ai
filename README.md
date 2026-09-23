# Mrittika AI

**Turning India's paper land records into verified, map-linked digital records — with a human signing off on every one.**

A Data Entry Operator uploads a scanned khasra. Mrittika checks the scan,
reads it (printed or handwritten, in nine Indian scripts), pulls out the
fields that matter, checks them against the map, the rules and the record's
history, and puts anything uncertain in front of a verifier. A tehsildar
approves the result. The citizen can then see their land, its history on a
map, and ask questions about it in plain Hindi.

> **This is a hackathon prototype (SIH 2026, PS-1).** Every record, owner,
> parcel and document in it is synthetic. It holds no real citizen data and is
> not connected to DILRMP, BhuNaksha or any government system. The accuracy
> figures below are measured on synthetic pages and public datasets, not on
> real land records. The [limits](#what-it-does-not-do-yet) are listed plainly.

---

## Why it is built this way

Most "AI digitization" demos run OCR and show the output. Land records are
different: a wrong owner name or a wrong khasra number moves someone's land.
So Mrittika is built around a few rules, and they are enforced in code:

- **The AI never has the last word.** Every field carries a confidence score.
  Uncertain fields, and every field on a handwritten page, go to a verifier.
  Only a tehsildar can approve a record.
- **Every number here was measured.** Where a model did not help, it is
  switched off and the measurement says so. The YOLO layout detector, for
  example, is trained but off, because it improved extraction by 0.001 F1.
- **An AI answer can only use what you are allowed to see.** The assistant
  works out which parcels you may see *before* it retrieves anything, so a
  clever prompt has nothing to leak.
- **Every change is tamper-evident.** Each state change is written to a
  SHA-256 hash chain, and each approved record gets a QR-verifiable
  certificate.
- **Ownership is history, not a column.** Owners come from the chain of
  mutations, so the record can always show how land changed hands, and when.
- **Nothing is invented on failure.** If OCR or a model fails, the document is
  marked for review with the reason. It is never filled with guesses.

---

## How a record moves through the system

```
 DEO uploads a scan (PDF / image, web or phone camera)
   │
   ▼
 Quality gate ── blur, skew, contrast; unreadable scans sent back for rescan
   │
   ▼
 Preprocess ── deskew, denoise, contrast (OpenCV)
   │
   ▼
 OCR ── PaddleOCR PP-OCRv5 (hi · te · ta · kn) or Gemini vision (any script)
   │
   ├── handwriting? ── trained detector → trained Devanagari reader
   │                   (optional Gemini second opinion)
   ▼
 Extraction ── label-anchored rules in 9 scripts → khasra, khata, owner,
   │           guardian, area, village, tehsil, district, mutation, date …
   ▼
 Checks ── validation rules · duplicate detection · anomaly model ·
   │       cross-check against the PostGIS cadastre
   ▼
 Confidence ── per field; the lowest decides the verifier queue order
   │
   ▼
 Verifier corrects ──► Tehsildar approves ──► pushed to the LRMS/DILRMP
   │                                           connectors (mock mode)
   ▼
 Citizen sees their land, its map, its history, and can ask the assistant
```

---

## What it does today

The problem statement lists twelve capabilities. **Ten work end to end and
two are partial.**

| # | Capability | Status | What is actually there |
|---|---|---|---|
| 1 | Multilingual recognition | **Partial** | Hindi, Telugu, Tamil and Kannada are read by PaddleOCR; Bengali, Gujarati, Punjabi, Odia and Malayalam by Gemini. Field labels exist for all nine scripts. **English text is read, but there are no English field labels yet**, so an English-language record extracts no fields. |
| 2 | PDFs, images, handwritten and historical pages | **Partial** | PDFs (multi-page) and images: yes. Handwriting: **Hindi only**, with a detector and reader trained on public handwriting data ([results](docs/handwriting.md)), not yet measured on real registers. Historical pages: blur/skew/contrast correction, tested on artificially aged pages only. |
| 3 | Classification into land-record fields | **Yes** | Rule-based extraction. Field-level F1 is **0.592** over all scan qualities and **0.872** on clean scans (synthetic validation pages). A trained IndicBERT v2 extractor exists but is not used, because it has not measured better. |
| 4 | Validation, duplicates, anomalies, spatial checks | **Yes** | Business rules (area, shares, dates, declared vs. read khasra). Duplicates: exact file hash, then a perceptual (dHash) match for rescans. Anomalies: Isolation Forest. Spatial: PostGIS cross-reference. |
| 5 | Confidence scores | **Yes** | Each field's score fuses OCR, extraction, layout, validation and language signals. Low scores are held for review. |
| 6 | Human-assisted verification | **Yes** | Verifier queue (filterable to handwritten pages), side-by-side workspace with the scan, correction, re-run, and tehsildar approval. |
| 7 | Feedback and retraining | **Yes** | Accepted corrections are exported. A nightly job retrains, evaluates on held-out pages, and promotes the new model only if it beats the current one. **It has never promoted a model**, because there are no real corrections yet. |
| 8 | GIS, cadastral map, parcel history | **Yes** | PostGIS parcels, map views, parcel ownership history, optional GeoServer (WMS/WFS) and pg_featureserv. The cadastre is synthetic. |
| 9 | LRMS/DILRMP integration | **Yes (mock)** | Approved records are pushed through connectors; every attempt is logged in `integration_log`. There is a status endpoint and an [AsyncAPI](docs/asyncapi.yaml) contract. No real NIC endpoint, and no message broker publishes the events. |
| 10 | Secure storage, access control, audit | **Yes** | MinIO document storage, role-based access limited to each officer's own jurisdiction, API keys for other systems, hash-chained audit log. |
| 11 | Dashboards | **Yes** | Document volume, extraction quality, validation status, pending verification, error statistics, and state → district → tehsil → village progress. |
| 12 | APIs for government systems | **Yes** | REST API with OpenAPI docs at `/docs`, API-key access for service accounts, anonymised research export. |

### Also included

- **Citizen portal and mobile app:** my land, map, record search, grievances,
  and an assistant that cites the records behind each answer.
- **Field app for DEOs:** camera capture with an offline upload queue.
- **Bilingual UI:** Hindi and English. Record values are shown as written and
  never machine-translated.
- **Notifications:** in-app, always. WhatsApp, SMS (MSG91), email and push
  are wired in, and send once their credentials are configured.
- **Two states:** Uttar Pradesh and Bihar, each with its own districts,
  tehsils and villages, to show jurisdiction scoping across states.

---

## Measured results

| What | Measured on | Result |
|---|---|---|
| Field extraction (rules, in production) | 75 synthetic Hindi validation pages, 4 scan qualities | F1 **0.592** overall: **0.872** clean, 0.778 moderate, 0.310 hard, 0 extreme |
| Layout detector (YOLO11n, off by default) | same pages | mAP50-95 0.958, but +0.001 extraction F1, so it stays off |
| Handwriting reader (CRNN) | 12,869 IIIT-HW-Dev handwritten words | **7.7%** character error rate, 69.8% of words exact |
| Handwritten numbers | 2,000 numbers built from DHCD/MNIST digits | 97.4% exact (synthetic numbers; expect lower on real ones) |
| Handwriting detector | printed text in **font families it never trained on** | 99.1% of handwriting caught, 0.3% of print wrongly flagged |

The handwriting figures come from each dataset's own test split, scored once.
The extraction figures come from the validation split. The rules were tuned
while looking at that split, so treat them as optimistic. The v1 test split has
not been scored yet (`scripts/evaluate_extraction.py --split test`).

**What these numbers are not:** accuracy on real land records. The fastest way
to get that figure is to run
[`scripts/evaluate_handwriting_real.py`](docs/handwriting.md#measuring-it-on-real-records)
on 20–50 real scans.

---

## Try it

### Demo accounts

Password for all: `demo_change_me`

| Role | Email | Can do |
|---|---|---|
| Citizen | `ram31@mrittika.demo` | See own land, map, history, ask the assistant |
| Citizen (second) | `seema32@mrittika.demo` | Same, to show one citizen cannot see another's land |
| Data Entry Operator | `deo@mrittika.demo` | Upload and process scans |
| Verifier / Lekhpal | `lekhpal@mrittika.demo` | Correct extracted fields |
| Tehsildar | `tehsildar@mrittika.demo` | Approve records, see analytics, ask the officer assistant |
| State Revenue Officer | `state@mrittika.demo` | Read-only, Uttar Pradesh |
| Central Ministry Officer | `central@mrittika.demo` | Read-only, all states |
| Survey Department | `survey@mrittika.demo` | Read-only map and spatial inconsistencies |
| Research Institution | `research@mrittika.demo` | Anonymised export only |

Every rule in that table is enforced by the API, not just hidden in the UI.
[docs/demo.md](docs/demo.md) walks through it role by role.

### Run it locally

You need Docker Desktop, Node.js 20+, Python 3.12 and Git.

```bash
git clone https://github.com/krishh0310/mritrrika-ai.git
cd mritrrika-ai
npm install

# 1. Database (PostgreSQL 16 + PostGIS + pgvector), Redis and MinIO
docker compose up -d

# 2. Python environment (3.12 is pinned; see pyproject.toml)
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt -r requirements-ai.txt
cp .env.example .env            # add GEMINI_API_KEY for Gemini OCR and the assistant

# 3. Schema and synthetic demo data
.venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head
.venv/bin/python scripts/seed_demo.py

# 4. API (shell 1)
.venv/bin/python -m uvicorn app.main:app --app-dir apps/api --port 8000

# 5. Worker (shell 2); uploads wait in the queue without it
cd apps/api && ../../.venv/bin/python -m celery -A app.worker.celery_app worker \
  --loglevel=info --concurrency=1

# 6. Web (shell 3)
npm run dev
```

Open <http://localhost:3000>. The API docs are at <http://localhost:8000/docs>,
and <http://localhost:8000/ready> confirms that PostGIS and pgvector are present.

**Optional extras:**

```bash
npm run mobile                                   # Expo citizen + field app
docker compose --profile gis up -d pg_featureserv   # vector features (see note below)
python scripts/download_handwriting_dataset.py      # ~2 GB, then:
python scripts/train_handwriting.py --task detector
python scripts/train_handwriting.py --task reader --epochs 15   # ~1 h on an M4 Pro
```

The handwriting model weights are not in git. Without them, handwriting is
still detected (by a simpler heuristic) and sent for review, but not read.

**Stop everything:** `Ctrl+C` in each shell, then `docker compose stop`. Use
`docker compose down -v` only if you want to delete the local data.

### Switches

Everything optional is off or degrades gracefully. The main switches in `.env`:

| Variable | Default | What it does |
|---|---|---|
| `OCR_PROVIDER` | `gemini` | `paddle` runs OCR locally and offline; `gemini` needs `GEMINI_API_KEY` |
| `HANDWRITING_MODELS_ENABLED` | `true` | Use the trained handwriting models when their weights exist |
| `GEMINI_HANDWRITING_ENABLED` | `false` | Gemini re-reads handwritten lines as a second opinion (sends crops to Google) |
| `USE_YOLO` | `false` | YOLO11n layout regions (measured no gain) |
| `INDICTRANS2_ENABLED` | `false` | Translate unreadable-label pages to Hindi. Needs `transformers<5`; see [ai-pipeline](docs/ai-pipeline.md) |
| `EMBEDDING_PROVIDER` | `ngram` | `gemini` makes record search semantic; `ngram` matches spelling, offline |
| `RETRAIN_SCHEDULER_ENABLED` | `true` | Nightly retrain check at 02:00 |
| `LRMS_ADAPTER` | `file` | Deliver approved records to a folder, over `http`, or `disabled` |

---

## Tech stack, and why

| Layer | Choice | Why this and not something else |
|---|---|---|
| API | FastAPI, SQLAlchemy 2, Alembic | Typed contracts and automatic OpenAPI docs. Every schema change is a migration |
| Database | PostgreSQL 16 + PostGIS + pgvector + pg_trgm | One database for records, parcel geometry, vector search and fuzzy name matching, all under one transaction and one access check |
| Jobs | Celery + Redis | OCR takes seconds, so an upload returns at once and the worker reads the page. Progress streams to the browser over SSE |
| Files | MinIO (S3 API) | Scans are files, not rows; the S3 API means real object storage is a config change |
| OCR | PaddleOCR PP-OCRv5, Gemini vision fallback | Paddle runs locally with native Indic models; Gemini covers scripts Paddle cannot read |
| Handwriting | Own CNN detector + CRNN/CTC reader (PyTorch) | Small (5 ms a line on CPU), runs offline, and is trained on public data. TrOCR is English-only, and the HF-hosted options are not served |
| Extraction | Label-anchored rules | Measured best on our data; explainable; IndicBERT v2 is trained and waiting to beat it |
| Anomalies | Isolation Forest (scikit-learn) | Unsupervised: there are no labelled fraud cases to train on |
| Web | Next.js 16, React 19, Tailwind 4, TanStack Query | Role-based dashboards with cached data and a shared design vocabulary |
| Maps | MapLibre GL | Open source; parcels drawn from GeoJSON |
| Mobile | Expo / React Native | One codebase for the citizen app and the DEO field app |
| Monitoring | Prometheus + Grafana (optional) | `/metrics` is computed from the database, so it matches what the dashboards show |

---

## What it does not do yet

Stated plainly, because a prototype that overclaims is worse than one that
says where it stops:

- **No real data, no real accuracy figure.** Everything is measured on synthetic
  pages or public datasets.
- **English records do not extract.** English text is read, but English field
  labels are not defined yet.
- **Handwriting is Hindi-only** and not validated on land registers. Every
  field on a handwritten page goes to a verifier.
- **The rule extractor misses fields on unfamiliar layouts.** On one clean,
  differently laid-out khasra, owner and khasra number were not extracted.
- **IndicTrans2 does not run here.** Its toolkit needs `transformers<5`.
  Extraction continues untranslated.
- **Government connectors are mocks.** The DILRMP XML field names are our
  mapping, not an official NIC schema.
- **The retraining loop has never promoted a model**, because there are no
  real corrections yet.
- **Known bug:** pg_featureserv and MinIO both bind port 9000, so the optional
  `gis` profile will not start alongside MinIO without changing one port.
- **Figures in [existing-system-study.md](docs/existing-system-study.md) marked
  † are unverified** and need checking against their sources.
- **Licences:** IIIT-HW-Dev states no licence. It is used here for research,
  with attribution. Clear it with CVIT, IIIT Hyderabad before production use.

---

## Repository layout

```
apps/
  api/                FastAPI — the single authoritative backend
  web/                Next.js — officer workstations and the citizen portal
  mobile/             Expo — citizen app and DEO field capture
services/
  ai-worker/          quality, preprocessing, OCR, handwriting, extraction,
                      normalisation, validation, anomaly
  dataset-generator/  synthetic records → templates → rendering → degradation
  gis/                village boundaries, Voronoi cadastre, PostGIS loading
packages/
  domain/             canonical record, confidence fusion, state machine
  ui/                 shared interface components
  shared-types/       generated from packages/domain — do not hand-edit
datasets/             generated data, annotations, splits, reports (mostly untracked)
models/               model configuration; weights are untracked
scripts/              reproducible commands: seed, generate, train, evaluate
tests/                backend, AI, dataset, integration, browser end-to-end
docs/                 design, pipeline, security, integration, demo
```

## Tests

```bash
.venv/bin/python -m pytest tests      # 826 tests (1 skipped) as of 2026-09-20
.venv/bin/python -m ruff check .
npm test                              # web + mobile unit tests
npm run lint && npm run typecheck
npm run e2e                           # 25 browser tests; needs the app running
```

Backend tests run against the real seeded database, because RBAC and
citizen-isolation are properties of the SQL, not something a mock can show.
To see the whole workflow in one place, read
[`tests/e2e/lifecycle.spec.ts`](tests/e2e/lifecycle.spec.ts): it follows one
document and one parcel through every role.

## Documentation

| Document | What it covers |
|---|---|
| [demo.md](docs/demo.md) | Step-by-step walkthrough, role by role |
| [architecture.md](docs/architecture.md) | System shape, runtime topology, why each directory exists |
| [ai-pipeline.md](docs/ai-pipeline.md) | Every pipeline stage, its fallback, and what it may claim |
| [handwriting.md](docs/handwriting.md) | Handwriting detection and reading: data, results, how to measure on real scans |
| [data-model.md](docs/data-model.md) | The schema, and why ownership is not a column |
| [security.md](docs/security.md) | Authorisation before retrieval, and known limitations |
| [api.md](docs/api.md) | API contracts, route groups, limits |
| [gis-integration.md](docs/gis-integration.md) | GeoServer / pg_featureserv, and why they never see ownership |
| [lrms-integration.md](docs/lrms-integration.md) · [dilrmp-integration.md](docs/dilrmp-integration.md) | Delivering approved records to state systems |
| [asyncapi.yaml](docs/asyncapi.yaml) | Event contract for `record.approved` and `record.flagged` |
| [existing-system-study.md](docs/existing-system-study.md) | Today's manual process, its pain points, what Mrittika can claim |
| [ai-ml.md](docs/ai-ml.md) · [database.md](docs/database.md) · [deployment.md](docs/deployment.md) · [monitoring.md](docs/monitoring.md) · [i18n.md](docs/i18n.md) | Model promotion, migrations, production target, metrics, languages |
| [handwriting-audit.md](docs/handwriting-audit.md) | The heuristic handwriting fallback, kept as a record |

## Regenerating the dataset

| Profile | Villages | Parcels | Pages |
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

Ground truth is written *before* each page is rendered. It is never recovered
by running OCR on the generated image. Splits are grouped by parcel, so a
clean page and its degraded copy can never land on opposite sides of the
train/test line.

## Credits and licence

Code: MIT, see [LICENSE](LICENSE).

Handwriting training data:
- [IIIT-HW-Dev](https://cvit.iiit.ac.in/research/projects/cvit-projects/indic-hw-data):
  Dutta, Krishnan, Mathew and Jawahar, CVIT, IIIT Hyderabad (DAS 2018).
- [DHCD](https://archive.ics.uci.edu/dataset/389/devanagari+handwritten+character+dataset)
  (UCI, CC BY 4.0).
- MNIST: LeCun, Cortes and Burges.
- Printed-font negatives: [Google Fonts](https://github.com/google/fonts)
  (SIL Open Font License).

OCR by [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR). Language models
by [AI4Bharat](https://ai4bharat.iitm.ac.in/).
