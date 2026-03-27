from __future__ import annotations

from typing import Any

from ...domain.errors import TerminalEvent
from .runner import SequentialWorkflowRunner
from .services import WorkflowServices
from .subgraphs import (
    run_rag_subgraph,
    run_tool_subgraph,
    run_understand_turn,
    should_clarify,
    should_recommend,
    should_run_rag,
    should_run_tools,
)

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - optional dependency
    END = "__end__"
    StateGraph = None


LANGGRAPH_AVAILABLE = StateGraph is not None


class LangGraphWorkflowRunner(SequentialWorkflowRunner):
    def __init__(self, services: WorkflowServices, workflow_version: str = "learn-agent/v1") -> None:
        super().__init__(services=services, workflow_version=workflow_version)
        self._graph = _build_langgraph_runner(services)

    def run_state(self, state):
        if self._is_terminal(state):
            return self._finalize_terminal(state)

        try:
            result = self._graph.invoke(state)
        except Exception as exc:
            result = self._record_unexpected_error(state, "langgraph.invoke", exc)

        runtime = result["runtime"]
        if runtime.emitted_events:
            if runtime.terminal_event is None:
                default_terminal = (
                    TerminalEvent.ERROR
                    if runtime.errors
                    else TerminalEvent.CLARIFICATION_CARD
                    if should_clarify(result)
                    else TerminalEvent.FINAL
                )
                result["runtime"] = runtime.model_copy(update={"terminal_event": default_terminal})
            return result

        if result["runtime"].terminal_event == TerminalEvent.ERROR:
            return self._finalize_terminal(result)
        if should_clarify(result):
            return self._finalize_terminal(result, default_terminal=TerminalEvent.CLARIFICATION_CARD)
        return self._finalize_terminal(result, default_terminal=TerminalEvent.FINAL)



def _build_langgraph_runner(services: WorkflowServices):
    if not LANGGRAPH_AVAILABLE:
        raise RuntimeError("langgraph is not installed")

    graph = StateGraph(dict)
    graph.add_node("load_context", services.load_context)
    graph.add_node("understand_turn", lambda state: run_understand_turn(state, services.understand_turn))
    graph.add_node("rag_subgraph", lambda state: run_rag_subgraph(state, services.rag_subgraph))
    graph.add_node("tool_subgraph", lambda state: run_tool_subgraph(state, services.tool_subgraph))
    graph.add_node("compose_answer", services.compose_answer)
    graph.add_node("persist_session", services.persist_session)
    graph.add_node("update_mastery", services.update_mastery)
    graph.add_node("recommend_next", services.recommend_next)
    graph.add_node("emit_final", services.emit_final)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "understand_turn")
    graph.add_conditional_edges(
        "understand_turn",
        _route_after_understanding,
        {
            "emit_final": "emit_final",
            "rag_subgraph": "rag_subgraph",
            "tool_subgraph": "tool_subgraph",
            "compose_answer": "compose_answer",
        },
    )
    graph.add_conditional_edges(
        "rag_subgraph",
        _route_after_rag,
        {
            "tool_subgraph": "tool_subgraph",
            "compose_answer": "compose_answer",
        },
    )
    graph.add_edge("tool_subgraph", "compose_answer")
    graph.add_edge("compose_answer", "persist_session")
    graph.add_edge("persist_session", "update_mastery")
    graph.add_conditional_edges(
        "update_mastery",
        _route_after_mastery,
        {
            "recommend_next": "recommend_next",
            "emit_final": "emit_final",
        },
    )
    graph.add_edge("recommend_next", "emit_final")
    graph.add_edge("emit_final", END)
    return graph.compile()



def _route_after_understanding(state: Any) -> str:
    if should_clarify(state):
        return "emit_final"
    if should_run_rag(state):
        return "rag_subgraph"
    if should_run_tools(state):
        return "tool_subgraph"
    return "compose_answer"



def _route_after_rag(state: Any) -> str:
    if should_run_tools(state):
        return "tool_subgraph"
    return "compose_answer"



def _route_after_mastery(state: Any) -> str:
    if should_recommend(state):
        return "recommend_next"
    return "emit_final"



def create_workflow_runner(
    services: WorkflowServices,
    prefer_langgraph: bool = True,
    workflow_version: str = "learn-agent/v1",
):
    if prefer_langgraph and LANGGRAPH_AVAILABLE:
        return LangGraphWorkflowRunner(services=services, workflow_version=workflow_version)
    return SequentialWorkflowRunner(services=services, workflow_version=workflow_version)
