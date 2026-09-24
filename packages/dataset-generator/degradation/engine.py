"""Controlled degradation of clean renders (§48, §49).

The engine splits transforms into two kinds, and the distinction is the whole
point of the module:

  PHOTOMETRIC -- blur, noise, fading, stains, compression. Pixels change,
                 geometry does not, so annotations are untouched.

  GEOMETRIC   -- rotation, perspective, rescaling. These MOVE the content, so
                 every bounding box must be carried through the same transform.
                 A geometric degradation that forgets its annotations produces
                 a dataset that silently lies about where its labels are.

Every applied operation and its parameters are recorded on the result, so any
sample can be traced back to exactly how it was produced (§49).
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

BBox = tuple[int, int, int, int]


@dataclass
class DegradationResult:
    image: Image.Image
    #: Bounding boxes in the SAME order they were supplied, transformed.
    boxes: list[BBox]
    applied: list[dict] = field(default_factory=list)
    difficulty: str = "clean"


# ── geometric helpers ───────────────────────────────────────────────────────

def _corners(box: BBox) -> list[tuple[float, float]]:
    x1, y1, x2, y2 = box
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def _bounds(points: list[tuple[float, float]]) -> BBox:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (int(round(min(xs))), int(round(min(ys))),
            int(round(max(xs))), int(round(max(ys))))


def rotate(image: Image.Image, boxes: list[BBox], angle: float,
           fill: str = "#FFFEF8") -> tuple[Image.Image, list[BBox]]:
    """Rotate the page and carry the annotations with it.

    PIL rotates counter-clockwise about the centre and, with expand=True,
    grows the canvas. The same affine map is applied to every box corner and
    the axis-aligned hull is taken, so a rotated box stays a valid (slightly
    looser) rectangle.
    """
    w, h = image.size
    rotated = image.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=fill)
    nw, nh = rotated.size

    theta = math.radians(angle)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cx, cy = w / 2.0, h / 2.0
    ncx, ncy = nw / 2.0, nh / 2.0

    def map_point(x: float, y: float) -> tuple[float, float]:
        dx, dy = x - cx, y - cy
        return (cos_t * dx + sin_t * dy + ncx, -sin_t * dx + cos_t * dy + ncy)

    moved = [_bounds([map_point(*p) for p in _corners(b)]) for b in boxes]
    return rotated, moved


def perspective(image: Image.Image, boxes: list[BBox], strength: float,
                rng: random.Random, fill: str = "#FFFEF8"
                ) -> tuple[Image.Image, list[BBox]]:
    """Simulate a page photographed at an angle.

    PIL's PERSPECTIVE transform maps OUTPUT coords back to INPUT coords, so the
    coefficients it needs are the inverse of the visual warp. Boxes therefore
    have to be pushed through the FORWARD map, which we solve for separately --
    using the same coefficients for both is a classic way to get annotations
    that drift further off as you move from the centre.
    """
    w, h = image.size
    m = strength * min(w, h)

    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [
        (rng.uniform(0, m), rng.uniform(0, m)),
        (w - rng.uniform(0, m), rng.uniform(0, m)),
        (w - rng.uniform(0, m), h - rng.uniform(0, m)),
        (rng.uniform(0, m), h - rng.uniform(0, m)),
    ]

    forward = _solve_perspective(src, dst)   # src -> dst, for the boxes
    inverse = _solve_perspective(dst, src)   # dst -> src, for PIL

    warped = image.transform(
        (w, h), Image.PERSPECTIVE, inverse, resample=Image.BICUBIC, fillcolor=fill
    )

    def apply(coeffs, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f, g, hh = coeffs
        denom = g * x + hh * y + 1.0
        return ((a * x + b * y + c) / denom, (d * x + e * y + f) / denom)

    moved = [_bounds([apply(forward, *p) for p in _corners(bx)]) for bx in boxes]
    return warped, moved


def _solve_perspective(src, dst) -> list[float]:
    """Coefficients mapping src -> dst for a projective transform."""
    matrix = []
    for (sx, sy), (dx, dy) in zip(src, dst, strict=True):
        matrix.append([sx, sy, 1, 0, 0, 0, -dx * sx, -dx * sy])
        matrix.append([0, 0, 0, sx, sy, 1, -dy * sx, -dy * sy])
    A = np.array(matrix, dtype=np.float64)
    B = np.array([c for point in dst for c in point], dtype=np.float64)
    return np.linalg.solve(A, B).tolist()


def rescale(image: Image.Image, boxes: list[BBox], factor: float
            ) -> tuple[Image.Image, list[BBox]]:
    """Reduce effective DPI, then restore size -- detail is genuinely lost."""
    w, h = image.size
    small = image.resize((max(1, int(w * factor)), max(1, int(h * factor))), Image.BILINEAR)
    back = small.resize((w, h), Image.BICUBIC)
    return back, list(boxes)  # net geometry unchanged


# ── photometric operations ──────────────────────────────────────────────────

def gaussian_blur(image, radius): return image.filter(ImageFilter.GaussianBlur(radius))


def motion_blur(image: Image.Image, length: int, angle: float) -> Image.Image:
    kernel = np.zeros((length, length), dtype=np.float32)
    cx = length // 2
    rad = math.radians(angle)
    for i in range(length):
        offset = int(round((i - cx) * math.tan(rad))) if abs(angle) < 45 else 0
        kernel[min(max(cx + offset, 0), length - 1), i] = 1.0
    kernel /= kernel.sum()
    arr = np.array(image, dtype=np.float32)
    out = np.zeros_like(arr)
    pad = length // 2
    padded = np.pad(arr, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    for c in range(3):
        for i in range(length):
            for j in range(length):
                if kernel[i, j]:
                    out[:, :, c] += kernel[i, j] * padded[i:i + arr.shape[0], j:j + arr.shape[1], c]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def gaussian_noise(image: Image.Image, sigma: float, rng: random.Random) -> Image.Image:
    arr = np.array(image, dtype=np.float32)
    seed = rng.randint(0, 2**31 - 1)
    noise = np.random.default_rng(seed).normal(0, sigma, arr.shape)
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))


def salt_pepper(image: Image.Image, amount: float, rng: random.Random) -> Image.Image:
    arr = np.array(image)
    gen = np.random.default_rng(rng.randint(0, 2**31 - 1))
    mask = gen.random(arr.shape[:2])
    arr[mask < amount / 2] = 0
    arr[mask > 1 - amount / 2] = 255
    return Image.fromarray(arr)


def jpeg_compress(image: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def fade_ink(image: Image.Image, amount: float) -> Image.Image:
    """Lift the darks towards the paper tone, as old ink does."""
    arr = np.array(image, dtype=np.float32)
    return Image.fromarray(np.clip(arr + (255 - arr) * amount, 0, 255).astype(np.uint8))


def yellowing(image: Image.Image, amount: float) -> Image.Image:
    arr = np.array(image, dtype=np.float32)
    arr[:, :, 2] *= (1.0 - 0.35 * amount)
    arr[:, :, 1] *= (1.0 - 0.12 * amount)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def uneven_illumination(image: Image.Image, amount: float, rng: random.Random) -> Image.Image:
    w, h = image.size
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = rng.uniform(0.2, 0.8) * w, rng.uniform(0.2, 0.8) * h
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    grad = 1.0 - amount * (dist / dist.max())
    arr = np.array(image, dtype=np.float32) * grad[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def stains(image: Image.Image, count: int, rng: random.Random) -> Image.Image:
    out = image.convert("RGBA")
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, h = out.size
    for _ in range(count):
        r = rng.randint(30, 130)
        x, y = rng.randint(0, w), rng.randint(0, h)
        tone = (rng.randint(120, 175), rng.randint(85, 130), rng.randint(40, 80),
                rng.randint(28, 70))
        d.ellipse((x - r, y - r, x + int(r * rng.uniform(0.6, 1.4)), y + r), fill=tone)
    blurred = layer.filter(ImageFilter.GaussianBlur(14))
    return Image.alpha_composite(out, blurred).convert("RGB")


def fold_lines(image: Image.Image, count: int, rng: random.Random) -> Image.Image:
    out = image.copy()
    d = ImageDraw.Draw(out, "RGBA")
    w, h = out.size
    for _ in range(count):
        if rng.random() < 0.5:
            y = rng.randint(int(h * 0.15), int(h * 0.85))
            d.line([(0, y), (w, y)], fill=(90, 80, 65, 55), width=rng.randint(2, 5))
        else:
            x = rng.randint(int(w * 0.15), int(w * 0.85))
            d.line([(x, 0), (x, h)], fill=(90, 80, 65, 55), width=rng.randint(2, 5))
    return out


def edge_damage(image: Image.Image, amount: float, rng: random.Random) -> Image.Image:
    out = image.copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    bite = int(min(w, h) * amount)
    for _ in range(rng.randint(3, 9)):
        side = rng.choice(["t", "b", "l", "r"])
        s = rng.randint(bite // 3, max(bite // 3 + 1, bite))
        # Each bite is a circle centred ON the edge, so half of it falls
        # outside the page and the visible part is a scallop.
        if side in ("t", "b"):
            cx, cy = rng.randint(0, w), (0 if side == "t" else h)
        else:
            cx, cy = (0 if side == "l" else w), rng.randint(0, h)
        d.ellipse((cx - s, cy - s, cx + s, cy + s), fill="#EFE7D5")
    return out


def adjust(image: Image.Image, brightness: float, contrast: float) -> Image.Image:
    out = ImageEnhance.Brightness(image).enhance(brightness)
    return ImageEnhance.Contrast(out).enhance(contrast)
