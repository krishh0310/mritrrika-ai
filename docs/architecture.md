# Mrittika AI — Architecture

> **All data in this system is synthetic.** No real citizen land record is used
> anywhere in this prototype (§83).

Mrittika AI converts legacy land documents into AI-extracted, human-verified,
officer-approved, spatially linked digital records that authorized citizens and
officials can search, inspect and query through a grounded AI assistant.

---

## 1. Runtime topology

```
   apps/web (Next.js)              apps/mobile (Expo)
            \                             /
             \_______ HTTPS + JWT _______/
                          |
                 apps/api (FastAPI)          <-- sole authority for business logic
          router -> service -> repository -> PostgreSQL (PostGIS + pgvector)
                          |
                    Redis (broker)
                          |
            services/ai-worker (Celery)      <-- OCR / layout / extraction
                          |
                        MinIO                <-- documents, page images, derivatives
```

Run once, offline, via `scripts/` — never on the request path:

- `services/dataset-generator` — structured ground truth → render → degrade → annotate
- `services/gis` — Voronoi cadastre → PostGIS

### Why the AI worker runs natively

Spec §75 lists `worker` as a Docker Compose service. On this Apple-Silicon dev
machine it is not, and that is a deliberate, documented departure:

- `paddlepaddle` publishes solid **macOS-arm64** wheels but has a much weaker
  **linux/arm64** story.
- Running the worker under x86 emulation makes OCR too slow for a live demo.

So `docker-compose.yml` provides **postgres, redis, minio** only; the API,
worker and web app run natively against them. The full all-in-Docker stack is
still maintained at `infrastructure/docker/compose.full.yml` for x86
demo/deployment machines, so the spec's one-command story survives.

### Why Python is pinned to 3.12

The dev machine's system Python is **3.14.7**. `paddlepaddle` 3.3.1 ships
macOS-arm64 wheels for **cp39–cp313 only — there is no cp314 wheel**. Building
on 3.14 would have failed at the OCR stage, after the schemas, dataset,
database, auth and upload layers were already written against it. Pin:
`/opt/homebrew/bin/python3.12`.

### Why Postgres is a custom image

Mrittika needs PostGIS (parcel geometry, §11) **and** pgvector (semantic
retrieval, §10) in the same database. No official image ships both, so
`infrastructure/docker/postgres/Dockerfile` builds pgvector on top of
`postgis/postgis:16-3.4` and enables both extensions at init, failing loudly if
either is missing.

---

## 2. Verified environment findings

Recorded here because each one is silent-and-costly if rediscovered late.
All are guarded by `tests/ai/test_devanagari_stack.py`.

| # | Finding | Consequence if ignored |
|---|---|---|
| 1 | No cp314 paddle wheel | AI stack unbuildable on system Python |
| 2 | **Pillow needs libraqm** for Devanagari shaping | Generated images would not match their own ground-truth labels (§44), so OCR would appear to fail on text that is actually malformed |
| 3 | PaddleOCR lang code is **`hi`**, not `devanagari` | `ValueError: No models are available` |
| 4 | PaddleOCR does **not** guarantee reading order | Field values silently scrambled on concatenation |
| 5 | Devanagari line grouping must use **vertical overlap**, not y-centre | Matras/anusvara inflate box height; `सिंह` (y 17–76) bands apart from `राम` (y 35–70) on the *same line* and sorts first |

### Finding 2 in detail

Devanagari's `ि` matra is stored after its consonant but must *render* before
it. Without libraqm, Pillow does no complex-script shaping and the matra stays
on the right. The output looks superficially plausible — which is the danger.
Because §44 mandates that ground truth exists *before* rendering, broken
shaping produces a dataset whose labels and pixels disagree. That failure would
present as poor OCR accuracy and be extremely hard to trace back to rendering.

Fix:
```bash
brew install libraqm
PKG_CONFIG_PATH=/opt/homebrew/lib/pkgconfig \
  pip install --force-reinstall --no-binary :all: --no-cache-dir Pillow
```

### OCR baseline (measured)

PaddleOCR `lang='hi'` on clean rendered Devanagari, this machine, CPU:

| conf | text |
|---|---|
| 1.000 | रामपुर |
| 0.966 | राम प्रसाद सिंह |
| 0.987 | खसरा संख्या १४२/२ |
| 0.977 | क्षेत्रफल २.७५ बीघा |
| 0.977 | सिंचित |

Conjuncts (`क्ष`, `प्र`) and Devanagari digits read correctly.

