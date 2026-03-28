from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class SessionPersistenceContext:
    session_id: str
    turn_id: str
    trace_id: str
    user_id: str
    request_ts: datetime


@dataclass(frozen=True)
class PreferenceProfileWrite:
    user_id: str
    answer_style: Optional[str] = None
    explanation_depth: Optional[str] = None
    prefer_code_examples: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AsyncLogEvent:
    aggregate_type: str
    aggregate_id: str
    event_type: str
    dedupe_key: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    available_at: Optional[datetime] = None

    def as_mapping(self) -> Mapping[str, Any]:
        payload = {
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "dedupe_key": self.dedupe_key,
            "payload": dict(self.payload),
            "trace_id": self.trace_id,
        }
        if self.available_at is not None:
            payload["available_at"] = self.available_at
        return payload


@dataclass(frozen=True)
class UserPreferenceProfile:
    user_id: str
    preferred_output_style: Optional[str] = None
    answer_style_counter: Mapping[str, int] = field(default_factory=dict)
    prefers_code_examples: bool = False
    prefers_interview_mode: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistentSessionContext:
    current_topic: Optional[str] = None
    recent_entities: Tuple[str, ...] = ()
    clarification_result: Mapping[str, Any] = field(default_factory=dict)
    user_preferences: Mapping[str, Any] = field(default_factory=dict)
    last_retrieval_topic: Optional[str] = None
    active_plan_id: Optional[str] = None
    learning_mode: Optional[bool] = None
    history_summary: Optional[str] = None
    pending_clarification: Optional[Mapping[str, Any]] = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopicMasteryRecord:
    topic: str
    mastery_score: float = 0.5
    confidence_score: float = 0.3
    evidence_count: int = 0
    last_seen_at: Optional[datetime] = None
    last_quiz_score: Optional[float] = None
    review_priority: float = 20.0
    positive_signals: int = 0
    negative_signals: int = 0
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticMemoryFact:
    fact_id: str
    topic: str
    content: str
    fact_type: str
    strength: float = 0.5
    created_at: Optional[datetime] = None
    last_referenced_at: Optional[datetime] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExplicitUserSignals:
    preferred_output_style: Optional[str] = None
    wants_code_examples: bool = False
    wants_interview_answer: bool = False
    confirmed_plan: bool = False
    mastered: bool = False
    confused: bool = False
    confirmed_output_style: bool = False
    confirmed_code_examples: bool = False
    confirmed_interview_mode: bool = False
    repeated_topic_signal: bool = False
    low_quiz_score: Optional[float] = None
    focus_topics: Tuple[str, ...] = ()
    weak_topics: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionUpdate:
    current_topic: Optional[str] = None
    recent_entities: Tuple[str, ...] = ()
    clarification_result: Mapping[str, Any] = field(default_factory=dict)
    last_retrieval_topic: Optional[str] = None
    learning_mode: Optional[bool] = None
    history_summary: Optional[str] = None
    pending_clarification: Optional[Mapping[str, Any]] = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryPromotionInput:
    session_id: str
    turn_id: str
    user_id: str
    query: str
    answer_text: str
    resolved_topic: Optional[str] = None
    intent: Optional[str] = None
    output_style: Optional[str] = None
    tool_name: Optional[str] = None
    explicit_signals: ExplicitUserSignals = field(default_factory=ExplicitUserSignals)
    current_session: PersistentSessionContext = field(default_factory=PersistentSessionContext)
    current_preferences: Optional[UserPreferenceProfile] = None
    current_mastery: Optional[TopicMasteryRecord] = None
    quiz_score: Optional[float] = None
    current_time: Optional[datetime] = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DurableFactRequest:
    fact_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryPromotionResult:
    session_update: SessionUpdate
    preference_patch: Mapping[str, Any] = field(default_factory=dict)
    semantic_facts: Tuple[SemanticMemoryFact, ...] = ()
    weak_topics: Tuple[str, ...] = ()
    reasons: Tuple[str, ...] = ()
    durable_fact_requests: Tuple[DurableFactRequest, ...] = ()
    outbox_events: Tuple[Mapping[str, Any], ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistSessionPlan:
    updated_context: PersistentSessionContext
    preference_patch: Mapping[str, Any] = field(default_factory=dict)
    semantic_facts: Tuple[SemanticMemoryFact, ...] = ()
    weak_topics: Tuple[str, ...] = ()
    durable_fact_requests: Tuple[DurableFactRequest, ...] = ()
    outbox_events: Tuple[Mapping[str, Any], ...] = ()
    memory_updates: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticIndexUpdate:
    topic: str
    indexed: bool
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MasteryComputation:
    topic: str
    updated_record: TopicMasteryRecord
    signal_summary: Mapping[str, Any] = field(default_factory=dict)
    semantic_index_updates: Tuple[SemanticIndexUpdate, ...] = ()
    metrics_patch: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationContext:
    current_topic: Optional[str] = None
    weak_topics: Tuple[str, ...] = ()
    mastery_records: Tuple[TopicMasteryRecord, ...] = ()
    active_plan_topics: Tuple[str, ...] = ()
    recent_topics: Tuple[str, ...] = ()
    preferred_output_style: Optional[str] = None
    learning_mode: bool = True
    requested_limit: int = 3
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Recommendation:
    topic: str
    reason: str
    priority: float
    source: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationSnapshot:
    topic: str
    reason: str
    source: str
    priority: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuizTarget:
    topic: str
    reason: str
    difficulty_hint: str
    priority: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


class MemoryCapabilityError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        stage: str,
        message: str,
        retryable: bool = True,
        degraded_to: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.message = message
        self.retryable = retryable
        self.degraded_to = degraded_to

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "retryable": self.retryable,
            "degraded_to": self.degraded_to,
        }
