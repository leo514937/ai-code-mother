from __future__ import annotations

from ...domain.contracts import NormalizedToolResult, PlanExecutionSummary, RagResult, ToolExecutionResult
from ...domain.enums import RagStatus, ToolExecutionStatus, TurnDecision
from ...domain.state import GraphState
from .services import PlanExecuteSubgraphServices, RagSubgraphServices, ToolSubgraphServices, UnderstandTurnServices


CLARIFY_DECISIONS = {TurnDecision.CLARIFY}
RAG_DECISIONS = {TurnDecision.RETRIEVE_THEN_ANSWER, TurnDecision.TOOL_THEN_ANSWER}
TOOL_DECISIONS = {TurnDecision.TOOL_THEN_ANSWER}


def _ensure_rag_result(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.rag_result is None:
        status = RagStatus.EMPTY if turn.evidence_pack is None else RagStatus.OK
        state["turn"] = turn.model_copy(
            update={
                "rag_result": RagResult(
                    status=status,
                    evidence_pack=turn.evidence_pack,
                    citations=list(turn.citations),
                )
            }
        )
    return state


def _ensure_tool_result(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.tool_result is None:
        selection = turn.tool_plan
        tool_name = selection.tool_name if selection else None
        state["turn"] = turn.model_copy(
            update={
                "tool_result": NormalizedToolResult(
                    status=ToolExecutionStatus.SKIPPED,
                    tool_name=tool_name,
                )
            }
        )
    return state


def _ensure_raw_tool_result(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.raw_tool_result is None and turn.tool_plan is not None:
        state["turn"] = turn.model_copy(
            update={
                "raw_tool_result": ToolExecutionResult(
                    status=ToolExecutionStatus.SKIPPED,
                    tool_name=turn.tool_plan.tool_name,
                )
            }
        )
    return state


def run_understand_turn(state: GraphState, services: UnderstandTurnServices) -> GraphState:
    state = services.parse_intent_slots(state)
    state = services.resolve_reference(state)
    state = services.ambiguity_check(state)
    if state["turn"].decision in CLARIFY_DECISIONS:
        return state
    if state["turn"].decision in RAG_DECISIONS:
        state = services.rewrite_query(state)
    return state


def run_rag_subgraph(state: GraphState, services: RagSubgraphServices) -> GraphState:
    if state["turn"].retrieval_plan is None:
        return _ensure_rag_result(state)

    state = services.hybrid_retrieve(state)
    state = services.evaluate_evidence(state)
    state = services.citation_builder(state)
    return _ensure_rag_result(state)


def run_tool_subgraph(state: GraphState, services: ToolSubgraphServices) -> GraphState:
    state = services.tool_planner(state)
    selection = state["turn"].tool_plan
    if selection is None or not selection.should_execute:
        state = _ensure_raw_tool_result(state)
    else:
        state = services.tool_executor(state)
        state = _ensure_raw_tool_result(state)

    state = services.tool_result_normalizer(state)
    return _ensure_tool_result(state)


def run_plan_execute_subgraph(state: GraphState, services: PlanExecuteSubgraphServices) -> GraphState:
    turn = state["turn"]
    if turn.execution_mode != "plan_execute" and not (
        turn.execution_mode == "auto"
        and (
            turn.task_complexity == "complex"
            or turn.need_human_approval
            or turn.risk_level in {"medium", "high"}
        )
    ):
        return state

    state = services.plan_planner(state)
    state = _ensure_plan_progress_state(state)
    state = services.plan_validator(state)
    state = services.step_executor(state)
    state = _ensure_plan_progress_state(state)
    state = services.progress_checker(state)
    state = services.plan_reviewer(state)

    if state["turn"].need_human_approval:
        state = services.human_approval_stub(state)
        return _ensure_plan_summary(state)

    if state["turn"].need_replan:
        state = services.replanner(state)
        state = _ensure_plan_progress_state(state)
        if state["turn"].need_replan:
            state = services.plan_reviewer(state)
            return _ensure_plan_summary(state)
        state = services.step_executor(state)
        state = _ensure_plan_progress_state(state)
        state = services.progress_checker(state)
        state = services.plan_reviewer(state)
        if state["turn"].need_human_approval:
            state = services.human_approval_stub(state)
            return _ensure_plan_summary(state)

    return _ensure_plan_summary(state)


def should_clarify(state: GraphState) -> bool:
    return state["turn"].decision in CLARIFY_DECISIONS


def should_run_rag(state: GraphState) -> bool:
    return state["turn"].decision in RAG_DECISIONS and state["turn"].retrieval_plan is not None


def should_run_tools(state: GraphState) -> bool:
    return state["turn"].decision in TOOL_DECISIONS


def should_run_plan_execute(state: GraphState) -> bool:
    turn = state["turn"]
    return turn.execution_mode == "plan_execute" or (
        turn.execution_mode == "auto"
        and (
            turn.task_complexity == "complex"
            or turn.need_human_approval
            or turn.risk_level in {"medium", "high"}
        )
    )


def route_after_understand(state: GraphState) -> str:
    if should_clarify(state):
        return "emit_final"
    if should_run_plan_execute(state):
        return "plan_execute_subgraph"
    if should_run_rag(state):
        return "rag_subgraph"
    if should_run_tools(state):
        return "tool_subgraph"
    return "compose_answer"


def route_after_rag(state: GraphState) -> str:
    if should_run_tools(state):
        return "tool_subgraph"
    return "compose_answer"


def route_after_mastery(state: GraphState) -> str:
    if should_recommend(state):
        return "recommend_next"
    return "emit_final"


def should_recommend(state: GraphState) -> bool:
    if not state["persistent"].learning_mode:
        return False
    rag_result = state["turn"].rag_result
    if rag_result is not None and rag_result.status == RagStatus.EMPTY:
        return False
    terminal = state["runtime"].terminal_event
    return terminal is None


def _ensure_plan_progress_state(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.current_step is None and turn.plan:
        index = min(max(turn.current_step_index, 0), len(turn.plan) - 1)
        state["turn"] = turn.model_copy(
            update={
                "current_step_index": index,
                "current_step": turn.plan[index],
            }
        )
    return state


def _ensure_plan_summary(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.final_task_summary is not None:
        return state
    if not turn.plan and not turn.step_results and not turn.need_human_approval and not turn.approval_request:
        return state

    completed_steps = len([item for item in turn.step_results if item.status == "success"])
    total_steps = len(turn.plan) if turn.plan else len(turn.step_results)
    if turn.need_human_approval:
        status = "need_approval"
    elif turn.need_replan and completed_steps < total_steps:
        status = "partial" if completed_steps > 0 else "failed"
    elif total_steps and completed_steps >= total_steps:
        status = "completed"
    elif completed_steps > 0:
        status = "partial"
    else:
        status = "failed"

    key_findings: list[str] = []
    for result in turn.step_results:
        key_findings.extend(result.observations[:1])

    summary = PlanExecutionSummary(
        status=status,
        completed_steps=completed_steps,
        total_steps=total_steps,
        key_findings=key_findings[:5],
        final_decision=turn.replan_reason or turn.final_answer,
    )
    state["turn"] = turn.model_copy(update={"final_task_summary": summary})
    return state
