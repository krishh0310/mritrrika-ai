# Gap audit — verified against the working tree

Branch: `fix/cadastre-extraction-rag-e2e` @ `2b6f50d`. Audited 2026-09-13.

This document exists because a prior gap analysis was written against a build
report rather than the code. Every line below was checked by reading the repo,
running the suites, and building the apps. Where the report was wrong, this
says so.

Baseline captured before any change:

| check | result |
|---|---|
| `pytest` | 387 passed, 1 skipped |
| `tsc --noEmit` (mobile) | clean |
| `expo export --platform web` | succeeds, 420 modules |

---

## Verdicts

| # | Claimed gap | Verdict | Evidence |
|---|---|---|---|
| 1 | No YOLOv8 / layout-region detection | **CONFIRMED MISSING** | No `yolo`/`ultralytics`/`detectron`/`layoutparser` anywhere. `services/ai-worker/layout/` is an empty, *untracked* directory. Training data, however, exists — see the note below. |
| 2 | No trained field-extraction model (LayoutLMv3) | **CONFIRMED MISSING** | Extraction is label-anchored and spatial — `services/ai-worker/extraction/field_extractor.py`. No checkpoints, no training script. |
| 3 | No AI4Bharat / IndicBERT / MuRIL | **CONFIRMED MISSING** (deliberately) | Absent from `requirements-ai.txt`. The only references are in `tests/ai/test_model_registry.py`, which *asserts* these names stay out of the registry until integrated. |
| 4 | OCR is Hindi-only | **CONFIRMED** | `RECOGNITION_MODELS = {"hi": "devanagari_PP-OCRv5_mobile_rec"}`, `lang: str = "hi"` — `services/ai-worker/ocr/provider.py:336`. |
| 5 | No duplicate detection at upload | **PARTIALLY DONE** | `documents.checksum_sha256` exists and is **indexed** (`apps/api/app/models/documents.py:68`); `storage_service.py:140` computes it. Nothing ever *queries* it — no rejection or warning path. The hard part is done; the check is missing. |
| 6 | No cross-database verification | **CONFIRMED MISSING** | `services/ai-worker/validation/rules.py` is format + business rules only. The `reconcil*` hits are flag reconciliation, not cross-source verification. |
| 7 | `ai_feedback` table is dead | **CONFIRMED** | Table + model exist (`apps/api/app/models/ai.py:59`, migration `f67d310791a5`). Zero readers, zero writers outside the model export. |
| 8 | No GeoServer / WMS / WFS | **CONFIRMED MISSING** | No match for `geoserver`/`wms`/`wfs` in any source or compose file. |
| 9 | No notification delivery | **PARTIALLY DONE** | A `notifications` table and model exist (`apps/api/app/models/ai.py:79`). No code constructs a `Notification`, and there is no SMS/WhatsApp/email provider — not even a stub. |
| 10 | No bilingual UI / i18n | **PARTIALLY DONE — narrower than reported** | No i18n library and no translated UI chrome in web or mobile (the only library grep hits are `apps/web/.next/` build artifacts). But an English *record-data* view already exists: `packages/ui/src/script.ts` (`toEnglish`, `transliterate`), covered by 32 unit tests in `apps/web/lib/script.test.ts` and by two Playwright specs in `officer-and-pdf.spec.ts:150,174`. Phase 8 must add chrome translation only, and must not disturb this. |
| 11 | Mobile app build broken | **REPORT WAS WRONG — ALREADY WORKING** | `npx tsc --noEmit` exits 0; `npx expo export --platform web` bundles 420 modules and writes `dist/`. Nothing to fix. |
| 12 | Empty `infrastructure/monitoring` + `infrastructure/nginx` | **REPORT WAS WRONG — NOT IN THE REPO** | `git ls-files infrastructure` returns only the six `docker/` files. These are untracked local empty directories referenced by no compose file. Local cruft, not a repo defect. |
| 13 | Misleading `services/ai-worker/confidence/` | **CONFIRMED** | `confidence/__init__.py` *is* tracked and is empty. Real confidence scoring lives in `services/ai-worker/extraction_pipeline.py` (`_status_for`, `lowest_confidence`) and `validation/rules.py:232`. The package advertises a module that does not exist. |
| 14 | README inaccurate | **CONFIRMED** | Two defects. (a) Quick start never starts the Celery worker, yet the pipeline is async and depends on it — a reader following the README gets uploads that never process. (b) Every test count in the Tests section is stale: 322/12/11 against an actual 388/38/17. Command spellings themselves check out against `package.json`. |
| 15 | Branch unmerged / unpushed | **CONFIRMED — and blocked** | 4 commits ahead of `main`. `git remote -v` is **empty**: there is no remote, so the branch cannot be pushed and no pull request can be opened from here. |

### Correction found while checking Phase 2 feasibility

`datasets/annotations/layout/`, `ocr/` and `tables/` are all empty, which reads
as "there is no layout ground truth to train on". That is wrong.

`scripts/generate_documents.py` created those three directories and never wrote
to them. All four annotation views are written into a single file per page
under `annotations/fields/`, because they describe the same render and must not
drift apart. Every one of the 500 pages carries its `layout` boxes inline:

    500 header boxes, 667 table boxes, 2 classes

The templates genuinely produce this ground truth —
`services/dataset-generator/templates/base.py` calls `add_layout_box` in four
places, and `annotations/writer.py` plumbs it through. So Phase 2 has a real,
if small, two-class training set.

