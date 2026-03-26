from __future__ import annotations

from typing import Protocol, Sequence

from .models import PersistentSessionContext, SemanticMemoryFact, TopicMasteryRecord, UserPreferenceProfile


class SessionStore(Protocol):
    def load(self, session_id: str) -> PersistentSessionContext:
        ...

    def save(self, session_id: str, context: PersistentSessionContext) -> None:
        ...


class TopicMasteryStore(Protocol):
    def get(self, user_id: str, topic: str) -> TopicMasteryRecord:
        ...

    def upsert(self, user_id: str, record: TopicMasteryRecord) -> None:
        ...

    def list_for_user(self, user_id: str) -> Sequence[TopicMasteryRecord]:
        ...


class PreferenceStore(Protocol):
    def get(self, user_id: str) -> UserPreferenceProfile:
        ...

    def upsert(self, profile: UserPreferenceProfile) -> None:
        ...


class SemanticMemoryStore(Protocol):
    def search(self, user_id: str, query: str, limit: int = 5) -> Sequence[SemanticMemoryFact]:
        ...

    def upsert(self, user_id: str, fact: SemanticMemoryFact) -> None:
        ...

    def mark_indexed_state(self, user_id: str, topic: str, indexed: bool) -> None:
        ...
