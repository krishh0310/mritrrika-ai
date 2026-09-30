# Audit report

> Historical audit at commit `2d77f49`. Its 35-concept mapping does not prove
> resolution of the evaluator's unenumerated 67 terms or the subsequently
> supplied IEEE CIS track requirements. See [current evaluation readiness](evaluation-readiness.md).

## Phase 1 — declaration and artifact audit (2026-09-30)

Scope: feature and domain claims in `README.md` and `docs/*.md`. A term is verified only when a callable function, class, route, model, or UI component implements it; prose and comments are not evidence. The earlier score's list of 67 terms was not supplied, so its exact numerator cannot be reproduced. This inventory uses the actual declarations in this checkout.

### ✅ Verified terms

| Declared term | Working artifact |
|---|---|
| PDF and image ingestion | `services/ai-worker/ingest/rasterize.py:decode_pages` |
| Scan quality | `services/ai-worker/quality/assessment.py` |
| Preprocessing | `services/ai-worker/preprocessing/enhance.py` |
| Multilingual OCR | `services/ai-worker/ocr/provider.py:build_default_engine` |
| Script routing | `services/ai-worker/ocr/scripts.py` |
| Handwriting detection and reading | `services/ai-worker/ocr/handwriting_model.py` |
| Land field extraction | `services/ai-worker/extraction/field_extractor.py:extract` |
| Nine-script label vocabulary | `services/ai-worker/extraction/labels.py:LABELS_BY_LANGUAGE` |
| Normalization | `services/ai-worker/normalization/normalizers.py:normalize_field` |
| Validation | `services/ai-worker/validation/rules.py:run_all` |
| Confidence fusion | `packages/domain/mrittika_domain/confidence.py` |
| Anomaly detection | `services/ai-worker/anomaly/engine.py` |
| Duplicate detection | `apps/api/app/services/duplicate_service.py` |
| Cadastral cross-check | `apps/api/app/services/cross_reference_service.py:cross_reference` |
| PostGIS parcels and history | `apps/api/app/models/geography.py:Parcel`; `apps/api/app/models/land.py:OwnershipRecord` |
| GIS viewport | `apps/api/app/services/search_service.py:parcels_in_bounds` |
| Human verification and approval | `apps/api/app/routers/workflow.py` |
| Corrections and retraining | `apps/api/app/services/feedback_service.py`; `apps/api/app/tasks/retrain_scheduler.py` |
| LRMS and DILRMP mock delivery | `apps/api/app/integrations/lrms.py`; `apps/api/app/integrations/dilrmp_connector.py` |
| Audit chain and certificate | `apps/api/app/services/audit_service.py`; `apps/api/app/services/certificate_service.py` |
| Jurisdiction and citizen access | `apps/api/app/auth/dependencies.py`; `apps/api/app/services/citizen_service.py` |
| Search and RAG assistant | `apps/api/app/services/search_service.py`; `apps/api/app/services/rag_service.py` |
| Dashboards and metrics | `apps/api/app/services/dashboard_service.py`; `apps/api/app/services/metrics_service.py` |
| Notifications | `apps/api/app/services/notification_service.py` |
| Web and mobile interfaces | `apps/web/app`; `apps/mobile/app` |
| Synthetic data generation | `packages/dataset-generator`; `scripts/generate_dataset.py` |

### ❌ Unverified or incomplete declared terms

| Term | Finding |
|---|---|
| English field extraction | README explicitly says OCR reads English but labels are absent. |
| DILRMP event publication | `docs/asyncapi.yaml` defines events but README says no broker publishes them. This is an explicitly excluded prototype capability, not an implemented feature. |
| Real government integration | Explicitly excluded; connectors run in mock mode. |
| Real-record accuracy and real-register handwriting | Explicitly excluded pending authorized real data. |
| Resource-efficiency impact report | No computed impact module or measured throughput report. |
| Reproducible latency benchmark | No benchmark harness for the current hot path. |
| Accessibility audit | No documented WCAG review or keyboard check. |

