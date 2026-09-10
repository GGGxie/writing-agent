export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
}

function renderParagraph(value) {
  const lines = String(value || "").split("\n").filter((line) => line.trim());
  if (lines.length && lines.every((line) => /^[-*]\s+/.test(line))) {
    const items = lines.map((line) => (
      `<li>${renderInlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>`
    ));
    return `<ul>${items.join("")}</ul>`;
  }
  if (lines.length && lines.every((line) => /^\d+[.)]\s+/.test(line))) {
    const items = lines.map((line) => (
      `<li>${renderInlineMarkdown(line.replace(/^\d+[.)]\s+/, ""))}</li>`
    ));
    return `<ol>${items.join("")}</ol>`;
  }
  return `<p>${lines.map(renderInlineMarkdown).join("<br />")}</p>`;
}

function sourceItemHtml(item) {
  const tierState = item.tier_verified ? "已确认等级" : "仅声明等级";
  const sourceUrl = item.url ? ` · ${escapeHtml(item.url)}` : "";
  const excerpt = item.content_excerpt
    ? `<div class="hint">${escapeHtml(item.content_excerpt)}</div>`
    : "";
  const fetchError = item.fetch_error
    ? `<div class="source-error">抓取失败：${escapeHtml(item.fetch_error)}</div>`
    : "";
  return `
    <div class="block summary">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.summary)}</p>
      ${excerpt}
      <div class="hint">
        ${escapeHtml(item.source_tier)}级 · ${tierState} ·
        ${escapeHtml(item.source_kind)} · ${escapeHtml(item.platform)}${sourceUrl}
      </div>
      ${fetchError}
    </div>`;
}

function renderSourceItems(items) {
  return `
    <div class="draft">
      <h2>素材与来源</h2>
      ${(items || []).map(sourceItemHtml).join("")}
    </div>
  `;
}

function renderArticleBlock(block) {
  if (block.type === "cover" || block.type === "image") {
    return `
      <figure class="article-image ${block.type}">
        <img src="${escapeHtml(block.image_url)}" alt="${escapeHtml(block.alt_text || "")}" />
        ${block.caption ? `<figcaption>${escapeHtml(block.caption)}</figcaption>` : ""}
      </figure>
    `;
  }
  if (!block.text || block.type === "title") return "";
  if (block.type === "heading") return `<h3>${renderInlineMarkdown(block.text)}</h3>`;
  if (block.type === "quote") return `<blockquote>${renderInlineMarkdown(block.text)}</blockquote>`;
  if (["summary", "tips", "tags"].includes(block.type)) {
    return `<aside class="article-callout">${renderParagraph(block.text)}</aside>`;
  }
  return renderParagraph(block.text);
}

export function responseHtml(data) {
  const topicScore = data.topic_score
    ? `${data.topic_score.total}/25 · ${data.topic_score.recommendation}`
    : "未评分";
  const gate = data.evidence_gate;
  const evidenceCounts = gate
    ? `${gate.primary_source_count}/${gate.reliable_source_count}/${gate.signal_source_count}`
    : "";
  const draftDecision = gate?.can_draft ? "允许生成草稿" : "只生成研究材料";
  const gateSummary = gate
    ? `A/B/C：${evidenceCounts} · ${draftDecision}`
    : "";
  const missingRequirements = (gate?.missing_requirements || [])
    .map((item) => `<div class="hint">缺失：${escapeHtml(item)}</div>`)
    .join("");
  const warnings = (data.warnings || [])
    .map((item) => `<div class="hint">提醒：${escapeHtml(item)}</div>`)
    .join("");
  const research = `
    <div class="draft">
      <h2>选题与证据闸门</h2>
      <p>${escapeHtml(topicScore)}</p>
      <div class="hint">${escapeHtml(gateSummary)}</div>
      ${missingRequirements}
      ${warnings}
    </div>
    <div class="columns">
      ${renderSourceItems(data.source_items || [])}
      <div class="draft">
        <h2>研究摘要</h2>
        ${data.research_notes.map((note) => `
          <div class="block summary">
            <strong>${escapeHtml(note.title)}</strong>
            <p>${escapeHtml(note.summary)}</p>
            <div class="hint">${escapeHtml((note.bullets || []).join(" · "))}</div>
          </div>`).join("")}
      </div>
      <div class="draft">
        <h2>配图计划</h2>
        ${data.image_plan.map((item) => `
          <div class="block tips">
            <strong>${escapeHtml(item.purpose)}</strong>
            <p>${escapeHtml(item.placement_hint)}</p>
            <div class="hint">${escapeHtml(item.prompt)}</div>
          </div>`).join("")}
      </div>
    </div>
  `;

  const drafts = data.drafts.map((draft) => {
    const articleBlocks = (draft.blocks || []).map(renderArticleBlock).join("");
    const qualityLines = draft.quality
      ? [
          ...(draft.quality.blockers || []),
          ...(draft.quality.findings || []),
          "",
          ...(draft.quality.suggestions || []),
        ]
      : [];
    const qualityDetails = draft.quality ? `
      <details>
        <summary>查看质检结果（${draft.quality.score} 分）</summary>
        <pre>${escapeHtml(qualityLines.join("\n"))}</pre>
      </details>` : "";
    return `
      <article class="draft article-preview">
        <span class="badge">${escapeHtml(draft.platform)}</span>
        <h2>${escapeHtml(draft.title)}</h2>
        <p class="meta article-deck">${renderInlineMarkdown(draft.summary)}</p>
        <div class="article-body">${articleBlocks}</div>
        <details>
          <summary>查看 Markdown 导出</summary>
          <pre>${escapeHtml(draft.markdown)}</pre>
        </details>
        ${qualityDetails}
      </article>
    `;
  }).join("");
  return { research, drafts };
}

export function sourceSummaryHtml(data) {
  return `<div class="columns">${renderSourceItems(data.source_items || [])}</div>`;
}

export function signalsHtml(items) {
  const signals = items.map((item, index) => `
    <div class="block summary">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.content)}</p>
      <div class="hint">
        ${escapeHtml(item.source_tier)}级 · ${escapeHtml(item.source_name)} ·
        ${escapeHtml(item.url)}
      </div>
      <button class="secondary signal-create-button" data-signal-index="${index}">
        基于此线索创作
      </button>
    </div>`).join("");
  return `
    <div class="draft">
      <h2>最近线索</h2>
      ${signals || '<div class="hint">当前没有采集线索。</div>'}
    </div>`;
}
