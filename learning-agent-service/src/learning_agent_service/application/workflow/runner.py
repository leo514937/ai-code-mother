from __future__ import annotations

from typing import Iterable, Optional, Protocol

from ...domain.contracts import (
    ChatTurnCommand,
    PersistentSessionContext,
    SseEnvelope,
)
from ...domain.errors import TerminalEvent, WorkflowErrorCode, build_error
from ...domain.state import GraphState, build_initial_state, clone_graph_state
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


class WorkflowRunner(Protocol):
    def run(
        self,
        command: ChatTurnCommand,
        persistent_context: Optional[PersistentSessionContext] = None,
    ) -> GraphState:
        ...

    def run_stream(
        self,
        command: ChatTurnCommand,
        persistent_context: Optional[PersistentSessionContext] = None,
    ) -> Iterable[SseEnvelope]:
        ...


class SequentialWorkflowRunner:
    def __init__(self, services: WorkflowServices, workflow_version: str = "learn-agent/v1") -> None:
        self.services = services
        self.workflow_version = workflow_version

    def run(
        self,
        command: ChatTurnCommand,
        persistent_context: Optional[PersistentSessionContext] = None,
    ) -> GraphState:
        initial = build_initial_state(
            command=command,
            workflow_version=self.workflow_version,
            persistent=persistent_context,
        )
        return self.run_state(initial)

    def run_state(self, state: GraphState) -> GraphState:
        state = clone_graph_state(state)
        state = self._invoke_stage("load_context", self.services.load_context, state)
        if self._is_terminal(state):
            return self._finalize_terminal(state)

        state = self._invoke_stage(
            "understand_turn",
            lambda current: run_understand_turn(current, self.services.understand_turn),
            state,
        )
        if self._is_terminal(state) or should_clarify(state):
            return self._finalize_terminal(state, default_terminal=TerminalEvent.CLARIFICATION_CARD)

        if should_run_rag(state):
            state = self._invoke_stage(
                "rag_subgraph",
                lambda current: run_rag_subgraph(current, self.services.rag_subgraph),
                state,
            )
            if self._is_terminal(state):
                return self._finalize_terminal(state)

        if should_run_tools(state):
            state = self._invoke_stage(
                "tool_subgraph",
                lambda current: run_tool_subgraph(current, self.services.tool_subgraph),
                state,
            )
            if self._is_terminal(state):
                return self._finalize_terminal(state)

        state = self._invoke_stage("compose_answer", self.services.compose_answer, state)
        if self._is_terminal(state):
            return self._finalize_terminal(state)

        state = self._invoke_stage("persist_session", self.services.persist_session, state)
        if self._is_terminal(state):
            return self._finalize_terminal(state)

        state = self._invoke_stage("update_mastery", self.services.update_mastery, state)
        if self._is_terminal(state):
            return self._finalize_terminal(state)

        if should_recommend(state):
            state = self._invoke_stage("recommend_next", self.services.recommend_next, state)
            if self._is_terminal(state):
                return self._finalize_terminal(state)

        return self._finalize_terminal(state, default_terminal=TerminalEvent.FINAL)

    def run_stream(
        self,
        command: ChatTurnCommand,
        persistent_context: Optional[PersistentSessionContext] = None,
    ) -> Iterable[SseEnvelope]:
        state = self.run(command=command, persistent_context=persistent_context)
        if state["runtime"].emitted_events:
            return list(state["runtime"].emitted_events)
        error_state = self._record_unexpected_error(
            state,
            "emit_final",
            RuntimeError("emit_final did not emit any SSE events"),
        )
        error_state = self._invoke_stage("emit_final", self.services.emit_final, error_state)
        return list(error_state["runtime"].emitted_events)

    def _invoke_stage(self, stage_name: str, handler, state: GraphState) -> GraphState:
        try:
            return handler(state)
        except Exception as exc:  # pragma: no cover - defensive safeguard
            return self._record_unexpected_error(state, stage_name, exc)

    def _record_unexpected_error(self, state: GraphState, stage_name: str, exc: Exception) -> GraphState:
        runtime = state["runtime"]
        errors = list(runtime.errors)
        errors.append(
            build_error(
                WorkflowErrorCode.INTERNAL_ERROR,
                stage=stage_name,
                message=str(exc),
                is_terminal=True,
            )
        )
        state["runtime"] = runtime.model_copy(update={"errors": errors, "terminal_event": TerminalEvent.ERROR})
        return state

    @staticmethod
    def _is_terminal(state: GraphState) -> bool:
        return state["runtime"].terminal_event == TerminalEvent.ERROR

    def _finalize_terminal(
        self,
        state: GraphState,
        default_terminal: Optional[TerminalEvent] = None,
    ) -> GraphState:
        runtime = state["runtime"]
        if runtime.terminal_event is None and default_terminal is not None:
            state["runtime"] = runtime.model_copy(update={"terminal_event": default_terminal})

        state = self._invoke_stage("emit_final", self.services.emit_final, state)
        runtime = state["runtime"]
        if runtime.terminal_event is None:
            state["runtime"] = runtime.model_copy(update={"terminal_event": default_terminal or TerminalEvent.FINAL})
        return state
