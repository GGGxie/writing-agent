from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel

event_logger = logging.getLogger("writing_agent.events")
event_logger.setLevel(logging.INFO)
if not event_logger.handlers:
    _event_handler = logging.StreamHandler()
    _event_handler.setFormatter(logging.Formatter("%(message)s"))
    event_logger.addHandler(_event_handler)
event_logger.propagate = False


def _json_value(value: Any) -> Any:
    if isinstance(value, _MappingView):
        return _json_value(value.values)
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump())
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, Path)):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def emit_event(
    event_name: str,
    *,
    level: int = logging.INFO,
    error: BaseException | None = None,
    **attributes: Any,
) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_name": event_name,
        **_json_value(attributes),
    }
    if error is not None:
        payload["error"] = {
            "type": type(error).__name__,
            "message": str(error)[:500],
        }
    event_logger.log(
        level,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
        exc_info=error is not None,
    )


def request_summary(request: Any) -> dict[str, Any]:
    materials = list(getattr(request, "materials", []) or [])
    kinds = Counter(getattr(item, "kind", "unknown") for item in materials)
    hosts: list[str] = []
    total_characters = 0
    for material in materials:
        content = str(getattr(material, "content", ""))
        total_characters += len(content)
        source = getattr(material, "source", None) or content
        if source.startswith(("http://", "https://")):
            host = (urlparse(source).hostname or "").lower()
            if host and host not in hosts:
                hosts.append(host)

    platforms = [getattr(item, "value", str(item)) for item in getattr(request, "platforms", [])]
    return {
        "workflow_id": getattr(request, "workflow_id", None),
        "topic": getattr(request, "topic", None),
        "creation_mode": getattr(getattr(request, "creation_mode", None), "value", None),
        "content_type": getattr(getattr(request, "content_type", None), "value", None),
        "platforms": platforms,
        "has_core_question": bool(getattr(request, "core_question", None)),
        "has_initial_thesis": bool(getattr(request, "initial_thesis", None)),
        "analysis_target": getattr(request, "analysis_target", None),
        "source_version": getattr(request, "source_version", None),
        "source_snapshot_present": bool(getattr(request, "source_summary_token", None)),
        "material_count": len(materials),
        "material_kinds": dict(kinds),
        "material_characters": total_characters,
        "source_hosts": hosts[:20],
    }


def source_summary(items: list[Any]) -> dict[str, Any]:
    tiers = Counter(
        getattr(getattr(item, "source_tier", None), "value", "unknown") for item in items
    )
    return {
        "count": len(items),
        "fetched_count": sum(bool(getattr(item, "fetched", False)) for item in items),
        "failed_count": sum(bool(getattr(item, "fetch_error", None)) for item in items),
        "verified_tier_count": sum(bool(getattr(item, "tier_verified", False)) for item in items),
        "tiers": dict(tiers),
        "hosts": list(
            dict.fromkeys(
                (urlparse(getattr(item, "url", "") or "").hostname or "").lower()
                for item in items
                if getattr(item, "url", None)
            )
        )[:20],
    }


