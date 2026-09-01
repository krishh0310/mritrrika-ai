from types import SimpleNamespace

import httpx
from app.services import rag_service


def _answer():
    return rag_service.Answer(answer="structured", records=[{"parcel_id": "P-1"}])


def test_groq_falls_back_when_gemini_is_unavailable(monkeypatch):
    settings = SimpleNamespace(llm_provider="gemini")
    monkeypatch.setattr(rag_service, "get_settings", lambda: settings)
    monkeypatch.setattr(
        rag_service, "_generate_gemini", lambda _settings, _prompt: (_ for _ in ()).throw(
            RuntimeError("offline")
        )
    )
    monkeypatch.setattr(rag_service, "_generate_groq", lambda _settings, _prompt: "Groq answer")

    result = rag_service.explain(_answer(), "What is recorded?")

    assert result.answer == "Groq answer"
    assert result.llm_used is True
    assert result.degraded is False


def test_structured_answer_survives_when_all_providers_fail(monkeypatch):
    settings = SimpleNamespace(llm_provider="groq")
    monkeypatch.setattr(rag_service, "get_settings", lambda: settings)
    monkeypatch.setattr(rag_service, "_generate_groq", lambda _settings, _prompt: "")
    monkeypatch.setattr(rag_service, "_generate_gemini", lambda _settings, _prompt: "")

    result = rag_service.explain(_answer(), "What is recorded?")

    assert result.answer == "structured"
    assert result.llm_used is False
    assert result.degraded is True


def test_gemini_authorization_key_uses_interactions_response(monkeypatch):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "steps": [
                {"type": "thought"},
                {"type": "model_output", "content": [{"type": "text", "text": "OK"}]},
            ]
        },
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    settings = SimpleNamespace(gemini_api_key="AQ.test", gemini_llm_model="gemini-test")

    assert rag_service._generate_gemini(settings, "test") == "OK"
