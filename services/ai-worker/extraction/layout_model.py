"""A layout-aware field extractor for Devanagari land records (§6, §66).

Why not LayoutLMv3, which is what one would reach for first: its tokenizer
cannot represent Devanagari. It is a byte-level BPE trained on English, so
`ग्राम रामपुर खसरा १४२/२ क्षेत्रफल` becomes 55 tokens for 33 characters --
1.67 tokens per CHARACTER -- and the pieces are mojibake fragments
(`['Ġà¤', 'Ĺ', 'à¥', 'į', ...]`) carrying no pretrained meaning. MuRIL, trained
on Indian languages, tokenises the same string in 8 tokens, one per word, with
`ग्राम` and `क्षेत्रफल` each a single learned unit.

LayoutXLM would solve the tokenizer and reintroduces a different problem: its
visual backbone requires detectron2, which does not install cleanly on this
platform.

So this takes LayoutLM's actual contribution -- learned 2D position embeddings
summed into the token embeddings, so the encoder knows WHERE each word sits --
and applies it to a Devanagari-native encoder instead of an English one. That
is the part of LayoutLM that matters for a form: a value's meaning on a Khasra
page is decided by its position relative to a printed label, not by the
sentence it appears in.

What this model is asked to do is deliberately narrow: label which words on a
page belong to which field. It never reads, corrects or generates a value. The
text it labels is whatever OCR produced, unchanged (§44).
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import torch
    from torch import nn

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by whichever env is installed
    torch = None
    nn = object
    TORCH_AVAILABLE = False


#: Fixed order: label ids are baked into a checkpoint, so reordering this
#: silently invalidates every trained model.
FIELDS = [
    "DISTRICT", "TEHSIL", "VILLAGE", "RECORD_YEAR", "KHATA", "KHASRA",
    "AREA", "AREA_UNIT", "LAND_CLASS", "MUTATION", "DATE",
    "OWNER", "GUARDIAN", "SHARE",
]
LABELS = ["O"] + [f"{p}-{f}" for f in FIELDS for p in ("B", "I")]
LABEL_TO_ID = {label: i for i, label in enumerate(LABELS)}

BASE_MODEL = "google/muril-base-cased"

#: Boxes arrive on a 0-1000 grid, so 1001 positions per coordinate.
COORD_BINS = 1001


@dataclass
class FieldSpan:
    """One predicted value: which field, which words, how sure."""

    field: str
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float
    word_indices: list[int]


class LayoutAwareTokenClassifier(nn.Module):
    """MuRIL plus LayoutLM-style 2D position embeddings."""

    def __init__(self, base_model: str = BASE_MODEL, num_labels: int = len(LABELS)):
        if not TORCH_AVAILABLE:
            raise RuntimeError("torch is required to construct this model")
        super().__init__()
        from transformers import AutoConfig, AutoModel

        self.config = AutoConfig.from_pretrained(base_model)
        self.encoder = AutoModel.from_pretrained(base_model)
        hidden = self.config.hidden_size

        # Separate embeddings per coordinate, as LayoutLM does, rather than one
        # projection of the 4-vector: x and y are not interchangeable, and a
        # shared table would force the model to learn that they are not.
        self.x_position = nn.Embedding(COORD_BINS, hidden)
        self.y_position = nn.Embedding(COORD_BINS, hidden)
        self.width_embedding = nn.Embedding(COORD_BINS, hidden)
        self.height_embedding = nn.Embedding(COORD_BINS, hidden)

        self.layout_norm = nn.LayerNorm(hidden, eps=self.config.layer_norm_eps)
        self.dropout = nn.Dropout(self.config.hidden_dropout_prob)
        self.classifier = nn.Linear(hidden, num_labels)
        self.num_labels = num_labels

        # Zero-initialised so an untrained model starts as plain MuRIL and the
        # layout signal is learned rather than injected as noise.
        for embedding in (self.x_position, self.y_position,
                          self.width_embedding, self.height_embedding):
            nn.init.zeros_(embedding.weight)

    def layout_embedding(self, boxes):
        x1, y1, x2, y2 = boxes[..., 0], boxes[..., 1], boxes[..., 2], boxes[..., 3]
        width = (x2 - x1).clamp(0, COORD_BINS - 1)
        height = (y2 - y1).clamp(0, COORD_BINS - 1)
        return (
            self.x_position(x1) + self.x_position(x2)
            + self.y_position(y1) + self.y_position(y2)
            + self.width_embedding(width) + self.height_embedding(height)
        )

    def forward(self, input_ids, attention_mask, boxes, labels=None):
        words = self.encoder.embeddings.word_embeddings(input_ids)
        embeddings = words + self.layout_embedding(boxes)
        embeddings = self.layout_norm(embeddings)

        output = self.encoder(
            inputs_embeds=embeddings, attention_mask=attention_mask
        ).last_hidden_state
        logits = self.classifier(self.dropout(output))

        loss = None
        if labels is not None:
            loss = nn.functional.cross_entropy(
                logits.view(-1, self.num_labels), labels.view(-1), ignore_index=-100
            )
        return {"loss": loss, "logits": logits}


def decode_spans(
    words: list[str],
    boxes: list[list[int]],
    label_ids: list[int],
    probabilities: list[float],
) -> list[FieldSpan]:
    """Turn per-word BIO labels into field values.

    A run of B- followed by I- of the same field is one value. A bare I- with
    no B- before it starts a value anyway: the model is not required to be
    self-consistent, and dropping such a run would silently lose a field over a
    formatting technicality.
    """
    spans: list[FieldSpan] = []
    current: dict | None = None

    def close() -> None:
        nonlocal current
        if current is None:
            return
        xs1 = [boxes[i][0] for i in current["indices"]]
        ys1 = [boxes[i][1] for i in current["indices"]]
        xs2 = [boxes[i][2] for i in current["indices"]]
        ys2 = [boxes[i][3] for i in current["indices"]]
        spans.append(FieldSpan(
            field=current["field"],
            text=" ".join(words[i] for i in current["indices"]).strip(),
            bbox=(min(xs1), min(ys1), max(xs2), max(ys2)),
            confidence=sum(current["scores"]) / len(current["scores"]),
            word_indices=list(current["indices"]),
        ))
        current = None

    for index, label_id in enumerate(label_ids):
        label = LABELS[label_id] if 0 <= label_id < len(LABELS) else "O"
        if label == "O":
            close()
            continue
        prefix, field = label.split("-", 1)
        if current is not None and current["field"] == field and prefix == "I":
            current["indices"].append(index)
            current["scores"].append(probabilities[index])
        else:
            close()
            current = {"field": field, "indices": [index],
                       "scores": [probabilities[index]]}
    close()
    return spans


__all__ = [
    "BASE_MODEL", "FIELDS", "LABELS", "LABEL_TO_ID", "TORCH_AVAILABLE",
    "FieldSpan", "LayoutAwareTokenClassifier", "decode_spans",
]
