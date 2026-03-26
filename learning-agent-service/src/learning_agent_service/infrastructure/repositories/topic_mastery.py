"""SQLAlchemy repository for ``topic_mastery`` durable facts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from learning_agent_service.infrastructure.db.models import TopicMasteryModel

from .base import SqlAlchemyRepositoryBase
from .records import TopicMasteryRecord

try:
    from sqlalchemy import select
except ImportError:  # pragma: no cover - depends on optional runtime installation.
    select = None


class TopicMasteryRepository(SqlAlchemyRepositoryBase):
    """Read/write access for user-topic mastery snapshots."""

    def get(self, user_id: str, topic: str) -> Optional[TopicMasteryModel]:
        self._require_sqlalchemy()
        with self.session_scope() as session:
            return session.execute(
                select(TopicMasteryModel).where(
                    TopicMasteryModel.user_id == user_id,
                    TopicMasteryModel.topic == topic,
                )
            ).scalar_one_or_none()

    def upsert(self, record: TopicMasteryRecord) -> TopicMasteryModel:
        self._require_sqlalchemy()
        with self.session_scope() as session:
            instance = session.execute(
                select(TopicMasteryModel).where(
                    TopicMasteryModel.user_id == record.user_id,
                    TopicMasteryModel.topic == record.topic,
                )
            ).scalar_one_or_none()
            if instance is None:
                instance = TopicMasteryModel(user_id=record.user_id, topic=record.topic)
            instance.mastery_score = record.mastery_score
            instance.confidence_score = record.confidence_score
            instance.evidence_count = record.evidence_count
            instance.last_seen_at = record.last_seen_at or datetime.now(timezone.utc)
            instance.last_quiz_score = record.last_quiz_score
            instance.review_priority = record.review_priority
            instance.source_turn_id = record.source_turn_id
            instance.extra = dict(record.extra)
            session.add(instance)
            session.flush()
            return instance
