"""Gemini provider: configuration and client behaviour with an explicitly mocked SDK client.

These do not prove live inference; run the opt-in live tests with a real key for that.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from campuspulse.config import Settings
from campuspulse.gemma_client import GemmaClient
from campuspulse.models import AIError


def gemini_settings(key="test-key"):
    return replace(Settings(), provider="gemini", gemini_api_key=key)


def test_gemini_is_remote_and_labelled_honestly():
    s = gemini_settings()
    assert s.model_name == "gemma-4-26b-a4b-it"
    assert s.endpoint_kind == "Remote"  # keeps the consent gate active
    assert "Google" in s.endpoint_label
    assert "test-key" not in repr(s)


def test_ollama_default_unchanged():
    s = Settings()
    assert s.provider == "ollama"
    assert s.endpoint_kind == "Local to app server"


def test_invalid_provider_rejected(monkeypatch):
    monkeypatch.setenv("GEMMA_PROVIDER", "other")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_missing_key_not_ready():
    status = GemmaClient(gemini_settings(key="")).check()
    assert not status.ready and "GEMINI_API_KEY" in status.message


def test_ready_when_model_available():
    sdk = MagicMock()
    status = GemmaClient(gemini_settings(), client=sdk).check()
    assert status.ready
    sdk.models.get.assert_called_once_with(model="gemma-4-26b-a4b-it")


def test_json_returned_from_response_text():
    pytest.importorskip("google.genai")
    sdk = MagicMock()
    sdk.models.generate_content.return_value = SimpleNamespace(text='{"ok": true}')
    out = GemmaClient(gemini_settings(), client=sdk).explanation_json("sys", "payload", {"type": "object"})
    assert out == '{"ok": true}'
    assert sdk.models.generate_content.call_args.kwargs["model"] == "gemma-4-26b-a4b-it"


def test_api_failure_becomes_ai_error():
    pytest.importorskip("google.genai")
    sdk = MagicMock()
    sdk.models.generate_content.side_effect = RuntimeError("boom")
    with pytest.raises(AIError):
        GemmaClient(gemini_settings(), client=sdk).explanation_json("s", "p", {"type": "object"})


def test_fallback_when_native_json_mode_rejected():
    pytest.importorskip("google.genai")
    sdk = MagicMock()
    sdk.models.generate_content.side_effect = [
        RuntimeError("JSON mode is not enabled"),
        SimpleNamespace(text='```json\n{"ok": true}\n```'),
    ]
    out = GemmaClient(gemini_settings(), client=sdk).explanation_json("s", "p", {"type": "object"})
    assert out == '{"ok": true}'
    assert sdk.models.generate_content.call_count == 2


def test_extract_json_handles_prose_and_fences():
    assert GemmaClient._extract_json('Sure! {"a": 1} Done') == '{"a": 1}'
    assert GemmaClient._extract_json("```\n{\"a\": 1}\n```") == '{"a": 1}'
    assert GemmaClient._extract_json(None) == ""


def test_key_alone_selects_gemini(monkeypatch):
    monkeypatch.delenv("GEMMA_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    assert Settings.from_env().provider == "gemini"
