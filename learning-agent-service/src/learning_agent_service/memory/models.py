from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple


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
    focus_topics: Tuple[str, ...] = ()
    weak_topics: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionUpdate:
    current_topic: Optional[str] = None
    recent_entities: Tuple[str, ...] = ()
    clarification_result: Mapping[str, Any] = field(default_factory=dict)
    last_retrieval_topic: Optional[str] = None
    learning_mode: Optional[bool] = None
    summary_delta: Optional[str] = None
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
    current_time: Optional[datetime] = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryPromotionResult:
    session_update: SessionUpdate
    preference_patch: Mapping[str, Any] = field(default_factory=dict)
    semantic_facts: Tuple[SemanticMemoryFact, ...] = ()
    weak_topics: Tuple[str, ...] = ()
    reasons: Tuple[str, ...] = ()
    outbox_events: Tuple[Mapping[str, Any], ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)


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
class QuizTarget:
    topic: str
    reason: str
    difficulty_hint: str
    priority: float
    metadata: Mapping[str, Any] = field(default_factory=dict)
