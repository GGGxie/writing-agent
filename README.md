# writing-agent

面向微信公众号与小红书的中文图文写作 Agent。项目把高时效信息采集、来源分级、研究材料、内容类型模板、统一作者声线、草稿生成和人工发布闸门放进同一套 Python 应用。

默认编辑档案是：一个研发工程师对科技与 AI 新变化的持续观察——追热点、做实测、拆技术、造工具，判断什么真正有用。

## 工作流

```text
外部线索 ─┐
原创问题 ─┼→ 写作简报 → 素材与来源分析 → 选题评分 → 证据闸门
源码实践 ─┘
      ├── 证据不足 → workspace/research/
      └── 证据满足 → 大纲 → 指定平台草稿 → 机械质检
                                      ↓
                              workspace/drafts/
                                      ↓ 人工确认
                              workspace/published/
```

系统不会自动把内容改成 `approved`，也不会自动发布到外部平台。

## 安装

```bash
cd /root/Document/writing-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

在 `.env` 中至少配置文本模型：

```env
OPENAI_API_KEY=...
TEXT_MODEL_NAME=gpt-5.6-terra
```

公网运行时还必须配置 Google 登录。创建 Web 类型的 Google OAuth Client，
把 `https://writing.gggxie.com` 加入 Authorized JavaScript origins，然后设置：

```env
WEB_ORIGIN=https://writing.gggxie.com
AUTH_REQUIRED=true
GOOGLE_CLIENT_ID=你的客户端ID.apps.googleusercontent.com
AUTH_ALLOWED_EMAILS=gavinxie1219@gmail.com
SESSION_SECRET_KEY=至少32字节的随机字符串
```

登录凭据由后端使用 Google 公钥校验，功能接口只允许白名单会话访问。
`/health` 只表示进程存活；`/ready` 还会检查鉴权、文本模型、工作区和配置文件。

也可以配置兼容 OpenAI Chat Completions 的服务：

```env
OPENAI_BASE_URL=https://example.com/v1
OPENAI_API_KEY=...
TEXT_MODEL_NAME=your-model
```

### 使用 ChatGPT Codex 订阅

本项目可通过本机 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)
sidecar 使用 Codex OAuth。代理必须只监听 `127.0.0.1`，不得通过 Cloudflare
或反向代理公开：

```env
OPENAI_BASE_URL=http://127.0.0.1:8317/v1
OPENAI_API_KEY=与CLIProxyAPI配置一致的本地密钥
TEXT_MODEL_NAME=gpt-5.6-terra
TEXT_REQUEST_TIMEOUT_SECONDS=180
TEXT_MAX_RETRIES=3
```

CLIProxyAPI 7.x 可通过同一份本地 Codex OAuth 凭据生成配图。图片请求仅发往
本机代理，单张失败时会自动回退为本地 SVG：

```env
IMAGE_MODEL_NAME=gpt-image-2
IMAGE_QUALITY=low
IMAGE_SIZE=1024x1024
IMAGE_MAX_CONCURRENCY=2
IMAGE_REQUEST_TIMEOUT_SECONDS=240
```

`IMAGE_API_KEY` 和 `IMAGE_BASE_URL` 留空时复用上面的 `OPENAI_API_KEY` 与
`OPENAI_BASE_URL`。若改用 OpenAI Platform API，可单独设置这两个变量和当前
受支持的 GPT Image 模型。Codex/ChatGPT 订阅与 Platform API 计费是两条独立链路。

部署模板位于 `deploy/cliproxyapi.config.example.yaml` 和
`deploy/cliproxyapi.service`。Codex OAuth 凭据保存在仓库外的
`/var/lib/cliproxyapi/auths`，不要复制、提交或对外分享。

检查配置：

```bash
writing-agent doctor
```

## 启动 Web/API

