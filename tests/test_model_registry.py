import httpx
import pytest

from writing_agent.config import get_settings
from writing_agent.services import model_registry
from writing_agent.services.model_registry import (
    ModelSelectionError,
    discover_models,
    resolve_selected_model_id,
)


def _reload(monkeypatch):
    get_settings.cache_clear()


def _fake_models_response(ids):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": model_id} for model_id in ids]}

    return FakeResponse()


def test_discover_models_without_api_key_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TEXT_MODEL_NAME", "gpt-test")
    _reload(monkeypatch)

    catalog = discover_models()

    assert catalog.default_model_id == "gpt-test"
    assert len(catalog.options) == 1
    assert catalog.options[0].available is False


def test_discover_models_filters_non_text_models(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TEXT_MODEL_NAME", "gpt-5.6-terra")
    _reload(monkeypatch)

    def fake_get(url, headers=None, timeout=None):
        assert url.endswith("/models")
        assert headers == {"Authorization": "Bearer sk-test"}
        return _fake_models_response(
            [
                "gpt-5.6-terra",
                "gpt-5.6-sol",
                "gpt-image-1.5",
                "codex-auto-review",
            ]
        )

    monkeypatch.setattr(model_registry.httpx, "get", fake_get)

    catalog = discover_models()

    ids = {option.id for option in catalog.options}
    assert ids == {"gpt-5.6-terra", "gpt-5.6-sol"}
    assert catalog.default_model_id == "gpt-5.6-terra"
    assert all(option.available for option in catalog.options)


def test_discover_models_falls_back_on_request_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TEXT_MODEL_NAME", "gpt-test")
    _reload(monkeypatch)

    def fake_get(url, headers=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(model_registry.httpx, "get", fake_get)

    catalog = discover_models()

    assert catalog.default_model_id == "gpt-test"
    assert len(catalog.options) == 1


def test_discover_models_falls_back_when_only_non_text_models_available(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TEXT_MODEL_NAME", "gpt-test")
    _reload(monkeypatch)

    def fake_get(url, headers=None, timeout=None):
        return _fake_models_response(["gpt-image-1.5", "codex-auto-review"])

    monkeypatch.setattr(model_registry.httpx, "get", fake_get)

    catalog = discover_models()

    assert catalog.default_model_id == "gpt-test"
    assert len(catalog.options) == 1


def test_resolve_selected_model_id_none_never_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    _reload(monkeypatch)
    assert resolve_selected_model_id(None) is None


def test_resolve_selected_model_id_unknown_id_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TEXT_MODEL_NAME", "gpt-test")
    _reload(monkeypatch)

    with pytest.raises(ModelSelectionError):
        resolve_selected_model_id("does-not-exist")


def test_resolve_selected_model_id_known_id_returns_it(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TEXT_MODEL_NAME", "gpt-5.6-terra")
    _reload(monkeypatch)

    def fake_get(url, headers=None, timeout=None):
        return _fake_models_response(["gpt-5.6-terra", "gpt-5.6-sol"])

    monkeypatch.setattr(model_registry.httpx, "get", fake_get)

    assert resolve_selected_model_id("gpt-5.6-sol") == "gpt-5.6-sol"
