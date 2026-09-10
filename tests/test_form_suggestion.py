import pytest

from writing_agent.models import FormSuggestionRequest
from writing_agent.services.form_suggestion import suggest_form_fields


def test_suggest_form_fields_parses_model_json(monkeypatch):
    monkeypatch.setattr(
        "writing_agent.services.form_suggestion.generate_text_strict",
        lambda _prompt: """```json
        {
          "topic": "一个新 AI 产品值不值得关注",
          "audience": "关注 AI 产品的普通读者",
          "tone": "专业、克制、清楚",
          "goal": "解释产品变化及其适用人群",
          "content_type": "rapid-analysis",
          "source_version": null
        }
        ```""",
    )

    result = suggest_form_fields(
        FormSuggestionRequest(
            materials=[{"kind": "text", "content": "某公司发布了新的 AI 产品。"}]
        )
    )

    assert result.topic == "一个新 AI 产品值不值得关注"
    assert result.content_type.value == "rapid-analysis"


def test_suggest_form_supports_original_idea_without_external_source(monkeypatch):
    captured = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return """{
          "topic": "Harness 工程不是提示词工程",
          "audience": "负责 AI Agent 落地的研发工程师",
          "tone": "专业、克制、清楚",
          "goal": "解释 Harness 工程的边界和实践价值",
          "content_type": "opinion",
          "source_version": null,
          "core_question": "Harness 工程究竟在解决什么问题？",
          "initial_thesis": "它解决的是模型之外的可靠执行环境问题。",
          "analysis_target": null
        }"""

    monkeypatch.setattr(
        "writing_agent.services.form_suggestion.generate_text_strict",
        fake_generate,
    )
    result = suggest_form_fields(
        FormSuggestionRequest(
            creation_mode="original-idea",
            core_question="Harness 工程解决什么问题？",
            initial_thesis="重点不只是提示词，而是完整执行环境。",
        )
    )

    assert result.content_type.value == "opinion"
    assert "作者问题/观点驱动" in captured["prompt"]


def test_suggest_form_rejects_empty_input():
    with pytest.raises(ValueError, match="线索、作者笔记或分析对象"):
        suggest_form_fields(FormSuggestionRequest())


def test_suggest_form_downgrades_unverified_review_to_product_analysis(monkeypatch):
    monkeypatch.setattr(
        "writing_agent.services.form_suggestion.generate_text_strict",
        lambda _prompt: """{
          "topic": "一个产品的能力边界",
          "audience": "需要评估产品的技术团队",
          "tone": "专业、克制",
          "goal": "解释产品能力与限制",
          "content_type": "product-review"
        }""",
    )

    result = suggest_form_fields(
        FormSuggestionRequest(
            materials=[{"kind": "text", "content": "只有产品介绍，没有实测记录。"}]
        )
    )

    assert result.content_type.value == "product-analysis"
    assert result.source_items


def test_suggest_form_keeps_review_when_real_practice_record_exists(monkeypatch):
    monkeypatch.setattr(
        "writing_agent.services.form_suggestion.generate_text_strict",
        lambda _prompt: """{
          "topic": "产品实测",
          "audience": "准备选型的开发者",
          "tone": "专业、克制",
          "goal": "说明真实测试结果",
          "content_type": "product-review"
        }""",
    )

    result = suggest_form_fields(
        FormSuggestionRequest(
            materials=[
                {
                    "kind": "practice_record",
                    "content": "我在本地环境完成了安装、登录、数据查询、导出和异常恢复测试。"
                    "测试记录包含具体版本、环境、步骤、成功结果、失败情况和已知限制，"
                    "所有结论只覆盖本次实际执行过的任务。",
                }
            ]
        )
    )

    assert result.content_type.value == "product-review"
