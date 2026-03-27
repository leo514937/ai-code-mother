"""Runtime adapters that bridge infrastructure repositories into service-friendly stores."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from learning_agent_service.domain import GraphRuntimeMeta, PersistentSessionContext
from learning_agent_service.domain.protocols import SessionContextPort
from learning_agent_service.infrastructure.db.redis import RedisRuntime
from learning_agent_service.infrastructure.observability.outbox import AsyncLogWriteRequest

from .outbox import OutboxRepository
from .records import OutboxEventRecord, TopicMasteryRecord
from .topic_mastery import TopicMasteryRepository


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


@dataclass
class RedisSessionContextStore(SessionContextPort):
    """Redis-backed short-term session truth store."""

    runtime: RedisRuntime

    def load(self, session_id: str, user_id: str) -> PersistentSessionContext:
        state_key = self.runtime.keys.session_state(session_id)
        raw = self.runtime.client.get(state_key)
        if not raw:
            return PersistentSessionContext()

        payload = json.loads(raw)
        payload.setdefault("extra", {})
        payload["extra"].setdefault("user_id", user_id)
        return PersistentSessionContext.model_validate(payload)

    def save(self, context: PersistentSessionContext, runtime: GraphRuntimeMeta) -> None:
        state_key = self.runtime.keys.session_state(runtime.session_id)
        summary_key = self.runtime.keys.summary(runtime.session_id)
        clarification_key = self.runtime.keys.clarification(runtime.session_id)
        payload = context.model_dump(mode="json")
        payload.setdefault("extra", {})
        payload["extra"]["user_id"] = runtime.user_id
        self.runtime.client.set(state_key, json.dumps(payload, default=_json_default))

        summary_payload = {
            "current_topic": context.current_topic,
            "last_retrieval_topic": context.last_retrieval_topic,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.runtime.client.set(summary_key, json.dumps(summary_payload))

        if context.clarification_result:
            self.runtime.client.set(clarification_key, json.dumps(context.clarification_result, default=_json_default))
        else:
            self.runtime.client.delete(clarification_key)


@dataclass
class DurableTopicMasteryStore:
    """Store adapter exposing the legacy in-memory API on top of the SQL repository."""

    repository: TopicMasteryRepository

    def get(self, user_id: str, topic: str) -> Dict[str, Any]:
        model = self.repository.get(user_id, topic)
        if model is None:
            return {
                "topic": topic,
                "mastery_score": 0.5,
                "confidence_score": 0.3,
                "evidence_count": 0,
                "last_seen_at": None,
                "last_quiz_score": None,
                "review_priority": 20,
            }
        return {
            "topic": model.topic,
            "mastery_score": float(model.mastery_score),
            "confidence_score": float(model.confidence_score),
            "evidence_count": int(model.evidence_count),
            "last_seen_at": model.last_seen_at.isoformat() if model.last_seen_at else None,
            "last_quiz_score": model.last_quiz_score,
            "review_priority": int(model.review_priority),
            "source_turn_id": model.source_turn_id,
            **dict(model.extra or {}),
        }

    def upsert(self, user_id: str, topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = TopicMasteryRecord(
            user_id=user_id,
            topic=topic,
            mastery_score=float(payload.get("mastery_score", 0.5)),
            confidence_score=float(payload.get("confidence_score", 0.3)),
            evidence_count=int(payload.get("evidence_count", 0)),
            last_seen_at=payload.get("last_seen_at"),
            last_quiz_score=payload.get("last_quiz_score"),
            review_priority=int(payload.get("review_priority", 20)),
            source_turn_id=payload.get("source_turn_id"),
            extra={key: value for key, value in payload.items() if key not in {
                "mastery_score",
                "confidence_score",
                "evidence_count",
                "last_seen_at",
                "last_quiz_score",
                "review_priority",
                "source_turn_id",
            }},
        )
        model = self.repository.upsert(record)
        return {
            "topic": model.topic,
            "mastery_score": float(model.mastery_score),
            "confidence_score": float(model.confidence_score),
            "evidence_count": int(model.evidence_count),
            "last_seen_at": model.last_seen_at.isoformat() if model.last_seen_at else None,
            "last_quiz_score": model.last_quiz_score,
            "review_priority": int(model.review_priority),
            "source_turn_id": model.source_turn_id,
            **dict(model.extra or {}),
        }

    def list_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        models = self.repository.list_for_user(user_id)
        items = []
        for model in models:
            items.append(
                {
                    "topic": model.topic,
                    "mastery_score": float(model.mastery_score),
                    "confidence_score": float(model.confidence_score),
                    "evidence_count": int(model.evidence_count),
                    "last_seen_at": model.last_seen_at.isoformat() if model.last_seen_at else None,
                    "last_quiz_score": model.last_quiz_score,
                    "review_priority": int(model.review_priority),
                    "source_turn_id": model.source_turn_id,
                    **dict(model.extra or {}),
                }
            )
        return items


@dataclass
class OutboxAsyncLogStore:
    """Converts fire-and-forget async log writes into outbox records."""

    repository: OutboxRepository
    aggregate_type: str = "async_log"

    def append(self, entry: Dict[str, Any]) -> None:
        session_id = str(entry.get("session_id") or "unknown-session")
        turn_id = str(entry.get("turn_id") or "unknown-turn")
        event_type = str(entry.get("event_type") or "log.appended")
        dedupe_key = "%s:%s:%s" % (session_id, turn_id, event_type)
        record = OutboxEventRecord(
            aggregate_type=self.aggregate_type,
            aggregate_id="%s:%s" % (session_id, turn_id),
            event_type=event_type,
            dedupe_key=dedupe_key,
            payload=deepcopy(entry),
            trace_id=entry.get("trace_id"),
        )
        self.repository.enqueue(record)


@dataclass(frozen=True)
class AdapterStatus:
    name: str
    mode: str
    ready: bool
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeDependencyStatus:
    adapters: Tuple[AdapterStatus, ...]
    bootstrap_errors: Tuple[Tuple[str, str], ...] = ()

    @property
    def fallback_names(self) -> Tuple[str, ...]:
        return tuple(adapter.name for adapter in self.adapters if adapter.mode == "fallback")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "adapters": [
                {
                    "name": adapter.name,
                    "mode": adapter.mode,
                    "ready": adapter.ready,
                    "details": dict(adapter.details),
                }
                for adapter in self.adapters
            ],
            "bootstrap_errors": list(self.bootstrap_errors),
            "fallbacks": list(self.fallback_names),
        }
