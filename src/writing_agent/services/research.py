from __future__ import annotations

import json

from writing_agent.schemas.blocks import GenerateRequest, ResearchNote, SourceItem
from writing_agent.services.llm import concise_excerpt, generate_text
from writing_agent.services.tracing import traceable

try:
    from deepagents import create_deep_agent
except ImportError:
    create_deep_agent = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

from writing_agent.config import get_settings
from writing_agent.services.pydantic_compat import model_dump


def _source_note(source_items: list[SourceItem]) -> ResearchNote | None:
    if not source_items:
        return None

    bullets = [
        f"{item.source_kind}/{item.platform}: {item.title}"
        for item in source_items[:4]
    ]
    summary = "；".join(item.summary for item in source_items[:2] if item.summary)
    return ResearchNote(
        title="来源内容摘要",
        summary=summary or "已基于链接来源提炼出关键信息。",
        bullets=bullets,
    )


def _fallback_notes(
    request: GenerateRequest,
    source_items: list[SourceItem] | None = None,
) -> list[ResearchNote]:
    material_excerpt = "；".join(
        concise_excerpt(material.content, width=80) for material in request.materials[:3]
    )
    notes = [
        ResearchNote(
            title="用户目标拆解",
            summary=f"围绕“{request.topic}”产出兼顾小红书与公众号的图文内容。",
            bullets=[
                f"受众：{request.audience}",
                f"语气：{request.tone}",
                f"目标：{request.goal}",
            ],
        ),
        ResearchNote(
            title="素材要点提炼",
            summary=material_excerpt or "当前未提供详细素材，成稿会更多依赖主题常识和结构化表达。",
            bullets=[material.content[:60] for material in request.materials[:4]],
        ),
        ResearchNote(
            title="图文表达建议",
            summary="小红书需要更强的首屏钩子和高频配图，公众号需要章节化与视觉留白。",
            bullets=[
                "封面图突出主题与场景",
                "段间插图用于切换节奏和承接小标题",
                "结尾加入明确互动或行动建议",
            ],
        ),
    ]
    source_note = _source_note(source_items or [])
    if source_note is not None:
        notes.insert(1, source_note)
    return notes


def _coerce_deepagents_output(raw: object) -> list[ResearchNote]:
    content = ""
    if isinstance(raw, dict):
        messages = raw.get("messages", [])
        if messages:
            last = messages[-1]
            content = str(last.get("content", ""))
    else:
        content = str(raw)

    try:
        parsed = json.loads(content)
        notes = [ResearchNote(**item) for item in parsed]
        if notes:
            return notes
    except Exception:
        pass

    return [
        ResearchNote(
            title="DeepAgents 研究摘要",
            summary=concise_excerpt(content, width=180),
            bullets=[line.strip("- ").strip() for line in content.splitlines()[:5] if line.strip()],
        )
    ]


@traceable(name="run_research")
def run_research(
    request: GenerateRequest,
    source_items: list[SourceItem] | None = None,
) -> list[ResearchNote]:
    settings = get_settings()
    if create_deep_agent is None or ChatOpenAI is None or not settings.has_text_model:
        return _fallback_notes(request, source_items)

    try:
        model_kwargs = {"model": settings.text_model_name, "api_key": settings.text_api_key}
        if settings.text_base_url:
            model_kwargs["base_url"] = settings.text_base_url
        model = ChatOpenAI(**model_kwargs)
        agent = create_deep_agent(
            model=model,
            system_prompt=(
                "你是中文内容研究员。请为后续写作流程输出研究结论，"
                "只返回 JSON 数组，每项包含 title、summary、bullets。"
            ),
        )
        prompt = (
            f"主题：{request.topic}\n"
            f"受众：{request.audience}\n"
            f"语气：{request.tone}\n"
            f"目标：{request.goal}\n"
            f"素材：{[model_dump(material) for material in request.materials]}\n"
            f"来源摘要：{[model_dump(item) for item in (source_items or [])]}\n"
            "请给出 3 条研究摘要，突出平台差异、事实支撑方向和配图建议。"
        )
        raw = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        notes = _coerce_deepagents_output(raw)
        source_note = _source_note(source_items or [])
        if source_note is not None:
            notes.insert(0, source_note)
        return notes
    except Exception:
        return _fallback_notes(request, source_items)


def improve_with_feedback(notes: list[ResearchNote], feedback: str) -> list[ResearchNote]:
    if not feedback:
        return notes

    note = ResearchNote(
        title="人工反馈补充",
        summary=feedback,
        bullets=[
            "后续改稿要优先吸收该反馈",
            "图片风格与图文节奏也应向反馈靠拢",
        ],
    )
    return [*notes, note]


def summarize_notes(notes: list[ResearchNote]) -> str:
    return "\n".join(
        f"- {note.title}: {note.summary}" for note in notes
    )
