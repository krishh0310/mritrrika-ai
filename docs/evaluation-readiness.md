# Evaluation readiness (current improvement branch)

The supplied track specification is **IEEE CIS 04: Multi-Objective Heuristics +
Deep Evolutionary Networks**. The historical evaluator's 67 unverified terms
were not enumerated. The 35-term artifact inventory in `audit-report.md` is
therefore not proof that those 67 findings are closed.

| Requirement | Callable implementation | API/UI flow | Behavioral check and evidence | Remaining gap |
|---|---|---|---|---|
| Upload through human approval | `pipeline_service.process_document`, workflow routes | DEO upload, verifier correction, tehsildar approval | Existing backend and browser suites; rerun on clean stack required | Full stack result on this branch pending |
| Citizen access by authorization | `citizen_service`, auth dependencies | Citizen record and certificate routes | Existing authorization suites | Cross-jurisdiction browser pass pending |
| Indic document rendering | `mrittika_domain.fonts.find_font`, `RecordingCanvas`, certificate renderer | Synthetic pages and certificate download | Linux Python 3.12: 2 passed after source-building Pillow with libraqm | Full certificate rendering on Linux not independently run |
| Advisory forensic checks | `forensic_service.validate_reply` | Verifier forensic panel | `test_forensics.py` checks invalid verdicts, scores, injected fields | Queue/progress, full localization and independent validity study pending |
| Multi-objective heuristic | None tied to model selection yet | None | None | **Required track mechanism unimplemented** |
| Deep evolutionary network | None | None | None | **Required track mechanism unimplemented**; needs a defined search space and labeled grouped splits |
| OOD generalization and fair calibration | Existing extraction evaluation scripts | Review queue | Synthetic evaluation reports only | Grouped OOD and subgroup calibration evaluation pending |
| Full pipeline latency | Extractor-only `benchmarks/benchmark.py` | Document processing | `benchmarks/results.json` measures extraction only | OCR, queue, API, DB, storage, total, concurrency pending |
| SDG 9 resource efficiency | `impact.ImpactReporter` | CLI/report | `tests/ai/test_impact.py` | Only extraction time measured; no energy or real-world impact inference |

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