def response_summary(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        response = _MappingView(response)
    result: dict[str, Any] = {}
    if getattr(response, "workflow_id", None):
        result["workflow_id"] = response.workflow_id
    if getattr(response, "run_id", None):
        result["run_id"] = response.run_id
    if getattr(response, "topic", None):
        result["topic"] = response.topic
    if getattr(response, "content_type", None):
        result["content_type"] = getattr(response.content_type, "value", response.content_type)
    if getattr(response, "status", None):
        result["status"] = getattr(response.status, "value", response.status)
    if hasattr(response, "source_items"):
        result["sources"] = source_summary(list(response.source_items))
    if hasattr(response, "research_notes"):
        result["research_note_count"] = len(response.research_notes)
    if hasattr(response, "outline"):
        result["outline_section_count"] = len(response.outline)
    if hasattr(response, "image_plan"):
        result["image_plan_count"] = len(response.image_plan)
    if hasattr(response, "generated_images"):
        result["generated_image_count"] = len(response.generated_images)
    if hasattr(response, "drafts"):
        result["drafts"] = [
            {
                "platform": getattr(draft.platform, "value", draft.platform),
                "title": draft.title,
                "characters": len(draft.markdown),
                "quality_score": draft.quality.score if draft.quality else None,
                "quality_passed": draft.quality.passed if draft.quality else None,
            }
            for draft in response.drafts
        ]
    if getattr(response, "topic_score", None):
        result["topic_score"] = _json_value(response.topic_score)
    if getattr(response, "evidence_gate", None):
        result["evidence_gate"] = _json_value(response.evidence_gate)
    if hasattr(response, "warnings"):
        result["warnings"] = list(response.warnings)[:20]
    if hasattr(response, "artifact_paths"):
        result["artifact_paths"] = list(response.artifact_paths)
    return _json_value(result)


class _MappingView:
    """Expose a response dict through attributes without logging its full contents."""

    def __init__(self, values: dict[str, Any]):
        self.values = values

    def __getattr__(self, name: str) -> Any:
        try:
            value = self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
        if isinstance(value, dict):
            return _MappingView(value)
        if isinstance(value, list):
            return [_MappingView(item) if isinstance(item, dict) else item for item in value]
        return value


def graph_state_summary(state: dict[str, Any]) -> dict[str, Any]:
    summary = request_summary(state.get("request"))
    summary.update(
        {
            "run_id": state.get("run_id"),
            "normalized_material_count": len(state.get("materials", [])),
            "source_count": len(state.get("source_items", [])),
            "research_note_count": len(state.get("research_notes", [])),
            "outline_section_count": len(state.get("outline", [])),
            "image_plan_count": len(state.get("image_plan", [])),
            "generated_image_count": len(state.get("generated_images", [])),
            "draft_platforms": [
                name
                for key, name in (("wechat_draft", "wechat"), ("xhs_draft", "xiaohongshu"))
                if state.get(key) is not None
            ],
            "warning_count": len(state.get("warnings", [])),
        }
    )
    return summary


def node_output_summary(output: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"updated_fields": sorted(output)}
    if "materials" in output:
        summary["materials"] = {
            "count": len(output["materials"]),
            "characters": sum(len(str(item)) for item in output["materials"]),
        }
    if "source_items" in output:
        summary["sources"] = source_summary(output["source_items"])
    if "research_notes" in output:
        summary["research_notes"] = {
            "count": len(output["research_notes"]),
            "titles": [item.title for item in output["research_notes"][:10]],
        }
    if "topic_score" in output and output["topic_score"] is not None:
        summary["topic_score"] = output["topic_score"].model_dump()
    if "evidence_gate" in output and output["evidence_gate"] is not None:
        summary["evidence_gate"] = output["evidence_gate"].model_dump()
    if "outline" in output:
        summary["outline"] = {
            "count": len(output["outline"]),
            "headings": [item.heading for item in output["outline"][:12]],
        }
    if "image_plan" in output:
        summary["image_plan_count"] = len(output["image_plan"])
    if "generated_images" in output:
        summary["generated_image_count"] = len(output["generated_images"])
    for field in ("wechat_draft", "xhs_draft"):
        if field in output:
            draft = output[field]
            summary[field] = None if draft is None else {
                "title": draft.title,
                "characters": len(draft.markdown),
                "block_count": len(draft.blocks),
            }
    if "quality_checks" in output:
        summary["quality_checks"] = {
            platform: result.model_dump()
            for platform, result in output["quality_checks"].items()
        }
    if "response" in output:
        summary["response"] = response_summary(output["response"])
    if "warnings" in output:
        summary["warnings"] = list(output["warnings"])[-10:]
    if "artifact_paths" in output:
        summary["artifact_paths"] = list(output["artifact_paths"])
    if "editorial_context" in output:
        summary["editorial_context_characters"] = len(output["editorial_context"])
    if "selected_template" in output:
        summary["selected_template_characters"] = len(output["selected_template"])
    return _json_value(summary)


def instrument_graph_node(name: str, node):
    @wraps(node)
    def observed(state):
        operation_id = uuid4().hex
        started_at = perf_counter()
        context = graph_state_summary(state)
        emit_event(
            "langgraph.node.started",
            operation_id=operation_id,
            node=name,
            **context,
        )
        try:
            output = node(state)
        except Exception as exc:
            emit_event(
                "langgraph.node.failed",
                level=logging.ERROR,
                error=exc,
                operation_id=operation_id,
                node=name,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
                **context,
            )
            raise
        emit_event(
            "langgraph.node.completed",
            operation_id=operation_id,
            node=name,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            workflow_id=context.get("workflow_id"),
            run_id=context.get("run_id"),
            output=node_output_summary(output),
        )
        return output

    return observed
