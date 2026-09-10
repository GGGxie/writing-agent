from pathlib import Path

from writing_agent.config import AppConfig
from writing_agent.services.auth import create_session, read_authenticated_user, read_session


def _settings() -> AppConfig:
    return AppConfig(
        app_env="test",
        host="127.0.0.1",
        port=8000,
        web_origin="http://test",
        text_model_name="test",
        text_api_key="",
        text_base_url="",
        text_request_timeout_seconds=180,
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
        google_client_id="client.apps.googleusercontent.com",
        auth_allowed_emails=("gavinxie1219@gmail.com",),
        session_secret_key="test-secret-that-is-at-least-thirty-two-bytes",
        session_ttl_seconds=3600,
        max_request_bytes=1_048_576,
        max_concurrent_generations=2,
    )


def test_signed_session_rejects_tampering_and_non_whitelisted_email():
    settings = _settings()
    token = create_session(
        {"sub": "1", "email": "gavinxie1219@gmail.com", "name": "Gavin"},
        settings,
    )
    assert read_session(token, settings)["email"] == "gavinxie1219@gmail.com"
    assert read_session(f"{token}x", settings) is None

    other = create_session({"sub": "2", "email": "other@example.com", "name": "Other"}, settings)
    assert read_session(other, settings) is None


def test_signed_session_accepts_bearer_fallback():
    settings = _settings()
    token = create_session(
        {"sub": "1", "email": "gavinxie1219@gmail.com", "name": "Gavin"},
        settings,
    )

    user = read_authenticated_user(None, f"Bearer {token}", settings)
    assert user and user["email"] == "gavinxie1219@gmail.com"
    assert read_authenticated_user(None, f"Basic {token}", settings) is None
