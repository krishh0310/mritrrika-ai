"""Model-based field extraction, with the rules kept underneath (§6, §66, §82).

The deterministic extractor in field_extractor.py is not replaced. It is the
floor. This module runs the trained layout model first and falls back to the
rules per FIELD -- not per page -- so a page where the model finds nine fields
confidently and misses one still gets the tenth from the rules.

That composition is the point. A model that is better on average is still worse
on some fields, and swapping wholesale would trade those away invisibly. Every
value records which path produced it (`strategy`), so the split is measurable
rather than assumed (§64).

Unavailability is inert, as everywhere else here (§82): no torch, no
transformers, no checkpoint, or a failing forward pass all mean the rules run
alone and extraction is exactly what it was before this file existed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .field_extractor import ExtractedValue
from .field_extractor import extract as extract_with_rules
from .layout_model import LABELS, FieldSpan, decode_spans

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WEIGHTS = (
    REPO_ROOT / "models" / "checkpoints" / "extraction" / "extractor-v1" / "best.pt"
)

#: Below this the model's answer is not preferred over a rule's. Deliberately
#: high: the rules are explainable and already measured, so the model has to be
#: clearly sure before it displaces one.
MIN_CONFIDENCE = 0.70

#: Fields that legitimately repeat down a table. For everything else only the
#: most confident span is kept -- a page has one village, not four.
MULTI_VALUED = frozenset({"OWNER", "GUARDIAN", "SHARE"})

MAX_LENGTH = 512


class ModelExtractor:
    """Loads the checkpoint lazily and labels one page's OCR blocks."""

    def __init__(
        self,
        weights: Path | str | None = None,
        *,
        min_confidence: float = MIN_CONFIDENCE,
        device: str | None = None,
        model_version: str = "extractor-v1",
    ) -> None:
        self.weights = Path(weights) if weights else DEFAULT_WEIGHTS
        self.min_confidence = min_confidence
        self.model_version = model_version
        self._device = device
        self._model = None
        self._tokenizer = None
        self._loaded = False
        self._reason: str | None = None

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._model is not None

    @property
    def unavailable_reason(self) -> str | None:
        self._ensure_loaded()
        return self._reason

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.weights.exists():
            self._reason = f"no checkpoint at {self.weights}"
            logger.info("extractor: %s, rules only (§82)", self._reason)
            return
        try:
            import torch
            from transformers import AutoTokenizer

            from .layout_model import BASE_MODEL, LayoutAwareTokenClassifier
        except ImportError as exc:
            self._reason = f"torch/transformers unavailable: {exc}"
            logger.info("extractor: %s, rules only (§82)", self._reason)
            return

        try:
            checkpoint = torch.load(self.weights, map_location="cpu", weights_only=False)
            model = LayoutAwareTokenClassifier(
                base_model=checkpoint.get("base_model", BASE_MODEL)
            )
            model.load_state_dict(checkpoint["model_state"])
            model.eval()

            tokenizer_dir = self.weights.parent.parent / "tokenizer"
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(tokenizer_dir) if tokenizer_dir.exists()
                else checkpoint.get("base_model", BASE_MODEL)
            )
            self._device = self._device or "cpu"
            self._model = model.to(self._device)
            self._torch = torch
        except Exception as exc:  # pragma: no cover - depends on the checkpoint
            self._reason = f"checkpoint failed to load: {exc}"
            logger.warning("extractor: %s", self._reason)

    def predict(self, blocks, page_width: int, page_height: int) -> list[FieldSpan]:
        """Field spans for one page. Never raises."""
        self._ensure_loaded()
        if self._model is None or not blocks:
            return []

        torch = self._torch
        words, boxes, block_indices = [], [], []
        for block_index, block in enumerate(blocks):
            text = (block.text or "").strip()
            if not text:
                continue
            x1, y1, x2, y2 = block.bbox
            words.append(text)
            block_indices.append(block_index)
            boxes.append([
                max(0, min(1000, int(1000 * x1 / max(page_width, 1)))),
                max(0, min(1000, int(1000 * y1 / max(page_height, 1)))),
                max(0, min(1000, int(1000 * x2 / max(page_width, 1)))),
                max(0, min(1000, int(1000 * y2 / max(page_height, 1)))),
            ])
        if not words:
            return []

        try:
            encoding = self._tokenizer(
                words, is_split_into_words=True, truncation=True,
                max_length=MAX_LENGTH, padding="max_length", return_tensors="pt",
            )
            word_ids = encoding.word_ids(0)

            token_boxes = [
                [0, 0, 0, 0] if wid is None else boxes[wid] for wid in word_ids
            ]
            with torch.no_grad():
                out = self._model(
                    encoding["input_ids"].to(self._device),
                    encoding["attention_mask"].to(self._device),
                    torch.tensor([token_boxes], dtype=torch.long).to(self._device),
                )
            probabilities = out["logits"].softmax(-1)[0]
            predictions = probabilities.argmax(-1)

            # Take the FIRST sub-token's prediction per word, matching how the
            # labels were assigned during training.
            word_labels = [0] * len(words)
            word_scores = [0.0] * len(words)
            seen: set[int] = set()
            for position, word_id in enumerate(word_ids):
                if word_id is None or word_id in seen:
                    continue
                seen.add(word_id)
                label_id = int(predictions[position])
                word_labels[word_id] = label_id
                word_scores[word_id] = float(probabilities[position][label_id])
        except Exception as exc:  # pragma: no cover - runtime/device dependent
            logger.warning("extractor: inference failed (%s), rules only", exc)
            return []

        # Boxes are handed back in ORIGINAL page coordinates, because that is
        # what the verifier's overlay draws in.
        spans = decode_spans(words, boxes, word_labels, word_scores)
        rescaled = []
        for span in spans:
            indices = [block_indices[i] for i in span.word_indices]
            xs1 = [blocks[i].bbox[0] for i in indices]
            ys1 = [blocks[i].bbox[1] for i in indices]
            xs2 = [blocks[i].bbox[2] for i in indices]
            ys2 = [blocks[i].bbox[3] for i in indices]
            rescaled.append(FieldSpan(
                field=span.field, text=span.text,
                bbox=(min(xs1), min(ys1), max(xs2), max(ys2)),
                confidence=span.confidence, word_indices=indices,
            ))
        return rescaled


