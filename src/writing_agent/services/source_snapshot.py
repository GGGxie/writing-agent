from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from writing_agent.config import AppConfig
from writing_agent.models import MaterialInput, SourceItem

_EPHEMERAL_SECRET = secrets.token_urlsafe(48)


class SourceSnapshotError(ValueError):
    pass


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret(settings: AppConfig) -> bytes:
    return (settings.session_secret_key or _EPHEMERAL_SECRET).encode("utf-8")


def _materials_digest(materials: list[MaterialInput]) -> str:
    payload = [material.model_dump(mode="json") for material in materials]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_source_snapshot(
    materials: list[MaterialInput],
    source_items: list[SourceItem],
    settings: AppConfig,
) -> str:
    payload = {
        "exp": int(time.time()) + 3_600,
        "materials_digest": _materials_digest(materials),
        "source_items": [item.model_dump(mode="json") for item in source_items],
    }
    encoded = _encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    signature = _encode(
        hmac.new(_secret(settings), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def read_source_snapshot(
    token: str,
    materials: list[MaterialInput],
    settings: AppConfig,
) -> list[SourceItem]:
    if "." not in token:
        raise SourceSnapshotError("来源检查结果格式无效")
    encoded, signature = token.rsplit(".", 1)
    expected = _encode(
        hmac.new(_secret(settings), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected):
        raise SourceSnapshotError("来源检查结果签名无效")
    try:
        payload = json.loads(_decode(encoded))
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise SourceSnapshotError("来源检查结果已过期")
        if payload.get("materials_digest") != _materials_digest(materials):
            raise SourceSnapshotError("素材已经变化")
        return [SourceItem(**item) for item in payload.get("source_items", [])]
    except SourceSnapshotError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SourceSnapshotError("来源检查结果无法读取") from exc
