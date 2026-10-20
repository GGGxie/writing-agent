from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

from fastapi.responses import JSONResponse

from writing_agent.config import AppConfig
from writing_agent.services.auth import SESSION_COOKIE, read_authenticated_user

PUBLIC_PATHS = {
    "/",
    "/favicon.ico",
    "/health",
    "/ready",
    "/api/auth/config",
    "/api/auth/google",
    "/api/auth/logout",
    "/api/auth/me",
}


class SecurityBoundaryMiddleware:
    """Apply request limits, authentication and browser security headers."""

    def __init__(self, app: Any, settings: AppConfig):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"cross-origin-opener-policy", b"same-origin-allow-popups"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                        (
                            b"permissions-policy",
                            b"camera=(), microphone=(), geolocation=(), "
                            b"identity-credentials-get=(self)",
                        ),
                    ]
                )
                message["headers"] = response_headers
            await send(message)

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        method = scope.get("method", "GET")
        content_length = headers.get("content-length")
        if content_length and method in {"POST", "PUT", "PATCH"}:
            try:
                if int(content_length) > self.settings.max_request_bytes:
                    await JSONResponse({"detail": "请求体过大"}, status_code=413)(
                        scope, receive, send_with_security_headers
                    )
                    return
            except ValueError:
                await JSONResponse({"detail": "Content-Length 无效"}, status_code=400)(
                    scope, receive, send_with_security_headers
                )
                return

        path = scope.get("path", "")
        is_public = (
            path in PUBLIC_PATHS
            or path.startswith("/assets/")
            or path.startswith("/generated_images/")
        )
        if self.settings.auth_required and not is_public:
            if not self.settings.auth_configured:
                await JSONResponse({"detail": "Google 登录尚未完成配置"}, status_code=503)(
                    scope, receive, send_with_security_headers
                )
                return
            cookies = SimpleCookie()
            cookies.load(headers.get("cookie", ""))
            session_cookie = cookies.get(SESSION_COOKIE)
            session_value = session_cookie.value if session_cookie else None
            user = read_authenticated_user(
                session_value,
                headers.get("authorization"),
                self.settings,
            )
            if user is None:
                await JSONResponse({"detail": "需要登录"}, status_code=401)(
                    scope, receive, send_with_security_headers
                )
                return
            scope.setdefault("state", {})["user"] = user

        await self.app(scope, receive, send_with_security_headers)
