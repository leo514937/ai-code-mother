"""SQLAlchemy repository for durable user answer-style preferences."""

from __future__ import annotations

from typing import Optional

from learning_agent_service.infrastructure.db.models import UserPreferenceProfileModel

from .base import SqlAlchemyRepositoryBase
from .records import UserPreferenceProfileRecord

try:
    from sqlalchemy import select
except ImportError:  # pragma: no cover - depends on optional runtime installation.
    select = None


class UserPreferenceRepository(SqlAlchemyRepositoryBase):
    """Read/write access for durable user preference profiles."""

    def get(self, user_id: str) -> Optional[UserPreferenceProfileModel]:
        self._require_sqlalchemy()
        with self.session_scope() as session:
            return session.execute(
                select(UserPreferenceProfileModel).where(UserPreferenceProfileModel.user_id == user_id)
            ).scalar_one_or_none()

    def upsert(self, record: UserPreferenceProfileRecord) -> UserPreferenceProfileModel:
        self._require_sqlalchemy()
        with self.session_scope() as session:
            instance = session.execute(
                select(UserPreferenceProfileModel).where(UserPreferenceProfileModel.user_id == record.user_id)
            ).scalar_one_or_none()
            if instance is None:
                instance = UserPreferenceProfileModel(user_id=record.user_id)
            instance.answer_style = record.answer_style
            instance.explanation_depth = record.explanation_depth
            instance.prefer_code_examples = record.prefer_code_examples
            instance.extra = dict(record.extra)
            session.add(instance)
            session.flush()
            return instance
