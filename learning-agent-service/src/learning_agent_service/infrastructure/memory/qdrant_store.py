from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from learning_agent_service.domain.memory import MemoryRecord, MemoryStatus

try:  # pragma: no cover - optional runtime dependency
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue, PointIdsList, VectorParams
    from qdrant_client.models import Distance, PointStruct
except Exception:  # pragma: no cover - import-tolerant fallback
    Filter = FieldCondition = MatchValue = PointIdsList = VectorParams = Distance = PointStruct = None


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> List[str]:
    return [token for token in re.findall(r"[\w\u4e00-\u9fff]+", text.lower()) if token]


def _embed_text(text: str, vector_size: int) -> List[float]:
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * vector_size
    vector = [0.0] * vector_size
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % vector_size
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    total = 0.0
    for index, value in enumerate(left):
        if index >= len(right):
            break
        total += value * right[index]
    return total


def _record_text(record: MemoryRecord) -> str:
    content = record.content
    if isinstance(content, Mapping):
        content_text = " ".join(f"{key}:{value}" for key, value in content.items())
    else:
        content_text = str(content)
    return " ".join(
        [
            record.summary or "",
            content_text,
            " ".join(record.tags),
            " ".join(record.entities),
            record.type.value,
            record.scope.value,
            record.status.value,
        ]
    )


def _status_is_active(status: Any) -> bool:
    status_value = status.value if hasattr(status, "value") else str(status or "")
    return status_value not in {"deleted", "expired", "superseded"}


