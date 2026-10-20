from __future__ import annotations

from dataclasses import dataclass

import httpx

from writing_agent.config import get_settings

NON_TEXT_MODEL_MARKERS = (
    "image",
    "dall-e",
    "audio",
    "whisper",
    "tts",
    "embed",
    "moderation",
    "auto-review",
)


@dataclass(frozen=True)
class ModelOption:
    id: str
    available: bool


@dataclass(frozen=True)
class ModelCatalog:
    default_model_id: str
    options: tuple[ModelOption, ...]

    def has(self, model_id: str) -> bool:
        return any(option.id == model_id for option in self.options)


class ModelSelectionError(ValueError):
    pass


def _is_text_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in NON_TEXT_MODEL_MARKERS)


def _fallback_catalog() -> ModelCatalog:
    settings = get_settings()
    option = ModelOption(id=settings.text_model_name, available=settings.has_text_model)
    return ModelCatalog(default_model_id=option.id, options=(option,))


def discover_models() -> ModelCatalog:
    """List selectable text models by asking the configured OpenAI-compatible

    endpoint what it currently offers, instead of maintaining a static list.
    Falls back to the single configured default model if the endpoint has no
    key, is unreachable, or returns nothing usable.
    """
    settings = get_settings()
    if not settings.has_text_model:
        return _fallback_catalog()

    base_url = (settings.text_base_url or "https://api.openai.com/v1").rstrip("/")
    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {settings.text_api_key}"},
            timeout=5.0,
        )
        response.raise_for_status()
        raw_ids = [str(item["id"]) for item in response.json().get("data", [])]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return _fallback_catalog()

    text_ids = sorted({model_id for model_id in raw_ids if _is_text_model(model_id)})
    if not text_ids:
        return _fallback_catalog()

    default_model_id = (
        settings.text_model_name if settings.text_model_name in text_ids else text_ids[0]
    )
    options = tuple(ModelOption(id=model_id, available=True) for model_id in text_ids)
    return ModelCatalog(default_model_id=default_model_id, options=options)


def resolve_selected_model_id(model_id: str | None) -> str | None:
    if model_id is None:
        return None
    catalog = discover_models()
    if not catalog.has(model_id):
        raise ModelSelectionError(f"未知或当前不可用的模型：{model_id}")
    return model_id
