from writing_agent.config import get_settings
from writing_agent.graph.nodes.outline import outline_node
from writing_agent.models import (
    ContentType,
    GenerateRequest,
    MaterialInput,
    Platform,
    SourceTier,
    WorkflowStatus,
)
from writing_agent.services.pipeline import run_pipeline

MODEL_ARTICLE = """# 一个经过证据约束的标题

这是完整正文的第一段，说明发生了什么以及它为什么值得关注，并保留来源 https://example.com/source 。

## 已确认的信息

这里仅陈述来源明确支持的事实，不把推断写成事实。

## 对读者的影响

这里解释适用人群、限制和下一步行动。
"""


def test_outline_accepts_full_width_colon_and_skips_article_title(monkeypatch):
    monkeypatch.setattr(
        "writing_agent.graph.nodes.outline.generate_text_strict",
        lambda _prompt, **_kwargs: (
            "标题：不应成为正文段落\n"
            "它是什么：官方定位；核心能力\n"
            "适用边界：适合谁；不适合谁"
        ),
    )
    request = GenerateRequest(topic="产品解析", content_type=ContentType.PRODUCT_ANALYSIS)
    output = outline_node(
        {
            "request": request,
            "research_notes": [],
            "materials": [],
            "warnings": [],
        }
    )

    assert [section.heading for section in output["outline"]] == ["它是什么", "适用边界"]


def _stub_drafting(monkeypatch):
    monkeypatch.setattr(
        "writing_agent.graph.nodes.draft_wechat.generate_text_strict",
        lambda _prompt, **_kwargs: MODEL_ARTICLE,
    )
    monkeypatch.setattr(
        "writing_agent.graph.nodes.draft_xiaohongshu.generate_text_strict",
        lambda _prompt, **_kwargs: MODEL_ARTICLE,
    )


