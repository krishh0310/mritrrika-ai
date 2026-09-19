"""Value normalization (§18, §26).

Normalization NEVER destroys the raw value. Every function here is pure and
returns the cleaned form; the caller stores both. That is what makes
'१४२ / २' -> '142/2' an auditable transformation rather than a silent rewrite.
"""

from __future__ import annotations

import re
import unicodedata

# AI4Bharat's Indic NLP Library, used for one narrow job: canonicalising Indic
# text before anything is compared.
#
# The case that matters is the nukta. 'क़' can arrive from OCR as a single
# precomposed codepoint or as 'क' followed by U+093C, and the two are visually
# identical and byte-unequal -- so a village name matches its own record or
# does not, depending on which form the recogniser happened to emit. The
# library also strips the zero-width joiners that scanned text collects.
#
# Optional, like every other model dependency here (§82): absent, normalisation
# behaves exactly as it did before, which is NFC only.

#: Script -> the Indic NLP normaliser's language code. Each script has its own
#: canonical forms (nukta in Devanagari, the Telugu and Kannada length marks),
#: so the normaliser is chosen by the script the text is actually written in.
_NORMALIZER_LANG = {
    "devanagari": "hi",
    "telugu": "te",
    "tamil": "ta",
    "kannada": "kn",
}

try:  # pragma: no cover - exercised by whichever environment is installed
    from indicnlp.normalize.indic_normalize import IndicNormalizerFactory

    _factory = IndicNormalizerFactory()
    _INDIC_NORMALIZERS = {
        script: _factory.get_normalizer(lang) for script, lang in _NORMALIZER_LANG.items()
    }
except Exception:  # the library is optional and its import touches resources
    _INDIC_NORMALIZERS = {}

INDIC_NLP_AVAILABLE = bool(_INDIC_NORMALIZERS)

