from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from writing_agent.config import AppConfig

SESSION_COOKIE = "wa_session"
CSRF_COOKIE = "wa_csrf"
_EPHEMERAL_SESSION_SECRET = secrets.token_urlsafe(48)
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class AuthenticationError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(cookie_value: str | None, submitted_value: str) -> None:
    if not cookie_value or not hmac.compare_digest(cookie_value, submitted_value):
        raise AuthenticationError("登录请求的 CSRF 校验失败")


def verify_google_credential(credential: str, client_id: str) -> dict[str, Any]:
    if not client_id:
        raise AuthenticationError("Google 登录尚未配置")
    try:
        claims = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audience=client_id,
            clock_skew_in_seconds=10,
        )
    except Exception as exc:
        raise AuthenticationError("Google 身份凭据无效或已过期") from exc

    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise AuthenticationError("Google 身份签发方无效")
    if claims.get("aud") != client_id:
        raise AuthenticationError("Google 身份凭据不属于当前应用")
    if claims.get("email_verified") is not True:
        raise AuthenticationError("Google 邮箱尚未验证")
    if not claims.get("sub") or not claims.get("email"):
        raise AuthenticationError("Google 身份凭据缺少必要字段")
    return claims


def authorize_claims(claims: dict[str, Any], settings: AppConfig) -> dict[str, Any]:
    email = str(claims.get("email", "")).strip().lower()
    if email not in settings.auth_allowed_emails:
        raise AuthenticationError("该 Google 账号不在访问白名单中")
    return {
        "sub": str(claims["sub"]),
        "email": email,
        "name": str(claims.get("name", "")),
        "picture": str(claims.get("picture", "")),
    }


def _session_secret(settings: AppConfig) -> bytes:
    return (settings.session_secret_key or _EPHEMERAL_SESSION_SECRET).encode("utf-8")


def create_session(user: dict[str, Any], settings: AppConfig) -> str:
    now = int(time.time())
    payload = {
        **user,
        "iat": now,
        "exp": now + settings.session_ttl_seconds,
    }
    encoded = _b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    signature = _b64encode(
        hmac.new(_session_secret(settings), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def read_session(value: str | None, settings: AppConfig) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    encoded, signature = value.rsplit(".", 1)
    expected = _b64encode(
        hmac.new(_session_secret(settings), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64decode(encoded))
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if str(payload.get("email", "")).lower() not in settings.auth_allowed_emails:
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def read_authenticated_user(
    cookie_value: str | None,
    authorization: str | None,
    settings: AppConfig,
) -> dict[str, Any] | None:
    user = read_session(cookie_value, settings)
    if user is not None or not authorization:
        return user
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or len(token) > 8_192:
        return None
    return read_session(token.strip(), settings)


def secure_cookie(settings: AppConfig) -> bool:
    return settings.web_origin.lower().startswith("https://")
