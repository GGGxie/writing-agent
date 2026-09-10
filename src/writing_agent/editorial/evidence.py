from __future__ import annotations

from urllib.parse import urlparse

from writing_agent.models import (
    ContentType,
    CreationMode,
    EvidenceGateResult,
    GenerateRequest,
    SourceItem,
    SourceTier,
    TopicScoreResult,
    WorkflowStatus,
)

SIGNAL_HOSTS = {
    "x.com",
    "twitter.com",
    "reddit.com",
    "news.ycombinator.com",
    "producthunt.com",
}
PRIMARY_HOSTS = {
    "arxiv.org",
    "doi.org",
    "github.com",
    "gitlab.com",
}


def infer_source_tier(
    *,
    url: str | None,
    kind: str,
    explicit: SourceTier | None = None,
) -> tuple[SourceTier, str]:
    if explicit is not None:
        return explicit, "由提交素材显式指定"
    if kind in {"test_record", "practice_record", "tool_record", "code_record"}:
        return SourceTier.A, "用户提供的原始实测、工具或源码阅读记录"
    if kind == "author_note":
        return SourceTier.UNCLASSIFIED, "作者观点与笔记，不作为外部事实证据"
    if not url:
        return SourceTier.UNCLASSIFIED, "普通文本未声明证据类型"
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in SIGNAL_HOSTS or any(host.endswith(f".{item}") for item in SIGNAL_HOSTS):
        return SourceTier.C, "社区或社交平台线索"
    if host in PRIMARY_HOSTS or any(host.endswith(f".{item}") for item in PRIMARY_HOSTS):
        return SourceTier.A, "代码、论文或原始材料托管平台"
    if urlparse(url).path in {"", "/"}:
        return SourceTier.A, "发布主体官网首页或产品主页"
    return SourceTier.B, "可追溯网页，尚未确认是否为发布主体原始材料"


def score_topic(request: GenerateRequest, sources: list[SourceItem]) -> TopicScoreResult:
    primary = sum(
        item.source_tier == SourceTier.A and item.tier_verified and (item.fetched or not item.url)
        for item in sources
    )
    reliable = sum(item.source_tier == SourceTier.B and item.fetched for item in sources)
    signal = sum(item.source_tier == SourceTier.C for item in sources)
    timeliness = 5 if request.event_time else 3
    relevance = 4 if request.audience and request.audience != "泛内容读者" else 3
    author_foundation = bool(
        (request.initial_thesis and len(request.initial_thesis.strip()) >= 10)
        or any(
            item.kind == "author_note" and len(item.content.strip()) >= 80
            for item in request.materials
        )
    )
    credibility = (
        5 if primary >= 2 else 4 if primary == 1 else 3 if reliable else 1 if signal else 0
    )
    if request.creation_mode == CreationMode.ORIGINAL_IDEA and author_foundation:
        credibility = max(credibility, 3)
    has_unique_material = any(
        item.kind
        in {"test_record", "practice_record", "code_record", "tool_record", "author_note"}
        and len(item.content.strip()) >= 40
        for item in request.materials
    )
    if request.content_type in {ContentType.PRODUCT_REVIEW, ContentType.TOOL_RELEASE}:
        uniqueness = 5 if has_unique_material else 3
    elif request.content_type == ContentType.OPEN_SOURCE_ANALYSIS:
        uniqueness = 4 if has_unique_material else 3
    elif request.creation_mode == CreationMode.ORIGINAL_IDEA:
        uniqueness = 4 if author_foundation else 3
    else:
        uniqueness = 3
    extensibility = 4 if request.content_type != ContentType.FLASH_NEWS else 3
    total = timeliness + relevance + credibility + uniqueness + extensibility
    if credibility < 3:
        recommendation = "只进入研究，不直接成稿"
    elif total >= 20:
        recommendation = "优先研究"
    elif total >= 15:
        recommendation = "进入候选"
    else:
        recommendation = "通常不写"
    return TopicScoreResult(
        timeliness=timeliness,
        relevance=relevance,
        credibility=credibility,
        uniqueness=uniqueness,
        extensibility=extensibility,
        total=total,
        recommendation=recommendation,
    )


