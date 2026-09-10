from __future__ import annotations

import base64
import binascii
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from textwrap import wrap
from time import perf_counter

import httpx

from writing_agent.config import get_settings
from writing_agent.models import GeneratedImage, ImagePlanItem
from writing_agent.services.observability import emit_event
from writing_agent.services.tracing import traceable

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _svg_markup(title: str, body: str) -> str:
    body_lines = wrap(body, width=18)[:4]
    body_svg = "".join(
        f'<text x="40" y="{170 + index * 42}" font-size="28" '
        f'fill="#F3F4F6">{html.escape(line)}</text>'
        for index, line in enumerate(body_lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024"
  viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#111827" />
      <stop offset="100%" stop-color="#7C3AED" />
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" rx="48" fill="url(#bg)" />
  <circle cx="830" cy="220" r="160" fill="#F59E0B" fill-opacity="0.2" />
  <circle cx="180" cy="860" r="220" fill="#10B981" fill-opacity="0.14" />
  <text x="40" y="90" font-size="32" fill="#F9FAFB" opacity="0.8">Writing Agent Visual</text>
  <text x="40" y="145" font-size="54" font-weight="700" fill="#FFFFFF">
    {html.escape(title[:24])}
  </text>
  {body_svg}
</svg>"""


def _safe_identifier(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "", value)[:64]
    return normalized or fallback


def _write_bytes(file_path: Path, content: bytes) -> None:
    temporary_path = file_path.with_suffix(f"{file_path.suffix}.tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(file_path)


def _request_image(prompt: str) -> bytes:
    settings = get_settings()
    if not settings.image_api_key:
        raise RuntimeError("未配置图片服务凭据")

    url = f"{settings.image_base_url.rstrip('/')}/images/generations"
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.image_api_key}"},
        json={
            "model": settings.image_model_name,
            "prompt": prompt,
            "n": 1,
            "size": settings.image_size,
            "quality": settings.image_quality,
            "response_format": "b64_json",
            "output_format": "png",
        },
        timeout=settings.image_request_timeout_seconds,
    )
    if response.is_error:
        try:
            error_payload = response.json()
            error_value = error_payload.get("error", error_payload)
            if isinstance(error_value, dict):
                detail = error_value.get("message") or str(error_value)
            else:
                detail = str(error_value)
        except ValueError:
            detail = response.text[:500]
        raise RuntimeError(f"图片服务返回 HTTP {response.status_code}：{detail[:500]}")
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    encoded = data[0].get("b64_json") if isinstance(data, list) and data else None
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("图片服务未返回 b64_json")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("图片服务返回了无效的 base64 数据") from exc
    if not image_bytes:
        raise RuntimeError("图片服务返回了空图片")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError("图片服务返回的文件超过 20MB 限制")
    return image_bytes


def _generate_one(
    item: ImagePlanItem,
    output_dir: Path,
    public_directory: str,
) -> tuple[GeneratedImage, str | None]:
    settings = get_settings()
    image_id = _safe_identifier(item.image_id, "image")
    use_svg = settings.image_model_name.strip().lower() == "svg-fallback"
    started_at = perf_counter()
    prompt = f"{item.prompt}\n视觉风格：{item.style}\n不要添加文字、标题、水印或标志。"

    try:
        if use_svg:
            raise RuntimeError("已配置为本地 SVG 模式")
        file_path = output_dir / f"{image_id}.png"
        image_bytes = _request_image(prompt)
        _write_bytes(file_path, image_bytes)
        emit_event(
            "image.generated",
            run_id=public_directory,
            image_id=image_id,
            purpose=item.purpose,
            provider="openai-compatible",
            model=settings.image_model_name,
            size=settings.image_size,
            quality=settings.image_quality,
            output_bytes=len(image_bytes),
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return (
            GeneratedImage(
                image_id=image_id,
                purpose=item.purpose,
                prompt=item.prompt,
                alt_text=item.alt_text,
                file_path=str(file_path),
                public_url=f"/generated_images/{public_directory}/{file_path.name}",
            ),
            None,
        )
    except Exception as exc:
        file_path = output_dir / f"{image_id}.svg"
        file_path.write_text(_svg_markup(item.purpose, item.prompt), encoding="utf-8")
        warning = None if use_svg else f"配图“{item.purpose}”生成失败，已回退 SVG：{exc}"
        emit_event(
            "image.fallback",
            level=logging.WARNING if warning else logging.INFO,
            error=exc if warning else None,
            run_id=public_directory,
            image_id=image_id,
            purpose=item.purpose,
            configured_model=settings.image_model_name,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return (
            GeneratedImage(
                image_id=image_id,
                purpose=item.purpose,
                prompt=item.prompt,
                alt_text=item.alt_text,
                file_path=str(file_path),
                public_url=f"/generated_images/{public_directory}/{file_path.name}",
            ),
            warning,
        )


@traceable(name="generate_images")
def generate_images(
    items: list[ImagePlanItem], run_id: str
) -> tuple[list[GeneratedImage], list[str]]:
    settings = get_settings()
    safe_run_id = _safe_identifier(run_id, "")
    if not safe_run_id:
        raise ValueError("run_id 无效")
    output_dir: Path = settings.image_output_dir / safe_run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    worker_count = min(settings.image_max_concurrency, len(items))
    if not worker_count:
        return [], []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(
            executor.map(
                lambda item: _generate_one(item, output_dir, safe_run_id),
                items,
            )
        )
    generated = [image for image, _warning in results]
    warnings = [warning for _image, warning in results if warning]
    return generated, warnings
