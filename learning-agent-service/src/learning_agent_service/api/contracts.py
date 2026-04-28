from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from learning_agent_service.domain.contracts import (
    PlanExecutionSummary,
    PlanStep,
    Citation,
    ClarificationCard,
    ErrorPayload,
    FinalPayload,
    MemoryUsedSummary,
    StepResult,
    RetrievalSummary,
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
    MEMORY_RETRIEVAL_STARTED = "memory_retrieval_started"
    MEMORY_RETRIEVAL_RESULT = "memory_retrieval_result"
    MEMORY_PROMOTION_RESULT = "memory_promotion_result"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLAN_EXECUTION_STARTED = "plan_execution_started"
    PLAN_STEP_RESULT = "plan_step_result"
    APPROVAL_REQUIRED = "approval_required"
    PLAN_REPLANNED = "plan_replanned"
    PLAN_EXECUTION_SUMMARY = "plan_execution_summary"
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


class MemoryRetrievalStartedPayload(BaseModel):
    trace_id: str
    session_id: str
    turn_id: str
    user_id: str
    query: str
    current_topic: Optional[str] = None
    retrieval_budget: int = Field(default=0, ge=0)


class MemoryRetrievalResultPayload(BaseModel):
    trace_id: str
    session_id: str
    turn_id: str
    retrieved: List[str] = Field(default_factory=list)
    injected: List[str] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)
    candidates: List[str] = Field(default_factory=list)
    retrieval_reason: Optional[str] = None
    total_token_estimate: int = Field(default=0, ge=0)
    trace_summary: Dict[str, Any] = Field(default_factory=dict)


class MemoryPromotionResultPayload(BaseModel):
    trace_id: str
    session_id: str
    turn_id: str
    candidate_ids: List[str] = Field(default_factory=list)
    promoted_ids: List[str] = Field(default_factory=list)
    rejected_ids: List[str] = Field(default_factory=list)
    governed_actions: Dict[str, str] = Field(default_factory=dict)
    conflict_ids: List[str] = Field(default_factory=list)
    deletion_job_ids: List[str] = Field(default_factory=list)
    governance_summary: Dict[str, Any] = Field(default_factory=dict)
    memory_trace: Dict[str, Any] = Field(default_factory=dict)


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


class PlanExecutionStartedPayload(BaseModel):
    plan: List[PlanStep] = Field(default_factory=list)
    total_steps: int = Field(default=0, ge=0)
    current_step_index: int = Field(default=0, ge=0)
    execution_mode: Optional[str] = None
    risk_level: Optional[str] = None


class PlanStepResultPayload(BaseModel):
    step_result: StepResult
    current_step_index: int = Field(default=0, ge=0)
    total_steps: int = Field(default=0, ge=0)


class ApprovalRequiredPayload(BaseModel):
    step_id: str
    reason: str
    approval_request: Dict[str, Any] = Field(default_factory=dict)
    risk_level: Optional[str] = None


class PlanReplannedPayload(BaseModel):
    reason: str
    previous_steps: int = Field(default=0, ge=0)
    total_steps: int = Field(default=0, ge=0)
    plan: List[PlanStep] = Field(default_factory=list)


class PlanExecutionSummaryPayload(BaseModel):
    summary: PlanExecutionSummary


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
    history_summary: Optional[str] = None
    open_questions: List[str] = Field(default_factory=list)
    confirmed_facts: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    summary_version: int = 0
    summary_updated_at: Optional[datetime] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class FeedbackIssueType(str, Enum):
    HELPFUL = "helpful"
    UNHELPFUL = "unhelpful"
    CITATION_INCORRECT = "citation_incorrect"
    MISSED_RECALL = "missed_recall"
    OTHER = "other"


class FeedbackReportRequest(BaseModel):
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    thread_id: Optional[str] = None
    trace_id: Optional[str] = None
    issue_type: FeedbackIssueType = FeedbackIssueType.HELPFUL
    is_helpful: Optional[bool] = None
    comment: Optional[str] = None
    final_payload: Dict[str, Any] = Field(default_factory=dict)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    retrieval_summary: Dict[str, Any] = Field(default_factory=dict)
    memory_used_summary: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)


class FeedbackReportResponse(BaseModel):
    feedback_id: str
    status: str
    recorded_at: datetime
    dedupe_key: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class FeedbackSampleItem(BaseModel):
    event_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    status: str
    trace_id: Optional[str] = None
    available_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    last_error: Optional[str] = None


class FeedbackSampleResponse(BaseModel):
    records: List[FeedbackSampleItem] = Field(default_factory=list)
    total: int = 0


