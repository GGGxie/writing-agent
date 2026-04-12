# writing-agent

面向小红书与微信公众号的中文图文写作 Agent：支持文本/链接信息源、来源摘要、双平台图文混排草稿与本地配图生成。

## 功能概览

- **LangGraph** 编排写作流程（ingest → research → outline → 配图 → 双平台成稿 → 质检）
- **DeepAgents** 可选用于研究补料（需配置文本模型）
- **FastAPI** 提供 `POST /api/generate`、`POST /api/summarize_sources`、`POST /api/revise`
- 轻量 **Web** 页面：`web/index.html`

## 本地运行

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
cp .env.example .env
# 按需填写 OPENAI_API_KEY、LANGSMITH_API_KEY 等

uvicorn writing_agent.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

浏览器打开：<http://127.0.0.1:8000>

## 环境变量

见 [.env.example](.env.example)。

## 测试

```bash
pytest
```

## 许可证

MIT（与 `pyproject.toml` 中声明一致）。