def evaluate_evidence(
    request: GenerateRequest,
    sources: list[SourceItem],
    topic_score: TopicScoreResult,
) -> EvidenceGateResult:
    primary = [
        item
        for item in sources
        if item.source_tier == SourceTier.A
        and item.tier_verified
        and (item.fetched or not item.url)
    ]
    reliable = [item for item in sources if item.source_tier == SourceTier.B and item.fetched]
    signals = [item for item in sources if item.source_tier == SourceTier.C]
    traceable = [item for item in sources if item.url and item.fetched]
    missing: list[str] = []
    reasons: list[str] = []
    substantial_author_note = any(
        material.kind == "author_note" and len(material.content.strip()) >= 80
        for material in request.materials
    )
    has_initial_thesis = bool(
        request.initial_thesis and len(request.initial_thesis.strip()) >= 10
    )
    has_core_question = bool(request.core_question and request.core_question.strip())

    if request.creation_mode == CreationMode.ORIGINAL_IDEA:
        if not has_core_question:
            missing.append("一个明确的核心问题")
        if not has_initial_thesis:
            missing.append("不少于 10 字的初步观点")
        if not substantial_author_note:
            missing.append("不少于 80 字的作者笔记")

    if request.creation_mode == CreationMode.ARTIFACT_ANALYSIS:
        if not request.analysis_target or not request.analysis_target.strip():
            missing.append("明确的源码、产品或实践分析对象")
        if not has_core_question:
            missing.append("围绕分析对象的核心问题")

    if request.content_type in {ContentType.FLASH_NEWS, ContentType.RAPID_ANALYSIS}:
        if not primary:
            missing.append("至少一个 A 级原始来源")
    elif request.content_type == ContentType.DEEP_DIVE:
        if not primary:
            missing.append("至少一个 A 级原始来源")
        if len(traceable) < 2:
            missing.append("至少两个可追溯来源")
    elif request.content_type == ContentType.PRODUCT_ANALYSIS:
        if not primary:
            missing.append("至少一个 A 级官方产品来源")
    elif request.content_type == ContentType.PRODUCT_REVIEW:
        valid_test_record = any(
            material.kind in {"test_record", "practice_record"}
            and len(material.content.strip()) >= 80
            for material in request.materials
        )
        if not valid_test_record:
            missing.append("不少于 80 字的真实实测或实践记录")
    elif request.content_type == ContentType.OPEN_SOURCE_ANALYSIS:
        has_code_source = any(
            item.source_tier == SourceTier.A
            and item.tier_verified
            and item.fetched
            and item.url
            and (urlparse(item.url).hostname or "").lower() in {"github.com", "gitlab.com"}
            for item in sources
        )
        if not has_code_source:
            missing.append("GitHub 或 GitLab 原始代码来源")
        if not request.source_version:
            missing.append("仓库 commit、tag 或分支版本")
        has_code_record = any(
            material.kind in {"code_record", "practice_record"}
            and len(material.content.strip()) >= 80
            for material in request.materials
        )
        if request.creation_mode == CreationMode.ARTIFACT_ANALYSIS and not has_code_record:
            missing.append("不少于 80 字的源码阅读或运行验证记录")
    elif request.content_type == ContentType.TOOL_RELEASE:
        valid_tool_record = any(
            material.kind == "tool_record" and len(material.content.strip()) >= 40
            for material in request.materials
        )
        if not valid_tool_record:
            missing.append("不少于 40 字的工具说明或构建记录（material.kind=tool_record）")
    elif request.content_type == ContentType.OPINION:
        if request.creation_mode != CreationMode.ORIGINAL_IDEA and not traceable:
            missing.append("至少一个可追溯来源")
        if request.creation_mode == CreationMode.ORIGINAL_IDEA and not traceable:
            reasons.append("这是作者观点稿；外部事实仍需另行补充可追溯来源")

    if signals and not primary and not reliable:
        reasons.append("目前只有 C 级线索来源，不能写成确定性报道")
    if topic_score.credibility < 3 and request.content_type not in {
        ContentType.PRODUCT_REVIEW,
        ContentType.TOOL_RELEASE,
    } and request.creation_mode != CreationMode.ORIGINAL_IDEA:
        reasons.append("选题可信度评分低于 3")
    if missing:
        reasons.append("证据未达到该内容类型的最低要求")

    can_draft = not missing and not (
        signals
        and not primary
        and not reliable
        and request.content_type
        in {ContentType.FLASH_NEWS, ContentType.RAPID_ANALYSIS, ContentType.DEEP_DIVE}
    )
    return EvidenceGateResult(
        can_draft=can_draft,
        next_status=WorkflowStatus.DRAFT if can_draft else WorkflowStatus.RESEARCHING,
        primary_source_count=len(primary),
        reliable_source_count=len(reliable),
        signal_source_count=len(signals),
        reasons=reasons,
        missing_requirements=missing,
    )