def test_pipeline_generates_only_requested_platforms(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    get_settings.cache_clear()
    _stub_drafting(monkeypatch)

    request = GenerateRequest(
        workflow_id="workflow-pipeline-001",
        topic="我写的开源工具发布",
        content_type=ContentType.TOOL_RELEASE,
        platforms=[Platform.WECHAT],
        materials=[
            MaterialInput(
                kind="tool_record",
                content="工具解决重复整理来源的问题，仓库是 https://example.com/source",
            )
        ],
    )
    response = run_pipeline(request)

    assert response.status == WorkflowStatus.DRAFT
    assert response.workflow_id == request.workflow_id
    assert response.run_id
    assert [draft.platform for draft in response.drafts] == [Platform.WECHAT]
    assert response.evidence_gate and response.evidence_gate.can_draft
    assert all(draft.artifact_path for draft in response.drafts)
    assert any(path.endswith(".md") for path in response.artifact_paths)


def test_signal_only_stops_at_research(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    get_settings.cache_clear()

    def fake_fetch(_url: str) -> dict[str, str]:
        return {
            "title": "X 线索",
            "summary": "一条尚未获得官方确认的说法。",
            "site_name": "X",
            "content_excerpt": "未经确认",
        }

    monkeypatch.setattr(
        "writing_agent.services.source_resolver.fetch_url_metadata",
        fake_fetch,
    )
    response = run_pipeline(
        GenerateRequest(
            topic="未经证实的新模型消息",
            content_type=ContentType.RAPID_ANALYSIS,
            materials=[
                MaterialInput(
                    kind="article",
                    content="https://x.com/example/status/1",
                    source="https://x.com/example/status/1",
                )
            ],
        )
    )

    assert response.status == WorkflowStatus.RESEARCHING
    assert not response.drafts
    assert response.evidence_gate and not response.evidence_gate.can_draft
    assert response.evidence_gate.signal_source_count == 1
    assert response.artifact_paths


def test_primary_source_allows_rapid_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    get_settings.cache_clear()
    _stub_drafting(monkeypatch)

    def fake_fetch(url: str) -> dict[str, str]:
        return {
            "title": f"官方公告:{url}",
            "summary": "这是提取到的官方摘要。",
            "site_name": "official",
            "content_excerpt": "官方在绝对日期发布了更新。",
        }

    monkeypatch.setattr(
        "writing_agent.services.source_resolver.fetch_url_metadata",
        fake_fetch,
    )
    response = run_pipeline(
        GenerateRequest(
            topic="官方产品更新",
            content_type=ContentType.RAPID_ANALYSIS,
            materials=[
                MaterialInput(
                    kind="article",
                    content="https://example.com/official",
                    source="https://example.com/official",
                    source_tier=SourceTier.A,
                    verified_by_user=True,
                )
            ],
        )
    )

    assert response.evidence_gate and response.evidence_gate.can_draft
    assert len(response.drafts) == 1
    assert response.drafts[0].platform == Platform.WECHAT


def test_official_homepage_allows_product_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    get_settings.cache_clear()
    _stub_drafting(monkeypatch)

    monkeypatch.setattr(
        "writing_agent.services.source_resolver.fetch_url_metadata",
        lambda _url: {
            "title": "Example Product",
            "summary": "官方产品说明",
            "site_name": "Example Product",
            "content_excerpt": "官方列出的能力、要求和限制。",
        },
    )
    response = run_pipeline(
        GenerateRequest(
            topic="Example Product 的能力边界",
            content_type=ContentType.PRODUCT_ANALYSIS,
            materials=[
                MaterialInput(
                    kind="article",
                    content="https://product.example/",
                    source="https://product.example/",
                )
            ],
        )
    )

    assert response.evidence_gate and response.evidence_gate.can_draft
    assert response.source_items[0].source_tier == SourceTier.A
    assert response.drafts


def test_evidence_failure_skips_deep_research_model(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    get_settings.cache_clear()
    monkeypatch.setattr(
        "writing_agent.graph.nodes.research.run_research",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("证据不足时不应调用深度研究模型")
        ),
    )

    response = run_pipeline(
        GenerateRequest(
            topic="没有实测记录的产品评测",
            content_type=ContentType.PRODUCT_REVIEW,
            materials=[MaterialInput(kind="text", content="只有产品介绍")],
        )
    )

    assert response.status == WorkflowStatus.RESEARCHING
    assert response.research_notes[0].title == "成稿前需要补充的证据"
    assert not response.drafts


def test_request_cannot_disable_evidence_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    get_settings.cache_clear()
    request = GenerateRequest.model_validate(
        {
            "topic": "没有来源的快讯",
            "content_type": "rapid-analysis",
            "require_evidence": False,
        }
    )
    response = run_pipeline(request)
    assert response.evidence_gate and not response.evidence_gate.can_draft
    assert not response.drafts


def test_generic_text_does_not_unlock_tool_release(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    get_settings.cache_clear()
    response = run_pipeline(
        GenerateRequest(
            topic="工具发布",
            content_type=ContentType.TOOL_RELEASE,
            materials=[MaterialInput(kind="text", content="这只是普通文本")],
        )
    )
    assert response.evidence_gate and not response.evidence_gate.can_draft
    assert not response.drafts


def test_original_idea_can_draft_from_substantial_author_notes(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    get_settings.cache_clear()
    _stub_drafting(monkeypatch)
    response = run_pipeline(
        GenerateRequest(
            topic="Harness 工程不只是提示词工程",
            creation_mode="original-idea",
            core_question="Harness 工程究竟在解决什么问题？",
            initial_thesis="它解决的是模型之外的可靠执行环境问题。",
            content_type=ContentType.OPINION,
            materials=[
                MaterialInput(
                    kind="author_note",
                        content=(
                            "我想从任务状态、工具边界、上下文管理、失败恢复和人工确认几个维度展开。"
                            "核心不是让提示词越来越长，而是让模型在可观察、可约束、可恢复的环境里完成工作。"
                            "文章还要讨论评价标准、反例和适用边界，避免把新的工程概念包装成万能答案。"
                        ),
                )
            ],
        )
    )

    assert response.evidence_gate and response.evidence_gate.can_draft
    assert response.status == WorkflowStatus.DRAFT
    assert response.drafts


def test_artifact_analysis_requires_reading_or_verification_record(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    get_settings.cache_clear()

    def fake_fetch(url: str) -> dict[str, str]:
        return {
            "title": f"仓库:{url}",
            "summary": "项目仓库首页",
            "site_name": "GitHub",
            "content_excerpt": "仓库说明",
        }

    monkeypatch.setattr(
        "writing_agent.services.source_resolver.fetch_url_metadata",
        fake_fetch,
    )
    response = run_pipeline(
        GenerateRequest(
            topic="Codex 的执行循环",
            creation_mode="artifact-analysis",
            core_question="一次任务如何从输入走到工具执行？",
            analysis_target="openai/codex",
            source_version="main",
            content_type=ContentType.OPEN_SOURCE_ANALYSIS,
            materials=[
                MaterialInput(
                    kind="article",
                    content="https://github.com/openai/codex",
                    source="https://github.com/openai/codex",
                )
            ],
        )
    )

    assert response.evidence_gate and not response.evidence_gate.can_draft
    assert any(
        "源码阅读或运行验证记录" in item
        for item in response.evidence_gate.missing_requirements
    )


def test_generated_images_are_isolated_by_run(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    get_settings.cache_clear()
    _stub_drafting(monkeypatch)
    request = GenerateRequest(
        topic="隔离输出的工具发布",
        content_type=ContentType.TOOL_RELEASE,
        materials=[
            MaterialInput(
                kind="tool_record",
                content="这是一个用于验证不同生成任务不会互相覆盖图片和草稿的工具记录，包含实现、结果、限制和后续人工确认步骤。",
            )
        ],
    )
    first = run_pipeline(request)
    second = run_pipeline(request)
    assert first.run_id != second.run_id
    assert first.generated_images[0].file_path != second.generated_images[0].file_path
