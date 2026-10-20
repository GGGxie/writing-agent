from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from writing_agent.models import (
    OperationJobAccepted,
    OperationJobResponse,
    OperationJobStatus,
)
from writing_agent.services.observability import emit_event, request_summary, response_summary
from writing_agent.services.tracing import tracing_scope


@dataclass
class _OperationJob:
    job_id: str
    operation: str
    owner: str
    status: OperationJobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None


class OperationRunner:
    """Run blocking workflows with concurrency limits and consistent telemetry."""

    _job_ttl = timedelta(hours=24)
    _max_retained_jobs = 200

    def __init__(self, max_concurrency: int):
        self._slots = asyncio.Semaphore(max_concurrency)
        self._worker_executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="writing-agent-job",
        )
        self._jobs: dict[str, _OperationJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def run_limited(
        self,
        callable_: Callable[[], Any],
        *,
        wait_for_slot: bool = False,
        run_in_worker: bool = False,
        on_slot_acquired: Callable[[], None] | None = None,
    ) -> Any:
        if wait_for_slot:
            await self._slots.acquire()
        else:
            try:
                await asyncio.wait_for(self._slots.acquire(), timeout=0.05)
            except TimeoutError as exc:
                raise HTTPException(status_code=429, detail="生成任务已达到并发上限") from exc
        try:
            if on_slot_acquired is not None:
                on_slot_acquired()
            if not run_in_worker:
                return callable_()
            future = self._worker_executor.submit(callable_)
            while not future.done():
                await asyncio.sleep(0.05)
            return future.result()
        finally:
            self._slots.release()

    async def run_observed(
        self,
        operation: str,
        request: Any,
        callable_: Callable[[], Any],
        *,
        wait_for_slot: bool = False,
        run_in_worker: bool = False,
        on_slot_acquired: Callable[[], None] | None = None,
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
            result = await self.run_limited(
                execute,
                wait_for_slot=wait_for_slot,
                run_in_worker=run_in_worker,
                on_slot_acquired=on_slot_acquired,
            )
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

    def submit_observed(
        self,
        operation: str,
        request: Any,
        callable_: Callable[[], Any],
        *,
        owner: str,
        **metadata: Any,
    ) -> OperationJobAccepted:
        """Queue a long workflow and return an opaque polling handle immediately."""

        self._prune_jobs()
        job_id = uuid4().hex
        job = _OperationJob(
            job_id=job_id,
            operation=operation,
            owner=owner,
            status=OperationJobStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )
        self._jobs[job_id] = job
        emit_event(
            "workflow.job.submitted",
            job_id=job_id,
            operation=operation,
            request=request_summary(request),
            **metadata,
        )
        task = asyncio.create_task(
            self._execute_job(job, request, callable_, metadata),
            name=f"writing-agent-{operation}-{job_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return OperationJobAccepted(
            job_id=job_id,
            operation=operation,
            status=job.status,
            poll_url=f"/api/jobs/{job_id}",
        )

    def get_job(self, job_id: str, *, owner: str) -> OperationJobResponse | None:
        self._prune_jobs()
        job = self._jobs.get(job_id)
        if job is None or job.owner != owner:
            return None
        return OperationJobResponse(
            job_id=job.job_id,
            operation=job.operation,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job.result,
            error=job.error,
        )

    def shutdown(self, *, wait: bool = False) -> None:
        self._worker_executor.shutdown(wait=wait, cancel_futures=True)

    async def _execute_job(
        self,
        job: _OperationJob,
        request: Any,
        callable_: Callable[[], Any],
        metadata: dict[str, Any],
    ) -> None:
        def mark_running() -> None:
            job.status = OperationJobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            emit_event(
                "workflow.job.started",
                job_id=job.job_id,
                operation=job.operation,
            )

        try:
            job.result = await self.run_observed(
                job.operation,
                request,
                callable_,
                wait_for_slot=True,
                run_in_worker=True,
                on_slot_acquired=mark_running,
                job_id=job.job_id,
                **metadata,
            )
        except asyncio.CancelledError:
            job.status = OperationJobStatus.FAILED
            job.error = "服务已停止，任务未完成"
            job.completed_at = datetime.now(timezone.utc)
            emit_event(
                "workflow.job.cancelled",
                level=logging.WARNING,
                job_id=job.job_id,
                operation=job.operation,
            )
            raise
        except Exception as exc:
            job.status = OperationJobStatus.FAILED
            job.error = str(exc)[:500] or type(exc).__name__
            job.completed_at = datetime.now(timezone.utc)
            emit_event(
                "workflow.job.failed",
                level=logging.ERROR,
                error=exc,
                job_id=job.job_id,
                operation=job.operation,
            )
            return

        job.status = OperationJobStatus.SUCCEEDED
        job.completed_at = datetime.now(timezone.utc)
        emit_event(
            "workflow.job.completed",
            job_id=job.job_id,
            operation=job.operation,
            output=response_summary(job.result),
        )

    def _prune_jobs(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.completed_at is not None and now - job.completed_at > self._job_ttl
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)

        completed = sorted(
            (job for job in self._jobs.values() if job.completed_at is not None),
            key=lambda job: job.completed_at or job.created_at,
        )
        overflow = max(0, len(self._jobs) - self._max_retained_jobs)
        for job in completed[:overflow]:
            self._jobs.pop(job.job_id, None)
