from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List
from uuid import uuid4

from learning_agent_service.api.contracts import (
    AckPayload,
    ChatStreamRequest,
    ErrorPayload as ApiErrorPayload,
    EventType,
    QuizQuestion,
    QuizGenerateRequest,
    QuizGenerateResponse,
    SessionStateResponse,
    SseEnvelope as ApiSseEnvelope,
    StudyPlanItem,
    StudyPlanGenerateRequest,
    StudyPlanGenerateResponse,
)
from learning_agent_service.application.use_cases import (
    ChatWorkflowService,
    QuizGenerationService,
    SessionQueryService,
    StudyPlanGenerationService,
)
from learning_agent_service.domain import ChatTurnCommand
from learning_agent_service.domain.enums import OutputStyle


class WorkflowLearningAgentService:
    def __init__(self, container) -> None:
        self.container = container
        self.chat_use_case = ChatWorkflowService(container)
        self.quiz_use_case = QuizGenerationService(
            tool_planner=container.tool_planner,
            tool_executor=container.tool_executor,
            tool_result_normalizer=container.tool_result_normalizer,
        )
        self.study_plan_use_case = StudyPlanGenerationService(
            tool_planner=container.tool_planner,
            tool_executor=container.tool_executor,
            tool_result_normalizer=container.tool_result_normalizer,
        )
        self.session_query_use_case = SessionQueryService(memory_service=container.memory_service)

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
        ack = ApiSseEnvelope(
            event_type=EventType.ACK.value,
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
        events: List[ApiSseEnvelope] = [ack]
        try:
            events.extend(
                ApiSseEnvelope.model_validate(event.model_dump(mode="json"))
                for event in self.chat_use_case.run(command=command, persistent_context=persistent)
            )
        except RuntimeError as exc:
            events.append(
                ApiSseEnvelope(
                    event_type=EventType.ERROR.value,
                    trace_id=request.trace_id,
                    session_id=request.session_id,
                    turn_id=turn_id,
                    timestamp=datetime.now(timezone.utc),
                    workflow_version=self.container.settings.workflow_version,
                    payload=ApiErrorPayload(
                        code="LEARN-5600",
                        message=str(exc),
                        retryable=False,
                        stage="chat_stream",
                    ).model_dump(mode="json"),
                )
            )
        return events

    def generate_quiz(self, request: QuizGenerateRequest) -> QuizGenerateResponse:
        questions = self.quiz_use_case.generate(
            user_id=request.user_id,
            session_id=request.session_id,
            topic=request.topic,
            count=request.count,
            difficulty=request.difficulty or "intermediate",
        )
        return QuizGenerateResponse(
            topic=request.topic,
            questions=[QuizQuestion.model_validate(item) for item in questions],
        )

    def generate_study_plan(self, request: StudyPlanGenerateRequest) -> StudyPlanGenerateResponse:
        items = self.study_plan_use_case.generate(
            user_id=request.user_id,
            session_id=request.session_id,
            topic=request.topic,
            duration_days=request.duration_days,
            goal=request.goal or "systematic-review",
        )
        return StudyPlanGenerateResponse(
            topic=request.topic,
            items=[StudyPlanItem.model_validate(item) for item in items],
        )

    def get_session_state(self, session_id: str) -> SessionStateResponse:
        context = self.session_query_use_case.get(session_id)
        return SessionStateResponse(
            session_id=session_id,
            current_topic=context.current_topic,
            recent_entities=list(context.recent_entities),
            clarification_result=dict(context.clarification_result),
            user_preferences=dict(context.user_preferences),
            last_retrieval_topic=context.last_retrieval_topic,
            active_plan_id=context.active_plan_id,
            learning_mode=context.learning_mode,
            extra=dict(context.extra),
        )


def create_learning_agent_service(container) -> WorkflowLearningAgentService:
    return WorkflowLearningAgentService(container)
