import asyncio
from types import SimpleNamespace

from writing_agent.services import llm


def test_build_text_model_configures_compatible_endpoint_and_retries(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    settings = SimpleNamespace(
        has_text_model=True,
        text_model_name="gpt-5.6-terra",
        text_api_key="local-proxy-key",
        text_base_url="http://127.0.0.1:8317/v1",
        text_request_timeout_seconds=180.0,
        text_max_retries=3,
    )
    monkeypatch.setattr(llm, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    assert llm.build_text_model() is not None
    assert captured == {
        "model": "gpt-5.6-terra",
        "api_key": "local-proxy-key",
        "base_url": "http://127.0.0.1:8317/v1",
        "timeout": 180.0,
        "max_retries": 3,
    }


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

    settings = SimpleNamespace(
        has_text_model=True,
        text_api_key="local-proxy-key",
        text_base_url="http://127.0.0.1:8317/v1",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)

    assert asyncio.run(llm.text_model_ready()) is True
    assert requested["url"] == "http://127.0.0.1:8317/v1/models"
    assert requested["headers"] == {"Authorization": "Bearer local-proxy-key"}
    assert requested["client_kwargs"] == {"timeout": 5.0}
