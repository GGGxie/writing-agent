from fastapi.testclient import TestClient

from writing_agent.api.main import create_app


def test_generate_endpoint_returns_mixed_blocks():
    client = TestClient(create_app())
    response = client.post(
        "/api/generate",
        json={
            "topic": "AI 写作 Agent 如何做出图文感",
            "audience": "内容创作者",
            "tone": "专业但友好",
            "goal": "生成双平台草稿",
            "materials": [
                {"kind": "text", "content": "希望文章不只是大段文字。"},
                {"kind": "text", "content": "需要封面、配图和 Markdown 导出。"},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["drafts"]
    assert len(data["generated_images"]) >= 2
    assert any(block["type"] == "image" for block in data["drafts"][0]["blocks"])


def test_generate_endpoint_returns_source_items(monkeypatch):
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

    client = TestClient(create_app())
    response = client.post(
        "/api/generate",
        json={
            "topic": "多来源内容整理",
            "audience": "内容创作者",
            "tone": "专业但友好",
            "goal": "生成双平台草稿",
            "materials": [
                {"kind": "article", "content": "https://mp.weixin.qq.com/s/demo", "source": "https://mp.weixin.qq.com/s/demo"},
                {"kind": "video", "content": "https://www.youtube.com/watch?v=demo", "source": "https://www.youtube.com/watch?v=demo"},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["source_items"]) == 2
    assert {item["source_kind"] for item in data["source_items"]} == {"article", "video"}


def test_summarize_sources_endpoint(monkeypatch):
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

    client = TestClient(create_app())
    response = client.post(
        "/api/summarize_sources",
        json={
            "topic": "先总结再写",
            "materials": [
                {"kind": "article", "content": "https://mp.weixin.qq.com/s/demo", "source": "https://mp.weixin.qq.com/s/demo"},
                {"kind": "video", "content": "https://www.youtube.com/watch?v=demo", "source": "https://www.youtube.com/watch?v=demo"},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "先总结再写"
    assert len(data["source_items"]) == 2
