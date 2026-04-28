from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence
from uuid import uuid4

from learning_agent_service.domain.memory import (
    LongTermMemoryStore,
    MemoryEdge,
    MemoryEdgeType,
    MemoryRecord,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from learning_agent_service.infrastructure.db.models import LongTermMemoryModel
from learning_agent_service.infrastructure.repositories.memory_record_repository import MemoryRecordRepository

from learning_agent_service.memory.models import SemanticMemoryFact
from learning_agent_service.memory.protocols import SemanticMemoryStore

from .qdrant_store import QdrantLongTermMemoryIndex

try:  # pragma: no cover - optional runtime dependency
    from sqlalchemy import select
except Exception:  # pragma: no cover - import-tolerant fallback
    select = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _enum_or_default(enum_cls: Any, value: Any, default: Any) -> Any:
    if value is None:
        return default
    if hasattr(value, "value"):
        return value
    try:
        return enum_cls(value)
    except Exception:
        return default


def _record_to_model_fields(record: MemoryRecord) -> Dict[str, Any]:
    return {
        "memory_id": record.memory_id or f"{record.user_id}:{record.source_turn_id}:{record.type.value}:{uuid4().hex[:12]}",
        "user_id": record.user_id,
        "session_id": record.session_id,
        "project_id": record.project_id,
        "memory_type": _enum_value(record.type),
        "scope": _enum_value(record.scope),
        "status": _enum_value(record.status),
        "source": _enum_value(record.metadata.source if record.metadata else MemorySource.SYSTEM_EVENT),
        "source_turn_id": record.source_turn_id,
        "source_message_ids": list(record.source_message_ids),
        "content": _json_ready(record.content),
        "summary": record.summary,
        "tags": list(record.tags),
        "entities": list(record.entities),
        "confidence": float(record.confidence),
        "importance": float(record.importance),
        "last_accessed_at": record.last_accessed_at,
        "expires_at": record.expires_at,
        "supersedes": record.supersedes,
        "embedding_id": record.embedding_id or record.memory_id or None,
        "schema_version": record.schema_version,
        "extra": {
            "metadata": record.metadata.model_dump(mode="json") if record.metadata else None,
        },
    }


def _model_to_record(model: LongTermMemoryModel) -> MemoryRecord:
    extra = dict(model.extra or {})
    metadata_payload = extra.get("metadata") if isinstance(extra, Mapping) else None
    payload = {
        "memory_id": model.memory_id,
        "user_id": model.user_id,
        "session_id": model.session_id,
        "project_id": model.project_id,
        "type": model.memory_type,
        "scope": model.scope,
        "status": model.status,
        "content": model.content or {},
        "summary": model.summary,
        "tags": list(model.tags or []),
        "entities": list(model.entities or []),
        "source_turn_id": model.source_turn_id,
        "source_message_ids": list(model.source_message_ids or []),
        "confidence": float(model.confidence or 0.0),
        "importance": float(model.importance or 0.0),
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "last_accessed_at": model.last_accessed_at,
        "expires_at": model.expires_at,
        "supersedes": model.supersedes,
        "embedding_id": model.embedding_id,
        "schema_version": model.schema_version,
    }
    record = MemoryRecord.model_validate(payload)
    if metadata_payload and isinstance(metadata_payload, Mapping):
        record.metadata = record.metadata.model_copy(
            update={
                "source": _enum_or_default(MemorySource, metadata_payload.get("source"), record.metadata.source),
                "tags": list(metadata_payload.get("tags", record.metadata.tags)),
                "entities": list(metadata_payload.get("entities", record.metadata.entities)),
                "confidence": metadata_payload.get("confidence", record.metadata.confidence),
                "importance": metadata_payload.get("importance", record.metadata.importance),
            }
        )
    return record


def _record_to_semantic_fact(record: MemoryRecord) -> SemanticMemoryFact:
    metadata = {}
    if isinstance(record.content, Mapping):
        metadata = dict(record.content.get("metadata") or {})
        content = record.content.get("content") or record.summary or ""
        fact_type = str(record.content.get("fact_type") or (record.tags[0] if record.tags else "semantic"))
        topic = str(record.content.get("topic") or (record.entities[0] if record.entities else record.summary or "topic"))
    else:
        content = record.summary or str(record.content)
        fact_type = record.tags[0] if record.tags else "semantic"
        topic = record.entities[0] if record.entities else record.summary or "topic"
    return SemanticMemoryFact(
        fact_id=record.memory_id,
        topic=str(topic),
        content=str(content),
        fact_type=str(fact_type),
        strength=float(record.confidence or 0.5),
        created_at=record.created_at,
        last_referenced_at=record.last_accessed_at,
        metadata=metadata if metadata else (dict(record.content.get("metadata", {})) if isinstance(record.content, Mapping) else {}),
    )


class LongTermMemoryRepository(MemoryRecordRepository):
    """Backward-compatible alias for the governed memory repository."""

    pass


@dataclass
class DurableLongTermMemoryStore(LongTermMemoryStore):
    """Composite long-term memory adapter that writes metadata to Postgres and vectors to Qdrant."""

    repository: LongTermMemoryRepository
    index: Optional[QdrantLongTermMemoryIndex] = None
    last_qdrant_error: Optional[str] = None

    def upsert(self, record: MemoryRecord) -> MemoryRecord:
        self.last_qdrant_error = None
        stored = record.model_copy(
            update={
                "memory_id": record.memory_id or f"{record.user_id}:{record.source_turn_id}:{record.type.value}:{uuid4().hex[:12]}",
                "embedding_id": record.embedding_id or record.memory_id or None,
                "updated_at": _utcnow(),
            }
        )
        stored_record = self.repository.upsert(stored)
        if self.index is not None and _should_index(stored_record):
            try:
                embedding_id = self.index.upsert(stored_record)
            except Exception as exc:
                self.last_qdrant_error = type(exc).__name__
                stored_record = stored_record.model_copy(
                    update={
                        "extra": {
                            **dict(stored_record.extra or {}),
                            "qdrant_degraded": True,
                            "qdrant_error": type(exc).__name__,
                        }
                    }
                )
            else:
                if getattr(self.index, "last_error", None):
                    self.last_qdrant_error = str(self.index.last_error)
                    stored_record = stored_record.model_copy(
                        update={
                            "extra": {
                                **dict(stored_record.extra or {}),
                                "qdrant_degraded": True,
                                "qdrant_error": str(self.index.last_error),
                            }
                        }
                    )
                if embedding_id and embedding_id != stored_record.embedding_id:
                    stored_record = stored_record.model_copy(update={"embedding_id": embedding_id})
                    stored_record = self.repository.upsert(stored_record)
        return stored_record

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        return self.repository.get(memory_id)

    def search(self, query: str, user_id: str, limit: int = 10) -> Sequence[MemoryRecord]:
        self.last_qdrant_error = None
        if self.index is not None:
            try:
                indexed = list(self.index.search(query, user_id=user_id, limit=limit))
            except Exception:
                indexed = []
                self.last_qdrant_error = "search_failed"
            else:
                if getattr(self.index, "last_error", None):
                    self.last_qdrant_error = str(self.index.last_error)
            if indexed:
                return indexed
        return list(self.repository.search(query, user_id=user_id, limit=limit))

    def list_by_scope(self, user_id: str, scope: MemoryScope) -> Sequence[MemoryRecord]:
        return list(self.repository.list_by_scope(user_id, scope))

    def supersede(
        self,
        memory_id: str,
        superseded_by: str,
        reason: str,
        edge_type: MemoryEdgeType = MemoryEdgeType.SUPERSEDES,
    ) -> None:
        self.repository.mark_superseded(memory_id, superseded_by, reason, edge_type=edge_type)
        current = self.get(memory_id)
        if current is not None and self.index is not None:
            self.index.delete_many([current.vector_id or current.memory_id])
            if getattr(self.index, "last_error", None):
                self.last_qdrant_error = str(self.index.last_error)

    def soft_delete(self, memory_id: str, reason: str) -> None:
        self.last_qdrant_error = None
        deleted = self.repository.soft_delete(memory_id, reason)
        if deleted is None:
            return
        current = self.get(memory_id)
        if current is not None and self.index is not None:
            self.index.delete_many([current.vector_id or current.memory_id])
            if getattr(self.index, "last_error", None):
                self.last_qdrant_error = str(self.index.last_error)

    def create_edge(self, edge: MemoryEdge) -> MemoryEdge:
        return self.repository.create_edge(edge)


@dataclass
class DurableSemanticMemoryStore(SemanticMemoryStore):
    """Semantic memory adapter that persists facts as long-term memory records."""

    long_term_store: DurableLongTermMemoryStore
    indexed_topics: Dict[tuple[str, str], bool] = field(default_factory=dict)

    def search(self, user_id: str, query: str, limit: int = 5) -> Sequence[SemanticMemoryFact]:
        records = self.long_term_store.search(query, user_id=user_id, limit=limit)
        facts: List[SemanticMemoryFact] = []
        for record in records:
            if record.type != MemoryType.SEMANTIC:
                continue
            facts.append(_record_to_semantic_fact(record))
        return facts

    def upsert(self, user_id: str, fact: SemanticMemoryFact) -> None:
        record = MemoryRecord(
            memory_id=fact.fact_id or f"{user_id}:{fact.topic}:{uuid4().hex[:12]}",
            user_id=user_id,
            session_id=None,
            project_id=None,
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.USER,
            status=MemoryStatus.CONFIRMED,
            content={
                "topic": fact.topic,
                "content": fact.content,
                "fact_type": fact.fact_type,
                "metadata": dict(fact.metadata),
            },
            summary=fact.content,
            source_turn_id=str(fact.metadata.get("source_turn_id") or fact.fact_id or ""),
            confidence=float(fact.strength),
            importance=min(1.0, float(fact.strength) + 0.1),
            tags=[fact.fact_type, fact.topic],
            entities=[fact.topic],
            created_at=fact.created_at or _utcnow(),
            last_accessed_at=fact.last_referenced_at,
            embedding_id=fact.fact_id or None,
        )
        self.long_term_store.upsert(record)

    def mark_indexed_state(self, user_id: str, topic: str, indexed: bool) -> None:
        self.indexed_topics[(user_id, topic)] = indexed


def _should_index(record: MemoryRecord) -> bool:
    return record.type in {MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.PROCEDURAL}
