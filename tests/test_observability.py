from __future__ import annotations

import json
import logging

from writing_agent.models import GenerateRequest, MaterialInput
from writing_agent.services.observability import instrument_graph_node


def test_node_logs_are_structured_without_full_material_content(caplog, monkeypatch):
    sensitive_material = "这段完整素材不应该进入本地结构化日志"
    request = GenerateRequest(
        workflow_id="workflow-observability-001",
        topic="日志测试",
        materials=[MaterialInput(content=sensitive_material)],
    )
    observed = instrument_graph_node("demo", lambda _state: {"warnings": ["测试提醒"]})

    monkeypatch.setattr("writing_agent.services.observability.event_logger.propagate", True)
    with caplog.at_level(logging.INFO, logger="writing_agent.events"):
        output = observed({"run_id": "run-001", "request": request})

    assert output == {"warnings": ["测试提醒"]}
    payloads = [json.loads(record.message) for record in caplog.records]
    event_names = {payload["event_name"] for payload in payloads}
    assert event_names == {"langgraph.node.started", "langgraph.node.completed"}
    assert all(payload["workflow_id"] == request.workflow_id for payload in payloads)
    assert all(sensitive_material not in record.message for record in caplog.records)
    started = next(
        payload for payload in payloads if payload["event_name"] == "langgraph.node.started"
    )
    assert started["material_characters"] == len(sensitive_material)
