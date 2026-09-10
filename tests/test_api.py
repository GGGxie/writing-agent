import asyncio

import httpx

from writing_agent.api.main import create_app
from writing_agent.config import ROOT_DIR, get_settings
from writing_agent.models import FormSuggestionResponse

MODEL_ARTICLE = """# 工具发布：解决重复整理素材的问题

这是工具的完整说明，原始材料见 https://example.com/tool 。

## 为什么做

它解决了重复整理素材的问题。

## 限制

当前仍需要人工确认输出。
"""


def _prepare(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "writing_agent.graph.nodes.draft_wechat.generate_text_strict",
        lambda _prompt: MODEL_ARTICLE,
    )
    return create_app()


def _request(app, method: str, path: str, **kwargs):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_generate_endpoint_returns_wechat_draft(tmp_path, monkeypatch):
    app = _prepare(tmp_path, monkeypatch)
    response = _request(
        app,
        "POST",
        "/api/generate",
        json={
            "workflow_id": "workflow-generate-001",
            "topic": "我的素材整理工具",
            "content_type": "tool-release",
            "platforms": ["wechat"],
            "materials": [
                {
                    "kind": "tool_record",
                    "content": "这个工具用于整理来源、生成研究材料和草稿，当前实现地址是 https://example.com/tool，并保留人工发布闸门。",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["workflow_id"] == "workflow-generate-001"
    assert data["run_id"]
    assert [draft["platform"] for draft in data["drafts"]] == ["wechat"]
    assert data["evidence_gate"]["can_draft"] is True


def test_generate_endpoint_returns_research_when_evidence_missing(tmp_path, monkeypatch):
    app = _prepare(tmp_path, monkeypatch)
    response = _request(
        app,
        "POST",
        "/api/generate",
        json={
            "topic": "没有来源的新产品传闻",
            "content_type": "rapid-analysis",
            "materials": [{"kind": "text", "content": "听说某产品要发布"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "researching"
    assert data["drafts"] == []
    assert data["evidence_gate"]["can_draft"] is False


def test_summarize_sources_endpoint(tmp_path, monkeypatch):
    app = _prepare(tmp_path, monkeypatch)

    def fake_fetch(url: str) -> dict[str, str]:
        return {
            "title": f"标题:{url}",
            "summary": "来源摘要",
            "site_name": "demo-site",
            "content_excerpt": "来源正文摘要",
        }

    monkeypatch.setattr(
        "writing_agent.services.source_resolver.fetch_url_metadata",
        fake_fetch,
    )
    response = _request(
        app,
        "POST",
        "/api/summarize_sources",
        json={
            "workflow_id": "workflow-sources-001",
            "topic": "先总结再写",
            "materials": [
                {
                    "kind": "article",
                    "content": "https://example.com/demo",
                    "source": "https://example.com/demo",
                }
            ],
        },
    )
    assert response.status_code == 200
    summary = response.json()
    assert summary["workflow_id"] == "workflow-sources-001"
    assert len(summary["source_items"]) == 1
    assert summary["source_summary_token"]

    def fail_if_sources_are_fetched_again(_materials):
        raise AssertionError("confirmed source summary should be reused")

    monkeypatch.setattr(
        "writing_agent.graph.nodes.ingest.resolve_source_inputs",
        fail_if_sources_are_fetched_again,
    )
    generate = _request(
        app,
        "POST",
        "/api/generate",
        json={
            "topic": "先总结再写",
            "content_type": "opinion",
            "source_summary_token": summary["source_summary_token"],
            "materials": [
                {
                    "kind": "article",
                    "content": "https://example.com/demo",
                    "source": "https://example.com/demo",
                }
            ],
        },
    )
    assert generate.status_code == 200
    assert generate.json()["source_items"][0]["title"].startswith("标题:")


def test_signals_endpoint_starts_empty(tmp_path, monkeypatch):
    app = _prepare(tmp_path, monkeypatch)
    response = _request(app, "GET", "/api/signals")
    assert response.status_code == 200
    assert response.json() == []


def test_suggest_form_endpoint_returns_editable_fields(tmp_path, monkeypatch):
    app = _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "writing_agent.api.main.suggest_form_fields",
        lambda _request: FormSuggestionResponse(
            topic="OpenAI 发布新功能：对内容创作者有什么影响",
            audience="关注 AI 产品的内容创作者",
            tone="专业、克制、清楚",
            goal="解释变化、证据边界和适用人群",
            content_type="rapid-analysis",
        ),
    )

    response = _request(
        app,
        "POST",
        "/api/suggest_form",
        json={"materials": [{"kind": "text", "content": "OpenAI 发布了一项新功能"}]},
    )

    assert response.status_code == 200
    assert response.json()["content_type"] == "rapid-analysis"
    assert response.json()["topic"].startswith("OpenAI")
    assert response.json()["source_summary_token"]


def test_suggested_source_snapshot_avoids_duplicate_source_analysis(tmp_path, monkeypatch):
    app = _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "writing_agent.api.main.suggest_form_fields",
        lambda _request: FormSuggestionResponse(
            topic="Example Product 的能力边界",
            audience="准备评估产品的开发者",
            tone="专业、克制",
            goal="解释能力和限制",
            content_type="product-analysis",
            source_items=[
                {
                    "source_kind": "article",
                    "url": "https://product.example/",
                    "platform": "product",
                    "title": "Example Product",
                    "summary": "官方产品说明",
                    "fetched": True,
                    "source_tier": "A",
                    "tier_reason": "发布主体官网首页或产品主页",
                    "tier_verified": True,
                }
            ],
        ),
    )
    materials = [
        {
            "kind": "article",
            "content": "https://product.example/",
            "source": "https://product.example/",
        }
    ]
    suggestion = _request(
        app,
        "POST",
        "/api/suggest_form",
        json={"workflow_id": "workflow-cache-001", "materials": materials},
    ).json()

    monkeypatch.setattr(
        "writing_agent.services.pipeline.summarize_only",
        lambda _materials: (_ for _ in ()).throw(
            AssertionError("来源快照存在时不应重复抓取")
        ),
    )
    summary = _request(
        app,
        "POST",
        "/api/summarize_sources",
        json={
            "workflow_id": "workflow-cache-001",
            "topic": suggestion["topic"],
            "content_type": suggestion["content_type"],
            "materials": materials,
            "source_summary_token": suggestion["source_summary_token"],
        },
    )

    assert summary.status_code == 200
    assert summary.json()["source_items"][0]["title"] == "Example Product"


def test_homepage_is_public_and_actions_are_login_gated(tmp_path, monkeypatch):
    app = _prepare(tmp_path, monkeypatch)
    response = _request(app, "GET", "/")

    assert response.status_code == 200
    html = response.text
    assert '<script type="module" src="/assets/app.js?v=20260910-1"></script>' in html
    assert '<link rel="stylesheet" href="/assets/styles.css?v=20260910-1" />' in html
    html = "\n".join(
        (
            html,
            (ROOT_DIR / "web/app.js").read_text(encoding="utf-8"),
            (ROOT_DIR / "web/render.js").read_text(encoding="utf-8"),
            (ROOT_DIR / "web/styles.css").read_text(encoding="utf-8"),
        )
    )
    assert '<div class="shell" id="appShell">' in html
    assert 'id="authGate"' in html
    assert 'id="authGate" role="dialog"' in html
    assert "公开作品预览" not in html
    assert "登录成功 · 可以使用全部功能" not in html
    assert "作品演示" not in html
    assert "浏览演示模式" not in html
    assert "requireAuthentication" in html
    assert "use_fedcm_for_button: true" in html
    assert 'id="generateButton"' in html
    assert 'id="topic" placeholder=' in html
    assert 'id="topic" value=' not in html
    assert "请先填写主题" in html
    assert "请先填写线索、作者笔记或分析对象" in html
    assert "readableApiError" in html
    assert "renderInlineMarkdown" in html
    assert 'class="article-body"' in html
    assert ".article-body p" in html
    assert 'id="suggestButton"' in html
    assert 'authFetch("/api/suggest_form"' in html
    assert 'id="creationMode"' in html
    assert 'value="original-idea"' in html
    assert 'value="artifact-analysis"' in html
    assert 'value="product-analysis"' in html
    assert 'id="authorNotes"' in html
    assert 'id="artifactNotes"' in html
    assert '>分析素材与来源</button>' in html
    assert '>生成图文草稿</button>' in html
    assert "素材尚未分析，请先点击“分析素材与来源”" in html
    assert "抓取失败：" in html
    assert "基于此线索创作" in html
    assert "signal-create-button" in html
    assert 'id="actionFeedback"' in html
    assert "runButtonAction" in html
    assert "已等待" in html
    assert 'button.setAttribute("aria-busy", "true")' in html
    assert "setActionButtonsDisabled(true)" in html
    assert "sessionStorageKey" in html
    assert "data.source_summary_token" in html
    assert "authFetch" in html
    assert 'credentials: "include"' in html
    assert response.headers["cross-origin-opener-policy"] == "same-origin-allow-popups"
    assert "identity-credentials-get=(self)" in response.headers["permissions-policy"]


def test_auth_fails_closed_when_google_is_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "gavinxie1219@gmail.com")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    get_settings.cache_clear()
    app = create_app()

    assert _request(app, "GET", "/health").status_code == 200
    assert _request(app, "GET", "/").status_code == 200
    assert _request(app, "GET", "/api/signals").status_code == 503
    ready = _request(app, "GET", "/ready")
    assert ready.status_code == 503
    assert ready.json()["checks"]["auth"] is False


def test_google_login_allows_only_whitelisted_email(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("COLLECTOR_DATABASE_PATH", str(tmp_path / "collector.sqlite3"))
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("WEB_ORIGIN", "http://test")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "gavinxie1219@gmail.com")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-secret-that-is-at-least-thirty-two-bytes")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "writing_agent.api.main.verify_google_credential",
        lambda _credential, _client_id: {
            "sub": "google-user-1",
            "email": "gavinxie1219@gmail.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": "client.apps.googleusercontent.com",
        },
    )
    app = create_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            config = await client.get("/api/auth/config")
            csrf_token = config.json()["csrf_token"]
            login = await client.post(
                "/api/auth/google",
                headers={"Origin": "http://test"},
                json={"credential": "signed-google-token", "csrf_token": csrf_token},
            )
            assert login.status_code == 200
            assert login.json()["user"]["email"] == "gavinxie1219@gmail.com"
            session_token = login.json()["session_token"]
            signals = await client.get("/api/signals")
            assert signals.status_code == 200

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            me = await client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {session_token}"},
            )
            assert me.json()["authenticated"] is True
            signals = await client.get(
                "/api/signals",
                headers={"Authorization": f"Bearer {session_token}"},
            )
            assert signals.status_code == 200

    asyncio.run(run())
