#!/usr/bin/env python
"""Train the handwriting detector and reader (§6 handwriting).

    python scripts/download_handwriting_dataset.py        # once, ~1.9 GB
    python scripts/train_handwriting.py --task reader     # CRNN + CTC
    python scripts/train_handwriting.py --task detector   # handwritten vs printed

Data
  Handwritten: IIIT-HW-Dev, with CVIT's own train / validation / test split.
    The test split is touched once, at the end, for the reported numbers.
  Printed (detector only): the OCR line boxes of our generated record pages,
    split by the same parcel-grouped datasets/splits/*.v1.jsonl as every other
    model here, so no page is on both sides.

What the numbers mean
  Reader CER / word accuracy are on IIIT-HW-Dev test WORDS: handwritten Hindi
  by the dataset's writers, not land records. They say the reader learned
  handwritten Devanagari; they do not say how it does on a Patwari's register.
  scripts/evaluate_handwriting_real.py answers that, on real scans.

Lines, not just words
  PaddleOCR hands the pipeline LINE crops. The reader is trained on single
  words and on 2-4 words joined with a gap, so a line of handwriting is in
  distribution. Crops get the degradations a scan adds (blur, stroke weight,
  noise, paper tone, loose margins) so neither model learns "clean = IIIT".
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import unicodedata
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from ocr.handwriting_model import (  # noqa: E402
    CHECKPOINTS,
    DETECTOR_WIDTH,
    HEIGHT,
    build_detector,
    build_reader,
    ctc_decode,
    to_input,
)

DATA = REPO_ROOT / "datasets" / "handwriting" / "iiit-hw-dev" / "data"
CACHE = REPO_ROOT / "datasets" / "handwriting" / "cache"
REPORTS = REPO_ROOT / "datasets" / "reports"
SPLIT_FILES = {"train": "train", "val": "validation", "test": "test"}
MAX_LINE_WIDTH = 1024
#: Batches drawn together and sorted by width (see train_reader).
BUCKET = 20
#: Share of printed validation lines the detector may flag. A printed line
#: sent to the handwriting reader loses PaddleOCR's better reading of it.
TARGET_FPR = 0.005


# --------------------------------------------------------------------------- data

def _prepared(split: str) -> tuple[list[np.ndarray], list[str]]:
    """Word images at HEIGHT px (uint8, ink dark) and NFC labels, cached."""
    cache = CACHE / f"{split}.npz"
    if not cache.exists():
        import pyarrow.parquet as pq

        images, labels = [], []
        for path in sorted(DATA.glob(f"{SPLIT_FILES[split]}-*.parquet")):
            table = pq.read_table(path, columns=["image", "text"]).to_pylist()
            for row in table:
                gray = cv2.imdecode(np.frombuffer(row["image"]["bytes"], np.uint8),
                                    cv2.IMREAD_GRAYSCALE)
                if gray is None or not row["text"]:
                    continue
                h, w = gray.shape
                width = int(np.clip(round(w * HEIGHT / h), 8, 800))
                images.append(cv2.resize(gray, (width, HEIGHT), interpolation=cv2.INTER_AREA))
                labels.append(unicodedata.normalize("NFC", row["text"].strip()))
        if not images:
            raise SystemExit(f"no {split} data under {DATA}; run download_handwriting_dataset.py")
        CACHE.mkdir(parents=True, exist_ok=True)
        widths = np.array([im.shape[1] for im in images])
        np.savez(cache, pixels=np.concatenate([im.ravel() for im in images]),
                 widths=widths, labels=np.array(labels))
    data = np.load(cache)
    # Read each member once: every data[...] access re-reads it from disk.
    pixels, widths = data["pixels"], data["widths"]
    offsets = np.concatenate([[0], np.cumsum(widths * HEIGHT)])
    images = [pixels[offsets[i]:offsets[i + 1]].reshape(HEIGHT, w)
              for i, w in enumerate(widths)]
    return images, [str(s) for s in data["labels"]]


def _printed_crops(split: str, limit: int, seed: int) -> list[np.ndarray]:
    """Printed line crops from generated record pages in `split`."""
    rng = random.Random(seed)
    crops = []
    for line in (REPO_ROOT / "datasets" / "splits" / f"{split}.v1.jsonl").read_text().splitlines():
        record = json.loads(line)
        page = cv2.imread(str(REPO_ROOT / "datasets" / record["degraded_image"]),
                          cv2.IMREAD_GRAYSCALE)
        annotation = json.loads((REPO_ROOT / "datasets" / record["annotation"]).read_text())
        for block in annotation["ocr"]:
            x1, y1, x2, y2 = block["bbox"]
            if x2 - x1 >= 8 and y2 - y1 >= 8:
                crops.append(page[max(0, y1):y2, max(0, x1):x2])
    rng.shuffle(crops)
    return crops[:limit]


FONTS = REPO_ROOT / "datasets" / "handwriting" / "fonts"
SYSTEM_FONTS = Path("/System/Library/Fonts")
#: (file, face indices, split). Whole families are held out, so the test
#: split measures print in a typeface the detector has never seen.
DEVANAGARI_FONTS = [
    (FONTS / "NotoSansDevanagari[wdth,wght].ttf", [0], "train"),
    (FONTS / "NotoSerifDevanagari[wdth,wght].ttf", [0], "train"),
    (FONTS / "Hind-Regular.ttf", [0], "train"), (FONTS / "Hind-Bold.ttf", [0], "train"),
    (FONTS / "Mukta-Regular.ttf", [0], "train"), (FONTS / "Mukta-Bold.ttf", [0], "train"),
    (FONTS / "Poppins-Regular.ttf", [0], "train"),
    (SYSTEM_FONTS / "Supplemental" / "DevanagariMT.ttc", [0, 1], "train"),
    (SYSTEM_FONTS / "Supplemental" / "ITFDevanagari.ttc", [0, 1, 2, 3, 4], "train"),
    (SYSTEM_FONTS / "Kohinoor.ttc", [0, 1, 2, 3, 4], "train"),
    (SYSTEM_FONTS / "Supplemental" / "Shree714.ttc", [0, 1], "train"),
    (FONTS / "Yantramanav-Regular.ttf", [0], "val"),
    (FONTS / "Martel-Regular.ttf", [0], "test"),
    (FONTS / "TiroDevanagariHindi-Regular.ttf", [0], "test"),
    (SYSTEM_FONTS / "Supplemental" / "Devanagari Sangam MN.ttc", [0, 1], "test"),
]


def _fonts(split: str) -> list[tuple[str, int]]:
    return [(str(path), face) for path, faces, font_split in DEVANAGARI_FONTS
            if font_split == split and path.exists() for face in faces]


def _render_printed(text: str, font: tuple[str, int], rng: random.Random) -> np.ndarray:
    """`text` typeset in `font`, dark on paper, cropped like an OCR box."""
    from PIL import Image, ImageDraw, ImageFont

    face = ImageFont.truetype(font[0], rng.randint(22, 46), index=font[1],
                              layout_engine=ImageFont.Layout.RAQM)
    try:                                   # variable fonts: vary the weight too
        face.set_variation_by_axes([rng.choice([400, 500, 700])] +
                                   [100] * (len(face.get_variation_axes()) - 1))
    except Exception:
        pass
    left, top, right, bottom = face.getbbox(text)
    margin = rng.randint(2, 10)
    image = Image.new("L", (right - left + 2 * margin, bottom - top + 2 * margin),
                      rng.randint(200, 255))
    ImageDraw.Draw(image).text((margin - left, margin - top), text, font=face,
                               fill=rng.randint(0, 90))
    return np.array(image)


def _decorate(gray: np.ndarray, rng: random.Random) -> np.ndarray:
    """Underlines and ruled lines, which record forms put under printed and
    handwritten entries alike -- applied to both, so they are not a cue."""
    image = gray.copy()
    h, w = image.shape
    tone = rng.randint(60, 170)
    if rng.random() < 0.35:                                   # an underline
        y = min(h - 1, int(h * rng.uniform(0.8, 0.98)))
        cv2.line(image, (rng.randint(0, w // 8), y), (w - 1 - rng.randint(0, w // 8), y),
                 tone, rng.randint(1, 2))
    if rng.random() < 0.2:                                    # a table rule
        y = rng.choice([rng.randint(0, 2), h - 1 - rng.randint(0, 2)])
        cv2.line(image, (0, y), (w - 1, y), tone, 1)
    return image


DEVANAGARI_DIGITS = "०१२३४५६७८९"
NUMBER_CHARS = "0123456789" + DEVANAGARI_DIGITS + "/.-"


def _digit_glyphs(split: str) -> dict[str, list[np.ndarray]]:
    """Single handwritten digits, ink dark on white: DHCD -> ०-९, MNIST -> 0-9.

    Each source's own test set is our test; its training set is cut 90/10 into
    train and val, so no glyph is on both sides.
    """
    import gzip

    digits_dir = REPO_ROOT / "datasets" / "handwriting" / "digits"
    glyphs: dict[str, list[np.ndarray]] = {}
    folder = "Test" if split == "test" else "Train"
    for d in range(10):
        paths = sorted((digits_dir / "dhcd").glob(f"*/{folder}/digit_{d}/*.png"))
        if split != "test":
            cut = int(len(paths) * 0.9)
            paths = paths[:cut] if split == "train" else paths[cut:]
        glyphs[DEVANAGARI_DIGITS[d]] = [255 - cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
                                        for p in paths]
    prefix = "t10k" if split == "test" else "train"
    with gzip.open(digits_dir / "mnist" / f"{prefix}-images-idx3-ubyte.gz") as f:
        images = np.frombuffer(f.read(), np.uint8, offset=16).reshape(-1, 28, 28)
    with gzip.open(digits_dir / "mnist" / f"{prefix}-labels-idx1-ubyte.gz") as f:
        labels = np.frombuffer(f.read(), np.uint8, offset=8)
    if split != "test":
        cut = int(len(images) * 0.9)
        images, labels = (images[:cut], labels[:cut]) if split == "train" else \
            (images[cut:], labels[cut:])
    for d in range(10):
        glyphs[str(d)] = list(255 - images[labels == d])
    return glyphs


def _number_text(rng: random.Random) -> str:
    """A value as land records write it: khasra, sub-division, area, date."""
    digits = DEVANAGARI_DIGITS if rng.random() < 0.5 else "0123456789"

    def run(low, high):
        return "".join(rng.choice(digits) for _ in range(rng.randint(low, high)))

    kind = rng.random()
    if kind < 0.35:
        return run(1, 4)                                   # khasra 142
    if kind < 0.6:
        return f"{run(1, 4)}/{run(1, 2)}"                  # 142/3
    if kind < 0.85:
        return f"{run(1, 2)}.{run(2, 4)}"                  # 0.405
    return f"{run(1, 2)}/{run(1, 2)}/{run(4, 4)}" if rng.random() < 0.5 else \
        f"{run(1, 2)}-{run(1, 2)}-{run(4, 4)}"             # a date


def _render_number(text: str, glyphs, rng: random.Random) -> np.ndarray:
    """Write `text` from separate handwritten glyphs on one baseline."""
    size = rng.randint(34, 50)
    thickness = rng.randint(2, 4)
    parts = []
    for char in text:
        if char in glyphs:
            glyph = rng.choice(glyphs[char])
            ys, xs = np.where(glyph < 128)
            if len(xs):
                glyph = glyph[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            h = int(size * rng.uniform(0.85, 1.1))
            w = max(4, int(glyph.shape[1] * h / glyph.shape[0]))
            glyph = cv2.resize(glyph, (w, h), interpolation=cv2.INTER_AREA)
        else:                                               # / . - drawn by hand
            w = {"/": size // 2, ".": size // 4, "-": size // 2}[char]
            glyph = np.full((size, w), 255, np.uint8)
            if char == "/":
                cv2.line(glyph, (w - 2, rng.randint(0, 4)), (1, size - rng.randint(1, 5)),
                         0, thickness)
            elif char == ".":
                cv2.circle(glyph, (w // 2, size - 5), max(2, thickness), 0, -1)
            else:
                y = size // 2 + rng.randint(-3, 3)
                cv2.line(glyph, (1, y), (w - 2, y + rng.randint(-2, 2)), 0, thickness)
        cell = np.full((HEIGHT, glyph.shape[1]), 255, np.uint8)
        top = int(np.clip((HEIGHT - glyph.shape[0]) // 2 + rng.randint(-4, 4),
                          0, HEIGHT - glyph.shape[0]))
        cell[top:top + glyph.shape[0]] = glyph
        parts += [cell, np.full((HEIGHT, rng.randint(1, 8)), 255, np.uint8)]
    return np.hstack(parts)


def _number(glyphs, rng) -> tuple[np.ndarray, str]:
    text = _number_text(rng)
    return _render_number(text, glyphs, rng), text


def _compose(images, labels, rng, index, glyphs=None) -> tuple[np.ndarray, str]:
    """A line as OCR would crop it: a word, 2-4 words, a handwritten number
    (with `glyphs`), or words followed by a number ("खसरा १४२")."""
    if glyphs is not None and rng.random() < 0.25:
        return _number(glyphs, rng)
    picks = [index] + ([rng.randrange(len(images)) for _ in range(rng.randint(1, 3))]
                       if rng.random() < 0.5 else [])
    parts, words = [], []
    for i in picks:
        if parts:
            parts.append(np.full((HEIGHT, rng.randint(12, 40)), 255, np.uint8))
        parts.append(images[i])
        words.append(labels[i])
    if glyphs is not None and rng.random() < 0.15:
        number, text = _number(glyphs, rng)
        parts += [np.full((HEIGHT, rng.randint(12, 40)), 255, np.uint8), number]
        words.append(text)
    line = np.hstack(parts)
    if line.shape[1] > MAX_LINE_WIDTH:
        return images[index], labels[index]
    return line, " ".join(words)


def degrade(gray: np.ndarray, rng: random.Random) -> np.ndarray:
    """Scan-like damage, applied alike to handwritten and printed crops."""
    image = gray.copy()
    pad = [rng.randint(0, int(HEIGHT * 0.25)) for _ in range(4)]
    image = cv2.copyMakeBorder(image, pad[0], pad[1], pad[2], pad[3],
                               cv2.BORDER_CONSTANT, value=255)
    if rng.random() < 0.5:
        h, w = image.shape
        angle = rng.uniform(-2.5, 2.5)
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        matrix[0, 1] += rng.uniform(-0.25, 0.25)       # slant
        image = cv2.warpAffine(image, matrix, (w, h), borderValue=255)
    if rng.random() < 0.3:
        kernel = np.ones((2, 2), np.uint8)
        image = (cv2.erode if rng.random() < 0.5 else cv2.dilate)(image, kernel)
    if rng.random() < 0.4:
        image = cv2.GaussianBlur(image, (0, 0), rng.uniform(0.4, 1.3))
    paper = rng.uniform(170, 255)
    ink = rng.uniform(0, 90)
    image = (ink + (image.astype(np.float32) / 255.0) * (paper - ink))
    if rng.random() < 0.5:
        image += np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(2, 14),
                                                                     image.shape)
    image = np.clip(image, 0, 255).astype(np.uint8)
    if rng.random() < 0.3:
        _, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(30, 80)])
        image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    return image


def _device(torch):
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _pad_batch(torch, arrays):
    width = max(a.shape[1] for a in arrays)
    batch = np.zeros((len(arrays), 1, HEIGHT, width), np.float32)
    for i, a in enumerate(arrays):
        batch[i, 0, :, :a.shape[1]] = a
    return torch.from_numpy(batch)


# ------------------------------------------------------------------------- reader

def _edit_distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def score(pairs) -> dict:
    """CER over characters and exact-match accuracy over items."""
    errors = sum(_edit_distance(p, t) for p, t in pairs)
    chars = sum(len(t) for _, t in pairs)
    return {"items": len(pairs), "cer": round(errors / max(chars, 1), 4),
            "exact_match": round(sum(p == t for p, t in pairs) / max(len(pairs), 1), 4)}


def _read_all(torch, model, device, charset, crops, batch_size=64):
    predictions = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(crops), batch_size):
            arrays = [to_input(c) for c in crops[start:start + batch_size]]
            log_probs = model(_pad_batch(torch, arrays).to(device)).float().cpu().numpy()
            for i, a in enumerate(arrays):
                steps = max(1, a.shape[1] // 4)
                predictions.append(ctc_decode(log_probs[:steps, i], charset)[0])
    return predictions


def train_reader(args) -> dict:
    import torch

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    train_images, train_labels = _prepared("train")
    val_images, val_labels = _prepared("val")
    glyphs = _digit_glyphs("train")
    charset = "".join(sorted({c for label in train_labels for c in label}
                             | set(NUMBER_CHARS) | {" "}))
    index = {c: i + 1 for i, c in enumerate(charset)}
    device = _device(torch)
    model = build_reader(len(charset) + 1).to(device)
    steps_per_epoch = min(len(train_images) // args.batch_size, args.max_steps or 1 << 30)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=args.lr, total_steps=args.epochs * steps_per_epoch, pct_start=0.1)
    ctc = torch.nn.CTCLoss(blank=0, zero_infinity=True)

    val_pick = random.Random(0).sample(range(len(val_images)), min(3000, len(val_images)))
    val_crops = [val_images[i] for i in val_pick]
    val_truth = [val_labels[i] for i in val_pick]
    val_glyphs, number_rng = _digit_glyphs("val"), random.Random(0)
    val_numbers = [_number(val_glyphs, number_rng) for _ in range(1000)]
    out = CHECKPOINTS / "reader"
    out.mkdir(parents=True, exist_ok=True)
    best, history = None, []

    for epoch in range(1, args.epochs + 1):
        model.train()
        order = list(range(len(train_images)))
        rng.shuffle(order)
        started, total = time.time(), 0.0
        batches = []
        for step in range(steps_per_epoch):
            if not batches:
                # Batches of similar width: padding a 200 px word to the widest
                # line in its batch was half of every step's compute.
                pool = [_compose(train_images, train_labels, rng, i, glyphs)
                        for i in order[step * args.batch_size:
                                       (step + BUCKET) * args.batch_size]]
                pool = [(to_input(degrade(image, rng)), text) for image, text in pool]
                pool.sort(key=lambda sample: sample[0].shape[1])
                batches = [pool[i:i + args.batch_size]
                           for i in range(0, len(pool), args.batch_size)]
                rng.shuffle(batches)
            batch = batches.pop()
            arrays = [array for array, _ in batch]
            targets = [torch.tensor([index[c] for c in text if c in index]) for _, text in batch]
            log_probs = model(_pad_batch(torch, arrays).to(device))
            input_lengths = torch.tensor([max(1, a.shape[1] // 4) for a in arrays])
            loss = ctc(log_probs.float().cpu(), torch.cat(targets), input_lengths,
                       torch.tensor([len(t) for t in targets]))
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            schedule.step()
            total += float(loss)
        metrics = score(list(zip(_read_all(torch, model, device, charset, val_crops),
                                 val_truth, strict=True)))
        numbers = score(list(zip(
            _read_all(torch, model, device, charset, [im for im, _ in val_numbers]),
            [t for _, t in val_numbers], strict=True)))
        metrics["numbers"] = numbers
        history.append({"epoch": epoch, "loss": round(total / steps_per_epoch, 4), **metrics})
        print(f"epoch {epoch}: loss {total / steps_per_epoch:.3f}  val CER {metrics['cer']:.4f}"
              f"  word acc {metrics['exact_match']:.4f}  numbers CER {numbers['cer']:.4f}"
              f" exact {numbers['exact_match']:.4f}  ({time.time() - started:.0f}s)", flush=True)
        # Words and numbers weigh equally: a reader that learns names and
        # misreads every khasra number is no use on a land record.
        metrics["selection_cer"] = round((metrics["cer"] + numbers["cer"]) / 2, 4)
        if best is None or metrics["selection_cer"] < best["selection_cer"]:
            best = {"epoch": epoch, **metrics}
            torch.save({"model": model.state_dict(), "charset": charset,
                        "version": f"handwriting-reader-{args.name}", "val": best},
                       out / "best.pt")

    # The test split, once, with the best checkpoint.
    state = torch.load(out / "best.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"])
    test_images, test_labels = _prepared("test")
    words = score(list(zip(_read_all(torch, model, device, charset, test_images),
                           test_labels, strict=True)))
    line_rng = random.Random(1)
    test_glyphs = _digit_glyphs("test")
    lines = [_compose(test_images, test_labels, line_rng, i)
             for i in line_rng.sample(range(len(test_images)), 2000)]
    numbers = [_number(test_glyphs, line_rng) for _ in range(2000)]
    number_scores = score(list(zip(
        _read_all(torch, model, device, charset, [degrade(im, line_rng) for im, _ in numbers]),
        [t for _, t in numbers], strict=True)))
    line_scores = score(list(zip(
        _read_all(torch, model, device, charset, [degrade(im, line_rng) for im, _ in lines]),
        [t for _, t in lines], strict=True)))
    return {"task": "reader", "name": args.name, "charset_size": len(charset),
            "best_val": best, "test_words_clean": words,
            "test_lines_degraded": line_scores,
            "test_numbers_degraded": number_scores, "history": history}


# ----------------------------------------------------------------------- detector

def _detector_set(split, rng, per_class):
    images, labels = _prepared(split)
    glyphs = _digit_glyphs(split)
    handwritten = [_compose(images, labels, rng, rng.randrange(len(images)), glyphs)[0]
                   for _ in range(per_class)]
    # Printed: half our generator's pages, half the SAME words and numbers
    # typeset in this split's fonts -- so style, not content, separates them.
    printed = _printed_crops(split, per_class // 2, rng.randrange(1 << 30))
    printed += _typeset(split, labels, per_class - len(printed), rng)
    return handwritten, printed


def _typeset(split, labels, count, rng) -> list[np.ndarray]:
    fonts = _fonts(split)
    crops = []
    for _ in range(count):
        text = (_number_text(rng) if rng.random() < 0.25 else
                " ".join(rng.choice(labels) for _ in range(rng.randint(1, 3))))
        crops.append(_render_printed(text, rng.choice(fonts), rng))
    return crops


def _loose(gray, rng):
    """A clean crop with the loose margins an OCR box has, nothing else."""
    pad = [rng.randint(0, int(HEIGHT * 0.25)) for _ in range(4)]
    return cv2.copyMakeBorder(gray, *pad, cv2.BORDER_CONSTANT, value=int(np.median(gray)))


def _detector_batch(torch, crops, rng, degraded: float):
    """`degraded` = share of crops given scan damage. Training uses 0.5: with
    every crop damaged (v1) the detector learned "damaged" as a cue for
    handwriting and caught only 62% of clean handwritten words."""
    crops = [_decorate(c, rng) for c in crops]
    arrays = [to_input(degrade(c, rng) if rng.random() < degraded else _loose(c, rng),
                       width=DETECTOR_WIDTH) for c in crops]
    return torch.from_numpy(np.stack(arrays)[:, None])


def train_detector(args) -> dict:
    import torch

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    device = _device(torch)
    hand, printed = _detector_set("train", rng, 12000)
    samples = [(c, 1.0) for c in hand] + [(c, 0.0) for c in printed]
    val_hand, val_printed = _detector_set("val", random.Random(0), 2000)
    model = build_detector().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    out = CHECKPOINTS / "detector"
    out.mkdir(parents=True, exist_ok=True)

    views = {"clean": 0.0, "degraded": 1.0}

    def probabilities(hand_crops, printed_crops, seed, degraded):
        eval_rng = random.Random(seed)
        model.eval()
        probs = []
        with torch.no_grad():
            for crops in (hand_crops, printed_crops):
                p = []
                for s in range(0, len(crops), 256):
                    x = _detector_batch(torch, crops[s:s + 256], eval_rng,
                                        degraded).to(device)
                    p.extend(torch.sigmoid(model(x)).float().cpu().numpy()[:, 0].tolist())
                probs.append(np.array(p))
        return probs

    def at(threshold, hand_probs, printed_probs):
        tp = int((hand_probs >= threshold).sum())
        fp = int((printed_probs >= threshold).sum())
        return {"threshold": round(threshold, 4), "handwritten": len(hand_probs),
                "printed": len(printed_probs),
                "recall": round(tp / max(len(hand_probs), 1), 4),
                "precision": round(tp / max(tp + fp, 1), 4),
                "false_positive_rate": round(fp / max(len(printed_probs), 1), 4)}

    def evaluate(hand_crops, printed_crops, seed, threshold=None):
        """Scored on clean and scan-damaged crops, because a detector can pass
        one and fail the other. Without `threshold`, it is calibrated here:
        the lowest that flags at most TARGET_FPR of these printed lines (both
        views pooled), and never below 0.5."""
        probs = {name: probabilities(hand_crops, printed_crops, seed, degraded)
                 for name, degraded in views.items()}
        if threshold is None:
            printed = np.concatenate([p[1] for p in probs.values()])
            threshold = max(0.5, float(np.quantile(printed, 1 - TARGET_FPR)) + 1e-6)
        return {name: at(threshold, *p) for name, p in probs.items()}

    best, history = None, []
    for epoch in range(1, args.epochs + 1):
        model.train()
        rng.shuffle(samples)
        for s in range(0, len(samples), args.batch_size):
            chunk = samples[s:s + args.batch_size]
            x = _detector_batch(torch, [c for c, _ in chunk], rng, 0.5).to(device)
            y = torch.tensor([[label] for _, label in chunk], device=device)
            loss = loss_fn(model(x), y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        metrics = evaluate(val_hand, val_printed, 0)
        history.append({"epoch": epoch, **metrics})
        print(f"epoch {epoch}: {metrics}", flush=True)
        # Every epoch is held to the same false-positive budget by its own
        # threshold; the best is the one that then catches the most handwriting.
        recall = min(m["recall"] for m in metrics.values())
        if best is None or recall > best[0]:
            best = (recall, {"epoch": epoch, **metrics})
            torch.save({"model": model.state_dict(),
                        "threshold": metrics["clean"]["threshold"],
                        "version": f"handwriting-detector-{args.name}", "val": best[1]},
                       out / "best.pt")

    state = torch.load(out / "best.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"])
    test_rng = random.Random(2)
    test_hand, test_printed = _detector_set("test", test_rng, 3000)
    unseen = _typeset("test", _prepared("test")[1], 2000, test_rng)
    return {"task": "detector", "name": args.name, "best_val": best[1],
            "test": evaluate(test_hand, test_printed, 1, state["threshold"]),
            # Print in font families that were in no training batch.
            "test_unseen_fonts": evaluate(test_hand[:2000], unseen, 3, state["threshold"]),
            "history": history}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", choices=["reader", "detector"], required=True)
    parser.add_argument("--name", default="v1")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--max-steps", type=int, default=None,
                        help="cap steps per epoch (smoke runs)")
    args = parser.parse_args()
    reader = args.task == "reader"
    args.epochs = args.epochs or (25 if reader else 6)
    args.batch_size = args.batch_size or (48 if reader else 64)
    args.lr = args.lr or (1e-3 if reader else 1e-3)

    report = (train_reader if reader else train_detector)(args)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"handwriting_{args.task}.{args.name}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    summary = {k: v for k, v in report.items() if k != "history"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report: {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
