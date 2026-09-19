#!/usr/bin/env python
"""Fetch the handwriting training data (§6 handwriting). Not tracked by git.

    python scripts/download_handwriting_dataset.py

1. IIIT-HW-Dev -- 95,430 handwritten Hindi word images with CVIT's own
   train / validation / test split (69,900 / 12,700 / 12,900), from the
   Parquet copy on Hugging Face. About 1.9 GB.
   Dutta, Krishnan, Mathew, Jawahar, "Offline Handwriting Recognition on
   Devanagari using a new Benchmark Dataset", DAS 2018, CVIT, IIIT Hyderabad.
   Neither CVIT's page nor the Hugging Face copy states a licence: treat it
   as research use with attribution, and clear it with CVIT before production.

2. Handwritten DIGITS, which IIIT-HW-Dev almost lacks (under 1% of its words
   contain one, and never 0-9, '/' or '.') while khasra numbers and areas are
   exactly what a land record needs read. train_handwriting.py writes number
   strings like "142/3" and "0.405" from single-digit glyphs:
     * DHCD, the Devanagari Handwritten Character Dataset (UCI #389, CC BY 4.0):
       2,000 handwritten images of each Devanagari digit.
     * MNIST (LeCun, Cortes, Burges): 70,000 handwritten 0-9, from the PyTorch
       project's mirror.
"""

from __future__ import annotations

import os
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT = REPO_ROOT / "datasets" / "handwriting"
REPO_ID = "c3rl/IIIT-INDIC-HW-WORDS-Hindi"
TARGET = ROOT / "iiit-hw-dev"
DIGITS = ROOT / "digits"
DHCD_URL = ("https://archive.ics.uci.edu/static/public/389/"
            "devanagari+handwritten+character+dataset.zip")
MNIST_URL = "https://ossci-datasets.s3.amazonaws.com/mnist/"
MNIST_FILES = ["train-images-idx3-ubyte.gz", "train-labels-idx1-ubyte.gz",
               "t10k-images-idx3-ubyte.gz", "t10k-labels-idx1-ubyte.gz"]


def _fetch(url: str, path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, path)
    print(f"{path.relative_to(REPO_ROOT)}  {path.stat().st_size / 1e6:.0f} MB")


def main() -> None:
    # The Xet transfer backend stalled at 0 bytes here; plain HTTPS does not.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import snapshot_download

    snapshot_download(REPO_ID, repo_type="dataset", local_dir=TARGET,
                      allow_patterns=["data/*.parquet", "README.md"])
    for path in sorted((TARGET / "data").glob("*.parquet")):
        print(f"{path.relative_to(REPO_ROOT)}  {path.stat().st_size / 1e6:.0f} MB")

    _fetch(DHCD_URL, DIGITS / "dhcd.zip")
    with zipfile.ZipFile(DIGITS / "dhcd.zip") as archive:
        archive.extractall(DIGITS / "dhcd",
                           [n for n in archive.namelist() if "/digit_" in n])
    for name in MNIST_FILES:
        _fetch(MNIST_URL + name, DIGITS / "mnist" / name)


if __name__ == "__main__":
    main()
