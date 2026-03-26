"""Bootstrap-friendly Qdrant client factory and collection descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from learning_agent_service.config.settings import QdrantSettings

from .errors import require_dependency

try:
    from qdrant_client import QdrantClient
except ImportError:  # pragma: no cover - depends on optional runtime installation.
    QdrantClient = None


@dataclass(frozen=True)
class QdrantRuntime:
    """Holds the Qdrant client and canonical collection names."""

    client: Any
    knowledge_collection: str
    user_memory_collection: str

    def collection_map(self) -> Dict[str, str]:
        return {
            "knowledge": self.knowledge_collection,
            "user_memory": self.user_memory_collection,
        }


def build_qdrant_runtime(settings: QdrantSettings) -> QdrantRuntime:
    """Create a Qdrant runtime with the service-owned collection names."""

    if QdrantClient is None:
        require_dependency("qdrant-client", "knowledge and semantic memory retrieval")
    client = QdrantClient(
        url=settings.url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        prefer_grpc=settings.prefer_grpc,
    )
    return QdrantRuntime(
        client=client,
        knowledge_collection=settings.knowledge_collection,
        user_memory_collection=settings.user_memory_collection,
    )
