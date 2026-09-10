from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from writing_agent.api.operations import OperationRunner
from writing_agent.api.security import SecurityBoundaryMiddleware
from writing_agent.collectors.config import load_collector_config
from writing_agent.collectors.rsshub import collect_rss_once
from writing_agent.collectors.store import CollectorStore
from writing_agent.config import ROOT_DIR, get_settings
from writing_agent.editorial.resources import load_editorial_context
from writing_agent.models import (
    FormSuggestionRequest,
    FormSuggestionResponse,
    GenerateRequest,
    GenerateResponse,
    GoogleCredentialRequest,
    ReviewRequest,
    SignalRecord,
    SourceSummaryResponse,
)
from writing_agent.services.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    AuthenticationError,
    authorize_claims,
    create_session,
    new_csrf_token,
    read_authenticated_user,
    secure_cookie,
    verify_csrf,
    verify_google_credential,
)
from writing_agent.services.form_suggestion import suggest_form_fields
from writing_agent.services.llm import text_model_ready
from writing_agent.services.pipeline import run_pipeline, summarize_sources
from writing_agent.services.source_snapshot import create_source_snapshot


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Writing Agent", version="0.2.0")
    web_dir = ROOT_DIR / "web"
    generated_dir = settings.image_output_dir
    operations = OperationRunner(settings.max_concurrent_generations)

    configured_origin = settings.web_origin.rstrip("/")
    allowed_origins = {configured_origin}
    if settings.app_env != "production":
        allowed_origins.update(
            {
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
            }
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    public_host = urlparse(configured_origin).hostname
    trusted_hosts = ["localhost", "127.0.0.1", "test"]
    if public_host:
        trusted_hosts.append(public_host)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
    app.add_middleware(SecurityBoundaryMiddleware, settings=settings)

    if generated_dir.exists():
        app.mount(
            "/generated_images",
            StaticFiles(directory=generated_dir),
            name="generated_images",
        )
    if web_dir.exists():
        app.mount("/assets", StaticFiles(directory=web_dir), name="web_assets")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    async def readiness():
        checks = {
            "auth": not settings.auth_required or settings.auth_configured,
            "text_model": await text_model_ready(),
            "langsmith": not settings.langsmith_tracing or settings.has_langsmith,
            "workspace_writable": os.access(settings.workspace_dir, os.W_OK),
            "editorial_resources": settings.editorial_resources_dir.is_dir(),
            "sources_config": settings.sources_config_path.is_file(),
        }
        ready = all(checks.values())
        return JSONResponse(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status_code=200 if ready else 503,
        )

    @app.get("/api/auth/config")
    async def auth_config():
        csrf_token = new_csrf_token()
        response = JSONResponse(
            {
                "required": settings.auth_required,
                "configured": settings.auth_configured,
                "google_client_id": settings.google_client_id,
                "csrf_token": csrf_token,
            }
        )
        response.set_cookie(
            CSRF_COOKIE,
            csrf_token,
            max_age=600,
            httponly=True,
            secure=secure_cookie(settings),
            samesite="strict",
            path="/api/auth",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/auth/me")
    async def auth_me(request: Request) -> JSONResponse:
        user = read_authenticated_user(
            request.cookies.get(SESSION_COOKIE),
            request.headers.get("authorization"),
            settings,
        )
        return JSONResponse(
            {
                "authenticated": user is not None,
                "user": user if user is not None else None,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/auth/google")
    async def auth_google(payload: GoogleCredentialRequest, request: Request):
        origin = request.headers.get("origin", "").rstrip("/")
        if origin not in allowed_origins:
            raise HTTPException(status_code=403, detail="登录来源无效")
        if not settings.auth_configured:
            raise HTTPException(status_code=503, detail="Google 登录尚未完成配置")
        try:
            verify_csrf(request.cookies.get(CSRF_COOKIE), payload.csrf_token)
            claims = verify_google_credential(payload.credential, settings.google_client_id)
            user = authorize_claims(claims, settings)
        except AuthenticationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        session_token = create_session(user, settings)
        response = JSONResponse(
            {
                "authenticated": True,
                "user": user,
                "session_token": session_token,
            },
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            SESSION_COOKIE,
            session_token,
            max_age=settings.session_ttl_seconds,
            httponly=True,
            secure=secure_cookie(settings),
            samesite="lax",
            path="/",
        )
        response.delete_cookie(CSRF_COOKIE, path="/api/auth")
        return response

    @app.post("/api/auth/logout")
    async def auth_logout():
        response = JSONResponse(
            {"authenticated": False},
            headers={"Cache-Control": "no-store"},
        )
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/editorial/profile")
    async def editorial_profile() -> dict:
        return {
            "profile_id": "tech-ai-wechat",
            "content": load_editorial_context("tech-ai-wechat"),
        }

    @app.get("/api/signals", response_model=list[SignalRecord])
    async def list_signals(limit: int = 50) -> list[SignalRecord]:
        store = CollectorStore()
        try:
            return store.list_signals(limit)
        finally:
            store.close()

    @app.post("/api/collect/rss")
    async def collect_rss() -> dict[str, int]:
        config = load_collector_config()
        if not config.rsshub.enabled:
            return {
                "fetched": 0,
                "saved": 0,
                "duplicates": 0,
                "skipped_old": 0,
                "failed_feeds": 0,
            }

        def run_collection() -> dict[str, int]:
            store = CollectorStore(max_seen_items=config.max_seen_items)
            try:
                return collect_rss_once(config.rsshub, store)
            finally:
                store.close()

        return await operations.run_limited(run_collection)

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse((web_dir / "index.html").read_text(encoding="utf-8"))

    @app.post("/api/generate", response_model=GenerateResponse)
    async def generate(request: GenerateRequest) -> GenerateResponse:
        return await operations.run_observed(
            "generate", request, lambda: run_pipeline(request)
        )

    @app.post("/api/suggest_form", response_model=FormSuggestionResponse)
    async def suggest_form(request: FormSuggestionRequest) -> FormSuggestionResponse:
        try:
            result = await operations.run_observed(
                "suggest_form",
                request,
                lambda: suggest_form_fields(request),
            )
            result.source_summary_token = create_source_snapshot(
                request.materials,
                result.source_items,
                settings,
            )
            return result
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/summarize_sources", response_model=SourceSummaryResponse)
    async def summarize_sources_api(
        request: GenerateRequest,
    ) -> SourceSummaryResponse:
        result = await operations.run_observed(
            "summarize_sources",
            request,
            lambda: summarize_sources(request),
        )
        result.source_summary_token = create_source_snapshot(
            request.materials,
            result.source_items,
            settings,
        )
        return result

    @app.post("/api/revise", response_model=GenerateResponse)
    async def revise(request: ReviewRequest) -> GenerateResponse:
        return await operations.run_observed(
            "revise",
            request.request,
            lambda: run_pipeline(request.request, feedback=request.feedback),
            feedback_characters=len(request.feedback),
        )

    return app


app = create_app()
