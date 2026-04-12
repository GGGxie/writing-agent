from __future__ import annotations

from textwrap import shorten

from writing_agent.config import get_settings
from writing_agent.services.tracing import traceable

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None


def _build_client() -> ChatOpenAI | None:
    settings = get_settings()
    if ChatOpenAI is None or not settings.has_text_model:
        return None

    kwargs = {"model": settings.text_model_name, "api_key": settings.text_api_key}
    if settings.text_base_url:
        kwargs["base_url"] = settings.text_base_url
    return ChatOpenAI(**kwargs)


@traceable(name="generate_text")
def generate_text(prompt: str, fallback: str) -> str:
    client = _build_client()
    if client is None:
        return fallback

    try:
        response = client.invoke(prompt)
        content = getattr(response, "content", "")
        if isinstance(content, list):
            return " ".join(str(item) for item in content if item).strip() or fallback
        return str(content).strip() or fallback
    except Exception:
        return fallback


def concise_excerpt(text: str, width: int = 120) -> str:
    return shorten(" ".join(text.split()), width=width, placeholder="...")