def _to_values(spans, blocks, model_version: str) -> list[ExtractedValue]:
    values = []
    for span in spans:
        first = span.word_indices[0]
        values.append(ExtractedValue(
            field=span.field,
            raw_value=span.text,
            bbox=span.bbox,
            ocr_confidence=blocks[first].confidence if first < len(blocks) else 0.0,
            extraction_confidence=round(span.confidence, 4),
            source_block_index=first,
            strategy=f"model:{model_version}",
        ))
    return values


def extract(
    blocks,
    page_width: int = 1240,
    page_height: int = 1754,
    *,
    extractor: ModelExtractor | None = None,
    regions=None,
    table_rows=None,
):
    """Model first, rules underneath, per field.

    Returns the same ExtractionResult shape as the rule-based extractor, so
    this is a drop-in substitution for callers that want it.
    """
    rule_result = extract_with_rules(
        blocks, page_width, table_rows=table_rows, regions=regions
    )
    if extractor is None or not extractor.available:
        return rule_result

    from normalization.normalizers import normalize_field

    spans = [
        s for s in extractor.predict(blocks, page_width, page_height)
        if s.confidence >= extractor.min_confidence
        and normalize_field(s.field, s.text) is not None
    ]
    if not spans:
        return rule_result

    model_values = _to_values(spans, blocks, extractor.model_version)

    # Keep the best model span per single-valued field; keep all for the table
    # columns that legitimately repeat.
    kept: list[ExtractedValue] = []
    best_single: dict[str, ExtractedValue] = {}
    for value in model_values:
        if value.field in MULTI_VALUED:
            kept.append(value)
        else:
            current = best_single.get(value.field)
            if current is None or value.extraction_confidence > current.extraction_confidence:
                best_single[value.field] = value
    kept.extend(best_single.values())

    # The fallback, per field: a rule value survives only where the model
    # offered nothing for that field.
    model_fields = {v.field for v in kept}
    kept.extend(v for v in rule_result.values if v.field not in model_fields)

    # Normalisation still decides what is keepable -- an unparseable value is
    # dropped whichever path produced it (§82).
    final = [v for v in kept if normalize_field(v.field, v.raw_value) is not None]

    expected = {"DISTRICT", "TEHSIL", "VILLAGE", "KHASRA", "AREA", "OWNER"}
    found = {v.field for v in final}
    rule_result.values = final
    rule_result.missing = sorted(expected - found)
    rule_result.model_version = f"{extractor.model_version}+rules"
    return rule_result


def build_default_extractor() -> ModelExtractor:
    return ModelExtractor(os.environ.get("MRITTIKA_EXTRACTOR_WEIGHTS") or None)


__all__ = [
    "DEFAULT_WEIGHTS", "LABELS", "MIN_CONFIDENCE", "MULTI_VALUED",
    "ModelExtractor", "build_default_extractor", "extract",
]
