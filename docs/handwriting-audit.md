# Workspace audit and handwriting experiment — 2026-09-14

The workspace started clean on `fix/cadastre-extraction-rag-e2e` at `6107410`,
tracking the same remote commit. History and all local/remote branches were
inspected before edits. No previous report was treated as evidence of runtime
behavior.

## What was actually present

- PaddleOCR, deterministic field/table extraction, weighted confidence fusion,
  and rules plus a corpus-fitted Isolation Forest have real implementations.
- The optional MuRIL and YOLO experiment code has training/evaluation callers.
  It is retained for reproducibility of the documented negative results;
  neither is being advertised as a production provider.
- The registry's `trained: false` conflated pretrained OCR with deterministic
  rules. It now names explicit training statuses and omits speculative model
  names from active entries. No training or calibration result was invented.
- `models/configs/pipeline.json` had no readers and disagreed with runtime
  defaults. It was removed. Ruff found no unused Python imports; generated
  checkpoints/images were already untracked. No corpus was deleted merely
  because its model experiment failed.
- OCR blocks and the database already had `is_handwritten`, but nothing
  computed it, persisted provider flags, or returned them to verification.

## Fixes

- Concurrent audit appends now take a PostgreSQL transaction-scoped advisory
  lock before reading the chain head. The concurrent suite exposed a real
  duplicate-sequence failure; a two-writer regression verifies chain continuity.

- An exact KHASRA label can no longer be stolen by a weaker KHATA fuzzy match.
- Invalid model output cannot replace a valid rule value.
- Blank OCR blocks no longer shift model span indices and bounding boxes.
- Importing the optional extractor works without PyTorch.
- A failed Isolation Forest refit discards the previous corpus model.
- Exceptions during lazy PaddleOCR iteration reach the fallback contract.
- Field, OCR, and optional layout boxes account for deskew rotation as well as
  scaling. All four corners are transformed to an enclosing axis-aligned box.

## Handwriting: implemented, with a negative accuracy result

`ocr/handwriting.py` measures character-baseline irregularity after removing
overall line tilt. It runs on OCR line crops in the prepared image. A positive
flag is persisted and returned in the verification workspace. The pipeline
adds a visible `SUSPECTED_HANDWRITING` finding and holds the page's fields for
review. A provider-supplied positive flag is retained.

**This is a weak experimental detector, not reliable handwriting recognition.**
False means “not detected,” not “confirmed printed.” Short words, connected
scripts, neat handwriting, and text missed entirely by OCR are blind spots.
Noise and approximate/multiline boxes can trigger false positives.

The current OCR provider still attempts transcription. There is no dedicated
handwriting reader and no measured handwriting character/word error rate.
No claim is made for reading handwritten Devanagari.

Reproduce the synthetic-only development measurement on macOS:

```bash
.venv/bin/python scripts/evaluate_handwriting.py --printed-cache
```

Use `--font-dir` elsewhere with the named fonts; missing fonts fail explicitly.
The optional printed-cache check needs the existing generated slice1 corpus
and OCR cache. No network calls or personal data are used. Each font has three
synthetic phrases at three sizes, with and without mild blur (18 samples).
These families informed the threshold, so this is **not a held-out benchmark**.

| Synthetic font style | Flagged / samples |
|---|---:|
| Arial | 0 / 18 |
| Times New Roman | 0 / 18 |
| Arial Italic | 0 / 18 |
| Devanagari Sangam MN | 0 / 18 |
| Bradley Hand Bold | 3 / 18 |
| Brush Script | 11 / 18 |
| Chalkboard | 0 / 18 |
| Comic Sans MS | 0 / 18 |
| Snell Roundhand | 14 / 18 |

Only **28/90 (31.1%)** handwriting-style proxies were detected, with **0/72**
false positives among these clean printed controls. The available printed
validation cache was harder: **5/214 blocks (2.3%)**, on **4/8 pages**, were
falsely flagged. This can create substantial extra review work. Font styles
are synthetic proxies, not examples of human handwriting; none of these
numbers estimates real-world handwriting accuracy.

## Verification record

Before edits: Python **348 passed / 261 skipped** with the database stopped;
web/mobile **38 passed**. Browser launch was initially sandbox-blocked, then
the retry confirmed the app was not running.

After starting the local synthetic stack and applying the first audit fixes:
Python **611 passed / 1 skipped**, web/mobile **38 passed**, browser **25 passed**.
The full suites were rerun after the handwriting batch. That run exposed the
audit sequence race (**616 passed / 1 failed / 1 skipped**) and a browser PDF
timeout while both suites ran OCR concurrently. The race was fixed; the
timeout was not hidden by changing the test.

Final verification, with Python and browser OCR run sequentially:

- Python: **621 passed / 1 skipped**, in 143.37 seconds. The existing skip is
  `test_end_to_end.py:200`: no low-confidence fields on that page.
- Web/mobile: **38 passed**.
- Browser: **25 passed**, in 2.0 minutes; the PDF test took 27.5 seconds.
  The worker was started for queued reprocessing after synchronous OCR checks.
- Ruff and `git diff --check`: passed. Web/mobile typechecks also passed.
- Three existing Starlette deprecation warnings remain.

There are no known failing tests from this final run. Handwriting detection
remains an explicitly limited experiment; dedicated reading, broad synthetic
script coverage, and held-out handwriting-style validation remain future work.
