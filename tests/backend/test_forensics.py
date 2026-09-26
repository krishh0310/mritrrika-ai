"""Gemini forensic checks: reply parsing and the UNABLE_TO_VERIFY fallback."""

from types import SimpleNamespace

import httpx
import pytest
from app.services import forensic_service as fs


def test_parse_json_tolerates_fences_and_prose():
    reply = 'Here you go:\n```json\n{"risk_level": "LOW", "risk_score": 12}\n```'
    assert fs.parse_json(reply) == {"risk_level": "LOW", "risk_score": 12}
    with pytest.raises(fs.Unverifiable):
        fs.parse_json("I cannot analyse this image.")


def test_ask_gemini_reads_interactions_reply(monkeypatch):
    settings = SimpleNamespace(gemini_api_key="k", gemini_llm_model="m")
    monkeypatch.setattr(fs, "get_settings", lambda: settings)
    monkeypatch.setattr(fs, "MIN_INTERVAL_SECONDS", 0)
    sent = {}

    def post(url, headers, json, timeout):
        sent.update(json)
        return SimpleNamespace(is_error=False, json=lambda: {"steps": [
            {"type": "model_output",
             "content": [{"type": "text", "text": '{"overall_assessment": "REVIEW"}'}]},
        ]})

    monkeypatch.setattr(httpx, "post", post)
    assert fs.ask_gemini("p", (b"img", "image/png")) == {"overall_assessment": "REVIEW"}
    assert [p["type"] for p in sent["input"]] == ["image", "text"]


def test_no_key_and_failures_store_unable_to_verify(monkeypatch):
    settings = SimpleNamespace(gemini_api_key=None, gemini_llm_model="m")
    monkeypatch.setattr(fs, "get_settings", lambda: settings)
    monkeypatch.setattr(fs, "_values", lambda session, document: {})
    monkeypatch.setattr(fs, "RUNNERS", {
        **fs.RUNNERS,
        "tamper": lambda s, d, v: fs.ask_gemini("p"),
        "fraud": lambda s, d, v: {"risk_level": "high", "risk_score": 81},
    })
    added = []
    session = SimpleNamespace(add=added.append, flush=lambda: None)
    document = SimpleNamespace(id="d1", external_id="DOC-1")

    tamper, fraud = fs.run(session, document, ("tamper", "fraud"))

    assert tamper.verdict == fs.UNABLE
    assert tamper.result["error"] == "forensic analysis is not configured"
    assert (fraud.verdict, fraud.score) == ("HIGH", 81.0)
    assert added == [tamper, fraud]
