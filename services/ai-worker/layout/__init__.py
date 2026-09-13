"""Structural region detection (§6)."""

from .detector import (
    DEFAULT_WEIGHTS,
    LayoutDetector,
    LayoutRegion,
    build_default_detector,
)

__all__ = [
    "DEFAULT_WEIGHTS", "LayoutDetector", "LayoutRegion", "build_default_detector",
]
