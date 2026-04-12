from writing_agent.config import get_settings
from writing_agent.schemas.blocks import GenerateRequest, MaterialInput, Platform
from writing_agent.services.pipeline import run_pipeline


def test_pipeline_generates_two_platform_drafts(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = run_pipeline(
        GenerateRequest(
            topic="如何把文章写得更有图文感",
            materials=[
                MaterialInput(content="希望内容更有留白，不要全是长段落。"),
                MaterialInput(content="需要封面和段间插图，并保留 Markdown 导出。"),
            ],
        )
    )

    assert response.topic == "如何把文章写得更有图文感"
    assert len(response.generated_images) >= 2
    assert {draft.platform for draft in response.drafts} == {
        Platform.XIAOHONGSHU,
        Platform.WECHAT,
    }
    assert all(draft.blocks for draft in response.drafts)


def test_pipeline_resolves_article_and_video_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))
    get_settings.cache_clear()

    def fake_fetch(url: str) -> dict[str, str]:
        return {
            "title": f"标题:{url}",
            "summary": "这是提取到的摘要。",
            "site_name": "test-site",
            "content_excerpt": "这是正文摘要。",
        }

    monkeypatch.setattr(
        "writing_agent.services.source_resolver.fetch_url_metadata",
        fake_fetch,
    )

    response = run_pipeline(
        GenerateRequest(
            topic="多来源图文写作",
            materials=[
                MaterialInput(kind="article", content="https://mp.weixin.qq.com/s/demo", source="https://mp.weixin.qq.com/s/demo"),
                MaterialInput(kind="video", content="https://www.youtube.com/watch?v=demo", source="https://www.youtube.com/watch?v=demo"),
            ],
        )
    )

    assert len(response.source_items) == 2
    assert {item.source_kind for item in response.source_items} == {"article", "video"}
    assert all(item.fetched for item in response.source_items)
    assert any(note.title == "来源内容摘要" for note in response.research_notes)
