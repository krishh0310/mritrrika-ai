# The AI pipeline

What runs over a scanned page, in what order, and what each stage is allowed to
claim.

```
bytes
  ↓  quality        blur, contrast, resolution, skew, brightness  → verdict
  ↓  preprocessing  grayscale, denoise, CLAHE, deskew, upscale
  ↓  ocr            PaddleOCR (Devanagari + Latin) → blocks with bbox + score
  ↓  layout         table rows detected from OCR box positions (geometry, not a model)
  ↓  extraction     deterministic rules over the OCR blocks → fields
  ↓  normalization  Devanagari digits, fractions, units, dates
  ↓  validation     §33 rules → findings
  ↓  confidence     five-signal weighted fusion → per-field score and band
  ↓  anomaly        §34 rules + Isolation Forest over the parcel's history
NEEDS_VERIFICATION
```

Every stage writes to `processing_jobs.stage`, which is what the operator's
progress list and the SSE stream read.

## The quality gate comes first, on purpose

`services/ai-worker/quality/assessment.py` runs **before any model loads**. It
measures five things and returns one of four verdicts:

| verdict | meaning |
|---|---|
| `PROCESS` | run the pipeline |
| `PROCESS_WITH_WARNING` | run it, but expect low confidence |
| `RESCAN_RECOMMENDED` | a better photograph would pay for itself |
| `REJECT_QUALITY` | too poor to read; do not waste the compute |

Running OCR on an unreadable page produces confident nonsense, which is worse
than no output — a verifier then has to disprove it rather than simply rescan.
The gate is cheap (a Laplacian variance and some histogram statistics) and it
is the reason the DEO screen can say "rescan this" in seconds rather than
minutes.

The individual measurements are surfaced, not just the verdict: "rescan
recommended" is only actionable if the operator can see it was the blur and not
the lighting.

## OCR, and what happens when it is unavailable

`ocr/provider.py` defines an `OcrProvider` interface with two implementations:

* `PaddleOcrProvider` — PP-OCRv5, Devanagari + Latin. The primary.
* `GeminiOcrProvider` — the §82 fallback when Paddle cannot load.

If neither is available the provider raises `OcrUnavailable`, the pipeline
records the failure, and the document moves to **`RESCAN_REQUIRED`** — never to
`NEEDS_VERIFICATION` with empty results. §82 is explicit: never fabricate AI
output when a model fails. A page with no recognised text needs a better scan,
not a reviewer staring at a blank field list.

Every block stores text, confidence, bbox, script and reading order. §6 forbids
storing plain text alone, because the verification workspace cannot exist
without bounding boxes.

### Bounding boxes are stored in ORIGINAL page coordinates

Preprocessing upscales and deskews the image before OCR runs, so the boxes come
back in enhanced-image space. `pipeline_service` divides by `scale_x`/`scale_y`
before writing them. Without that, the verifier's overlay would sit consistently
off its words and the §28 click-to-zoom interaction would be useless.

## Extraction is deterministic first

`extraction/field_extractor.py` is rules over OCR blocks — label proximity,
expected position, script and format. Not a model.

That ordering is §7 and §66: start with what is explainable and cheap, measure
where it fails, and only then reach for a fine-tuned model. An extractor that
can say *why* it chose a value is more useful to an officer than a slightly more
accurate one that cannot. (Measured numbers are in the evaluation section; that
comparison is an argument, not a result.)

No ML model assists extraction. `IndicBERT` and `LayoutLMv3` are **not
integrated** — an earlier version of this document and of the model registry
said they were "wired as optional assists", and no code ever referenced them.
The deterministic path carries the whole load, and every field records the
model version that produced it (§64).

## Normalization never destroys the raw value

`normalization/normalizers.py` handles:

* Devanagari digits → Latin (`१४२` → `142`)
* mixed-script numerals, which real OCR produces constantly (`२७६` → `276`)
* fractional shares kept as fractions (`१/२` → `1/2`, never `0.5`)
* area units (`बीघा` → `BIGHA`, with the raw form retained)
* record years (`1998-99`)

Both values are stored. §26 is the rule: `raw_value` is what the scanner saw,
`normalized_value` is what the system made of it, and a correction lands in a
third column. All three survive, which is what makes the provenance strip in
the UI possible and what lets an approved record be traced back to pixels.

## Confidence is fused, not averaged

§8 forbids `mean(all_scores)`. `packages/domain/confidence.py` combines four
signals with configurable weights:

