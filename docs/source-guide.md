# Writing Agent 源码导览

这份导览只解释代码如何协作，不重复产品使用说明。推荐先理解一条完整请求，再按兴趣深入。

## 一条生成请求如何运行

```text
web/index.html + app.js
        ↓ POST /api/generate
api/main.py
        ↓ OperationRunner：并发限制、日志、LangSmith
services/pipeline.py
        ↓ 创建状态并调用 LangGraph
graph/builder.py
        ↓ 依次执行 graph/nodes/
研究 → 证据闸门 → 大纲 → 配图 → 双平台草稿 → 质检 → 落盘
        ↓
workspace/research、workspace/drafts、generated_images
```

## 推荐阅读顺序

1. `models.py`：先看输入、输出和流程状态有哪些字段。
2. `api/main.py`：看网站公开了哪些接口，以及每个接口调用哪个业务函数。
3. `services/pipeline.py`：完整生成和仅分析来源的两个入口。
4. `graph/builder.py`、`graph/state.py`：LangGraph 节点顺序和共享状态。
5. `graph/nodes/`：按 builder 中的顺序逐个阅读，每个文件只负责一个节点。
6. `editorial/evidence.py`：证据闸门为什么允许或阻止成稿。
7. `services/research.py`、`drafting.py`、`image_generation.py`：模型研究、草稿组装和配图。
8. `collectors/`：RSSHub、X 和 SQLite 去重采集；它与 Web 请求进程相互独立。
9. `web/`：`index.html` 只保留结构，`styles.css` 负责视觉，`app.js` 负责状态和请求，
   `render.js` 负责把结构化结果安全渲染成文章预览。

## 目录职责

```text
src/writing_agent/
├── api/          HTTP 路由、安全边界、任务执行控制
├── collectors/   外部线索采集与 SQLite 索引
├── editorial/    编辑资源读取、选题与证据规则
├── graph/        LangGraph 状态、拓扑和业务节点
├── services/     可复用的模型、来源、文件、鉴权能力
├── config.py     环境变量到运行配置的唯一入口
├── models.py     API 与工作流共用的数据模型
└── cli.py        采集、检查和诊断命令入口
```

`resources/editorial/` 是可编辑的内容策略，不是程序代码；`workspace/` 和
`generated_images/` 是运行产物。OAuth、API Key 和生产配置只保存在仓库外或 `.env`。

## 三个容易混淆的边界

- `graph/nodes/` 决定流程，`services/` 完成具体工作；节点应保持短小。
- `workspace/` 保存可人工编辑的 Markdown，SQLite 只做采集索引和去重。
- 页面中的文章预览来自结构化 `blocks`，Markdown 字符串用于导出与落盘。

## 修改代码时的检查顺序

```bash
.venv/bin/ruff check src tests
.venv/bin/pytest -q
```

修改工作流时优先补节点测试；修改接口时补 API 测试；修改解析和文件输出时补 service 测试。
