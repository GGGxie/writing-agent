from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    host: str
    port: int
    web_origin: str
    text_model_name: str
    text_api_key: str
    text_base_url: str
    text_request_timeout_seconds: float
    text_max_retries: int
    image_model_name: str
    image_api_key: str
    image_base_url: str
    image_request_timeout_seconds: float
    image_quality: str
    image_size: str
    image_max_concurrency: int
    image_output_dir: Path
    langsmith_api_key: str
    langsmith_tracing: bool
    langsmith_project: str
    workspace_dir: Path
    editorial_resources_dir: Path
    sources_config_path: Path
    collector_database_path: Path
    x_bearer_token: str
    source_request_timeout_seconds: float
    auth_required: bool
    google_client_id: str
    auth_allowed_emails: tuple[str, ...]
    session_secret_key: str
    session_ttl_seconds: int
    max_request_bytes: int
    max_concurrent_generations: int

    @property
    def has_text_model(self) -> bool:
        return bool(self.text_api_key)

    @property
    def has_langsmith(self) -> bool:
        return bool(self.langsmith_api_key and self.langsmith_tracing)

    @property
    def auth_configured(self) -> bool:
        return bool(self.google_client_id and self.auth_allowed_emails)


@lru_cache(maxsize=1)
def get_settings() -> AppConfig:
    def project_path(env_name: str, default: str) -> Path:
        value = Path(os.getenv(env_name, default))
        return value if value.is_absolute() else ROOT_DIR / value

    allowed_emails = tuple(
        value.strip().lower()
        for value in os.getenv("AUTH_ALLOWED_EMAILS", "").split(",")
        if value.strip()
    )
    settings = AppConfig(
        app_env=os.getenv("APP_ENV", "development"),
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        web_origin=os.getenv("WEB_ORIGIN", "http://127.0.0.1:8000"),
        text_model_name=os.getenv("TEXT_MODEL_NAME", "gpt-5.6-terra"),
        text_api_key=os.getenv("OPENAI_API_KEY", ""),
        text_base_url=os.getenv("OPENAI_BASE_URL", ""),
        text_request_timeout_seconds=float(
            os.getenv("TEXT_REQUEST_TIMEOUT_SECONDS", "180")
        ),
        text_max_retries=max(0, int(os.getenv("TEXT_MAX_RETRIES", "3"))),
        image_model_name=os.getenv("IMAGE_MODEL_NAME", "svg-fallback"),
        image_api_key=os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
        image_base_url=(
            os.getenv("IMAGE_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ),
        image_request_timeout_seconds=float(
            os.getenv("IMAGE_REQUEST_TIMEOUT_SECONDS", "240")
        ),
        image_quality=os.getenv("IMAGE_QUALITY", "low"),
        image_size=os.getenv("IMAGE_SIZE", "1024x1024"),
        image_max_concurrency=max(1, int(os.getenv("IMAGE_MAX_CONCURRENCY", "2"))),
        image_output_dir=project_path("IMAGE_OUTPUT_DIR", "generated_images"),
        langsmith_api_key=os.getenv("LANGSMITH_API_KEY", ""),
        langsmith_tracing=os.getenv("LANGSMITH_TRACING", "false").lower()
        in {"1", "true", "yes", "on"},
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "writing-agent"),
        workspace_dir=project_path("EDITORIAL_WORKSPACE_DIR", "workspace"),
        editorial_resources_dir=project_path("EDITORIAL_RESOURCES_DIR", "resources/editorial"),
        sources_config_path=project_path("SOURCES_CONFIG_PATH", "config/sources.yaml"),
        collector_database_path=project_path(
            "COLLECTOR_DATABASE_PATH", "workspace/.collector.sqlite3"
        ),
        x_bearer_token=os.getenv("X_BEARER_TOKEN", ""),
        source_request_timeout_seconds=float(os.getenv("SOURCE_REQUEST_TIMEOUT_SECONDS", "20")),
        auth_required=os.getenv("AUTH_REQUIRED", "true").lower() in {"1", "true", "yes", "on"},
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        auth_allowed_emails=allowed_emails,
        session_secret_key=os.getenv("SESSION_SECRET_KEY", "").strip(),
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "43200")),
        max_request_bytes=int(os.getenv("MAX_REQUEST_BYTES", "1048576")),
        max_concurrent_generations=max(1, int(os.getenv("MAX_CONCURRENT_GENERATIONS", "2"))),
    )
    settings.image_output_dir.mkdir(parents=True, exist_ok=True)
    for directory in ("signals", "research", "drafts", "published"):
        (settings.workspace_dir / directory).mkdir(parents=True, exist_ok=True)
    return settings
