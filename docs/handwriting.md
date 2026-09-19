# Handwriting: detection and reading

Old land records are often handwritten, or printed forms with handwritten
entries. PaddleOCR is trained on print and mostly misreads handwriting, so
the pipeline has two trained models of its own for it.

```
PaddleOCR line boxes
   │
   ├─ detector: handwritten or printed? ──── printed ──► PaddleOCR's text stands
   │   (a small CNN; threshold 0.8)
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

**Detector** (`handwriting-detector-v2`, threshold 0.8): handwritten test
lines against printed lines from our test-split record pages.

| Crops | Handwritten caught | Printed wrongly flagged |
|---|---|---|
| Clean | 99.2% (of 3,000) | 0 of 2,513 |
| Scan damage added | 97.8% | 1 of 2,513 |

On the pipeline's real input, PaddleOCR's own line boxes on our 150
validation and test pages, all of them printed, the detector wrongly flagged
9 of 3,964 lines (0.23%) on 7 pages. The heuristic it replaces flagged 52
(1.31%). The misses were almost all one-character boxes (`2`, `=`, `\`),
which look the same printed or written.

The first detector (v1) was trained only on damaged crops. It caught just 62%
of clean handwritten words, because it had learned "looks damaged" as a sign
of handwriting. v2 trains on clean and damaged crops half and half, and is
scored on both.

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
