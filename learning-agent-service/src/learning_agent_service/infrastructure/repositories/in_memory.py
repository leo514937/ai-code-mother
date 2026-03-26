from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from learning_agent_service.domain import GraphRuntimeMeta, PersistentSessionContext
from learning_agent_service.domain.protocols import SessionContextPort


@dataclass
class InMemorySessionContextStore(SessionContextPort):
    sessions: Dict[Tuple[str, str], PersistentSessionContext] = field(default_factory=dict)

    def load(self, session_id: str, user_id: str) -> PersistentSessionContext:
        return deepcopy(self.sessions.get((session_id, user_id), PersistentSessionContext()))

    def save(self, context: PersistentSessionContext, runtime: GraphRuntimeMeta) -> None:
        self.sessions[(runtime.session_id, runtime.extra.get("user_id", "anonymous"))] = deepcopy(context)


@dataclass
class InMemoryTopicMasteryStore:
    records: Dict[Tuple[str, str], Dict[str, Any]] = field(default_factory=dict)

    def get(self, user_id: str, topic: str) -> Dict[str, Any]:
        return deepcopy(
            self.records.get(
                (user_id, topic),
                {
                    "topic": topic,
                    "mastery_score": 0.5,
                    "confidence_score": 0.3,
                    "evidence_count": 0,
                    "last_seen_at": None,
                    "last_quiz_score": None,
                    "review_priority": 20,
                },
            )
        )

    def upsert(self, user_id: str, topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = self.get(user_id, topic)
        merged.update(payload)
        merged["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        self.records[(user_id, topic)] = deepcopy(merged)
        return deepcopy(merged)

    def list_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        items = [value for (stored_user_id, _), value in self.records.items() if stored_user_id == user_id]
        return deepcopy(sorted(items, key=lambda item: item.get("review_priority", 0), reverse=True))


@dataclass
class InMemoryAsyncLogStore:
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def append(self, entry: Dict[str, Any]) -> None:
        self.entries.append(deepcopy(entry))
