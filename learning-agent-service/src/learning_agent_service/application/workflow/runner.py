from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol

from ...domain.contracts import (
    ChatTurnCommand,
    ErrorPayload,
    FinalPayload,
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
            return self._emit_terminal(state)

        state = self._invoke_stage(
            "understand_turn",
            lambda current: run_understand_turn(current, self.services.understand_turn),
            state,
        )
        if self._is_terminal(state) or should_clarify(state):
            return self._emit_terminal(state, default_terminal=TerminalEvent.CLARIFICATION_CARD)

        if should_run_rag(state):
            state = self._invoke_stage(
                "rag_subgraph",
                lambda current: run_rag_subgraph(current, self.services.rag_subgraph),
                state,
            )
            if self._is_terminal(state):
                return self._emit_terminal(state)

        if should_run_tools(state):
            state = self._invoke_stage(
                "tool_subgraph",
                lambda current: run_tool_subgraph(current, self.services.tool_subgraph),
                state,
            )
            if self._is_terminal(state):
                return self._emit_terminal(state)

        state = self._invoke_stage("compose_answer", self.services.compose_answer, state)
        if self._is_terminal(state):
            return self._emit_terminal(state)

        state = self._invoke_stage("persist_session", self.services.persist_session, state)
        if self._is_terminal(state):
            return self._emit_terminal(state)

        state = self._invoke_stage("update_mastery", self.services.update_mastery, state)
        if self._is_terminal(state):
            return self._emit_terminal(state)

        if should_recommend(state):
            state = self._invoke_stage("recommend_next", self.services.recommend_next, state)
            if self._is_terminal(state):
                return self._emit_terminal(state)

        return self._emit_terminal(state, default_terminal=TerminalEvent.FINAL)

    def run_stream(
        self,
        command: ChatTurnCommand,
        persistent_context: Optional[PersistentSessionContext] = None,
    ) -> Iterable[SseEnvelope]:
        state = self.run(command=command, persistent_context=persistent_context)
        emitted = state["runtime"].extra.get("emitted_events", [])
        if emitted:
            return list(emitted)
        return [self._build_terminal_envelope(state)]

    def _invoke_stage(self, stage_name: str, handler, state: GraphState) -> GraphState:
        try:
            return handler(state)
        except Exception as exc:
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

    def _is_terminal(self, state: GraphState) -> bool:
        return state["runtime"].terminal_event == TerminalEvent.ERROR

    def _emit_terminal(
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

        if not state["runtime"].extra.get("emitted_events"):
            envelope = self._build_terminal_envelope(state)
            runtime = state["runtime"]
            runtime_extra = dict(runtime.extra)
            runtime_extra["emitted_events"] = [envelope]
            state["runtime"] = runtime.model_copy(update={"extra": runtime_extra})
        return state

    def _build_terminal_envelope(self, state: GraphState) -> SseEnvelope:
        runtime = state["runtime"]
        terminal = runtime.terminal_event or TerminalEvent.FINAL
        timestamp = datetime.now(timezone.utc)
        workflow_version = str(runtime.extra.get("workflow_version", self.workflow_version))

        if terminal == TerminalEvent.ERROR:
            last_error = runtime.errors[-1] if runtime.errors else build_error(
                WorkflowErrorCode.INTERNAL_ERROR,
                stage="unknown",
                message="Unknown workflow error",
                is_terminal=True,
            )
            payload = ErrorPayload(
                code=last_error.code.value,
                message=last_error.message,
                retryable=last_error.retryable,
                stage=last_error.stage,
                degraded_to=last_error.degraded_to,
                details=last_error.details,
            )
            event_type = TerminalEvent.ERROR.value
        elif terminal == TerminalEvent.CLARIFICATION_CARD:
            card = None
            understanding = state["turn"].understanding_result
            if understanding is not None:
                card = understanding.clarification_card
            payload = card.model_dump() if card is not None else {}
            event_type = TerminalEvent.CLARIFICATION_CARD.value
        else:
            payload = self._build_final_payload(state)
            event_type = TerminalEvent.FINAL.value

        return SseEnvelope(
            event_type=event_type,
            trace_id=runtime.trace_id,
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            timestamp=timestamp,
            workflow_version=workflow_version,
            payload=payload.model_dump() if hasattr(payload, "model_dump") else payload,
        )

    def _build_final_payload(self, state: GraphState) -> FinalPayload:
        turn = state["turn"]
        persistent = state["persistent"]
        runtime = state["runtime"]
        understanding = turn.understanding_result
        rag_result = turn.rag_result
        tool_result = turn.tool_result
        resolved_topic = persistent.current_topic
        if not resolved_topic and understanding and understanding.reference_resolution:
            resolved_topic = understanding.reference_resolution.resolved_entity

        recommendation = turn.extra.get("recommendation")
        memory_updates = runtime.extra.get("memory_updates", {})
        final_confidence = runtime.metrics.get("final_answer_confidence", 0.0)

        return FinalPayload(
            answer_text=turn.final_answer or "",
            citations=rag_result.citations if rag_result is not None else [],
            used_tools=tool_result.used_tools if tool_result is not None else [],
            resolved_topic=resolved_topic,
            retrieval_strategy=rag_result.retrieval_strategy if rag_result is not None else None,
            memory_updates=memory_updates,
            recommendation=recommendation,
            confidence=final_confidence,
            intent=understanding.intent if understanding is not None else None,
            requested_output_style=(
                understanding.requested_output_style if understanding is not None else None
            ),
            metrics=runtime.metrics,
        )
