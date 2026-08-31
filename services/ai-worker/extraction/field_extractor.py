"""Field extraction from OCR blocks (§6, §17).

Deterministic and spatial, per §66: start with rules, measure, and only reach
for a trained model where the rules demonstrably fall short.

The method is label-anchored. Land records are forms: a value is positioned
relative to a printed label. So we locate the label, then take the nearest
plausible value in the direction that layout implies. Three geometries are
supported, because the templates deliberately differ (§47):

    label: value          (same line, value to the right)
    label —   value       (same line, wider gap)
    label                 (grid cell, value directly BELOW)
    value

Every extraction carries the bbox of the VALUE (never the label) so the
Verifier can zoom to the right region, plus the confidence of the OCR block it
came from (§26).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from difflib import SequenceMatcher

from ocr.provider import TextBlock, group_lines

#: Label variants per field. Multiple spellings because the templates use
#: different wording on purpose (जिला vs जनपद, ग्राम vs मौजा).
LABELS: dict[str, list[str]] = {
    "DISTRICT": ["जिला", "जनपद"],
    "TEHSIL": ["तहसील"],
    "VILLAGE": ["ग्राम", "मौजा", "ग्राम / मौजा"],
    "RECORD_YEAR": ["फसली वर्ष", "वर्ष"],
    "KHATA": ["खाता सं", "खाता संख्या", "खाता"],
    "KHASRA": ["खसरा सं", "खसरा संख्या", "खसरा"],
    "AREA": ["क्षेत्रफल"],
    "LAND_CLASS": ["भूमि श्रेणी", "श्रेणी"],
    "MUTATION": ["नामांतरण सं", "नामांतरण संख्या"],
    "DATE": ["दिनांक"],
    "GUARDIAN": ["पिता / पति", "पिता", "पति"],
}

#: Column headings that introduce a table of owners.
OWNER_COLUMN_LABELS = ["खातेदार का नाम", "नाम", "नवीन खातेदार"]
SHARE_COLUMN_LABELS = ["अंश"]

#: Blocks that are chrome, never values.
CHROME = {
    "उत्तर प्रदेश", "खसरा", "खतौनी", "नामांतरण पंजिका", "भूमि विवरण",
    "खातेदारों का विवरण", "प्रमाणित किया जाता है", "हस्ताक्षर / लेखपाल",
    "डेमो", "मुहर", "क्र.", "टिप्पणी", "प्रकार",
}

SYNTHETIC_NOTICE = "SYNTHETIC"


@dataclass
class ExtractedValue:
    field: str
    raw_value: str
    bbox: tuple[int, int, int, int]
    ocr_confidence: float
    extraction_confidence: float
    source_block_index: int
    row_index: int | None = None
    strategy: str = "label-right"


@dataclass
class ExtractionResult:
    values: list[ExtractedValue] = dc_field(default_factory=list)
    model_version: str = "extractor-v1"
    #: Fields we looked for and did not find -- surfaced rather than hidden, so
    #: a missing value is reviewable instead of silently absent.
    missing: list[str] = dc_field(default_factory=list)

    def by_field(self, name: str) -> list[ExtractedValue]:
        return [v for v in self.values if v.field == name]

    def first(self, name: str) -> ExtractedValue | None:
        found = self.by_field(name)
        return found[0] if found else None


def _norm(text: str) -> str:
    return re.sub(r"[\s:।|.,\-–—]+", "", text).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


#: Fuzzy-match floor for label recognition.
#:
#: Exact matching does not survive real OCR. On a 'hard' page the engine
#: returned विला for जिला, तहसौल for तहसील, and आातेदार का नास for
#: खातेदार का नाम. Requiring exact text meant zero fields were found on
#: exactly the pages the verification workflow exists to handle.
#:
#: 0.66 was chosen empirically: it accepts those misreadings while still
#: separating the labels from each other (जिला vs तहसील scores far lower).
LABEL_SIMILARITY = 0.66


def _label_score(text: str, variants: list[str]) -> float:
    """How strongly `text` reads as one of `variants` (0..1)."""
    normalized = _norm(text)
    if not normalized:
        return 0.0
    best = 0.0
    for variant in variants:
        candidate = _norm(variant)
        if normalized == candidate:
            return 1.0
        # A label may carry a trailing fragment ('खसरासं' for 'खसरा सं').
        if normalized.startswith(candidate) and len(normalized) <= len(candidate) + 3:
            best = max(best, 0.95)
            continue
        # LENGTH GUARD. Without it, a VALUE containing the label word scores as
        # a label: 'डेमो जिला' vs 'जिला' ratios at 0.67, so the district value
        # was being rejected as a heading and the field came back missing.
        # A genuine label is close in length to the word it is being matched
        # against; a value that merely contains it is not.
        if abs(len(normalized) - len(candidate)) > 3:
            continue
        best = max(best, _similar(normalized, candidate))
    return best


def _is_label(block: TextBlock, variants: list[str]) -> bool:
    return _label_score(block.text, variants) >= LABEL_SIMILARITY


def _is_any_label(block: TextBlock) -> bool:
    """True if the block is a label for ANY field.

    Used to stop one field harvesting another field's label as its value --
    the failure that made the grid layout return 'तहसील' as the district.
    """
    return any(_is_label(block, variants) for variants in LABELS.values()) or any(
        _label_score(block.text, group) >= LABEL_SIMILARITY
        for group in (OWNER_COLUMN_LABELS, SHARE_COLUMN_LABELS)
    )


def _split_inline_value(block: TextBlock, variants: list[str]) -> str | None:
    """Recover a value fused into the label's own block.

    OCR merges nearby runs: 'ग्राम : रामपुर' came back as the single block
    'यामः रामपुर'. When the head of a block reads as the label, the tail is
    the value.
    """
    text = block.text.strip()
    for variant in variants:
        candidate = _norm(variant)
        if not candidate:
            continue
        # Walk forward until the normalised prefix matches the label, then
        # treat whatever follows as the value.
        for cut in range(len(candidate), min(len(text), len(candidate) + 6) + 1):
            head, tail = text[:cut], text[cut:]
            if _similar(_norm(head), candidate) >= LABEL_SIMILARITY:
                tail = re.sub(r"^[\s:।|.,\-–—]+", "", tail).strip()
                # The tail must look like content, not leftover punctuation.
                # Without this the split emitted 'से:' as a khasra number --
                # fabricating a value is worse than reporting none (§82).
                if _plausible_value(tail):
                    return tail
    return None


def _plausible_value(text: str) -> bool:
    """Reject fragments that cannot be a real field value."""
    cleaned = _norm(text)
    if len(cleaned) < 2:
        return False
    # Must contain a digit or a Devanagari/Latin letter, not only marks.
    return bool(re.search(r"[0-9\u0966-\u096F\u0904-\u0939A-Za-z]", cleaned))


def _vertical_overlap(a: TextBlock, b: TextBlock) -> float:
    top = max(a.bbox[1], b.bbox[1])
    bottom = min(a.bbox[3], b.bbox[3])
    shorter = min(a.bbox[3] - a.bbox[1], b.bbox[3] - b.bbox[1])
    return (bottom - top) / shorter if shorter > 0 else 0.0


def _is_chrome(block: TextBlock) -> bool:
    text = _norm(block.text)
    if SYNTHETIC_NOTICE in block.text.upper():
        return True
    return any(_similar(text, _norm(c)) >= 0.85 for c in CHROME)


def _value_to_the_right(
    label: TextBlock, blocks: list[TextBlock], max_gap: int
) -> tuple[TextBlock, int] | None:
    """Nearest non-label block on the same visual line, right of the label."""
    best, best_index, best_gap = None, -1, max_gap + 1
    for index, block in enumerate(blocks):
        if block is label or _is_chrome(block) or _is_any_label(block):
            continue
        if _vertical_overlap(label, block) < 0.5:
            continue
        gap = block.bbox[0] - label.bbox[2]
        if 0 <= gap < best_gap:
            best, best_index, best_gap = block, index, gap
    return (best, best_index) if best is not None else None


def _value_below(
    label: TextBlock, blocks: list[TextBlock], max_gap: int
) -> tuple[TextBlock, int] | None:
    """Nearest non-label block directly beneath the label (grid layout)."""
    label_centre = (label.bbox[0] + label.bbox[2]) / 2
    label_width = label.bbox[2] - label.bbox[0]
    best, best_index, best_gap = None, -1, max_gap + 1
    for index, block in enumerate(blocks):
        if block is label or _is_chrome(block) or _is_any_label(block):
            continue
        gap = block.bbox[1] - label.bbox[3]
        if not (0 <= gap < best_gap):
            continue
        centre = (block.bbox[0] + block.bbox[2]) / 2
        if abs(centre - label_centre) > max(110, label_width):
            continue
        best, best_index, best_gap = block, index, gap
    return (best, best_index) if best is not None else None


def extract_scalar_fields(
    blocks: list[TextBlock], page_width: int
) -> list[ExtractedValue]:
    """Pull the single-value fields by locating their labels.

    For each field, every candidate label block is scored and the strongest is
    used. Three strategies are then tried IN ORDER, falling through rather than
    giving up:

        1. right-of-label  -- the common form-field arrangement
        2. inline          -- label and value fused into one OCR block
        3. below-label     -- grid layouts where headings sit above values

    Falling through matters: on the grid template, strategy 1 finds the NEXT
    HEADING to the right. Rejecting it and abandoning the field left the whole
    header unextracted; rejecting it and continuing to strategy 3 reads it
    correctly.
    """
    values: list[ExtractedValue] = []
    claimed: set[int] = set()
    max_right_gap = int(page_width * 0.32)
    max_below_gap = 110

    # Longest labels first so 'खसरा सं' wins over the bare 'खसरा'.
    ordered_fields = sorted(LABELS.items(), key=lambda kv: -max(len(v) for v in kv[1]))

    for field_name, variants in ordered_fields:
        candidates = sorted(
            ((b, _label_score(b.text, variants)) for b in blocks),
            key=lambda pair: -pair[1],
        )
        for label_block, score in candidates:
            if score < LABEL_SIMILARITY:
                break  # scored list -- nothing later can qualify

            # 1. value to the right
            found = _value_to_the_right(label_block, blocks, max_right_gap)
            if found is not None and found[1] not in claimed:
                value_block, index = found
                claimed.add(index)
                values.append(
                    ExtractedValue(
                        field=field_name,
                        raw_value=value_block.text,
                        bbox=value_block.bbox,
                        ocr_confidence=value_block.confidence,
                        extraction_confidence=0.92 * score,
                        source_block_index=index,
                        strategy="label-right",
                    )
                )
                break

            # 2. value fused into the label's own block
            inline = _split_inline_value(label_block, variants)
            if inline:
                values.append(
                    ExtractedValue(
                        field=field_name,
                        raw_value=inline,
                        bbox=label_block.bbox,
                        ocr_confidence=label_block.confidence,
                        # The bbox covers label AND value, so it is less precise
                        # than a standalone block -- discounted accordingly.
                        extraction_confidence=0.74 * score,
                        source_block_index=-1,
                        strategy="inline",
                    )
                )
                break

            # 3. value beneath the label
            found = _value_below(label_block, blocks, max_below_gap)
            if found is not None and found[1] not in claimed:
                value_block, index = found
                claimed.add(index)
                values.append(
                    ExtractedValue(
                        field=field_name,
                        raw_value=value_block.text,
                        bbox=value_block.bbox,
                        ocr_confidence=value_block.confidence,
                        extraction_confidence=0.84 * score,
                        source_block_index=index,
                        strategy="label-below",
                    )
                )
                break

    return values


def extract_table_rows(blocks: list[TextBlock]) -> list[ExtractedValue]:
    """Read the owners table: one OWNER (and SHARE) per row.

    Anchors on the column headings, then walks the lines beneath them, taking
    the block nearest each heading's horizontal position. Rows are numbered so
    an owner and their share stay associated.
    """
    values: list[ExtractedValue] = []

    owner_header = next(
        (b for b in blocks if any(_norm(b.text) == _norm(v) for v in OWNER_COLUMN_LABELS)),
        None,
    )
    if owner_header is None:
        return values

    share_header = next(
        (b for b in blocks if any(_norm(b.text) == _norm(v) for v in SHARE_COLUMN_LABELS)),
        None,
    )

    def column_pick(line: list[TextBlock], header: TextBlock) -> TextBlock | None:
        centre = (header.bbox[0] + header.bbox[2]) / 2
        candidates = [
            b for b in line
            if not _is_chrome(b) and abs(((b.bbox[0] + b.bbox[2]) / 2) - centre) < 220
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda b: abs(((b.bbox[0] + b.bbox[2]) / 2) - centre))

    lines = group_lines(blocks)
    header_bottom = owner_header.bbox[3]
    row_index = 0

    for line in lines:
        line_top = min(b.bbox[1] for b in line)
        if line_top <= header_bottom:
            continue
        # Stop at the footer rule.
        if any(_is_chrome(b) and "प्रमाणित" in b.text for b in line):
            break

        owner_block = column_pick(line, owner_header)
        if owner_block is None or _is_label(owner_block, sum(LABELS.values(), [])):
            continue
        # A serial-number cell is not a name.
        if re.fullmatch(r"[०-९0-9.]+", _norm(owner_block.text)):
            continue

        values.append(
            ExtractedValue(
                field="OWNER",
                raw_value=owner_block.text,
                bbox=owner_block.bbox,
                ocr_confidence=owner_block.confidence,
                extraction_confidence=0.88,
                source_block_index=-1,
                row_index=row_index,
                strategy="table-column",
            )
        )

        if share_header is not None:
            share_block = column_pick(line, share_header)
            if share_block is not None and share_block is not owner_block:
                if re.search(r"[०-९0-9]", share_block.text):
                    values.append(
                        ExtractedValue(
                            field="SHARE",
                            raw_value=share_block.text,
                            bbox=share_block.bbox,
                            ocr_confidence=share_block.confidence,
                            extraction_confidence=0.86,
                            source_block_index=-1,
                            row_index=row_index,
                            strategy="table-column",
                        )
                    )
        row_index += 1

    return values


def extract(blocks: list[TextBlock], page_width: int = 1240) -> ExtractionResult:
    """Extract every supported field from one page's OCR blocks."""
    values = extract_scalar_fields(blocks, page_width)
    values.extend(extract_table_rows(blocks))

    # AREA_UNIT often sits in the same block as AREA ('२.७५ बीघा'); when it
    # does not, it is the block immediately after AREA.
    area = next((v for v in values if v.field == "AREA"), None)
    if area and not any(v.field == "AREA_UNIT" for v in values):
        for block in blocks:
            if block.bbox[0] >= area.bbox[2] and _vertical_overlap(
                TextBlock(area.raw_value, 1.0, area.bbox), block
            ) > 0.5:
                if re.search(r"बीघा|बिस्वा|हेक्टेयर|एकड", block.text):
                    values.append(
                        ExtractedValue(
                            field="AREA_UNIT",
                            raw_value=block.text,
                            bbox=block.bbox,
                            ocr_confidence=block.confidence,
                            extraction_confidence=0.90,
                            source_block_index=-1,
                            strategy="adjacent-to-area",
                        )
                    )
                    break

    # Drop anything that cannot be normalised into a usable value. Reporting a
    # field as MISSING is honest and reviewable; emitting 'से:' as a khasra
    # number is a fabricated value that looks like a real extraction (§82).
    from normalization.normalizers import normalize_field

    kept: list[ExtractedValue] = []
    for value in values:
        if normalize_field(value.field, value.raw_value) is None:
            continue
        kept.append(value)

    expected = {"DISTRICT", "TEHSIL", "VILLAGE", "KHASRA", "AREA", "OWNER"}
    found = {v.field for v in kept}
    return ExtractionResult(values=kept, missing=sorted(expected - found))
