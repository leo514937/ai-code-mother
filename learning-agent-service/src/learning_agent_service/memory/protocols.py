from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from learning_agent_service.domain.contracts import (
    GraphRuntimeMeta,
    PersistentSessionContext as DomainPersistentSessionContext,
)

from .models import SemanticMemoryFact


class SessionStore(Protocol):
    def load(self, session_id: str, user_id: str) -> DomainPersistentSessionContext:
        ...

    def save(self, context: DomainPersistentSessionContext, runtime: GraphRuntimeMeta) -> None:
        ...


class TopicMasteryStore(Protocol):
    def get(self, user_id: str, topic: str) -> Mapping[str, Any]:
        ...

    def upsert(self, user_id: str, topic: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def list_for_user(self, user_id: str) -> Sequence[Mapping[str, Any]]:
        ...


class PreferenceStore(Protocol):
    def get(self, user_id: str) -> Any:
        ...

    def upsert(self, profile: Any) -> Any:
        ...


class LearningPlanStore(Protocol):
    def list_for_plan(self, plan_id: str) -> Sequence[Any]:
        ...

    def list_by_plan(self, user_id: str, plan_id: str) -> Sequence[Any]:
        ...


class AsyncLogStore(Protocol):
    def append(self, entry: Mapping[str, Any]) -> None:
        ...


class SemanticMemoryStore(Protocol):
    def search(self, user_id: str, query: str, limit: int = 5) -> Sequence[SemanticMemoryFact]:
        ...

    def upsert(self, user_id: str, fact: SemanticMemoryFact) -> None:
        ...

    def mark_indexed_state(self, user_id: str, topic: str, indexed: bool) -> None:
        ...
