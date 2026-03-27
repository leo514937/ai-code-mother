from __future__ import annotations

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


def _sync_turn_from_understanding(state: GraphState) -> GraphState:
    turn = state["turn"]
    understanding = turn.understanding_result
    if understanding is None:
        return state
    state["turn"] = turn.model_copy(
        update={
            "decision": understanding.decision,
            "intent": understanding.intent,
            "intent_confidence": understanding.intent_confidence,
            "requested_output_style": understanding.requested_output_style,
            "reference_resolution": understanding.reference_resolution,
            "retrieval_plan": turn.retrieval_plan or understanding.retrieval_plan,
            "clarification_card": understanding.clarification_card,
            "slots": dict(understanding.slots),
        }
    )
    return state


def _sync_understanding_from_turn(state: GraphState) -> GraphState:
    turn = state["turn"]
    understanding = turn.understanding_result or TurnUnderstandingResult()
    state["turn"] = turn.model_copy(
        update={
            "understanding_result": understanding.model_copy(
                update={
                    "decision": turn.decision,
                    "intent": turn.intent or understanding.intent,
                    "intent_confidence": turn.intent_confidence,
                    "requested_output_style": turn.requested_output_style,
                    "reference_resolution": turn.reference_resolution,
                    "retrieval_plan": turn.retrieval_plan,
                    "clarification_card": turn.clarification_card,
                    "slots": dict(turn.slots),
                }
            )
        }
    )
    return state


def _ensure_understanding_result(state: GraphState) -> GraphState:
    turn = state["turn"]
    if turn.understanding_result is None:
        state["turn"] = turn.model_copy(update={"understanding_result": TurnUnderstandingResult(decision=turn.decision)})
    return _sync_understanding_from_turn(state)


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
    state = _ensure_understanding_result(state)
    state = _sync_turn_from_understanding(state)

    state = services.resolve_reference(state)
    state = _ensure_understanding_result(state)
    state = _sync_turn_from_understanding(state)

    state = services.ambiguity_check(state)
    state = _ensure_understanding_result(state)
    state = _sync_turn_from_understanding(state)

    if state["turn"].decision in CLARIFY_DECISIONS:
        return state

    if state["turn"].decision in RAG_DECISIONS:
        state = services.rewrite_query(state)
        state = _ensure_understanding_result(state)
        state = _sync_turn_from_understanding(state)

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


def should_clarify(state: GraphState) -> bool:
    return state["turn"].decision in CLARIFY_DECISIONS


def should_run_rag(state: GraphState) -> bool:
    return state["turn"].decision in RAG_DECISIONS and state["turn"].retrieval_plan is not None


def should_run_tools(state: GraphState) -> bool:
    return state["turn"].decision in TOOL_DECISIONS


def should_recommend(state: GraphState) -> bool:
    if not state["persistent"].learning_mode:
        return False
    rag_result = state["turn"].rag_result
    if rag_result is not None and rag_result.status == RagStatus.EMPTY:
        return False
    terminal = state["runtime"].terminal_event
    return terminal is None
