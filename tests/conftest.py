import pytest

from writing_agent.config import get_settings


@pytest.fixture(autouse=True)
def isolate_tests_from_live_services(monkeypatch):
    """Prevent tests from using credentials loaded from the production .env."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("IMAGE_MODEL_NAME", "svg-fallback")
    monkeypatch.setenv("IMAGE_API_KEY", "")
    monkeypatch.setenv("IMAGE_BASE_URL", "")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("X_BEARER_TOKEN", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
