from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from writing_agent.config import ROOT_DIR, get_settings
from writing_agent.schemas.blocks import (
    GenerateRequest,
    GenerateResponse,
    ReviewRequest,
    SourceSummaryResponse,
)
from writing_agent.services.pipeline import run_pipeline, summarize_sources


settings = get_settings()
app = FastAPI(title="Writing Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_dir = ROOT_DIR / "web"
generated_dir = settings.image_output_dir

if generated_dir.exists():
    app.mount("/generated_images", StaticFiles(directory=generated_dir), name="generated_images")
if web_dir.exists():
    app.mount("/assets", StaticFiles(directory=web_dir), name="web_assets")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(web_dir / "index.html")


@app.get("/api/example", response_model=GenerateRequest)
def example_request() -> GenerateRequest:
    return GenerateRequest(
        topic="AI 写作 Agent 如何做出图文感",
        audience="希望做内容运营的创作者",
        tone="专业、克制、但不无聊",
        goal="同时生成小红书和公众号版本",
        materials=[
            {
                "kind": "article",
                "content": "https://mp.weixin.qq.com/s/example-article",
                "source": "https://mp.weixin.qq.com/s/example-article",
            },
            {
                "kind": "video",
                "content": "https://www.youtube.com/watch?v=example",
                "source": "https://www.youtube.com/watch?v=example",
            },
            {
                "kind": "text",
                "content": "希望内容不只是大段文字，而是读起来舒服，有封面和段间配图。",
            },
        ],
    )


@app.post("/api/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    return run_pipeline(request)


@app.post("/api/summarize_sources", response_model=SourceSummaryResponse)
def summarize_sources_api(request: GenerateRequest) -> SourceSummaryResponse:
    return summarize_sources(request)


@app.post("/api/revise", response_model=GenerateResponse)
def revise(request: ReviewRequest) -> GenerateResponse:
    return run_pipeline(request.request, feedback=request.feedback)


def create_app() -> FastAPI:
    return app
