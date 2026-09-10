from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from writing_agent.services.observability import emit_event, request_summary, response_summary
from writing_agent.services.tracing import tracing_scope


class OperationRunner:
    """Run blocking workflows with concurrency limits and consistent telemetry."""

    def __init__(self, max_concurrency: int):
        self._slots = asyncio.Semaphore(max_concurrency)

    async def run_limited(self, callable_: Callable[[], Any]) -> Any:
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise HTTPException(status_code=429, detail="生成任务已达到并发上限") from exc
        try:
            return callable_()
        finally:
            self._slots.release()

    async def run_observed(
        self,
        operation: str,
        request: Any,
        callable_: Callable[[], Any],
        **metadata: Any,
    ) -> Any:
        operation_id = uuid4().hex
        started_at = perf_counter()
        request_details = request_summary(request)
        emit_event(
            "workflow.operation.started",
            operation_id=operation_id,
            operation=operation,
            request=request_details,
            **metadata,
        )

        def execute():
            trace_metadata = {
                "creation_mode": request_details.get("creation_mode"),
                "content_type": request_details.get("content_type"),
                **metadata,
            }
            with tracing_scope(request.workflow_id, operation, trace_metadata):
                return callable_()

        try:
            result = await self.run_limited(execute)
        except Exception as exc:
            emit_event(
                "workflow.operation.failed",
                level=logging.ERROR,
                error=exc,
                operation_id=operation_id,
                operation=operation,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
                request=request_details,
                **metadata,
            )
            raise
        emit_event(
            "workflow.operation.completed",
            operation_id=operation_id,
            operation=operation,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            request=request_details,
            output=response_summary(result),
            **metadata,
        )
        return result