```bash
uvicorn writing_agent.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>，API 文档位于 <http://127.0.0.1:8000/docs>。

生产机使用 `deploy/writing-agent.service` 中的 systemd 沙箱配置。服务以独立的
`writing-agent` 用户运行，代码和配置只读，仅允许写入 `workspace/` 与
`generated_images/`。

主要接口：

- `POST /api/generate`：研究、证据判断并按条件生成草稿；
- `POST /api/suggest_form`：按创作方式智能整理可修改的写作简报；
- `POST /api/summarize_sources`：只解析和总结提交来源；
- `POST /api/revise`：根据人工反馈重新研究和生成；
- `GET /api/signals`：查看最近采集线索；
- `POST /api/collect/rss`：执行一次 RSSHub 采集；
- `GET /api/editorial/profile`：查看当前编辑档案。

## 运行日志与 LangSmith

每次页面会话都会生成一个 `workflow_id`。写作简报、素材分析、草稿生成和修订会使用
同一个 ID，因此可以在 LangSmith 中作为同一条 thread 查看；每次完整生成另有独立的
`run_id`。在 `.env` 中配置：

```env
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=你的LangSmith密钥
LANGSMITH_PROJECT=writing-agent
```

本地同时输出单行 JSON 结构化日志，记录操作与 LangGraph 节点的开始、结束、失败、耗时、
来源统计、状态、草稿长度和质检结果。日志不记录 API Key、登录令牌或完整素材正文。使用
systemd 部署时可查看：

```bash
journalctl -u writing-agent.service -f -o cat
```

LangSmith 云端 trace 会包含模型和图节点的详细输入输出，其中可能包括用户提交的素材与
提示词；处理敏感内容前应先关闭 `LANGSMITH_TRACING`。

## 阅读源码

项目按“入口 → 工作流 → 节点 → 基础能力”组织。建议先阅读
[源码导览](docs/source-guide.md)，再从 `src/writing_agent/api/main.py` 和
`src/writing_agent/graph/builder.py` 进入；前端的结构、样式和交互分别位于
`web/index.html`、`web/styles.css` 和 `web/app.js`。

## 提交素材

Web 页面先选择创作方式：

- **从外部线索开始**：适合新消息、帖子、文章和热点，原始来源决定能否成稿；
- **从自己的问题或观点开始**：填写核心问题、初步观点和作者笔记，系统不会把个人判断包装成新闻；
- **从源码、产品或实践开始**：填写分析对象、版本和真实阅读/验证记录，围绕一个问题组织文章。

三种方式最终都经过素材分析、证据判断、草稿生成和人工确认。作者笔记可以支持观点，
但不能替代产品能力、数据、版本和人物言论等外部事实的来源。

Web 页面支持每行一个来源，并可显式标注：

```text
A!|https://example.com/official-announcement
B|https://example.com/media-report
C|https://x.com/example/status/123
test|这里填写真实测试环境、版本、步骤、结果和失败情况
tool|这里填写自研工具的需求、实现、地址和已知限制
```

来源等级：

- A：官方公告、论文、源码、模型卡、法定披露、完整发言或真实实测记录；
- B：可靠媒体或专业转述；
- C：X、社区、论坛、热榜、截图等线索。

`A|URL` 只声明等级，不会通过 A 级证据闸门；人工打开并核验发布主体、日期和版本后，
可使用 `A!|URL` 标记为已确认等级。即使如此，发布前仍需完成逐项事实审校。

内容类型包括：`flash-news`、`rapid-analysis`、`deep-dive`、`product-analysis`、`product-review`、`open-source-analysis`、`tool-release`、`opinion`。

## 证据闸门

- 快讯和快速解读至少需要一个成功抓取的 A 级来源；
- 深度稿需要 A 级来源和至少两个成功抓取的可追溯来源；
- 产品解析至少需要一个 A 级官方产品来源，且不得写成作者实测；
- 产品实测需要 `test_record`；
- 原创观点需要明确问题、初步观点和不少于 80 字的作者笔记；
- 开源解析需要 GitHub/GitLab 原始来源、commit/tag/分支，以及不少于 80 字的源码阅读或验证记录；
- 自研工具需要工具说明或构建记录；
- 只有 C 级来源时只生成研究材料包。

如果没有配置文本模型，或者模型调用失败，系统会返回 warning 并停在研究阶段，不会用通用套话伪装成完整文章。

## 配置 RSSHub

运行时配置是 `config/sources.yaml`，可从 `config/sources.example.yaml` 重新复制。RSSHub 负责 X 以外的网站和平台：

```yaml
rsshub:
  enabled: true
  feeds:
    - id: official-blog
      name: 某官方博客
      url: http://localhost:1200/实际路由
      enabled: true
      tags: [AI, 官方]
      source_tier: A
```

RSSHub 只是传输方式，`source_tier` 应根据最终原始页面判断。

执行一次：

```bash
writing-agent collect-rss
```

持续轮询：

```bash
writing-agent collect-rss --watch
```

## 配置 X API

在 `.env` 中填写：

```env
X_BEARER_TOKEN=...
```

然后在 `config/sources.yaml` 设置 `x.enabled: true` 并维护 Filtered Stream 规则。

```bash
writing-agent collect-x --sync-only
writing-agent collect-x
```

规则同步只管理 `managed_tag_prefix` 前缀下的规则，不会删除同一 X 项目的其他规则。X 内容统一按 C 级线索保存。

## 草稿检查

```bash
writing-agent check workspace/drafts/文章.md
```

机械检查不能代替事实审校。发布前仍需确认关键来源、日期、版本、第一人称经历和图片许可。

## 编辑资源

- `resources/editorial/positioning.md`：账号定位；
- `resources/editorial/voice-guide.md`：统一作者声线；
- `resources/editorial/source-policy.md`：来源与核查规则；
- `resources/editorial/content-strategy.md`：选题评分和内容比例；
- `resources/editorial/workflow.md`：完整编辑流程；
- `resources/editorial/templates/`：各内容类型模板；
- `config/editorial-watchlist.yaml`：信息源规划清单。

## 测试

```bash
LANGSMITH_TRACING=false pytest
```

测试覆盖证据闸门、平台路由、研究/草稿落盘、RSS 去重、信号 Markdown 和 API。
