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
    app_env: str = os.getenv("APP_ENV", "development")
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8000"))
    web_origin: str = os.getenv("WEB_ORIGIN", "http://127.0.0.1:8000")
    text_model_name: str = os.getenv("TEXT_MODEL_NAME", "gpt-4o-mini")
    text_api_key: str = os.getenv("OPENAI_API_KEY", "")
    text_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    image_model_name: str = os.getenv("IMAGE_MODEL_NAME", "svg-fallback")
    image_output_dir: Path = ROOT_DIR / os.getenv("IMAGE_OUTPUT_DIR", "generated_images")
    langsmith_api_key: str = os.getenv("LANGSMITH_API_KEY", "")
    langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "writing-agent")

    @property
    def has_text_model(self) -> bool:
        return bool(self.text_api_key)

    @property
    def has_langsmith(self) -> bool:
        return bool(self.langsmith_api_key and self.langsmith_tracing)


@lru_cache(maxsize=1)
def get_settings() -> AppConfig:
    settings = AppConfig()
    settings.image_output_dir.mkdir(parents=True, exist_ok=True)
    return settings
