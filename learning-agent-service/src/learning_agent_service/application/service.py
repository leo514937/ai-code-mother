from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List
from uuid import uuid4

from learning_agent_service.api.contracts import (
    AckPayload,
    ChatStreamRequest,
    EventType,
    FinalPayload as ApiFinalPayload,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestion,
    SessionStateResponse,
    SseEnvelope as ApiSseEnvelope,
    StudyPlanGenerateRequest,
    StudyPlanGenerateResponse,
    StudyPlanItem,
)
from learning_agent_service.application.workflow import (
    RagSubgraphServices,
    ToolSubgraphServices,
    UnderstandTurnServices,
    WorkflowServices,
    create_workflow_runner,
)
from learning_agent_service.domain import (
    ChatTurnCommand,
    ClarificationCard,
    ClarificationOption,
    GraphState,
    TurnUnderstandingResult,
    build_initial_state,
)
from learning_agent_service.domain.enums import OutputStyle, TurnDecision


class WorkflowLearningAgentService:
    def __init__(self, container) -> None:
        self.container = container
        self.workflow_runner = create_workflow_runner(
            services=self._build_workflow_services(),
            prefer_langgraph=False,
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
                payload=AckPayload(message="accepted", accepted_at=datetime.now(timezone.utc)).model_dump(mode="json"),
            )
        ]
        for envelope in self.workflow_runner.run_stream(command=command, persistent_context=persistent):
            events.append(self._to_api_envelope(envelope))
        return events

    def generate_quiz(self, request: QuizGenerateRequest) -> QuizGenerateResponse:
        state = self._empty_state(request.user_id, request.session_id)
        selection = self.container.tool_planner.plan_from_name("generateQuiz", {"topic": request.topic, "count": request.count, "difficulty": request.difficulty or "intermediate"})
        raw = self.container.tool_executor.execute(selection, state)
        normalized = self.container.tool_result_normalizer.normalize(raw, state)
        questions = normalized.normalized_output.get("data", {}).get("questions", [])
        return QuizGenerateResponse(topic=request.topic, questions=[QuizQuestion(**item) for item in questions])

    def generate_study_plan(self, request: StudyPlanGenerateRequest) -> StudyPlanGenerateResponse:
        state = self._empty_state(request.user_id, request.session_id)
        selection = self.container.tool_planner.plan_from_name("generateStudyPlan", {"topic": request.topic, "duration_days": request.duration_days, "goal": request.goal or "systematic-review"})
        raw = self.container.tool_executor.execute(selection, state)
        normalized = self.container.tool_result_normalizer.normalize(raw, state)
        items = normalized.normalized_output.get("data", {}).get("items", [])
        return StudyPlanGenerateResponse(topic=request.topic, items=[StudyPlanItem(**item) for item in items])

    def get_session_state(self, session_id: str) -> SessionStateResponse:
        context = self.container.memory_service.load_any(session_id)
        return SessionStateResponse(session_id=session_id, current_topic=context.current_topic, recent_entities=context.recent_entities, clarification_result=context.clarification_result, user_preferences=context.user_preferences, last_retrieval_topic=context.last_retrieval_topic, active_plan_id=context.active_plan_id, learning_mode=context.learning_mode, extra=context.extra)

    def _build_workflow_services(self) -> WorkflowServices:
        return WorkflowServices(
            load_context=self._load_context,
            understand_turn=UnderstandTurnServices(parse_intent_slots=self._parse_intent_slots, resolve_reference=self._resolve_reference, ambiguity_check=self._ambiguity_check, rewrite_query=self._rewrite_query),
            rag_subgraph=RagSubgraphServices(hybrid_retrieve=self._hybrid_retrieve, evaluate_evidence=self._evaluate_evidence, citation_builder=self._citation_builder),
            tool_subgraph=ToolSubgraphServices(tool_planner=self._tool_planner, tool_executor=self._tool_executor, tool_result_normalizer=self._tool_result_normalizer),
            compose_answer=self.container.answer_composer.compose,
            persist_session=self.container.memory_service.persist_session,
            update_mastery=self.container.memory_service.update_mastery,
            recommend_next=self.container.memory_service.recommend_next,
            emit_final=self._emit_final,
        )

    def _load_context(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        user_id = str(runtime.extra.get("user_id", "anonymous"))
        state["persistent"] = self.container.session_context_store.load(runtime.session_id, user_id)
        return state

    def _parse_intent_slots(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        response_mode = runtime.extra.get("response_mode")
        command = ChatTurnCommand(trace_id=runtime.trace_id, session_id=runtime.session_id, turn_id=runtime.turn_id, user_id=str(runtime.extra.get("user_id", "anonymous")), message=state["turn"].raw_query, response_mode=OutputStyle(response_mode) if response_mode else None, topic_hint=runtime.extra.get("topic_hint"), client_context=runtime.extra.get("client_context", {}))
        state["turn"] = state["turn"].model_copy(update={"understanding_result": self.container.model_gateway.classify_turn(command, state)})
        return state

    def _resolve_reference(self, state: GraphState) -> GraphState:
        resolver = getattr(self.container.rag_orchestrator, "resolve_reference", None)
        if not callable(resolver):
            return state
        understanding = state["turn"].understanding_result or TurnUnderstandingResult()
        resolution = resolver(state)
        state["turn"] = state["turn"].model_copy(update={"understanding_result": understanding.model_copy(update={"reference_resolution": resolution})})
        return state

    def _ambiguity_check(self, state: GraphState) -> GraphState:
        understanding = state["turn"].understanding_result or TurnUnderstandingResult()
        reference = understanding.reference_resolution
        low_intent = understanding.intent_confidence < 0.5
        low_reference = understanding.intent.value == "follow_up" and (reference is None or reference.confidence < 0.5)
        if not low_intent and not low_reference:
            return state
        candidates = []
        if reference is not None:
            candidates.extend(reference.candidate_entities)
        candidates.extend(state["persistent"].recent_entities)
        candidates = [value for idx, value in enumerate(candidates) if value and value not in candidates[:idx]][:3]
        card = ClarificationCard(card_id="clarify-{turn_id}".format(turn_id=state["runtime"].turn_id), question="Which topic do you want to continue with?", options=[ClarificationOption(id=str(idx + 1), label=value, value=value) for idx, value in enumerate(candidates)], ambiguity_type="intent" if low_intent else "reference", source_turn_id=state["runtime"].turn_id)
        state["turn"] = state["turn"].model_copy(update={"understanding_result": understanding.model_copy(update={"decision": TurnDecision.CLARIFY, "clarification_card": card})})
        return state

    def _rewrite_query(self, state: GraphState) -> GraphState:
        plan = self.container.rag_orchestrator.rewrite_query(state)
        understanding = state["turn"].understanding_result or TurnUnderstandingResult()
        state["turn"] = state["turn"].model_copy(update={"retrieval_plan": plan, "understanding_result": understanding.model_copy(update={"retrieval_plan": plan})})
        return state

    def _hybrid_retrieve(self, state: GraphState) -> GraphState:
        state["turn"] = state["turn"].model_copy(update={"rag_result": self.container.rag_orchestrator.run(state)})
        return state

    def _evaluate_evidence(self, state: GraphState) -> GraphState:
        return state

    def _citation_builder(self, state: GraphState) -> GraphState:
        rag_result = state["turn"].rag_result
        if rag_result is None:
            return state
        citations = list(self.container.rag_orchestrator.build_citations(state))
        state["turn"] = state["turn"].model_copy(update={"rag_result": rag_result.model_copy(update={"citations": citations})})
        return state

    def _tool_planner(self, state: GraphState) -> GraphState:
        state["turn"] = state["turn"].model_copy(update={"tool_plan": self.container.tool_planner.plan(state)})
        return state

    def _tool_executor(self, state: GraphState) -> GraphState:
        plan = state["turn"].tool_plan
        if plan is None:
            return state
        raw = self.container.tool_executor.execute(plan, state)
        runtime = state["runtime"]
        runtime_extra = dict(runtime.extra)
        runtime_extra["raw_tool_result"] = raw.model_dump(mode="json")
        state["runtime"] = runtime.model_copy(update={"extra": runtime_extra})
        return state

    def _tool_result_normalizer(self, state: GraphState) -> GraphState:
        raw_payload = state["runtime"].extra.get("raw_tool_result")
        if not raw_payload:
            return state
        from learning_agent_service.domain import ToolExecutionResult

        raw = ToolExecutionResult.model_validate(raw_payload)
        state["turn"] = state["turn"].model_copy(update={"tool_result": self.container.tool_result_normalizer.normalize(raw, state)})
        return state

    def _emit_final(self, state: GraphState) -> GraphState:
        return state

    def _to_api_envelope(self, envelope) -> ApiSseEnvelope:
        event_type = EventType(envelope.event_type)
        payload = ApiFinalPayload.model_validate(envelope.payload).model_dump(mode="json") if event_type == EventType.FINAL else envelope.payload
        return ApiSseEnvelope(event_type=event_type, trace_id=envelope.trace_id, session_id=envelope.session_id, turn_id=envelope.turn_id, timestamp=envelope.timestamp, workflow_version=envelope.workflow_version, payload=payload)

    def _empty_state(self, user_id: str, session_id: str) -> GraphState:
        command = ChatTurnCommand(trace_id="tool-{value}".format(value=uuid4().hex[:8]), session_id=session_id, turn_id="tool-turn", user_id=user_id, message="tool invocation")
        persistent = self.container.session_context_store.load(session_id, user_id)
        return build_initial_state(command=command, workflow_version=self.container.settings.workflow_version, persistent=persistent)


def create_learning_agent_service(container) -> WorkflowLearningAgentService:
    return WorkflowLearningAgentService(container)
