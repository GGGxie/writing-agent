import asyncio
from pathlib import Path

from writing_agent.config import AppConfig
from writing_agent.services import llm


def _settings(**overrides) -> AppConfig:
    defaults = dict(
        app_env="test",
        host="127.0.0.1",
        port=8000,
        web_origin="http://test",
        text_model_name="gpt-5.6-terra",
        text_api_key="local-proxy-key",
        text_base_url="http://127.0.0.1:8317/v1",
        text_request_timeout_seconds=180.0,
        text_max_retries=3,
        image_model_name="svg-fallback",
        image_api_key="",
        image_base_url="https://api.openai.com/v1",
        image_request_timeout_seconds=240,
        image_quality="low",
        image_size="1024x1024",
        image_max_concurrency=2,
        image_output_dir=Path("/tmp/writing-agent-test-images"),
        langsmith_api_key="",
        langsmith_tracing=False,
        langsmith_project="test",
        workspace_dir=Path("/tmp/writing-agent-test-workspace"),
        editorial_resources_dir=Path("/tmp/writing-agent-test-resources"),
        sources_config_path=Path("/tmp/writing-agent-test-sources.yaml"),
        collector_database_path=Path("/tmp/writing-agent-test.sqlite3"),
        x_bearer_token="",
        source_request_timeout_seconds=20,
        auth_required=True,
        google_client_id="",
        auth_allowed_emails=(),
        session_secret_key="test-secret-that-is-at-least-thirty-two-bytes",
        session_ttl_seconds=3600,
        max_request_bytes=1_048_576,
        max_concurrent_generations=2,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_build_text_model_configures_compatible_endpoint_and_retries(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())

    assert llm.build_text_model() is not None
    assert captured == {
        "model": "gpt-5.6-terra",
        "api_key": "local-proxy-key",
        "base_url": "http://127.0.0.1:8317/v1",
        "timeout": 180.0,
        "max_retries": 3,
    }


def test_build_text_model_uses_selected_model_id_as_override(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())

    assert llm.build_text_model("gpt-5.6-sol") is not None
    assert captured["model"] == "gpt-5.6-sol"
    assert captured["api_key"] == "local-proxy-key"


def test_build_text_model_unavailable_returns_none(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(text_api_key=""))

    assert llm.build_text_model() is None


def test_text_model_ready_checks_compatible_models_endpoint(monkeypatch):
    requested = {}

    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            requested["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            requested["url"] = url
            requested["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)

    assert asyncio.run(llm.text_model_ready()) is True
    assert requested["url"] == "http://127.0.0.1:8317/v1/models"
    assert requested["headers"] == {"Authorization": "Bearer local-proxy-key"}
    assert requested["client_kwargs"] == {"timeout": 5.0}
