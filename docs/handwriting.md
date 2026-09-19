# Handwriting: detection and reading

Old land records are often handwritten, or printed forms with handwritten
entries. PaddleOCR is trained on print and mostly misreads handwriting, so
the pipeline has two trained models of its own for it.

```
PaddleOCR line boxes
   │
   ├─ detector: handwritten or printed? ──── printed ──► PaddleOCR's text stands
   │   (a small CNN; threshold calibrated in training)
   │
   └─ handwritten ──► reader (CRNN + CTC) re-reads the line
                        │
                        ├─ GEMINI_HANDWRITING_ENABLED: Gemini reads it too
                        │    agree → line confidence 0.8, disagree → 0.4
                        │    (the local reading stands either way)
                        ▼
          every field on the page → NEEDS_REVIEW, with a
          SUSPECTED_HANDWRITING finding naming the reader version,
          and documents.handwriting_meta.read_by set
```

Gemini is off by default because it sends each handwritten line crop to
Google. Without a local reader, Gemini reads alone. Which reader is more
accurate on land records is not assumed: the real-scan evaluation below is
what decides it.

Both local models are optional. Without weights on disk, or with
`HANDWRITING_MODELS_ENABLED=false`, the pipeline falls back to the geometry
heuristic in `ocr/handwriting.py`, which only flags handwriting and does not
read it.

## Data

| Source | What | Licence |
|---|---|---|
| IIIT-HW-Dev (CVIT, IIIT Hyderabad) | 95,430 handwritten Hindi word images; CVIT's train / val / test split | none stated; research use with attribution, **clear with CVIT before production** |
| DHCD (UCI #389) | 2,000 handwritten images of each Devanagari digit ०–९ | CC BY 4.0 |
| MNIST | 70,000 handwritten digits 0–9 | as published by LeCun, Cortes and Burges |
| Our generated record pages | printed line crops, the detector's negatives | ours |

IIIT-HW-Dev has almost no numbers. Fewer than 1% of its words contain a
digit, it never uses 0–9, and it has no `/` or `.`. Khasra numbers and areas
are exactly what a land record needs read, so the training script writes
number strings (`142/3`, `0.405`, `१२/०३/२०१९`) from single handwritten digit
glyphs. These are synthetic compositions of real handwritten digits, not
numbers as someone actually wrote them.

```bash
python scripts/download_handwriting_dataset.py        # ~2 GB, into datasets/handwriting/
python scripts/train_handwriting.py --task detector
python scripts/train_handwriting.py --task reader --epochs 15
```

Weights go to `models/checkpoints/handwriting/{detector,reader}/best.pt` and
reports to `datasets/reports/handwriting_{task}.v1.json`.

## Results

Measured on each dataset's own **test split**, run once with the checkpoint
chosen on validation (2026-09-19, Apple M4 Pro). Reports are in
`datasets/reports/handwriting_{reader,detector}.v*.json`.

**Reader** (`handwriting-reader-v1`: CRNN, 4.5M parameters, 15 epochs, best epoch 14)

| Test set | Items | Character error rate | Exact match |
|---|---|---|---|
| IIIT-HW-Dev test words, as scanned | 12,869 | **7.7%** | **69.8%** |
| Lines of 1–4 test words, scan damage added | 2,000 | 8.0% | 50.7% |
| Numbers written from DHCD/MNIST test digits, scan damage added | 2,000 | 0.6% | 97.4% |

Exact match on lines is lower than on words because one wrong character
anywhere fails the whole line. The numbers row is the easiest case: separate,
cleanly cropped digits on one baseline. Real handwritten numbers join and
overlap, so expect worse on real records.

Reading one line takes about 5 ms on the CPU.

**Detector** (`handwriting-detector-v3`): handwritten test lines against
printed lines. The threshold (0.78) is not fixed. Training sets it on
validation so that at most 0.5% of printed lines are flagged, and it is saved
with the weights.

| Printed side | Crops | Handwritten caught | Printed wrongly flagged |
|---|---|---|---|
| Our test pages + fonts seen in training | clean | 99.3% | 0.47% |
| | scan damage added | 97.7% | 1.6% |
| **Font families never trained on** (Martel, Tiro, Sangam) | clean | 99.1% | 0.3% |
| | scan damage added | 97.3% | 3.6% |

**How we got here, and why it matters.** v1 was trained only on scan-damaged
crops, and caught just 62% of clean handwriting. v2 fixed that, but its only
printed examples came from our own generator's single font. On a clean khasra
set in Noto Sans that was uploaded during testing, v2 called **36 of 82**
printed lines handwritten, and the reader turned them into nonsense.

v3 changes the printed training data. It adds the *same* words and numbers
typeset in 21 faces of Devanagari fonts, and puts underlines and table rules
on both classes. On that same page, v3 flags 4 of 82 lines ("5 Rs", "5", "/"
and a green date), and extraction gives **the same fields with and without
the handwriting models**. That page was never used in training; it is kept as
a regression check.

**What these numbers do not say.** Every handwritten sample above comes from
the datasets' own writers and paper, and every printed sample from our own
generated forms. Telling those two sources apart is easier than telling a
Patwari's entry from the printed form it sits on. No figure here is an
accuracy on land records. That is what the next section measures.

## Measuring it on real records

The numbers above are measured on the datasets, not on land records.
`scripts/evaluate_handwriting_real.py` measures real ones. It runs locally,
makes no network calls, and `datasets/handwriting/` is not tracked by git.

**Lines** (the quickest to label): crop each handwritten line from a scan into
`datasets/handwriting/real/lines/`. Then list each file and its exact text in
`labels.tsv`, separated by a tab:

```
line001.png	राम प्रसाद
line002.png	१४२/३
```

**Pages**: put each whole scan in `datasets/handwriting/real/pages/`, with a
`.json` file of the same name holding the values on it:

```json
{"KHASRA": "१४२/३", "OWNER": "राम प्रसाद", "AREA": "0.405"}
```

```bash
python scripts/evaluate_handwriting_real.py --lines datasets/handwriting/real/lines
python scripts/evaluate_handwriting_real.py --pages datasets/handwriting/real/pages
```

Add `--gemini` to the lines run to score Gemini on the same crops. This sends
them to Google. That comparison is what should decide whether Gemini stays a
second opinion or becomes the main reader.

The lines report gives the reader's and PaddleOCR's error rates on the same
crops. The pages report runs the whole pipeline with and without the
handwriting models and counts exact field matches.

Twenty to fifty pages is enough to tell whether the reader helps. It is not
enough to quote an accuracy with confidence, so report the count alongside
any figure.
