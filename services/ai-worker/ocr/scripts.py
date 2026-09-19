"""Indian script identification and the language each one routes to (§6).

Land records are not written in one script. A Khasra from Uttar Pradesh is
Devanagari; the same record in Telangana is Telugu, in Tamil Nadu Tamil, in
Karnataka Kannada. A pipeline hard-wired to one recogniser does not degrade on
the others -- it returns fluent nonsense at plausible confidence, which is
worse than returning nothing.

This module exists so the system can tell which script it is looking at, and
say plainly when that script is one it cannot read.

Identification is by Unicode block, not by a model. Indian scripts occupy
disjoint blocks, so counting characters is exact for text that has already been
recognised -- there is no ambiguity to learn away. What it cannot do is
identify the script of an IMAGE, which is why routing (see `route` in
provider.py) recognises with each candidate and compares, rather than guessing
first and recognising once.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

#: Unicode blocks, as (first, last, script name). Ranges are the canonical
#: block bounds; a character outside every range is counted as neither.
BLOCKS: tuple[tuple[int, int, str], ...] = (
    (0x0900, 0x097F, "devanagari"),
    (0x0980, 0x09FF, "bengali"),
    (0x0A00, 0x0A7F, "gurmukhi"),
    (0x0A80, 0x0AFF, "gujarati"),
    (0x0B00, 0x0B7F, "odia"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"),
    (0x0C80, 0x0CFF, "kannada"),
    (0x0D00, 0x0D7F, "malayalam"),
    (0x0600, 0x06FF, "arabic"),
    (0x0041, 0x005A, "latin"),
    (0x0061, 0x007A, "latin"),
)

#: Script -> the PaddleOCR language code that reads it. `hi` covers every
#: Devanagari language: PaddleOCR maps hi, mr, ne, sa, mai, bho and others onto
#: one `devanagari` recogniser, so the distinction is linguistic, not visual.
SCRIPT_TO_LANG: dict[str, str] = {
    "devanagari": "hi",
    "telugu": "te",
    "tamil": "ta",
    "kannada": "ka",
    "latin": "en",
    "arabic": "ur",
}

#: Scripts this module can NAME but the engine cannot READ. Listed explicitly
#: rather than omitted, so an unreadable page is reported as an unsupported
#: script instead of being silently handed to whichever recogniser is loaded
#: (§82). PP-OCRv5 ships no recogniser for these. The Gemini vision provider
#: does read them, and extraction has their form labels (extraction/labels.py),
#: so a deployment receiving these pages runs with OCR_PROVIDER=gemini.
UNSUPPORTED_SCRIPTS: frozenset[str] = frozenset(
    {"bengali", "gujarati", "gurmukhi", "odia", "malayalam"}
)

SUPPORTED_SCRIPTS: frozenset[str] = frozenset(SCRIPT_TO_LANG)


class UnsupportedScript(Exception):
    """The script was identified, and no available model reads it."""


@dataclass(frozen=True)
class ScriptProfile:
    """What scripts a piece of text is made of."""

    dominant: str | None
    counts: dict[str, int]
    total: int

    def fraction(self, script: str) -> float:
        return self.counts.get(script, 0) / self.total if self.total else 0.0

    @property
    def supported(self) -> bool:
        return self.dominant in SUPPORTED_SCRIPTS

    def to_dict(self) -> dict:
        return {
            "dominant": self.dominant,
            "counts": dict(self.counts),
            "total": self.total,
            "supported": self.supported,
        }


def script_of(char: str) -> str | None:
    """The script one character belongs to, or None."""
    point = ord(char)
    for first, last, name in BLOCKS:
        if first <= point <= last:
            return name
    return None


def profile(text: str) -> ScriptProfile:
    """Count the scripts present in `text`.

    Digits, punctuation and whitespace are excluded: they appear in every
    script's text and would dilute the counts without distinguishing anything.
    Devanagari digits are the exception that proves it -- they live INSIDE the
    Devanagari block, so they are counted, correctly.
    """
    counts: dict[str, int] = {}
    total = 0
    for char in unicodedata.normalize("NFC", text or ""):
        if char.isspace() or (char.isascii() and not char.isalpha()):
            continue
        name = script_of(char)
        if name is None:
            continue
        counts[name] = counts.get(name, 0) + 1
        total += 1

    dominant = max(counts, key=counts.get) if counts else None
    return ScriptProfile(dominant=dominant, counts=counts, total=total)


def detect_script(text: str) -> str | None:
    return profile(text).dominant


def language_for_script(script: str | None) -> str:
    """The recogniser language for a script, or raise.

    Raises rather than defaulting to Hindi: silently reading a Gujarati page
    with a Devanagari recogniser is exactly the failure this module exists to
    prevent.
    """
    if script in SCRIPT_TO_LANG:
        return SCRIPT_TO_LANG[script]
    if script in UNSUPPORTED_SCRIPTS:
        raise UnsupportedScript(
            f"{script} is recognised as a script but PaddleOCR has no model "
            f"for it; read it with OCR_PROVIDER=gemini, or enter it manually"
        )
    raise UnsupportedScript(f"could not identify a supported script (saw {script!r})")


__all__ = [
    "BLOCKS", "SCRIPT_TO_LANG", "SUPPORTED_SCRIPTS", "UNSUPPORTED_SCRIPTS",
    "ScriptProfile", "UnsupportedScript", "detect_script", "language_for_script",
    "profile", "script_of",
]