### Profiled bottleneck

`extract_scalar_fields` on a synthetic 150-block page, 10 calls under CPython 3.12: **5.385 s**, **31,455,423 function calls**. `_label_score` accounts for 4.349 s and is called 35,980 times; `SequenceMatcher` is invoked 438,430 times. Candidate ranking and each neighbor scan repeat the same label classification. The effective cost grows with blocks × fields × variants, plus repeated block scans. Separately, `check_parcel_exists` fetches every parcel in a village and scans them in Python despite the existing `(village_id, khasra_number)` index; this adds O(village parcels) transfer and work to each verification workspace request.

## Phase 2

English labels and owner/share headings are now in the real extractor vocabulary, with a representative extraction test. `docs/domain-mapping.md` maps the working declared capabilities to callable artifacts. The four external/real-data exclusions remain explicitly labeled as limits, not working features. **No unverified in-scope capability in this inventory remains.** The unavailable 67-item prior list prevents claiming an exact 67/67 comparison.

## Phase 3

Per-page label classification now runs once per block, fuzzy scores have bounded caches, and different scripts are rejected before `SequenceMatcher`. Exact parcel matches use the existing composite index; punctuation-tolerant matching remains a fallback. S3 connections have bounded connect/read timeouts and a 20-connection pool. `benchmarks/benchmark.py` records independent-page latency and the identical repeat workload used by the initial profile. Measured figures are in `benchmarks/results.json` and analyzed in `docs/performance.md`.

## Phase 4

`docs/innovation.md` documents two implemented extractor decisions with measured intermediate and final profiles. These are project-specific improvements, not claims of a new research algorithm.

## Phase 5

README now includes an architecture diagram, API reference, domain table, setup, benchmark, SDG section, and executable lifecycle demo entry point. `docs/accessibility.md` records the contrast calculation and its limits. The small-text color tokens were darkened to clear 4.5:1 on their common surfaces; a contrasting focus outline remains on dark header chrome. Added `CONTRIBUTING.md` and `docs/decisions/0001-extraction-hot-path.md`.

## Phase 6

`impact/ImpactReporter` computes saved processing time and relative throughput from equal-workload measured profiles. `docs/impact.md` records the 10-page result and clearly excludes OCR, storage, energy, and real-world emissions. README cites the actual UN Target 9.4 wording.

## Phase 7 and final self-audit

Complete. `gitleaks git` scanned 81 commits with 0 findings; `gitleaks dir` scanned a snapshot of tracked and new non-ignored files with 0 findings. `.env` remained outside that snapshot. The local regex scanner also reported 0 findings. `.gitleaks.toml` is included.

| Final check | Result |
|---|---|
| Declared concept artifact audit | **35 checked, 0 unverified** (`scripts/audit_domain_mapping.py`, AST check, stronger than text grep) |
| Full mapping | `docs/domain-mapping.md` covers all 35 in-scope concepts in this inventory |
| Benchmark executed | `benchmarks/results.json`; actual figures in README |
| README sections | Architecture, API, domain table, SDG 9, benchmarks, executable demo |
| Innovation and impact | Two measured components in `docs/innovation.md`; `ImpactReporter` computes from profiles |
| Secret scan | Gitleaks history and working snapshot: 0 findings |
| Python tests | **829 passed, 1 skipped, 6 slow deselected** against isolated PostGIS/Redis/MinIO; one additional indexed-lookup regression test passed separately |
| Coverage | **88%** of API, AI worker, and domain Python source (6,823 statements, 845 missed) |
| Frontend | ESLint, typecheck, 38 unit tests, web production build, mobile web export passed |
| Browser demo | **11 passed** using `scripts/demo.py` against the local stack |
| Placeholder marker search | 0 matches outside dependencies |

The earlier 76.19/100 rubric and its 67-term list were not supplied as reproducible inputs. This audit therefore cannot assert a new score of 95+ or equivalence to that exact list. External live integration and real-record accuracy remain explicitly out of scope for this synthetic prototype.
