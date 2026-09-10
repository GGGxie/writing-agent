from __future__ import annotations

import logging
from textwrap import shorten

import httpx

from writing_agent.config import get_settings
from writing_agent.services.tracing import traceable

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None


logger = logging.getLogger(__name__)


def build_text_model() -> ChatOpenAI | None:
    settings = get_settings()
    if ChatOpenAI is None or not settings.has_text_model:
        return None

    kwargs = {
        "model": settings.text_model_name,
        "api_key": settings.text_api_key,
        "timeout": settings.text_request_timeout_seconds,
        "max_retries": settings.text_max_retries,
    }
    if settings.text_base_url:
        kwargs["base_url"] = settings.text_base_url
    return ChatOpenAI(**kwargs)


async def text_model_ready() -> bool:
    """Check a configured compatible endpoint without issuing a model turn."""
    settings = get_settings()
    if not settings.has_text_model:
        return False
    if not settings.text_base_url:
        return True

    url = f"{settings.text_base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {settings.text_api_key}"},
            )
        return response.status_code == 200
    except httpx.HTTPError:
        logger.warning("文本模型兼容端点就绪检查失败", exc_info=True)
        return False


def _response_text(response: object) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif getattr(item, "text", None):
                parts.append(str(item.text))
        return " ".join(part for part in parts if part).strip()
    return str(content).strip()


@traceable(name="generate_text")
def generate_text(prompt: str, fallback: str) -> str:
    client = build_text_model()
    if client is None:
        return fallback

    try:
        response = client.invoke(prompt)
        return _response_text(response) or fallback
    except Exception:
        logger.exception("非关键文本模型调用失败，已使用显式 fallback")
        return fallback


@traceable(name="generate_text_strict")
def generate_text_strict(prompt: str) -> str:
    """Generate text without disguising model or network failures as a finished draft."""
    client = build_text_model()
    if client is None:
        raise RuntimeError("未配置可用的文本模型，已保留研究材料但不会伪造完整文章")
    try:
        content = _response_text(client.invoke(prompt))
    except Exception as exc:
        raise RuntimeError(f"文本模型调用失败：{exc}") from exc
    if not content:
        raise RuntimeError("文本模型返回空内容")
    return content


def concise_excerpt(text: str, width: int = 120) -> str:
    return shorten(" ".join(text.split()), width=width, placeholder="...")
