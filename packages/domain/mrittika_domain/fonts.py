"""Locate Indic fonts for rendered records and synthetic test pages.

Linux deployments install the OFL-licensed Noto fonts from fonts-noto-core.
Operators may override a face with MRITTIKA_FONT_<SCRIPT>[_BOLD].
"""

from __future__ import annotations

import os
from pathlib import Path

_LINUX = Path("/usr/share/fonts/truetype/noto")
_MAC = Path("/System/Library/Fonts/Supplemental")
_FONTS = {
    "devanagari": ("NotoSansDevanagari", "Devanagari Sangam MN.ttc"),
    "telugu": ("NotoSansTelugu", "Telugu MN.ttc"),
    "tamil": ("NotoSansTamil", "Tamil MN.ttc"),
    "kannada": ("NotoSansKannada", "Kannada MN.ttc"),
}


def find_font(script: str = "devanagari", *, bold: bool = False) -> str:
    """Return an installed face for ``script`` or fail before rendering boxes."""
    if script not in _FONTS:
        raise ValueError(f"unsupported font script: {script}")
    name, mac_name = _FONTS[script]
    suffix = "_BOLD" if bold else ""
    override = os.environ.get(f"MRITTIKA_FONT_{script.upper()}{suffix}")
    if override:
        if Path(override).is_file():
            return override
        raise FileNotFoundError(f"configured {script} font does not exist: {override}")
    candidates = [
        _LINUX / f"{name}-{'Bold' if bold else 'Regular'}.ttf",
        _LINUX / f"{name}[wdth,wght].ttf",
        _MAC / ("Kohinoor.ttc" if bold and script == "devanagari" else mac_name),
    ]
    if bold:
        candidates.insert(2, _LINUX / f"{name}-Regular.ttf")
    for path in candidates:
        if path.is_file():
            return str(path)
    raise FileNotFoundError(
        f"no {script} font installed; install fonts-noto-core or set "
        f"MRITTIKA_FONT_{script.upper()}{suffix}"
    )
