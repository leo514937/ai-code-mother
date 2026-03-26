"""SQLAlchemy durable models for the standalone learning agent service.

The model module is import-tolerant when SQLAlchemy is not installed so that
other workstreams can still import repository and bootstrap modules during early
integration. Methods that require actual SQLAlchemy behavior should still guard
against missing dependencies before use.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

try:
    from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    SQLALCHEMY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only before dependencies are installed.
    SQLALCHEMY_AVAILABLE = False

    class _PlaceholderType(object):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

    class _MappedAlias(object):
        def __class_getitem__(cls, item: Any) -> "_MappedAlias":
            return cls

    def mapped_column(*args: Any, **kwargs: Any) -> None:
        return None

    class _FallbackMetadata(object):
        def create_all(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("sqlalchemy is not installed")

    class DeclarativeBase(object):
        metadata = _FallbackMetadata()

    DateTime = Float = ForeignKey = Index = Integer = JSON = String = Text = UniqueConstraint = _PlaceholderType
    Mapped = _MappedAlias

    class _Func(object):
        @staticmethod
        def now() -> None:
            return None

    func = _Func()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for durable tables."""


class TimestampMixin(object):
    """Standard created/updated timestamps for durable rows."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TopicMasteryModel(TimestampMixin, Base):
    """Durable topic mastery facts keyed by user and canonical topic."""

    __tablename__ = "topic_mastery"
    __table_args__ = (
        UniqueConstraint("user_id", "topic", name="uq_topic_mastery_user_topic"),
        Index("ix_topic_mastery_user_review_priority", "user_id", "review_priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    mastery_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_quiz_score: Mapped[float] = mapped_column(Float, nullable=True)
    review_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    source_turn_id: Mapped[str] = mapped_column(String(128), nullable=True)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class UserPreferenceProfileModel(TimestampMixin, Base):
    """Durable user preference snapshot used by answer planning and routing."""

    __tablename__ = "user_preference_profile"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_preference_profile_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    answer_style: Mapped[str] = mapped_column(String(64), nullable=True)
    explanation_depth: Mapped[str] = mapped_column(String(64), nullable=True)
    prefer_code_examples: Mapped[str] = mapped_column(String(16), nullable=True)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class LearningPlanItemModel(TimestampMixin, Base):
    """Durable learning plan items split to the item level for progress tracking."""

    __tablename__ = "learning_plan_item"
    __table_args__ = (
        UniqueConstraint("plan_id", "item_id", name="uq_learning_plan_item_plan_item"),
        Index("ix_learning_plan_item_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    source_turn_id: Mapped[str] = mapped_column(String(128), nullable=True)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ClarificationRecordModel(TimestampMixin, Base):
    """Durable record of clarification prompts and user selections."""

    __tablename__ = "clarification_record"
    __table_args__ = (Index("ix_clarification_record_session_turn", "session_id", "turn_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    turn_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ambiguity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    selected_option_id: Mapped[str] = mapped_column(String(128), nullable=True)
    selected_option_label: Mapped[str] = mapped_column(String(255), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ToolInvocationLogModel(TimestampMixin, Base):
    """Durable tool invocation facts, written asynchronously through the outbox."""

    __tablename__ = "tool_invocation_log"
    __table_args__ = (
        UniqueConstraint("tool_call_id", name="uq_tool_invocation_log_tool_call_id"),
        Index("ix_tool_invocation_log_session_turn", "session_id", "turn_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    turn_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    degraded_to: Mapped[str] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str] = mapped_column(String(32), nullable=True)
    input_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class KnowledgeDocumentModel(TimestampMixin, Base):
    """Governance metadata for logical knowledge documents."""

    __tablename__ = "knowledge_document"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_knowledge_document_document_id"),
        Index("ix_knowledge_document_source_type_category", "source_type", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    active_version: Mapped[str] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class KnowledgeDocumentVersionModel(TimestampMixin, Base):
    """Version-level governance metadata used for rollout, invalidation, and rollback."""

    __tablename__ = "knowledge_document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_knowledge_document_version_doc_version"),
        Index("ix_knowledge_document_version_document_status", "document_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    document_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("knowledge_document.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_from_version: Mapped[str] = mapped_column(String(64), nullable=True)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class OutboxEventModel(TimestampMixin, Base):
    """Generic outbox table used for async log writes and deferred side effects."""

    __tablename__ = "outbox_event"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_outbox_event_dedupe_key"),
        Index("ix_outbox_event_status_available_at", "status", "available_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=True)
