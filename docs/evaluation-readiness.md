# Evaluation readiness (current improvement branch)

The supplied track specification is **IEEE CIS 04: Multi-Objective Heuristics +
Deep Evolutionary Networks**. The historical evaluator's 67 unverified terms and the latest screenshot's
54 unverified terms were not enumerated. The 35-term artifact inventory in `audit-report.md` is
therefore not proof that those 67 findings are closed.

| Requirement | Callable implementation | API/UI flow | Behavioral check and evidence | Remaining gap |
|---|---|---|---|---|
| Upload through human approval | `pipeline_service.process_document`, workflow routes | DEO upload, verifier correction, tehsildar approval | Existing backend and browser suites; rerun on clean stack required | Full stack result on this branch pending |
| Citizen access by authorization | `citizen_service`, auth dependencies | Citizen record and certificate routes | Existing authorization suites | Cross-jurisdiction browser pass pending |
| Indic document rendering | `mrittika_domain.fonts.find_font`, `RecordingCanvas`, certificate renderer | Synthetic pages and certificate download | Linux Python 3.12: 2 passed after source-building Pillow with libraqm | Full certificate rendering on Linux not independently run |
| Advisory forensic checks | `forensic_service.validate_reply` | Verifier forensic panel | `test_forensics.py` checks invalid verdicts, scores, injected fields | Queue/progress and independent validity study pending; interface localization and keyboard consent now tested |
| Multi-objective heuristic | `optimization/multi_objective.py:pareto_front`, `select_configuration` | Offline `benchmarks/compare_pipeline.py` recommendation | `test_multi_objective.py`; measured server/mobile operating points | Small synthetic corpus; broad validation and evolutionary search remain pending |
| Deep evolutionary network | None | None | None | **Required track mechanism unimplemented**; needs a defined search space and labeled grouped splits |
| OOD generalization and fair calibration | Existing extraction evaluation scripts | Review queue | Synthetic evaluation reports only | Grouped OOD and subgroup calibration evaluation pending |
| Local document pipeline latency | `benchmarks/document_pipeline.py` | Real Paddle OCR through validation and confidence, PNG/PDF | Raw timings and exact field outcomes in `benchmarks/document-pipeline/` | API, queue, DB/storage, concurrency, and multilingual timed runs pending |
| SDG 9 resource efficiency | `impact.ImpactReporter`, `pipeline_metrics` | CLI/report | `tests/ai/test_impact.py`; measured runtime, memory, and flagged-field counts | Human effort and energy not measured; no real-world impact inference |

## Reproduction and limits

- Python 3.12 is the supported version. Install `apps/api/requirements-test.txt`
  for the complete non-slow Python suite. AI model/runtime dependencies live in
  `services/ai-worker/requirements.txt` and require separate model artifacts.
- On Debian/Ubuntu install `fonts-noto-core libraqm-dev libfreetype6-dev
  libjpeg-dev zlib1g-dev build-essential pkg-config`, then build Pillow from
  source using `pip install --force-reinstall --no-deps --no-binary Pillow
  'Pillow>=11,<13'`. The default Linux arm64 wheel tested here lacked libraqm
  and failed both shaping assertions. Noto Devanagari is licensed under
  [SIL Open Font License 1.1](https://github.com/notofonts/devanagari/blob/main/OFL.txt).
  `MRITTIKA_FONT_DEVANAGARI`, `MRITTIKA_FONT_TELUGU`,
  `MRITTIKA_FONT_TAMIL`, and `MRITTIKA_FONT_KANNADA` override discovery;
  append `_BOLD` for a bold face.
- Run `.venv/bin/python -m pytest tests/ai/test_devanagari_stack.py
  tests/ai/test_script_routing.py -q -m 'not slow'` for font/shaping and script
  checks. Slow OCR routing requires downloaded recognition models.
- Run `.venv/bin/python -m pytest tests/backend/test_forensics.py -q` for the
  provider-output trust boundary. These are schema tests, not evidence that a
  model can detect forged records.

### Recorded checks on this branch

| Environment | Command / condition | Result |
|---|---|---|
| macOS, Python 3.12.14 | `ruff check .` | passed |
| macOS, Python 3.12.14 | `python -m pytest tests/backend/test_forensics.py tests/ai/test_devanagari_stack.py tests/ai/test_script_routing.py tests/ai/test_impact.py -q -m 'not slow'` | 36 passed, 6 deselected |
| Linux arm64, Python 3.12.14 | `fonts-noto-core` plus default Pillow wheel; `python -m pytest tests/ai/test_devanagari_stack.py -q -m 'not slow'` | 2 failed: libraqm absent and matra not shaped |
| Linux arm64, Python 3.12.14 | `fonts-noto-core` and Pillow source build with `libraqm-dev`; same test command | 2 passed, 1 deselected |

The branch does not have an official evaluator result. No category is assigned
a new percentage from these changes alone.

## Latest supplied evaluator baseline

The user identifies these screenshots as a run against `main`. The screenshot
itself does not contain an evaluated commit hash. These are reported evaluator
scores, not a new estimate for the changes on this branch.

| Category | Weight | Supplied score | Target |
|---|---:|---:|---:|
| Code quality | 20% | 87.43 | >85 |
| Efficiency and latency | 18% | 61.63 | >85 |
| Testing and validation | 18% | 94.53 | >85 |
| Security | 12% | 92.27 | >85 |
| Problem alignment | 12% | 65.02 | >85 |
| Track innovation | 10% | 67.10 | >85 |
| Accessibility and docs | 10% | 57.60 | >85 |
| Weighted total | 100% | 76.94 | — |

Social impact was shown separately as **74.43%**. Only a new evaluator run can
confirm whether any category clears the target.

## Current verified improvements

- Inline label/value extraction: nine language regressions reproduced before
  the fix; explicit inline values now outrank unrelated neighboring cells.
  Labels are scored before the separator so long values do not hide the label.
- Forensic UI: visible external-processing consent, Hindi/English controls and
  status codes, advisory wording, error announcements, and keyboard tests.
- Offline pipeline benchmark: real local OCR on four Hindi synthetic documents
  (six pages), plus field quality and per-stage timing. Server F1 changed from
  0.400 to 1.000 on this regression corpus; mobile F1 from 0.286 to 0.917.
  These are small synthetic measurements, not deployment accuracy claims.
- Pareto selection: measured latency, peak process memory, and field F1;
  rejects incompatible runs and returns no solution if hard budgets conflict.

Unresolved: deep evolutionary learning, OOD generalization guarantees,
sub-population calibration, full-stack concurrency measurements, queued
forensics, browser-wide accessibility verification, and the unenumerated
54-term evaluator inventory. Current changes do not establish >85 everywhere.