**This is the easiest possible input.** It establishes that the stack works, not
that accuracy is production-grade. Degraded-scan accuracy is a separate
measurement produced by the §65 evaluation harness, and no accuracy claim is
made until that harness reports one (§69).

---

## 3. Layering

Every domain follows §80 strictly:

```
router  ->  service  ->  repository  ->  database
```

- **router** — HTTP shape, auth dependency, request/response schemas. No SQL, no business rules.
- **service** — business rules, state-machine transitions, authorization decisions, orchestration.
- **repository** — data access. The only layer that touches SQLAlchemy.

Per §79 there are no `utils.py` / `helpers.py` catch-alls; modules are named for
their domain responsibility (`ocr_service.py`, `token_service.py`,
`parcel_service.py`, `audit_hash.py`).

---

## 4. Provider abstractions (§81)

What actually sits behind an abstraction today. Rows that are not built are
listed so the table cannot be read as a claim (§69):

| Capability | Implementation | Fallback (§82) |
|---|---|---|
| OCR — `OcrProvider` (abstract base) | `PaddleOcrProvider` (`lang='hi'`) | `GeminiVisionOcrProvider`, output marked degraded |
| LLM phrasing of answers | Gemini, via `rag_service` | Groq; if neither responds, the structured database answer is returned flagged `degraded` |
| Layout | deterministic geometry in the extractor; optional YOLO region detector behind `USE_YOLO` (off) | runs without it |
| Handwriting | geometry heuristic flags blocks and routes pages to review; no reader | — |
| Embeddings | n-gram vectors (default) or Gemini `text-embedding-004`, in pgvector | keyword search |

No `ANTHROPIC_API_KEY` exists on this machine; `GEMINI_API_KEY` and
`GROQ_API_KEY` do. The embedding dimension (768) fixes the `pgvector` column
width.

**A failed model never fabricates output.** It degrades to a `NEEDS_REVIEW`
state, and the failure is recorded against the document.

Every prediction persists its `model_version` (§64), so no stored value is ever
ambiguous about which model produced it.

### Computer vision

OpenCV does all image cleanup: deskew, denoise, contrast, and the quality
gate's blur/skew/contrast scores. The layout detector fine-tunes **YOLO11n**
(`services/ai-worker/config/cv_config.py`, one line to change). YOLO11 over
YOLOv10: its C3k2 blocks and C2PSA spatial-attention layer are what Ultralytics
credits for better small-object accuracy at the same model size, and document
regions (thin header strips, table rules) are small. That is the vendor's
claim; the measured result on this corpus is in
[ai-pipeline.md](ai-pipeline.md). The detector stays off by default
(`USE_YOLO=false`) because it did not improve extraction.

---

## 5. The data spine

Everything hangs off `parcel_id` (§11). The rule that must not be violated
(§39): **a parcel never carries `owner_name`.**

```
User ─1:1─ CitizenProfile ─N:1─ Owner
                                  │
                                  └─< OwnershipRecord >─┐  (share, valid_from,
                                                        │   valid_to, mutation_id)
Village ─< Parcel ──────────────────────────────────────┘
            │
            ├─< LandRecord ─< Mutation
            └─< Document ─< DocumentPage ─< OcrBlock ─< Extraction ─< FieldCorrection
```

`valid_from` / `valid_to` on `OwnershipRecord` is what makes *"who owned this in
1998?"* answerable — demo step 24, and therefore load-bearing.

**Provenance (§26):** every `Extraction` keeps `raw_value` *and*
`normalized_value`, plus `bbox`, `source_page`, per-stage confidences and
`model_version`. Normalization never overwrites raw. This is what powers the
Verifier's click-field → zoom-to-source-region interaction.

---

## 6. Authorization

Citizen identity is **derived server-side, never accepted from the client** (§62):

```
JWT -> user_id -> citizen_profile -> owner_id -> authorized parcel_ids
```

A request like `GET /my-land?owner_id=123` must ignore the parameter entirely.
This is enforced before retrieval, including inside the RAG path — the LLM is
never shown a parcel the caller cannot access (§18).

---

## 7. Honesty constraints (§69)

Not implemented, and not implied anywhere in the UI: blockchain, federated
learning, GNN fraud detection, signature forgery detection, Bhashini / DILRMP /
BhuNaksha integration, voice query, MAML.

- The audit chain is **hash-chained** (SHA-256 over canonicalized events). It is
  never called "blockchain."
- Anomalies read *"Potential inconsistency — manual investigation recommended,"*
  never "fraud detected" (§34).
- Every synthetic record is visibly marked **DEMO / SYNTHETIC DATA** (§83).
- No accuracy figure is published until the §65 harness measures it.