@dataclass
class QdrantLongTermMemoryIndex:
    """Best-effort Qdrant-backed semantic index with an in-memory fallback."""

    client: Any
    collection_name: str
    vector_size: int = 64
    fallback_points: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_error: Optional[str] = None
    last_operation: Optional[str] = None

    def ensure_collection(self) -> None:
        create_collection = getattr(self.client, "create_collection", None)
        if not callable(create_collection):
            return

        exists = False
        collection_exists = getattr(self.client, "collection_exists", None)
        if callable(collection_exists):
            try:
                exists = bool(collection_exists(self.collection_name))
            except Exception:
                exists = False
        if not exists and hasattr(self.client, "get_collection"):
            try:
                self.client.get_collection(self.collection_name)
                exists = True
            except Exception:
                exists = False
        if exists:
            return

        if VectorParams is None or Distance is None:
            return
        try:
            create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
        except Exception:
            return

    def upsert(self, record: MemoryRecord) -> str:
        self.last_operation = "upsert"
        self.last_error = None
        embedding_id = record.embedding_id or (record.memory_id if record.should_vectorize else None)
        record = record.model_copy(update={"embedding_id": embedding_id, "updated_at": record.updated_at})
        if not record.should_vectorize or not embedding_id:
            return embedding_id or ""
        payload = self._payload_from_record(record)
        vector = _embed_text(_record_text(record), self.vector_size)
        self.fallback_points[embedding_id] = {"vector": vector, "payload": payload}

        upsert = getattr(self.client, "upsert", None)
        if callable(upsert):
            self.ensure_collection()
            try:
                point = (
                    PointStruct(id=embedding_id, vector=vector, payload=payload)
                    if PointStruct is not None
                    else {"id": embedding_id, "vector": vector, "payload": payload}
                )
                upsert(collection_name=self.collection_name, points=[point])
            except Exception as exc:
                self.last_error = type(exc).__name__
        return embedding_id

    def delete(self, point_id: str) -> None:
        self.delete_many([point_id])

    def delete_many(self, point_ids: Sequence[str]) -> None:
        self.last_operation = "delete"
        self.last_error = None
        ids = [point_id for point_id in point_ids if point_id]
        if not ids:
            return
        for point_id in ids:
            self.fallback_points.pop(point_id, None)
        delete = getattr(self.client, "delete", None)
        if callable(delete):
            try:
                kwargs: Dict[str, Any] = {"collection_name": self.collection_name}
                if PointIdsList is not None:
                    kwargs["points_selector"] = PointIdsList(points=ids)
                else:
                    kwargs["points"] = ids
                delete(**kwargs)
            except Exception:
                self.last_error = "delete_failed"

    def search(self, query: str, user_id: str, limit: int = 10) -> Sequence[MemoryRecord]:
        self.last_operation = "search"
        self.last_error = None
        vector = _embed_text(query or "", self.vector_size)
        search = getattr(self.client, "search", None)
        if callable(search):
            try:
                query_filter = self._build_filter(user_id)
                kwargs: Dict[str, Any] = {
                    "collection_name": self.collection_name,
                    "query_vector": vector,
                    "limit": limit,
                    "with_payload": True,
                }
                if query_filter is not None:
                    kwargs["query_filter"] = query_filter
                points = search(**kwargs)
                records = self._points_to_records(points, user_id=user_id, limit=limit)
                if records:
                    return records
            except Exception:
                self.last_error = "search_failed"
        return self._search_fallback(vector=vector, user_id=user_id, limit=limit)

    def _search_fallback(self, *, vector: Sequence[float], user_id: str, limit: int) -> Sequence[MemoryRecord]:
        scored: List[tuple[float, Dict[str, Any]]] = []
        for point in self.fallback_points.values():
            payload = point.get("payload", {})
            if payload.get("user_id") != user_id:
                continue
            if not _status_is_active(payload.get("status")):
                continue
            score = _cosine(vector, point.get("vector", ()))
            scored.append((score, payload))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._payload_to_record(payload) for _, payload in scored[:limit]]

    def _build_filter(self, user_id: str) -> Any:
        if Filter is None or FieldCondition is None or MatchValue is None:
            return None
        return Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])

    def _points_to_records(self, points: Any, *, user_id: str, limit: int) -> Sequence[MemoryRecord]:
        records: List[MemoryRecord] = []
        for point in points or []:
            payload = getattr(point, "payload", None)
            if payload is None and isinstance(point, Mapping):
                payload = point.get("payload")
            if not isinstance(payload, Mapping):
                continue
            if payload.get("user_id") not in {None, user_id}:
                continue
            if not _status_is_active(payload.get("status")):
                continue
            records.append(self._payload_to_record(payload))
            if len(records) >= limit:
                break
        return records

    @staticmethod
    def _payload_from_record(record: MemoryRecord) -> Dict[str, Any]:
        return {
            "record": record.model_dump(mode="json"),
            "memory_id": record.memory_id,
            "user_id": record.user_id,
            "session_id": record.session_id,
            "project_id": record.project_id,
            "memory_type": record.type.value,
            "scope": record.scope.value,
            "status": record.status.value,
            "source_turn_id": record.source_turn_id,
            "summary": record.summary,
            "tags": list(record.tags),
            "entities": list(record.entities),
            "confidence": float(record.confidence),
            "importance": float(record.importance),
            "updated_at": record.updated_at.isoformat(),
            "created_at": record.created_at.isoformat(),
            "vector_id": record.embedding_id,
            "schema_version": record.schema_version,
            "indexed_at": _utcnow_iso(),
        }

    @staticmethod
    def _payload_to_record(payload: Mapping[str, Any]) -> MemoryRecord:
        record_payload = payload.get("record")
        if isinstance(record_payload, Mapping):
            return MemoryRecord.model_validate(record_payload)
        normalized = dict(payload)
        normalized.setdefault("memory_id", str(payload.get("memory_id") or payload.get("id") or ""))
        normalized.setdefault("user_id", str(payload.get("user_id") or ""))
        normalized.setdefault("source_turn_id", str(payload.get("source_turn_id") or ""))
        normalized.setdefault("content", payload.get("content") or {})
        normalized.setdefault("summary", payload.get("summary"))
        normalized.setdefault("tags", list(payload.get("tags") or []))
        normalized.setdefault("entities", list(payload.get("entities") or []))
        normalized.setdefault("type", payload.get("memory_type") or payload.get("type") or "semantic")
        normalized.setdefault("scope", payload.get("scope") or "user")
        normalized.setdefault("status", payload.get("status") or "active")
        normalized.setdefault("confidence", float(payload.get("confidence") or 0.0))
        normalized.setdefault("importance", float(payload.get("importance") or 0.0))
        normalized.setdefault("embedding_id", payload.get("vector_id") or payload.get("embedding_id"))
        return MemoryRecord.model_validate(normalized)