| signal | source |
|---|---|
| OCR confidence | the recogniser's own score for the block |
| extraction confidence | how well the rule matched |
| layout confidence | whether the value sat where the template expects |
| validation confidence | what the §33 rules said about this field |

plus a language/script evidence term. The breakdown is stored per field
(`confidence_breakdown`) and shown in the workspace, so a low score points at
which signal dragged it down.

Bands: `>= 0.85` HIGH, `0.60–0.85` MEDIUM, `< 0.60` LOW. The UI never shows a
band by colour alone (§86).

## Validation before ML

`validation/rules.py` is deterministic and runs on every document: required
fields, malformed khasra/khata, implausible area, invalid dates, share sums,
mismatch against the DEO's declared metadata, and large area changes.

A rule never blocks a document by itself. It attaches a finding, which feeds the
confidence engine and raises the document's queue priority.

## Anomaly detection is two engines, deliberately separated

`services/ai-worker/anomaly/` implements §34 as:

* **`rules.py`** — deterministic checks over a parcel's *history*: `AREA_JUMP`,
  `INVALID_CHRONOLOGY`, `DUPLICATE_PARCEL`, `MISSING_MUTATION`,
  `LOCATION_MISMATCH`, `REPEATED_MODIFICATION`, `UNUSUAL_OWNERSHIP_CHANGE`.
  These fire on facts and explain themselves with evidence.
* **`detector.py`** — an Isolation Forest over ten numeric features, for
  patterns nobody wrote a rule for. Fitted on the whole corpus, because
  "unusual" is only definable relative to what else exists.

The engine returns rule findings first and **suppresses the outlier score when a
rule already fired** on the same record. Telling an officer "this is also
unusual" on top of "these dates run backwards" adds noise, not information.

Fallbacks (§82): no scikit-learn, or a corpus under 30 records, and the detector
reports itself unavailable. The rules still run. Nothing is fabricated.

### Wording

No flag says "fraud", "forged" or "suspicious". Every one says *potential
inconsistency; manual investigation recommended*, and carries the values that
made it fire. There is a test that asserts this
(`tests/ai/test_anomaly_engine.py::TestWording`), because it is the kind of rule
that erodes the first time someone writes a punchier string.

## Two defects the seeded data exposed

Worth recording, because both were invisible in unit tests and obvious against
real records:

1. **`MISSING_MUTATION` counted ownership spans, not transfers.** A parcel held
   jointly by two co-heirs has two `ownership_records` rows created by one
   mutation. Counting rows flagged half the cadastre as having an unexplained
   transfer — 20 false positives across 40 parcels. Now counted as distinct
   `valid_from` dates minus the original grant: 2 genuine findings.

2. **A parcel-only pass closed flags it could not evaluate.** `AREA_JUMP` and
   `LOCATION_MISMATCH` need a document to compare against. The batch job has no
   document, so it saw no such flag and marked existing ones resolved — quietly
   erasing findings nobody had re-examined. `evaluable_types()` now tells the
   reconciler which anomaly types the current input could actually reach a
   verdict on.

## Model versioning and evaluation

Every prediction stores its model version (`ocr-v1`, `extractor-v1`,
`confidence-v1`, `anomaly-v1`), registered in `model_versions`. A correction
records the version that made the prediction it replaced, which is what makes
the §67 active-learning pool meaningful.

Evaluation lives in `scripts/evaluate_extraction.py` and reports per difficulty
tier (clean / moderate / hard / extreme) rather than as one headline number. §65
forbids claiming an accuracy figure that has not been measured, and a single
average over a corpus that is 20% clean and 15% extreme tells you nothing about
either.

## What is NOT implemented

Named here so nothing above reads as a claim (§69):

| | status |
|---|---|
| Handwriting recognition (TrOCR or any other) | not implemented, and no handwriting detection either — nothing sets `ocr_blocks.is_handwritten` |
| Layout models (PP-Structure, LayoutLMv3) | not integrated — layout is deterministic geometry inside the extractor |
| IndicBERT extraction assist | not integrated |
| Embeddings / pgvector retrieval | not implemented — the `embeddings` table exists, nothing writes or queries it |
| Confidence calibration (ECE, reliability diagrams) | planned, not measured |
| Federated learning, GNN ownership analysis, MAML | research direction only |
| Bhashini, DILRMP, BhuNaksha integration | not connected to anything |
| Continuous autonomous retraining | deliberately absent (§67) |
