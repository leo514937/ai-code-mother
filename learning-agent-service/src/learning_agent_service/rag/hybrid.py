from __future__ import annotations

from dataclasses import dataclass

from .retrieval import (
    CrossEncoderReranker,
    HeuristicDenseRetriever,
    HeuristicMetadataRetriever,
    HeuristicReranker,
    HeuristicSparseRetriever,
    HybridRetrieverService,
    InMemoryTokenRetriever,
    LocalBM25SparseRetriever,
    ParentChildResolver,
    QdrantOnlineDenseRetriever,
    QdrantOnlineSparseRetriever,
    RRFConfig,
    ReciprocalRankFusion,
    RemoteReranker,
)


@dataclass(frozen=True)
class HybridRetrieverConfig:
    dense_top_k: int = 20
    sparse_top_k: int = 20
    metadata_top_k: int = 10
    rrf_k: int = 60
    rerank_top_k: int = 15
    metadata_filter_confidence_threshold: float = 0.5


InMemoryReranker = HeuristicReranker


__all__ = [
    "HeuristicDenseRetriever",
    "HeuristicMetadataRetriever",
    "HeuristicReranker",
    "HeuristicSparseRetriever",
    "CrossEncoderReranker",
    "HybridRetrieverConfig",
    "HybridRetrieverService",
    "InMemoryReranker",
    "InMemoryTokenRetriever",
    "LocalBM25SparseRetriever",
    "ParentChildResolver",
    "QdrantOnlineDenseRetriever",
    "QdrantOnlineSparseRetriever",
    "RRFConfig",
    "ReciprocalRankFusion",
    "RemoteReranker",
]
