from __future__ import annotations

from collections.abc import Callable
from typing import Any


try:
    from langsmith import traceable as _traceable
except ImportError:
    _traceable = None


def traceable(*, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if _traceable is None:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator

    return _traceable(name=name)