The three permanently-empty directories are removed and no longer created, for
the same reason the empty `confidence/` package was: a directory that advertises
data it never holds costs a reader more than it saves.

### Correction to the prior analysis

Item 5 of the original Phase 5 list — *"Isolation Forest anomaly detection
replacing ad-hoc flagging"* — is **ALREADY DONE** and was missed entirely.

`services/ai-worker/anomaly/detector.py` implements `IsolationForestDetector`
with corpus fitting, a `MIN_CORPUS` floor of 30, 0.05 contamination, and a
normalised 0–1 score. `anomaly/engine.py` combines it with the rule engine and
suppresses the outlier score whenever a rule already fired on the same record.
`scikit-learn` is a declared dependency and the absent-sklearn path degrades to
rules only rather than fabricating a score. `tests/ai/test_anomaly_engine.py`
covers it.

Nothing here should be rebuilt.

---

## Outcome

Every item below was verified at the point it was closed, not asserted. Where a
measurement contradicted the expected result, the measurement is what is
recorded.

| # | Gap | Outcome |
|---|---|---|
| 1 | YOLOv8 region detection | **Built and measured.** mAP50-95 0.958 on the held-out val split; finds the exact ground-truth instance counts on all 75 pages. It does **not** improve extraction (F1 0.592 → 0.593), so it is opt-in and off by default. See `docs/ai-pipeline.md`. |
| 2 | Trained field-extraction model | **Skipped, on instruction, with a reason.** Phase 2 measured extraction as OCR-recall-bound (R 0.49 against P 0.75). LayoutLMv3 sits downstream of that same OCR, so it would very likely return the same null result at several times the cost. |
| 3 | AI4Bharat / IndicBERT / MuRIL | **Not integrated**, unchanged. The model registry still asserts they stay out until they are. |
| 4 | OCR is Hindi-only | **Six scripts read** (Devanagari, Telugu, Tamil, Kannada, Latin, Urdu) and five identified-and-refused by name. Routing recognises with each candidate and compares, scoring confidence × script agreement. Proven end to end on rendered Telugu, Tamil and Hindi pages. |
| 5 | No duplicate detection | **Two tiers.** Identical bytes refused with 409 naming the original; a page that merely looks similar is accepted and flagged, because a rescan after a quality rejection produces exactly that signal. |
| 6 | No cross-database verification | **Built.** Village, district, tehsil, khasra, khata and area checked against the location hierarchy, the cadastre and the PostGIS geometry. Kept in its own response key so nobody edits the page to match the reference. |
| 7 | `ai_feedback` dead | **Has a writer.** Every correction is scored by how much it would teach; CONFIDENT_BUT_WRONG outranks UNCERTAIN_AND_WRONG. Nothing retrains itself. |
| 8 | No GeoServer / WMS / WFS | **Running and verified.** 160 approved parcels served as GeoJSON and as rendered tiles. Ownership is unreachable at the database level, not merely omitted from a query. |
| 9 | No notification delivery | **Template-based providers** for WhatsApp Cloud API and MSG91, because both regimes require registered templates. No template carries record content. |
| 10 | No bilingual UI | **Chrome and all six citizen screens translated**, web and mobile, from one shared catalogue. Officer screen *body copy* is not translated — stated in `docs/i18n.md`. |
| 11 | Mobile build broken | **Report was wrong.** It built then and builds now. |
| 12 | Empty `infrastructure/monitoring` + `nginx` | **Report was wrong** — neither was in git. `monitoring/` is now real: Prometheus + Grafana. `nginx/` remains unneeded. |
| 13 | Misleading `confidence/` package | **Removed.** |
| 14 | README inaccurate | **Fixed** — missing worker step, three stale test counts. |
| 15 | Branch unmerged / unpushed | **Still blocked.** There is no git remote. See below. |

### Corrections to the prior analysis

Three claimed gaps were not real, and two things were found that the report did
not mention:

* **Isolation Forest anomaly detection already existed** — fitted on a corpus
  with a 30-record floor, suppressed when a rule already fired, degrading to
  rules when scikit-learn is absent. It was not rebuilt.
* **The mobile app already built.**
* **`infrastructure/monitoring` and `nginx` were never in git.**
* **A Prometheus exposition already existed** at `/metrics`, with nine metrics'
  worth of content. Only the scrape and the dashboard were missing.
* **The layout ground truth was silently wrong.** Boxes were written in
  pre-degradation coordinates while the annotation recorded the
  post-degradation size — on all 500 pages. Nothing read them, so nothing
  caught it. Fixed, and pinned by a table-cell containment test.

## Verification at the end of the work

| check | result |
|---|---|
| `ruff check .` | clean |
| `pytest tests` | 580 passed, 1 skipped |
| `npm run typecheck` (web + mobile) | clean |
| `npm run lint` | clean |
| `npm test` | 38 passed |
| `npm run build` | succeeds |
| `npm run build:mobile` | succeeds |
| Playwright | 25 passed |
| `scripts/check_i18n.py` | 137 keys, en + hi in parity |
| shared-types drift | up to date |

Baseline at the start was 387 passed / 1 skipped, 38 unit, 17 browser.

## The constraint that did not go away

There is still no git remote. `git remote -v` is empty, so the work cannot be
pushed and no pull request can be opened from this workspace. Everything lands
as commits on `fix/cadastre-extraction-rag-e2e`, and `docs/pr-description.md`
holds the description ready to use once a remote exists.