class MemoryRecordSummary(BaseModel):
    memory_id: str
    user_id: str
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    topic: Optional[str] = None
    memory_type: Optional[str] = None
    scope: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    summary: Optional[str] = None
    confidence: float = 0.0
    importance: float = 0.0
    stability: float = 0.0
    sensitivity: Optional[str] = None
    retrieval_mode: Optional[str] = None
    should_vectorize: bool = True
    ttl_seconds: Optional[int] = None
    valid_until: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    source_turn_id: Optional[str] = None
    source_message_ids: List[str] = Field(default_factory=list)
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    embedding_id: Optional[str] = None
    raw_evidence: Dict[str, Any] = Field(default_factory=dict)
    schema_version: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class MemoryCandidateSummary(BaseModel):
    candidate_id: str
    memory_id: Optional[str] = None
    user_id: str
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    topic: Optional[str] = None
    memory_type: Optional[str] = None
    scope: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    summary: Optional[str] = None
    confidence: float = 0.0
    importance: float = 0.0
    stability: float = 0.0
    governance_action: Optional[str] = None
    require_confirmation: bool = False
    approval_notes: List[str] = Field(default_factory=list)
    decision_reason: Optional[str] = None
    conflict_ids: List[str] = Field(default_factory=list)
    deletion_job_ids: List[str] = Field(default_factory=list)
    skip_reason: Optional[str] = None
    record: Optional[MemoryRecordSummary] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class MemoryTraceSummary(BaseModel):
    trace_id: str
    user_id: str
    session_id: str
    turn_id: str
    retrieved: List[str] = Field(default_factory=list)
    injected: List[str] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)
    candidates: List[str] = Field(default_factory=list)
    promoted: List[str] = Field(default_factory=list)
    rejected: List[str] = Field(default_factory=list)
    decision_reasons: Dict[str, str] = Field(default_factory=dict)
    conflict_ids: List[str] = Field(default_factory=list)
    deletion_job_ids: List[str] = Field(default_factory=list)
    skip_reasons: Dict[str, str] = Field(default_factory=dict)
    conflict_resolutions: List[Dict[str, Any]] = Field(default_factory=list)
    total_memory_tokens: int = 0
    qdrant_degraded: bool = False
    created_at: Optional[datetime] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class MemoryAccessLogSummary(BaseModel):
    access_log_id: str
    memory_id: str
    user_id: str
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    action: str = "read"
    accessed_at: datetime
    trace_id: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class MemoryDeletionJobSummary(BaseModel):
    deletion_job_id: str
    memory_id: str
    user_id: str
    session_id: Optional[str] = None
    target_store: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    vector_id: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class MemoryListResponse(BaseModel):
    records: List[MemoryRecordSummary] = Field(default_factory=list)
    total: int = 0


class MemoryCandidateListResponse(BaseModel):
    records: List[MemoryCandidateSummary] = Field(default_factory=list)
    total: int = 0


class MemoryTraceListResponse(BaseModel):
    records: List[MemoryTraceSummary] = Field(default_factory=list)
    total: int = 0


class MemoryAccessLogListResponse(BaseModel):
    records: List[MemoryAccessLogSummary] = Field(default_factory=list)
    total: int = 0


class MemoryDeletionJobListResponse(BaseModel):
    records: List[MemoryDeletionJobSummary] = Field(default_factory=list)
    total: int = 0


class MemoryActionRequest(BaseModel):
    reason: Optional[str] = None
    superseded_by: Optional[str] = None
    target_memory_id: Optional[str] = None


class MemoryActionResponse(BaseModel):
    status: str
    action: str
    message: Optional[str] = None
    record: Optional[MemoryRecordSummary] = None
    candidate: Optional[MemoryCandidateSummary] = None
    trace: Optional[MemoryTraceSummary] = None


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
    EventType.MEMORY_RETRIEVAL_STARTED: MemoryRetrievalStartedPayload,
    EventType.MEMORY_RETRIEVAL_RESULT: MemoryRetrievalResultPayload,
    EventType.MEMORY_PROMOTION_RESULT: MemoryPromotionResultPayload,
    EventType.TOOL_CALL: ToolCallPayload,
    EventType.TOOL_RESULT: ToolResultPayload,
    EventType.PLAN_EXECUTION_STARTED: PlanExecutionStartedPayload,
    EventType.PLAN_STEP_RESULT: PlanStepResultPayload,
    EventType.APPROVAL_REQUIRED: ApprovalRequiredPayload,
    EventType.PLAN_REPLANNED: PlanReplannedPayload,
    EventType.PLAN_EXECUTION_SUMMARY: PlanExecutionSummaryPayload,
    EventType.FINAL: FinalPayload,
    EventType.ERROR: ErrorPayload,
}


def validate_event_payload(event_type: EventType | str, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized_event = event_type if isinstance(event_type, EventType) else EventType(event_type)
    model = EVENT_PAYLOAD_MODELS[normalized_event]
    return model.model_validate(payload).model_dump(mode="json")
