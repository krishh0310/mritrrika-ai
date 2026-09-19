"""Translate a page to Hindi when native extraction finds nothing (§6).

Bengali, Gujarati, Punjabi, Odia and Malayalam pages are read by Gemini OCR and
extracted with their own form labels (extraction/labels.py). This is the
fallback for when that finds no field at all: translate each OCR line to Hindi
with IndicTrans2 and run the Hindi extractor over the translation.

A fallback, not the main path, because translation changes VALUES as well as
labels: a Bengali owner name comes back as a Hindi rendering of it, which is
not what the record says. So anything extracted this way is marked
`translated_from` and shown to the verifier as "verify carefully".

Off unless INDICTRANS2_ENABLED=true. The model is gated on Hugging Face and
large, so CI and most deployments never load it: disabled or unavailable, the
text comes back unchanged with a warning, and extraction behaves exactly as
if this module did not exist.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: The distilled Indic-to-Indic model. (There is no 200M indic-indic variant;
#: 200M exists only for English<->Indic.)
MODEL = os.environ.get("INDICTRANS2_MODEL", "ai4bharat/indictrans2-indic-indic-dist-320M")

#: Source codes this module accepts -> IndicTrans2's FLORES language tags.
SOURCE_TAGS = {
    "ben": "ben_Beng",
    "guj": "guj_Gujr",
    "pan": "pan_Guru",
    "ori": "ory_Orya",
    "mal": "mal_Mlym",
}
TARGET_TAG = "hin_Deva"

#: ocr/scripts.py script names -> the source codes above.
SCRIPT_TO_SOURCE = {
    "bengali": "ben",
    "gujarati": "guj",
    "gurmukhi": "pan",
    "odia": "ori",
    "malayalam": "mal",
}

_model = None


def enabled() -> bool:
    return os.environ.get("INDICTRANS2_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def _load():
    """Tokenizer, model and processor, loaded once per process."""
    global _model
    if _model is None:
        from IndicTransToolkit.processor import IndicProcessor
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL, trust_remote_code=True)
        _model = (tokenizer, model, IndicProcessor(inference=True))
    return _model


def translate_lines(lines: list[str], source_script: str) -> list[str] | None:
    """Each line translated to Hindi, or None when translation did not run."""
    if source_script not in SOURCE_TAGS:
        raise ValueError(f"unsupported source {source_script!r}; one of {sorted(SOURCE_TAGS)}")
    if not lines:
        return []
    if not enabled():
        logger.warning("IndicTrans2 is disabled (INDICTRANS2_ENABLED); %s text left as is",
                       source_script)
        return None
    try:
        tokenizer, model, processor = _load()
        batch = processor.preprocess_batch(lines, src_lang=SOURCE_TAGS[source_script],
                                           tgt_lang=TARGET_TAG)
        inputs = tokenizer(batch, padding="longest", truncation=True, return_tensors="pt")
        outputs = model.generate(**inputs, max_length=256, num_beams=1)
        decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)
        return processor.postprocess_batch(decoded, lang=TARGET_TAG)
    except Exception as exc:  # the fallback may never be what fails a page
        logger.warning("IndicTrans2 unavailable (%s); %s text left as is", exc, source_script)
        return None


def translate_to_hindi(text: str, source_script: str) -> str:
    """`text` in Hindi, or `text` unchanged (with a warning) if not possible."""
    translated = translate_lines([text], source_script)
    return translated[0] if translated else text


__all__ = ["SCRIPT_TO_SOURCE", "SOURCE_TAGS", "enabled", "translate_lines", "translate_to_hindi"]
