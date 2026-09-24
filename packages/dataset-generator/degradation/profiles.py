"""Difficulty tiers and the pipeline that applies them (§48, §49).

Target mix (§49):  20% clean / 35% moderate / 30% hard / 15% extreme.

Every sample records the exact operations and parameters used, so a failure
can be traced to the degradation that caused it rather than guessed at.
"""

from __future__ import annotations

import random

from PIL import Image

from . import engine as ops
from .engine import BBox, DegradationResult

DIFFICULTY_MIX = {"clean": 0.20, "moderate": 0.35, "hard": 0.30, "extreme": 0.15}


def pick_difficulty(rng: random.Random) -> str:
    r = rng.random()
    cumulative = 0.0
    for name, weight in DIFFICULTY_MIX.items():
        cumulative += weight
        if r < cumulative:
            return name
    return "extreme"


#: Parameter ranges per tier. Geometric ranges stay modest even at 'extreme':
#: a 25-degree rotation is not a scanned land record, it is a different problem.
TIERS: dict[str, dict] = {
    "clean": dict(
        rotation=(-0.4, 0.4), blur=(0.0, 0.3), noise=(0.0, 2.0), jpeg=(92, 98),
        fade=(0.0, 0.04), yellow=(0.0, 0.12), illum=(0.0, 0.06),
        stains=(0, 0), folds=(0, 0), perspective=0.0, scale=1.0,
        salt=0.0, edge=0.0, motion=False,
    ),
    "moderate": dict(
        rotation=(-2.2, 2.2), blur=(0.3, 0.9), noise=(2.0, 7.0), jpeg=(72, 90),
        fade=(0.04, 0.16), yellow=(0.12, 0.35), illum=(0.06, 0.20),
        stains=(0, 2), folds=(0, 1), perspective=0.012, scale=0.82,
        salt=0.0006, edge=0.0, motion=False,
    ),
    "hard": dict(
        rotation=(-5.0, 5.0), blur=(0.9, 1.7), noise=(7.0, 14.0), jpeg=(52, 74),
        fade=(0.16, 0.30), yellow=(0.30, 0.55), illum=(0.20, 0.36),
        stains=(1, 4), folds=(1, 2), perspective=0.028, scale=0.62,
        salt=0.002, edge=0.012, motion=False,
    ),
    "extreme": dict(
        rotation=(-9.0, 9.0), blur=(1.7, 2.8), noise=(14.0, 24.0), jpeg=(32, 55),
        fade=(0.30, 0.44), yellow=(0.55, 0.80), illum=(0.36, 0.52),
        stains=(3, 7), folds=(2, 4), perspective=0.05, scale=0.46,
        salt=0.005, edge=0.03, motion=True,
    ),
}


def degrade(
    image: Image.Image,
    boxes: list[BBox],
    difficulty: str,
    rng: random.Random,
) -> DegradationResult:
    """Apply one tier's worth of degradation, carrying annotations along.

    Order matters and mirrors physical reality: the page ages and is marked
    (photometric), then it is photographed or scanned badly (geometric), then
    the capture device adds its own noise and compression.
    """
    tier = TIERS[difficulty]
    applied: list[dict] = []
    img = image
    current = list(boxes)

    # 1. Ageing of the paper itself.
    if tier["yellow"][1] > 0:
        amount = rng.uniform(*tier["yellow"])
        img = ops.yellowing(img, amount)
        applied.append({"op": "yellowing", "amount": round(amount, 3)})

    if tier["fade"][1] > 0:
        amount = rng.uniform(*tier["fade"])
        img = ops.fade_ink(img, amount)
        applied.append({"op": "fade_ink", "amount": round(amount, 3)})

    lo, hi = tier["stains"]
    if hi > 0 and (count := rng.randint(lo, hi)):
        img = ops.stains(img, count, rng)
        applied.append({"op": "stains", "count": count})

    lo, hi = tier["folds"]
    if hi > 0 and (count := rng.randint(lo, hi)):
        img = ops.fold_lines(img, count, rng)
        applied.append({"op": "fold_lines", "count": count})

    if tier["edge"] > 0:
        img = ops.edge_damage(img, tier["edge"], rng)
        applied.append({"op": "edge_damage", "amount": tier["edge"]})

    # 2. Capture geometry -- these MOVE the annotations.
    if tier["perspective"] > 0:
        img, current = ops.perspective(img, current, tier["perspective"], rng)
        applied.append({"op": "perspective", "strength": tier["perspective"]})

    angle = rng.uniform(*tier["rotation"])
    if abs(angle) > 0.01:
        img, current = ops.rotate(img, current, angle)
        applied.append({"op": "rotate", "angle_deg": round(angle, 2)})

    if tier["scale"] < 1.0:
        img, current = ops.rescale(img, current, tier["scale"])
        applied.append({"op": "rescale", "factor": tier["scale"]})

    # 3. Lighting and the capture device.
    if tier["illum"][1] > 0:
        amount = rng.uniform(*tier["illum"])
        img = ops.uneven_illumination(img, amount, rng)
        applied.append({"op": "uneven_illumination", "amount": round(amount, 3)})

    brightness = rng.uniform(0.88, 1.10)
    contrast = rng.uniform(0.80, 1.06)
    img = ops.adjust(img, brightness, contrast)
    applied.append({"op": "adjust", "brightness": round(brightness, 3),
                    "contrast": round(contrast, 3)})

    if tier["motion"] and rng.random() < 0.4:
        img = ops.motion_blur(img, 9, rng.uniform(-25, 25))
        applied.append({"op": "motion_blur", "length": 9})

    radius = rng.uniform(*tier["blur"])
    if radius > 0.02:
        img = ops.gaussian_blur(img, radius)
        applied.append({"op": "gaussian_blur", "radius": round(radius, 2)})

    sigma = rng.uniform(*tier["noise"])
    if sigma > 0.1:
        img = ops.gaussian_noise(img, sigma, rng)
        applied.append({"op": "gaussian_noise", "sigma": round(sigma, 2)})

    if tier["salt"] > 0:
        img = ops.salt_pepper(img, tier["salt"], rng)
        applied.append({"op": "salt_pepper", "amount": tier["salt"]})

    quality = rng.randint(*tier["jpeg"])
    img = ops.jpeg_compress(img, quality)
    applied.append({"op": "jpeg_compress", "quality": quality})

    # Clamp boxes into the final frame; geometric ops can push edges outside.
    w, h = img.size
    clamped = [
        (max(0, min(x1, w - 1)), max(0, min(y1, h - 1)),
         max(0, min(x2, w - 1)), max(0, min(y2, h - 1)))
        for (x1, y1, x2, y2) in current
    ]

    return DegradationResult(image=img, boxes=clamped, applied=applied,
                             difficulty=difficulty)
