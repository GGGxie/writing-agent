from __future__ import annotations

from writing_agent.graph.state import GraphState
from writing_agent.models import GenerateResponse, WorkflowStatus
from writing_agent.services.workspace import save_draft, save_research_dossier


def export_node(state: GraphState) -> dict:
    request = state["request"]
    gate = state.get("evidence_gate")
    score = state.get("topic_score")
    artifact_paths = list(state.get("artifact_paths", []))
    if gate is None or score is None:
        raise RuntimeError("导出前缺少选题评分或证据闸门结果")

    dossier_path = save_research_dossier(
        request,
        state.get("source_items", []),
        state.get("research_notes", []),
        score,
        gate,
        state["run_id"],
    )
    artifact_paths.append(str(dossier_path))

    drafts = [
        draft for draft in [state.get("xhs_draft"), state.get("wechat_draft")] if draft is not None
    ]
    for draft in drafts:
        path = save_draft(draft, state["run_id"])
        draft.artifact_path = str(path)
        artifact_paths.append(str(path))

    status = WorkflowStatus.DRAFT if drafts else WorkflowStatus.RESEARCHING
    response = GenerateResponse(
        workflow_id=request.workflow_id,
        run_id=state["run_id"],
        topic=request.topic,
        source_items=state.get("source_items", []),
        research_notes=state.get("research_notes", []),
        outline=state.get("outline", []),
        image_plan=state.get("image_plan", []),
        generated_images=state.get("generated_images", []),
        drafts=drafts,
        status=status,
        topic_score=score,
        evidence_gate=gate,
        artifact_paths=artifact_paths,
        warnings=state.get("warnings", []),
    )
    return {"artifact_paths": artifact_paths, "response": response.model_dump()}
