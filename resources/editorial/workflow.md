# 编辑工作流

## 1. 线索

在 `inbox/signals/` 新建 Markdown，记录原始链接、发现时间、来源账号、初步价值和待确认问题。此阶段不得把线索改写成事实。

## 2. 事件材料包

在 `research/` 聚合同一事件，至少包含：

- 事件时间线与首次发现时间；
- 原始公告、代码、论文或完整发言；
- 已确认事实；
- 尚未确认、互相冲突或可能被夸大的信息；
- 对核心读者的影响；
- 可以加入的独立价值：实测、源码、工具或判断；
- 候选标题和适合的内容类型。

## 3. 选择成稿类型

- 事实已确认但细节有限：闪讯。
- 需要解释变化和影响：快速解读。
- 只有产品官方资料、尚未实测：产品解析。
- 已完成实测或掌握大量原始材料：深度稿或产品实测。
- 重点回答一个实现问题：开源/源码解析。
- 发布自己的产品：自研工具发布。

对应模板都在 `templates/`。模板中的提示文字在成稿前删除。

## 4. 起草与审校

先保证事实骨架，再写标题和开头。完成后分别进行两次审校：

1. **事实审校**：逐项对照来源，检查日期、数字、归因、版本、引语和不确定性。
2. **编辑审校**：检查读者收益、作者声线、重复、空话、标题承诺和移动端阅读体验。

运行：

```bash
python3 scripts/check_article.py drafts/文件名.md
```

脚本只做机械检查，不能替代事实审校。

## 5. 发布闸门

发布前确认：

- 关键来源仍可访问，事实没有在写作期间变化；
- 标题没有把推断写成事实；
- 第一人称经历与实测记录真实；
- 图片、引语与商业关系已妥善标注；
- `status` 已由用户明确确认改为 `approved`。

任何自动化只能生成线索、研究材料或草稿。对外发布必须由用户明确确认。

## 文章元数据

新文章使用以下 frontmatter：

```yaml
---
title: "文章标题"
content_type: "rapid-analysis"
status: "draft"
created_at: "2026-09-07"
updated_at: "2026-09-07"
event_time: "2026-09-07T10:00:00+08:00"
tags: ["AI", "产品"]
source_checked_at: "2026-09-07T12:00:00+08:00"
---
```

`content_type` 可用：`flash-news`、`rapid-analysis`、`deep-dive`、`product-analysis`、`product-review`、`open-source-analysis`、`tool-release`、`opinion`。

`status` 可用：`idea`、`researching`、`draft`、`fact-checked`、`approved`、`published`、`archived`。
