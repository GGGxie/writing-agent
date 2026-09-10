from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

try:
    from langsmith import traceable as _langsmith_traceable
    from langsmith import tracing_context as _langsmith_tracing_context
except ImportError:
    _langsmith_traceable = None
    _langsmith_tracing_context = None


def _tracing_enabled() -> bool:
    from writing_agent.config import get_settings

    return _langsmith_traceable is not None and get_settings().has_langsmith


def traceable(*, name: str, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Trace only when runtime settings enable LangSmith.

    The runtime check keeps tests and local commands from accidentally using credentials
    loaded earlier in the Python process.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if _langsmith_traceable is None:
            return func
        traced = _langsmith_traceable(name=name, **options)(func)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                target = traced if _tracing_enabled() else func
                return await target(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            target = traced if _tracing_enabled() else func
            return target(*args, **kwargs)

        return wrapper

    return decorator


@contextmanager
def tracing_scope(
    workflow_id: str,
    operation: str,
    metadata: dict[str, Any] | None = None,
):
    """Group independent UI operations into one LangSmith thread."""

    if not _tracing_enabled() or _langsmith_tracing_context is None:
        yield
        return

    from writing_agent.config import get_settings

    settings = get_settings()
    trace_metadata = {
        "thread_id": workflow_id,
        "workflow_id": workflow_id,
        "operation": operation,
        **(metadata or {}),
    }
    with _langsmith_tracing_context(
        project_name=settings.langsmith_project,
        tags=["writing-agent", operation],
        metadata=trace_metadata,
        enabled=True,
    ):
        yield
