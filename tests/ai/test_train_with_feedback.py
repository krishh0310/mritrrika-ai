"""train_extractor.py trains on exported verifier feedback (§67).

Loading only -- a training run is minutes of GPU time and belongs in the
evaluation scripts, not the test suite. What is tested is the contract between
export_feedback_dataset.py and the trainer: feedback pages are found, repeated
by their weight, kept out of validation, and refused when they were labelled
against a different vocabulary.
"""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

import train_extractor  # noqa: E402

ROW = {"document_id": "DOC-1", "words": ["142/2"], "boxes": [[0, 0, 10, 10]],
       "labels": [11], "dataset_tag": "feedback-x", "feedback_ids": ["f1"]}


def write(tmp_path, rows, labels=None):
    path = tmp_path / "feedback.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    path.with_suffix(".labels.json").write_text(
        json.dumps(labels if labels is not None else list(train_extractor.LABELS))
    )
    return path


def test_feedback_pages_are_repeated_by_weight(tmp_path):
    rows, report = train_extractor.load_feedback(write(tmp_path, [ROW, ROW]), weight=3)
    assert len(rows) == 6
    assert report["pages"] == 2
    assert report["used"] is True
    assert report["dataset_tags"] == ["feedback-x"]
    assert report["feedback_ids"] == ["f1"]


def test_a_missing_file_trains_on_the_corpus_alone(tmp_path):
    rows, report = train_extractor.load_feedback(tmp_path / "absent.jsonl", weight=3)
    assert rows == []
    assert report["used"] is False
    assert "export_feedback_dataset" in report["reason"]


def test_a_file_labelled_with_another_vocabulary_is_refused(tmp_path):
    path = write(tmp_path, [ROW], labels=["O", "B-SOMETHING-ELSE"])
    with pytest.raises(SystemExit, match="different vocabulary"):
        train_extractor.load_feedback(path, weight=1)
