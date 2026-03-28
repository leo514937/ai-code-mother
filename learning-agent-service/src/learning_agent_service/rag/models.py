from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


class ChunkType(str, Enum):
    CONCEPT = "concept"
    COMPARISON = "comparison"
    INTERVIEW_TEMPLATE = "interview_template"
    QA = "qa"
    CODE_EXAMPLE = "code_example"
    ROADMAP = "roadmap"
    PITFALL = "pitfall"
    PRACTICE_CASE = "practice_case"


class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class SourceType(str, Enum):
    DOCUMENT = "document"
    FAQ = "faq"
    INTERVIEW = "interview"
    NOTE = "note"
    PRACTICE = "practice"


class GovernanceAction(str, Enum):
    ACTIVATE_VERSION = "activate_version"
    ROLLBACK_VERSION = "rollback_version"
    REBUILD_DOCUMENT = "rebuild_document"
    CLEAN_DUPLICATES = "clean_duplicates"
    NOOP = "noop"


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    text: str
    title: str = ""
    category: Optional[str] = None
    subcategory: Optional[str] = None
    difficulty: Optional[str] = None
    source_type: Optional[str] = None
    chunk_type: Optional[str] = None
    version: Optional[str] = None
    tags: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def searchable_text(self) -> str:
        parts = [
            self.title,
            self.text,
            self.category or "",
            self.subcategory or "",
            " ".join(self.tags),
        ]
        return " ".join(part for part in parts if part).strip()


@dataclass(frozen=True)
class RetrievalFilters:
    category: Tuple[str, ...] = ()
    subcategory: Tuple[str, ...] = ()
    difficulty: Tuple[str, ...] = ()
    source_type: Tuple[str, ...] = ()
    chunk_type: Tuple[str, ...] = ()
    version: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Tuple[str, ...]]:
        return {
            "category": self.category,
            "subcategory": self.subcategory,
            "difficulty": self.difficulty,
            "source_type": self.source_type,
            "chunk_type": self.chunk_type,
            "version": self.version,
            "tags": self.tags,
        }

    def has_constraints(self) -> bool:
        return any(self.as_dict().values()) or bool(self.extra)


@dataclass(frozen=True)
class RetrievalPlan:
    semantic_query: str
    keyword_query: str
    retrieval_filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    preferred_chunk_types: Tuple[str, ...] = ()
    dense_top_k: int = 20
    sparse_top_k: int = 20
    metadata_top_k: int = 10
    rerank_top_k: int = 15
    max_evidence: int = 6
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallHit:
    chunk: KnowledgeChunk
    score: float
    route: str
    rank: int
    route_scores: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HybridRecallResult:
    hits: Tuple[RecallHit, ...]
    retrieval_strategy: str
    degraded_routes: Tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    query_plan: Optional[RetrievalPlan] = None


@dataclass(frozen=True)
class EvidenceItem:
    chunk: KnowledgeChunk
    score: float
    routes: Tuple[str, ...]
    reasons: Tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidencePack:
    items: Tuple[EvidenceItem, ...]
    status: str
    filtered_out: int = 0
    rationale: Tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    document_id: str
    title: str
    source_type: Optional[str]
    version: Optional[str]
    score: float
    excerpt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeGovernanceDecision:
    action: GovernanceAction
    document_id: str
    reason: str
    target_version: Optional[str] = None
    affected_chunk_ids: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReferenceResolutionRequest:
    message: str
    lowered_message: str
    current_topic: Optional[str] = None
    last_retrieval_topic: Optional[str] = None
    recent_entities: Tuple[str, ...] = ()
    pending_clarification_values: Tuple[str, ...] = ()
    clarification_result: Mapping[str, Any] = field(default_factory=dict)
    follow_up_intent: bool = False


@dataclass(frozen=True)
class ReferenceResolution:
    resolved: bool
    confidence: float
    resolved_entity: Optional[str] = None
    candidate_entities: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeSearchRequest:
    query: str
    limit: int = 5
    category: Optional[str] = None
    query_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeSearchMatch:
    chunk: KnowledgeChunk
    score: float
    citation: Optional[Citation] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeSearchResult:
    query: str
    retrieval_strategy: str
    runtime_mode: str
    plan: RetrievalPlan
    recall: HybridRecallResult
    evidence: EvidencePack
    citations: Tuple[Citation, ...]
    matches: Tuple[KnowledgeSearchMatch, ...]
    metrics: Mapping[str, Any] = field(default_factory=dict)


def coerce_tuple(values: Optional[Iterable[str]]) -> Tuple[str, ...]:
    if not values:
        return ()
    return tuple(value for value in values if value)


def latest_version(chunks: Sequence[KnowledgeChunk]) -> Optional[str]:
    versions = sorted({chunk.version for chunk in chunks if chunk.version})
    return versions[-1] if versions else None
