from __future__ import annotations

from typing import Optional

from ...domain.contracts import (
    NormalizedToolResult,
    RagResult,
    ToolExecutionResult,
    TurnUnderstandingResult,
)
from ...domain.enums import RagStatus, ToolExecutionStatus, TurnDecision
from ...domain.state import GraphState
from .services import RagSubgraphServices, ToolSubgraphServices, UnderstandTurnServices


CLARIFY_DECISIONS = {TurnDecision.CLARIFY}
RAG_DECISIONS = {TurnDecision.RETRIEVE_THEN_ANSWER, TurnDecision.TOOL_THEN_ANSWER}
TOOL_DECISIONS = {TurnDecision.TOOL_THEN_ANSWER}



def _ensure_understanding_result(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.understanding_result is None:
        state["turn"] = turn.model_copy(update={"understanding_result": TurnUnderstandingResult()})
    return state



def _ensure_rag_result(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.rag_result is None:
        state["turn"] = turn.model_copy(update={"rag_result": RagResult(status=RagStatus.EMPTY)})
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



def run_understand_turn(state: GraphState, services: UnderstandTurnServices) -> GraphState:
    state = services.parse_intent_slots(state)
    state = _ensure_understanding_result(state)
    state = services.resolve_reference(state)
    state = _ensure_understanding_result(state)
    state = services.ambiguity_check(state)
    state = _ensure_understanding_result(state)

    understanding = state["turn"].understanding_result
    if understanding and understanding.decision in CLARIFY_DECISIONS:
        return state

    if understanding and understanding.decision in RAG_DECISIONS:
        state = services.rewrite_query(state)
        state = _ensure_understanding_result(state)
        turn = state["turn"]
        understanding = turn.understanding_result
        retrieval_plan = turn.retrieval_plan
        if retrieval_plan is None and understanding is not None and understanding.retrieval_plan is not None:
            state["turn"] = turn.model_copy(update={"retrieval_plan": understanding.retrieval_plan})

    return state



def run_rag_subgraph(state: GraphState, services: RagSubgraphServices) -> GraphState:
    if state["turn"].retrieval_plan is None:
        return _ensure_rag_result(state)

    state = services.hybrid_retrieve(state)
    state = _ensure_rag_result(state)
    state = services.evaluate_evidence(state)
    state = _ensure_rag_result(state)
    state = services.citation_builder(state)
    state = _ensure_rag_result(state)
    return state



def run_tool_subgraph(state: GraphState, services: ToolSubgraphServices) -> GraphState:
    state = services.tool_planner(state)
    selection = state["turn"].tool_plan

    if selection is None or not selection.should_execute:
        raw_result = ToolExecutionResult(
            status=ToolExecutionStatus.SKIPPED,
            tool_name=selection.tool_name if selection else None,
        )
        runtime = state["runtime"]
        runtime_extra = dict(runtime.extra)
        runtime_extra["raw_tool_result"] = raw_result.model_dump(mode="python")
        state["runtime"] = runtime.model_copy(update={"extra": runtime_extra})
    else:
        state = services.tool_executor(state)

    state = services.tool_result_normalizer(state)
    state = _ensure_tool_result(state)
    return state



def should_clarify(state: GraphState) -> bool:
    understanding = state["turn"].understanding_result
    return bool(understanding and understanding.decision in CLARIFY_DECISIONS)



def should_run_rag(state: GraphState) -> bool:
    understanding = state["turn"].understanding_result
    if understanding is None:
        return False
    return understanding.decision in RAG_DECISIONS and state["turn"].retrieval_plan is not None



def should_run_tools(state: GraphState) -> bool:
    understanding = state["turn"].understanding_result
    if understanding is None:
        return False
    return understanding.decision in TOOL_DECISIONS



def should_recommend(state: GraphState) -> bool:
    if not state["persistent"].learning_mode:
        return False
    rag_result = state["turn"].rag_result
    if rag_result is not None and rag_result.status == RagStatus.EMPTY:
        return False
    terminal = state["runtime"].terminal_event
    return terminal is None
