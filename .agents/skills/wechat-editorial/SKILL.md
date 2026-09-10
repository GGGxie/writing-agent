---
name: wechat-editorial
description: Plan, research, draft, edit, or review Chinese WeChat articles about broad technology and AI, including timely news, product tests, open-source analysis, original tools, and evidence-based commentary.
---

# 微信公众号编辑

服务本项目的完整编辑流程。旧文章的主题不代表账号定位，不要默认把选题收窄到 Cursor、AI IDE、编程工具或任何单一产品类别。

## 路由

- 选题、栏目或账号规划：阅读 `../../../resources/editorial/positioning.md` 和 `../../../resources/editorial/content-strategy.md`。
- 起草、改写或统一风格：阅读 `../../../resources/editorial/positioning.md` 和 `../../../resources/editorial/voice-guide.md`，再选择 `../../../resources/editorial/templates/` 中最接近的文章模板。
- 热点、人物言论、产品版本、数据、论文或源码：额外阅读 `../../../resources/editorial/source-policy.md`。
- 从线索推进到发布准备：阅读 `../../../resources/editorial/workflow.md`。

只加载当前任务所需的模板，不要为了“完整”读取所有模板。

## 内容类型

- `flash-news`：核心事实已由原始来源确认，需要快速说明发生了什么。
- `rapid-analysis`：解释变化、背景、影响和被忽略的限制。
- `deep-dive`：拥有足够原始材料、实测或技术证据的深入分析。
- `product-analysis`：基于官方资料解释产品定位、能力与限制，不声称作者已经实测。
- `product-review`：作者确实使用过产品，并能说明条件、结果和失败。
- `open-source-analysis`：围绕一个实现问题解释代码、调用链或设计取舍。
- `tool-release`：发布作者自己的工具和真实构建过程。
- `opinion`：基于清楚证据和评价标准的个人判断。

如果证据不足，只生成线索卡或事件材料包，不用补写猜测凑成文章。

## 工作要求

1. 明确文章为谁解决什么问题，再决定标题和结构。
2. 涉及时效信息时主动核对当前原始来源，记录绝对日期与核查时间。
3. 把事实、基于材料的推断和作者判断分开表达。
4. 第一人称只能承载用户提供或当前任务真实完成的经历；不得虚构实测、采访、反馈和数据。
5. 模板提供检查框架，不要求文章保留对称的小标题。
6. 保持研发工程师的求证方式，但让结论对非研发读者也可读。
7. 完稿后通过应用的质量检查节点或 `writing-agent check <draft>` 检查；机械检查通过不等于事实已经核准。

## 发布边界

本 Skill 可以完成研究、写作和发布前准备，但不能把 `draft` 自行改为 `approved`，也不能在没有用户明确确认时对外发布、发送或作商业承诺。
