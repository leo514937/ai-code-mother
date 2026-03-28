from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from learning_agent_service.domain.contracts import (
    Citation,
    ClarificationCard,
    ErrorPayload,
    FinalPayload,
)


class ApiResponse(BaseModel):
    ok: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None

    @classmethod
    def success(cls, data: Any = None) -> "ApiResponse":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> "ApiResponse":
        return cls(ok=False, error=error)


class EventType(str, Enum):
    ACK = "ack"
    CLARIFICATION_CARD = "clarification_card"
    RETRIEVAL_STARTED = "retrieval_started"
    RETRIEVAL_RESULT = "retrieval_result"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINAL = "final"
    ERROR = "error"


class AckPayload(BaseModel):
    message: str
    accepted_at: datetime


class ClarificationOptionPayload(BaseModel):
    id: str
    label: str
    value: Optional[str] = None
    description: Optional[str] = None


class ClarificationCardPayload(BaseModel):
    card_id: str
    question: str
    options: List[ClarificationOptionPayload] = Field(default_factory=list)
    ambiguity_type: Optional[str] = None

    @classmethod
    def from_domain(cls, card: ClarificationCard) -> "ClarificationCardPayload":
        return cls.model_validate(card.model_dump(mode="json"))


class RetrievalStartedPayload(BaseModel):
    semantic_query: str
    keyword_query: str
    retrieval_filters: Dict[str, Any] = Field(default_factory=dict)


class RetrievalResultPayload(BaseModel):
    retrieval_strategy: str
    retrieval_hit_count: int = Field(ge=0)
    evidence_used_count: int = Field(ge=0)


class ToolCallPayload(BaseModel):
    tool_name: str
    tool_call_id: str
    input_summary: Dict[str, Any] = Field(default_factory=dict)


class ToolResultPayload(BaseModel):
    tool_name: str
    tool_call_id: str
    status: str
    degraded: bool = False
    retryable: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    degraded_to: Optional[str] = None
    output: Dict[str, Any] = Field(default_factory=dict)


class ChatStreamRequest(BaseModel):
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    turn_id: Optional[str] = None
    response_mode: Optional[str] = None
    topic_hint: Optional[str] = None
    history_summary: Optional[str] = None
    client_context: Dict[str, Any] = Field(default_factory=dict)


class QuizGenerateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    count: int = Field(default=5, ge=1, le=20)
    difficulty: Optional[str] = None


class QuizQuestion(BaseModel):
    question: str
    answer: Optional[str] = None
    difficulty: Optional[str] = None
    common_pitfall: Optional[str] = None


class QuizGenerateResponse(BaseModel):
    topic: str
    questions: List[QuizQuestion] = Field(default_factory=list)


class StudyPlanGenerateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    duration_days: int = Field(default=7, ge=1, le=60)
    goal: Optional[str] = None


class StudyPlanItem(BaseModel):
    day: int = Field(ge=1)
    title: str
    objective: Optional[str] = None


class StudyPlanGenerateResponse(BaseModel):
    topic: str
    items: List[StudyPlanItem] = Field(default_factory=list)


class SessionStateResponse(BaseModel):
    session_id: str
    current_topic: Optional[str] = None
    recent_entities: List[str] = Field(default_factory=list)
    clarification_result: Optional[Dict[str, Any]] = None
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    last_retrieval_topic: Optional[str] = None
    active_plan_id: Optional[str] = None
    learning_mode: Optional[bool] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class SseEnvelope(BaseModel):
    event_type: str
    trace_id: str
    session_id: str
    turn_id: str
    timestamp: datetime
    workflow_version: str
    payload: Dict[str, Any] = Field(default_factory=dict)


EVENT_PAYLOAD_MODELS: Dict[EventType, Type[BaseModel]] = {
    EventType.ACK: AckPayload,
    EventType.CLARIFICATION_CARD: ClarificationCardPayload,
    EventType.RETRIEVAL_STARTED: RetrievalStartedPayload,
    EventType.RETRIEVAL_RESULT: RetrievalResultPayload,
    EventType.TOOL_CALL: ToolCallPayload,
    EventType.TOOL_RESULT: ToolResultPayload,
    EventType.FINAL: FinalPayload,
    EventType.ERROR: ErrorPayload,
}


def validate_event_payload(event_type: EventType | str, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized_event = event_type if isinstance(event_type, EventType) else EventType(event_type)
    model = EVENT_PAYLOAD_MODELS[normalized_event]
    return model.model_validate(payload).model_dump(mode="json")
