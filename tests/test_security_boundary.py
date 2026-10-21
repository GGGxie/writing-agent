"""公网边界回归测试（GitHub Issue #1）。

writing.gggxie.com 经 Cloudflare Tunnel 直达本服务，认证完全依赖 SecurityBoundaryMiddleware。
这里保证两件事不会悄悄退化：
- 已配置认证时，公开清单以外的每个路由在没有会话时都返回 401；
- 请求体上限按实际读取的字节计算，分块传输（无 Content-Length）也不能绕过。
"""

import asyncio
import re

import httpx
import pytest
from fastapi.routing import APIRoute
from starlette.routing import Mount

from writing_agent.api.main import create_app
from writing_agent.api.security import PUBLIC_PATHS
from writing_agent.config import get_settings

BODY_LIMIT = 1024
PUBLIC_PREFIXES = ("/assets", "/generated_images")


@pytest.fixture
def protected_app(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("WEB_ORIGIN", "http://test")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "owner@example.com")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-secret-that-is-at-least-thirty-two-bytes")
    monkeypatch.setenv("MAX_REQUEST_BYTES", str(BODY_LIMIT))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    get_settings.cache_clear()
    yield create_app()
    get_settings.cache_clear()


def _send(app, method, path, **kwargs):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _protected_endpoints(app):
    endpoints = []
    for route in app.routes:
        if isinstance(route, Mount):
            continue
        path = route.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            continue
        concrete = re.sub(r"\{[^}]+\}", "probe", path)
        if isinstance(route, APIRoute):
            methods = route.methods
        else:
            methods = getattr(route, "methods", None) or {"GET"}
        for method in sorted(methods - {"HEAD"}):
            endpoints.append((method, concrete))
    return endpoints


def test_route_inventory_covers_the_sensitive_endpoints(protected_app):
    endpoints = set(_protected_endpoints(protected_app))
    # 会调用付费模型、写入数据或暴露接口文档的入口必须在受保护清单里
    for expected in [
        ("POST", "/api/generate"),
        ("POST", "/api/generate/jobs"),
        ("POST", "/api/revise"),
        ("POST", "/api/revise/jobs"),
        ("POST", "/api/suggest_form"),
        ("POST", "/api/summarize_sources"),
        ("POST", "/api/relay_signal"),
        ("POST", "/api/collect/rss"),
        ("GET", "/api/signals"),
        ("GET", "/api/jobs/probe"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
    ]:
        assert expected in endpoints, expected


def test_every_non_public_route_requires_a_session(protected_app):
    leaked = []
    for method, path in _protected_endpoints(protected_app):
        response = _send(protected_app, method, path, json={} if method == "POST" else None)
        if response.status_code != 401:
            leaked.append((method, path, response.status_code))
    assert not leaked, f"未登录即可访问: {leaked}"


def test_forged_session_is_rejected(protected_app):
    response = _send(
        protected_app,
        "POST",
        "/api/generate",
        json={},
        headers={
            "Authorization": "Bearer forged.signature",
            "Cookie": "wa_session=forged.signature",
        },
    )
    assert response.status_code == 401


def test_declared_oversized_body_is_rejected(protected_app):
    response = _send(
        protected_app,
        "POST",
        "/api/auth/google",
        content=b"x" * (BODY_LIMIT + 1),
        headers={"Content-Type": "application/json", "Origin": "http://test"},
    )
    assert response.status_code == 413


def test_chunked_oversized_body_is_rejected(protected_app):
    async def chunks():
        for _ in range(4):
            yield b"x" * (BODY_LIMIT // 2)

    response = _send(
        protected_app,
        "POST",
        "/api/auth/google",
        content=chunks(),
        headers={"Content-Type": "application/json", "Origin": "http://test"},
    )
    assert "content-length" not in {k.lower() for k in response.request.headers}
    assert response.status_code == 413


def test_chunked_body_within_limit_still_reaches_the_route(protected_app):
    async def chunks():
        yield b'{"credential": "x", '
        yield b'"csrf_token": "not-the-cookie-value"}'

    response = _send(
        protected_app,
        "POST",
        "/api/auth/google",
        content=chunks(),
        headers={"Content-Type": "application/json", "Origin": "http://test"},
    )
    # 到达登录路由：CSRF 不匹配被拒绝，而不是被请求体上限拦截
    assert response.status_code == 403
