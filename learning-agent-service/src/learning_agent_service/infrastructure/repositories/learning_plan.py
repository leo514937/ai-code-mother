"""SQLAlchemy repository for durable learning plan items."""

from __future__ import annotations

from typing import Iterable, List

from learning_agent_service.infrastructure.db.models import LearningPlanItemModel

from .base import SqlAlchemyRepositoryBase
from .records import LearningPlanItemRecord

try:
    from sqlalchemy import select
except ImportError:  # pragma: no cover - depends on optional runtime installation.
    select = None


class LearningPlanRepository(SqlAlchemyRepositoryBase):
    """Read/write access for itemized learning plans."""

    def upsert_items(self, items: Iterable[LearningPlanItemRecord]) -> List[LearningPlanItemModel]:
        self._require_sqlalchemy()
        saved = []
        with self.session_scope() as session:
            for item in items:
                instance = session.execute(
                    select(LearningPlanItemModel).where(
                        LearningPlanItemModel.plan_id == item.plan_id,
                        LearningPlanItemModel.item_id == item.item_id,
                    )
                ).scalar_one_or_none()
                if instance is None:
                    instance = LearningPlanItemModel(plan_id=item.plan_id, item_id=item.item_id, user_id=item.user_id)
                instance.topic = item.topic
                instance.title = item.title
                instance.description = item.description
                instance.sequence_no = item.sequence_no
                instance.status = item.status
                instance.due_at = item.due_at
                instance.source_turn_id = item.source_turn_id
                instance.extra = dict(item.extra)
                session.add(instance)
                saved.append(instance)
            session.flush()
            return saved

    def list_by_plan(self, user_id: str, plan_id: str) -> List[LearningPlanItemModel]:
        self._require_sqlalchemy()
        with self.session_scope() as session:
            return list(
                session.execute(
                    select(LearningPlanItemModel)
                    .where(
                        LearningPlanItemModel.user_id == user_id,
                        LearningPlanItemModel.plan_id == plan_id,
                    )
                    .order_by(LearningPlanItemModel.sequence_no.asc())
                ).scalars()
            )
