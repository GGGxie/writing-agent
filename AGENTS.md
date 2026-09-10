# 公众号内容项目规范

本项目是面向微信公众号与小红书的中文图文写作 Agent。`tech-ai-wechat` 编辑档案用于生产广义科技与 AI 公众号内容，不把账号定位为 Cursor、AI IDE 或开发者工具账号。

## 开始工作前

- 修改编辑策略、选题、策划或写作逻辑前阅读 `resources/editorial/positioning.md` 与 `resources/editorial/voice-guide.md`。
- 涉及时效性事实、产品能力、人物言论、数据或版本信息时，再阅读 `resources/editorial/source-policy.md`。
- 根据内容类型选择 `resources/editorial/templates/` 中最接近的模板；模板是检查框架，不是必须机械保留的标题结构。
- 需要完整流程时使用项目 Skill：`.agents/skills/wechat-editorial/SKILL.md`。

## 编辑原则

- 以研发工程师的求证方式观察科技与 AI，但不把账号限制为编程、源码或 AI IDE 垂类。
- X、社区讨论和热榜用于发现线索，原始公告、论文、代码、实测结果用于确认事实。
- 清楚区分“已确认事实”“基于材料的推断”和“作者判断”。
- 不虚构亲身经历、测试过程、用户反馈、采访、数据或引语。
- 不模仿任何具体创作者的标志性措辞或人设；只借鉴可复用的编辑方法。
- 热点内容优先保证准确，再追求速度。信息不足时生成研究卡或选题建议，不伪装成完整报道。
- 未经用户明确确认，不代替用户对外发布内容、发送消息或作商业承诺。

## 文件状态

- `workspace/signals/`：尚未验证的线索。
- `workspace/research/`：已聚合来源的事件材料包。
- `workspace/drafts/`：待编辑、待核查或待确认的文章。
- `workspace/published/`：确认发布后的定稿副本。
- SQLite 只保存采集索引与去重状态；可编辑内容以 Markdown 为准。
- API 和自动化最多生成 `draft` 或 `fact-checked`，不得自行设置 `approved`。

## 工程原则

- Python 是唯一应用运行时；不要重新引入独立 Node.js 采集服务。
- X/RSSHub 采集进程与 FastAPI 请求进程分开运行，共享工作区和 SQLite。
- 网络或模型失败必须显式进入 warnings/错误，不得静默伪装为已研究或已完成的文章。
- `platforms`、`content_type`、证据闸门必须真实影响图执行结果。

## 完成标准

一篇可发布稿必须做到：标题不超出证据、核心事实可追溯、时效信息带日期、作者判断有依据、第一人称经历真实、读者能明确知道这件事与自己有什么关系。