#: Unicode block ranges for the scripts above. Duplicated from ocr/scripts.py
#: rather than imported: normalization must stay importable on its own.
_SCRIPT_RANGES = (
    (0x0900, 0x097F, "devanagari"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"),
    (0x0C80, 0x0CFF, "kannada"),
)


def _dominant_script(text: str) -> str | None:
    counts: dict[str, int] = {}
    for ch in text:
        point = ord(ch)
        for first, last, name in _SCRIPT_RANGES:
            if first <= point <= last:
                counts[name] = counts.get(name, 0) + 1
                break
    return max(counts, key=counts.get) if counts else None


def canonicalise_indic(text: str) -> str:
    """One spelling per word, so comparison means what it appears to mean.

    NFC first, because the Indic normaliser expects composed input. Then the
    library's own pass for the text's script, which is where variants such as
    the Devanagari nukta forms converge.
    """
    if not text:
        return text
    composed = unicodedata.normalize("NFC", text)
    normalizer = _INDIC_NORMALIZERS.get(_dominant_script(composed) or "devanagari")
    if normalizer is None:
        return composed
    try:
        return normalizer.normalize(composed)
    except Exception:  # pragma: no cover - never fail a value over normalising it
        return composed


#: The original name, kept because callers and tests use it. It was always
#: the whole-value canonicaliser; it is simply no longer Devanagari-only.
canonicalise_devanagari = canonicalise_indic

DEVANAGARI_DIGITS = "०१२३४५६७८९"

#: Area units as written on records, mapped to the canonical enum value.
#: South Indian records state land in acres with guntas (te, kn) or cents
#: (te, ta), so those units are listed alongside the northern bigha and biswa.
UNIT_ALIASES: dict[str, str] = {
    # Hindi
    "बीघा": "BIGHA", "बिघा": "BIGHA", "बीधा": "BIGHA",
    "बिस्वा": "BISWA", "विस्वा": "BISWA",
    "हेक्टेयर": "HECTARE", "हेक्टर": "HECTARE",
    "एकड़": "ACRE", "एकड": "ACRE",
    "वर्ग मीटर": "SQUARE_METRE",
    # Telugu
    "ఎకరాలు": "ACRE", "ఎకరం": "ACRE", "ఎకరా": "ACRE",
    "హెక్టార్లు": "HECTARE", "హెక్టారు": "HECTARE", "హెక్టార్": "HECTARE",
    "గుంటలు": "GUNTHA", "గుంట": "GUNTHA",
    "సెంట్లు": "CENT", "సెంటు": "CENT",
    # Tamil
    "ஏக்கர்": "ACRE",
    "ஹெக்டேர்": "HECTARE",
    "சென்ட்": "CENT",
    # Kannada
    "ಎಕರೆ": "ACRE",
    "ಹೆಕ್ಟೇರ್": "HECTARE",
    "ಗುಂಟೆ": "GUNTHA",
    "ಸೆಂಟ್ಸ್": "CENT",
}


def to_ascii_digits(text: str) -> str:
    """'१४२/२' -> '142/2', and likewise '౧౪౨', '௧௪௨', '೧೪೨'.

    Any Unicode decimal digit is mapped, so every Indian script's numerals are
    covered without a table per script. Every other character is untouched.
    """
    return "".join(
        str(unicodedata.decimal(ch)) if not ch.isascii() and ch.isdecimal() else ch
        for ch in text
    )


def normalize_text(text: str | None) -> str | None:
    """NFC-normalise and collapse whitespace.

    NFC matters for Devanagari: the same visible word can be encoded with
    precomposed or decomposed forms, and two spellings that look identical
    would otherwise compare unequal in search and in evaluation.
    """
    if text is None:
        return None
    cleaned = unicodedata.normalize("NFC", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def normalize_khasra(raw: str | None) -> str | None:
    """'१४२ / २' -> '142/2'. Also tolerates OCR reading '/' as '।' or '।'."""
    text = normalize_text(raw)
    if not text:
        return None
    text = to_ascii_digits(text)
    text = text.replace("।", "/").replace("|", "/").replace("\\", "/")
    text = re.sub(r"\s*/\s*", "/", text)
    match = re.search(r"\d+(?:/\d+)*", text)
    return match.group(0) if match else None


def normalize_khata(raw: str | None) -> str | None:
    text = normalize_text(raw)
    if not text:
        return None
    match = re.search(r"\d+", to_ascii_digits(text))
    return match.group(0) if match else None


def normalize_number(raw: str | None) -> float | None:
    text = normalize_text(raw)
    if not text:
        return None
    ascii_text = to_ascii_digits(text).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", ascii_text)
    return float(match.group(0)) if match else None


def normalize_area(raw: str | None) -> tuple[float | None, str | None]:
    """'२.७५ बीघा' -> (2.75, 'BIGHA')."""
    text = normalize_text(raw)
    if not text:
        return None, None
    value = normalize_number(text)
    unit = None
    for alias, canonical in UNIT_ALIASES.items():
        if alias in text:
            unit = canonical
            break
    return value, unit


def normalize_unit(raw: str | None) -> str | None:
    text = normalize_text(raw)
    if not text:
        return None
    for alias, canonical in UNIT_ALIASES.items():
        if alias in text:
            return canonical
    return None


def normalize_share(raw: str | None) -> str | None:
    """'१/२' -> '1/2'. A bare number means a whole share."""
    text = normalize_text(raw)
    if not text:
        return None
    ascii_text = to_ascii_digits(text)
    match = re.search(r"(\d+)\s*/\s*(\d+)", ascii_text)
    if match:
        numerator, denominator = int(match.group(1)), int(match.group(2))
        if denominator == 0:
            return None
        return f"{numerator}/{denominator}"
    if re.fullmatch(r"\s*1\s*", ascii_text):
        return "1/1"
    return None


def normalize_year(raw: str | None) -> str | None:
    """'१९९८-९९' -> '1998-99'."""
    text = normalize_text(raw)
    if not text:
        return None
    ascii_text = to_ascii_digits(text).replace("–", "-").replace("—", "-")
    match = re.search(r"\d{4}\s*-\s*\d{2,4}", ascii_text)
    if match:
        return re.sub(r"\s*-\s*", "-", match.group(0))
    match = re.search(r"\d{4}", ascii_text)
    return match.group(0) if match else None


def normalize_date(raw: str | None) -> str | None:
    """'१२/०४/२००६' -> '2006-04-12' (ISO). Returns None if implausible."""
    text = normalize_text(raw)
    if not text:
        return None
    ascii_text = to_ascii_digits(text)
    match = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", ascii_text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_name(raw: str | None) -> str | None:
    """Tidy a person's name without changing its spelling.

    Deliberately conservative: transliteration variants are a real problem in
    land records, but silently 'correcting' a recorded name is exactly the kind
    of change that must go through a human verifier, not a regex.
    """
    text = normalize_text(raw)
    if not text:
        return None
    text = re.sub(r"^[\s:\-–—]+", "", text)
    text = re.sub(r"[\s:\-–—]+$", "", text)
    return text or None


#: field -> normalizer. Fields absent here fall through to normalize_text.
NORMALIZERS = {
    "KHASRA": normalize_khasra,
    "KHATA": normalize_khata,
    "SHARE": normalize_share,
    "RECORD_YEAR": normalize_year,
    "DATE": normalize_date,
    "MUTATION": normalize_khata,
    "OWNER": normalize_name,
    "GUARDIAN": normalize_name,
    "AREA_UNIT": normalize_unit,
}


def normalize_field(field: str, raw: str | None) -> str | None:
    """Apply the right normalizer for a field. Never mutates `raw`."""
    # Canonicalise the script BEFORE any field-specific rule looks at it, so
    # every rule below compares one spelling rather than two.
    if raw is not None:
        raw = canonicalise_indic(raw)
    if field == "AREA":
        value = normalize_number(raw)
        return None if value is None else f"{value:g}"
    normalizer = NORMALIZERS.get(field, normalize_text)
    result = normalizer(raw)
    return result if result is None or isinstance(result, str) else str(result)
