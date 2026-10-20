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

### 按次选择模型

前端"生成模型"下拉框里的选项不是手动配置的，而是每次请求时实时向
`OPENAI_BASE_URL`（例如本机 Codex sidecar）发一个 `GET /models` 请求，列出
该端点当前实际提供的模型——新增/下线模型时，下拉框会自动跟着变，不需要改
writing-agent 的任何配置。列表会过滤掉明显不是文本生成模型的条目（例如
`gpt-image-*`、`codex-auto-review` 等），只保留可以拿来写文章的模型。

如果 `OPENAI_API_KEY` 为空，或者这次探测失败（网络错误、端点不支持
`/models`、返回内容里没有可用的文本模型），会自动回退成只显示
`TEXT_MODEL_NAME` 这一个选项，行为跟不配置模型选择功能时完全一致。

这个选择只作用于当次生成/分析请求，不会保存为全局"当前模型"——每次都可以
重新选，也可以不选（留空即用默认模型）。

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
- `POST /api/generate/jobs`：提交后台生成任务并立即返回任务 ID；
- `POST /api/revise/jobs`：提交带反馈的后台修订任务；
- `GET /api/jobs/{job_id}`：查询后台任务状态和最终结果；
- `POST /api/suggest_form`：按创作方式智能整理可修改的写作简报；
- `POST /api/summarize_sources`：只解析和总结提交来源；
- `POST /api/revise`：根据人工反馈重新研究和生成；
- `GET /api/signals`：查看最近采集线索；
- `POST /api/collect/rss`：执行一次 RSSHub 采集；
- `GET /api/editorial/profile`：查看当前编辑档案。

Web 页面默认使用后台任务接口，避免研究、配图和成稿时间较长时被反向代理中断。
任务状态在当前 API 进程内保留 24 小时（最多 200 条已完成记录），服务重启后任务状态会
丢失，但已经导出的 Markdown 和配图仍保存在工作区。同步接口继续保留给兼容调用方。

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

### 自建 RSSHub，用来读 X/Twitter

`/twitter/*` 这类路由很少有公共实例维护者配置凭据，自建一个本机 RSSHub
sidecar 更可靠。部署模板位于 `deploy/rsshub.service` 和
`deploy/rsshub.env.example`，跟 CLIProxyAPI sidecar 的思路一致：只监听
`127.0.0.1`，不得通过 Cloudflare 或反向代理公开，容器加了内存上限
（`--memory=320m`）和只读根文件系统，不会影响这台机器上其他服务。

```bash
useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --user-group rsshub
mkdir -p /etc/rsshub && chown root:rsshub /etc/rsshub && chmod 750 /etc/rsshub
cp deploy/rsshub.env.example /etc/rsshub/rsshub.env
chown root:rsshub /etc/rsshub/rsshub.env && chmod 640 /etc/rsshub/rsshub.env

cp deploy/rsshub.service /etc/systemd/system/rsshub.service
systemctl daemon-reload
systemctl enable --now rsshub.service
```

`TWITTER_AUTH_TOKEN` 不需要填你的真实凭据：实测确认，只要这个变量非空，
RSSHub 就会启用它的 Twitter 集成分支，该分支对公开账号（`/twitter/user/:id`）
和公开 List（`/twitter/list/:id`）的读取会用内置的匿名 guest token 流程完成，
并不校验这个值本身是否真实有效——留一个任意占位字符串即可，不涉及你的个人
账号，没有账号被限流/冻结的风险。`config/sources.example.yaml` 里带了三条
对应示例（`x-openai-selfhosted`/`x-anthropic-selfhosted`/
`x-googledeepmind-selfhosted`，默认 `enabled: false`，改成 `true` 并确认
`rsshub.service` 已启动即可使用）。

只有在之后遇到限流、拉不到数据，或者需要读取非公开内容（比如你自己创建的
私密 List）时，才需要把 `TWITTER_AUTH_TOKEN` 换成你自己 X 账号登录后从浏览器
DevTools 的 Storage/Cookies 面板复制的真实 `auth_token` 值（不是
`document.cookie`，因为它是 HttpOnly 的）。这属于用个人账号做非官方自动化
访问，违反 X 服务条款，存在账号被限流甚至冻结的风险；`CACHE_EXPIRE`（默认
1800 秒）能降低对 Twitter 的实际请求频率，若只有一个账号，建议把想关注的
多个账号合并成一个 X List（`/twitter/list/:id`）一次抓取，而不是每个账号
单开一条 feed，进一步降低触发限流的概率，但无法降为零。

### 不想自己部署 RSSHub？用公共实例池自动选可用的

如果没有自建 RSSHub（比如上面配置里的 `http://localhost:1200`），可以把某条 `feeds`
配置改成 `auto_instance: true`，这样 `url` 不再是完整地址，而是一段以 `/` 开头的
RSSHub 路由路径，程序会在每次采集时从 RSSHub 官方维护的公共实例列表
（<https://docs.rsshub.app/zh/guide/instances>）里按顺序尝试，命中第一个能用的实例并缓存
1 小时，下次优先复用，减少对公共实例的骚扰：

```yaml
rsshub:
  feeds:
    - id: x-openai-auto
      name: OpenAI（经公共 RSSHub 实例池，仅供参考）
      url: /twitter/user/OpenAI
      auto_instance: true
      enabled: false
      tags: [AI, 官方, X]
      source_tier: C
```

`config/sources.example.yaml` 里就带了这一条示例（默认 `enabled: false`），可以直接
改成 `true` 试用。这条路径不限于 Twitter，任何 RSSHub 支持的路由都可以这样用。

风险提示，打开前请自行评估：

- 公共实例由社区自愿维护，不受本项目控制，长期在线率和响应速度没有保证；
- 实例列表页最后更新于 2023-11-30，可能包含已下线的实例，程序会自动跳过失败的
  候选，但无法保证列表里一定存在可用实例；
- 你的请求会经过这些第三方服务器，对方能看到你请求的路由和参数；
- 类似 `/twitter/*` 这种依赖维护者自行配置凭据的路由，具体某个公共实例是否
  支持完全不保证；
- 无论采集是否成功，来自 X/Twitter 的内容仍统一按 `source_tier: C` 处理。

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
