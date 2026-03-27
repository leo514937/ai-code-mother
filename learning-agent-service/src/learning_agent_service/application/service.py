from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List
from uuid import uuid4

from learning_agent_service.api.contracts import (
    AckPayload,
    ChatStreamRequest,
    ClarificationCardPayload,
    ErrorPayload as ApiErrorPayload,
    EventType,
    FinalPayload as ApiFinalPayload,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestion,
    RetrievalResultPayload,
    RetrievalStartedPayload,
    SessionStateResponse,
    SseEnvelope as ApiSseEnvelope,
    StudyPlanGenerateRequest,
    StudyPlanGenerateResponse,
    StudyPlanItem,
    ToolCallPayload,
    ToolResultPayload,
)
from learning_agent_service.application.workflow import (
    RagSubgraphServices,
    ToolSubgraphServices,
    UnderstandTurnServices,
    WorkflowServices,
    create_workflow_runner,
)
from learning_agent_service.application.workflow.adapters import WorkflowNodeAdapter
from learning_agent_service.domain import (
    ChatTurnCommand,
    GraphState,
    SseEnvelope,
    build_initial_state,
)
from learning_agent_service.domain.enums import OutputStyle, ToolExecutionStatus


class WorkflowLearningAgentService:
    def __init__(self, container) -> None:
        self.container = container
        self.nodes = WorkflowNodeAdapter(container)
        self.workflow_runner = create_workflow_runner(
            services=self._build_workflow_services(),
            prefer_langgraph=True,
            workflow_version=container.settings.workflow_version,
        )

    def run_stream(self, request: ChatStreamRequest) -> Iterable[ApiSseEnvelope]:
        turn_id = request.turn_id or "turn-{value}".format(value=uuid4().hex[:8])
        command = ChatTurnCommand(
            trace_id=request.trace_id,
            session_id=request.session_id,
            turn_id=turn_id,
            user_id=request.user_id,
            message=request.message,
            response_mode=OutputStyle(request.response_mode) if request.response_mode else None,
            topic_hint=request.topic_hint,
            history_summary=request.history_summary,
            client_context=request.client_context,
        )
        persistent = self.container.session_context_store.load(request.session_id, request.user_id)
        events: List[ApiSseEnvelope] = [
            ApiSseEnvelope(
                event_type=EventType.ACK,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=turn_id,
                timestamp=datetime.now(timezone.utc),
                workflow_version=self.container.settings.workflow_version,
                payload=AckPayload(
                    message="accepted",
                    accepted_at=datetime.now(timezone.utc),
                ).model_dump(mode="json"),
            )
        ]
        for envelope in self.workflow_runner.run_stream(command=command, persistent_context=persistent):
            events.append(self._to_api_envelope(envelope))
        return events

    def generate_quiz(self, request: QuizGenerateRequest) -> QuizGenerateResponse:
        state = self._empty_state(request.user_id, request.session_id)
        selection = self.container.tool_planner.plan_from_name(
            "generateQuiz",
            {
                "topic": request.topic,
                "count": request.count,
                "difficulty": request.difficulty or "intermediate",
            },
        )
        raw = self.container.tool_executor.execute(selection, state)
        normalized = self.container.tool_result_normalizer.normalize(raw, state)
        questions = normalized.normalized_output.get("data", {}).get("questions", [])
        return QuizGenerateResponse(topic=request.topic, questions=[QuizQuestion(**item) for item in questions])

    def generate_study_plan(self, request: StudyPlanGenerateRequest) -> StudyPlanGenerateResponse:
        state = self._empty_state(request.user_id, request.session_id)
        selection = self.container.tool_planner.plan_from_name(
            "generateStudyPlan",
            {
                "topic": request.topic,
                "duration_days": request.duration_days,
                "goal": request.goal or "systematic-review",
            },
        )
        raw = self.container.tool_executor.execute(selection, state)
        normalized = self.container.tool_result_normalizer.normalize(raw, state)
        items = normalized.normalized_output.get("data", {}).get("items", [])
        return StudyPlanGenerateResponse(topic=request.topic, items=[StudyPlanItem(**item) for item in items])

    def get_session_state(self, session_id: str) -> SessionStateResponse:
        context = self.container.memory_service.load_any(session_id)
        return SessionStateResponse(
            session_id=session_id,
            current_topic=context.current_topic,
            recent_entities=context.recent_entities,
            clarification_result=context.clarification_result,
            user_preferences=context.user_preferences,
            last_retrieval_topic=context.last_retrieval_topic,
            active_plan_id=context.active_plan_id,
            learning_mode=context.learning_mode,
            extra=context.extra,
        )

    def _build_workflow_services(self) -> WorkflowServices:
        return WorkflowServices(
            load_context=self._load_context,
            understand_turn=UnderstandTurnServices(
                parse_intent_slots=self._parse_intent_slots,
                resolve_reference=self._resolve_reference,
                ambiguity_check=self._ambiguity_check,
                rewrite_query=self._rewrite_query,
            ),
            rag_subgraph=RagSubgraphServices(
                hybrid_retrieve=self._hybrid_retrieve,
                evaluate_evidence=self._evaluate_evidence,
                citation_builder=self._citation_builder,
            ),
            tool_subgraph=ToolSubgraphServices(
                tool_planner=self._tool_planner,
                tool_executor=self._tool_executor,
                tool_result_normalizer=self._tool_result_normalizer,
            ),
            compose_answer=self.container.answer_composer.compose,
            persist_session=self.nodes.persist_session,
            update_mastery=self.nodes.update_mastery,
            recommend_next=self.nodes.recommend_next,
            emit_final=self._emit_final,
        )

    def _load_context(self, state: GraphState) -> GraphState:
        return self.nodes.load_context(state)

    def _parse_intent_slots(self, state: GraphState) -> GraphState:
        return self.nodes.parse_intent_slots(state)

    def _resolve_reference(self, state: GraphState) -> GraphState:
        return self.nodes.resolve_reference(state)

    def _ambiguity_check(self, state: GraphState) -> GraphState:
        return self.nodes.ambiguity_check(state)

    def _rewrite_query(self, state: GraphState) -> GraphState:
        return self.nodes.rewrite_query(state)

    def _hybrid_retrieve(self, state: GraphState) -> GraphState:
        return self.nodes.hybrid_retrieve(state)

    def _evaluate_evidence(self, state: GraphState) -> GraphState:
        return self.nodes.evaluate_evidence(state)

    def _citation_builder(self, state: GraphState) -> GraphState:
        return self.nodes.citation_builder(state)

    def _tool_planner(self, state: GraphState) -> GraphState:
        return self.nodes.tool_planner(state)

    def _tool_executor(self, state: GraphState) -> GraphState:
        return self.nodes.tool_executor(state)

    def _tool_result_normalizer(self, state: GraphState) -> GraphState:
        return self.nodes.tool_result_normalizer(state)

    def _emit_final(self, state: GraphState) -> GraphState:
        return self.nodes.emit_final(state)

    def _append_event(self, state: GraphState, event_type: str, payload: dict) -> None:
        runtime = state["runtime"]
        envelope = SseEnvelope(
            event_type=event_type,
            trace_id=runtime.trace_id,
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            timestamp=datetime.now(timezone.utc),
            workflow_version=runtime.workflow_version,
            payload=payload,
        )
        state["runtime"] = runtime.model_copy(update={"emitted_events": [*runtime.emitted_events, envelope]})

    def _to_api_envelope(self, envelope) -> ApiSseEnvelope:
        event_type = EventType(envelope.event_type)
        payload = envelope.payload
        if event_type == EventType.FINAL:
            payload = ApiFinalPayload.model_validate(payload).model_dump(mode="json")
        elif event_type == EventType.CLARIFICATION_CARD:
            payload = ClarificationCardPayload.model_validate(payload).model_dump(mode="json")
        elif event_type == EventType.ERROR:
            payload = ApiErrorPayload.model_validate(payload).model_dump(mode="json")
        elif event_type == EventType.RETRIEVAL_STARTED:
            payload = RetrievalStartedPayload.model_validate(payload).model_dump(mode="json")
        elif event_type == EventType.RETRIEVAL_RESULT:
            payload = RetrievalResultPayload.model_validate(payload).model_dump(mode="json")
        elif event_type == EventType.TOOL_CALL:
            payload = ToolCallPayload.model_validate(payload).model_dump(mode="json")
        elif event_type == EventType.TOOL_RESULT:
            payload = ToolResultPayload.model_validate(payload).model_dump(mode="json")
        return ApiSseEnvelope(
            event_type=event_type,
            trace_id=envelope.trace_id,
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
            timestamp=envelope.timestamp,
            workflow_version=envelope.workflow_version,
            payload=payload,
        )

    def _empty_state(self, user_id: str, session_id: str) -> GraphState:
        command = ChatTurnCommand(
            trace_id="tool-{value}".format(value=uuid4().hex[:8]),
            session_id=session_id,
            turn_id="tool-turn",
            user_id=user_id,
            message="tool invocation",
        )
        persistent = self.container.session_context_store.load(session_id, user_id)
        return build_initial_state(
            command=command,
            workflow_version=self.container.settings.workflow_version,
            persistent=persistent,
        )


def create_learning_agent_service(container) -> WorkflowLearningAgentService:
    return WorkflowLearningAgentService(container)
