from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import HybridRecallResult, KnowledgeChunk, RecallHit, RetrievalFilters, RetrievalPlan
from .protocols import DenseRetriever, MetadataRetriever, Reranker, SparseRetriever

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+#.:-]+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class HybridRetrieverConfig:
    dense_top_k: int = 20
    sparse_top_k: int = 20
    metadata_top_k: int = 10
    rrf_k: int = 60
    rerank_top_k: int = 15


class InMemoryTokenRetriever:
    def __init__(self, chunks: Iterable[KnowledgeChunk], route_name: str) -> None:
        self._chunks = tuple(chunks)
        self._route_name = route_name

    def retrieve(self, plan: RetrievalPlan) -> Sequence[RecallHit]:
        if self._route_name == "dense":
            query = plan.semantic_query
            limit = plan.dense_top_k
        elif self._route_name == "sparse":
            query = plan.keyword_query
            limit = plan.sparse_top_k
        else:
            query = plan.semantic_query
            limit = plan.metadata_top_k

        query_tokens = _tokenize(query)
        scored = []
        for chunk in self._chunks:
            score = self._score(plan.retrieval_filters, plan.preferred_chunk_types, query_tokens, chunk)
            if score <= 0:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        hits = []
        for index, (score, chunk) in enumerate(scored[:limit], start=1):
            hits.append(
                RecallHit(
                    chunk=chunk,
                    score=score,
                    route=self._route_name,
                    rank=index,
                    route_scores={self._route_name: score},
                )
            )
        return tuple(hits)

    def _score(
        self,
        filters: RetrievalFilters,
        preferred_chunk_types: Sequence[str],
        query_tokens: Sequence[str],
        chunk: KnowledgeChunk,
    ) -> float:
        if self._route_name == "metadata" and filters.has_constraints() and not _matches_filters(chunk, filters):
            return 0.0

        chunk_tokens = _tokenize(chunk.searchable_text())
        base_score = _jaccard(query_tokens, chunk_tokens)
        if self._route_name == "sparse":
            base_score = _term_overlap(query_tokens, chunk_tokens)
        elif self._route_name == "metadata":
            matched = _count_filter_matches(chunk, filters)
            total = max(_count_filter_constraints(filters), 1)
            base_score = matched / float(total)
            if query_tokens:
                base_score += 0.2 * _term_overlap(query_tokens, chunk_tokens)

        if chunk.chunk_type in preferred_chunk_types:
            base_score += 0.1
        return min(base_score, 1.0)


class InMemoryReranker:
    def rerank(self, plan: RetrievalPlan, hits: Sequence[RecallHit]) -> Sequence[RecallHit]:
        query_tokens = _tokenize(plan.semantic_query + " " + plan.keyword_query)
        preferred = set(plan.preferred_chunk_types)
        rescored = []
        for hit in hits:
            chunk_tokens = _tokenize(hit.chunk.searchable_text())
            overlap = _term_overlap(query_tokens, chunk_tokens)
            preferred_bonus = 0.08 if hit.chunk.chunk_type in preferred else 0.0
            route_bonus = 0.03 * len(hit.route_scores)
            rescored.append((hit.score + overlap + preferred_bonus + route_bonus, hit))

        rescored.sort(key=lambda item: item[0], reverse=True)
        reranked = []
        top_score = rescored[0][0] if rescored else 1.0
        for index, (score, hit) in enumerate(rescored, start=1):
            reranked.append(
                RecallHit(
                    chunk=hit.chunk,
                    score=score / top_score if top_score else 0.0,
                    route=hit.route,
                    rank=index,
                    route_scores=hit.route_scores,
                    metadata=dict(hit.metadata),
                )
            )
        return tuple(reranked)


class HybridRetrieverService:
    def __init__(
        self,
        dense_retriever: DenseRetriever,
        sparse_retriever: SparseRetriever,
        metadata_retriever: MetadataRetriever,
        reranker: Optional[Reranker] = None,
        config: Optional[HybridRetrieverConfig] = None,
    ) -> None:
        self._dense_retriever = dense_retriever
        self._sparse_retriever = sparse_retriever
        self._metadata_retriever = metadata_retriever
        self._reranker = reranker
        self._config = config or HybridRetrieverConfig()

    def retrieve(self, plan: RetrievalPlan) -> HybridRecallResult:
        route_hits: Dict[str, Sequence[RecallHit]] = {}
        degraded_routes: List[str] = []

        for route_name, retriever in (
            ("dense", self._dense_retriever),
            ("sparse", self._sparse_retriever),
            ("metadata", self._metadata_retriever),
        ):
            try:
                route_hits[route_name] = retriever.retrieve(plan)
            except Exception:
                degraded_routes.append(route_name)
                route_hits[route_name] = ()

        merged_hits = self._rrf_merge(route_hits)
        if self._reranker is not None and merged_hits:
            head = tuple(merged_hits[: plan.rerank_top_k or self._config.rerank_top_k])
            tail = tuple(merged_hits[len(head) :])
            merged_hits = tuple(self._reranker.rerank(plan, head)) + tail

        metrics = {
            "dense_hit_count": len(route_hits.get("dense", ())),
            "sparse_hit_count": len(route_hits.get("sparse", ())),
            "metadata_hit_count": len(route_hits.get("metadata", ())),
            "retrieval_hit_count": len(merged_hits),
            "retrieval_top_score": merged_hits[0].score if merged_hits else 0.0,
        }
        return HybridRecallResult(
            hits=tuple(merged_hits),
            retrieval_strategy="dense+sparse+metadata->rrf->rerank",
            degraded_routes=tuple(degraded_routes),
            metrics=metrics,
            query_plan=plan,
        )

    def _rrf_merge(self, route_hits: Mapping[str, Sequence[RecallHit]]) -> Sequence[RecallHit]:
        fused_scores = defaultdict(float)
        base_hits: Dict[str, RecallHit] = {}
        route_scores: Dict[str, Dict[str, float]] = defaultdict(dict)
        rrf_k = self._config.rrf_k

        for route_name, hits in route_hits.items():
            for rank, hit in enumerate(hits, start=1):
                chunk_id = hit.chunk.chunk_id
                fused_scores[chunk_id] += 1.0 / float(rrf_k + rank)
                base_hits.setdefault(chunk_id, hit)
                route_scores[chunk_id][route_name] = hit.score

        if not fused_scores:
            return ()

        max_score = max(fused_scores.values())
        merged = []
        for index, (chunk_id, fused_score) in enumerate(
            sorted(fused_scores.items(), key=lambda item: item[1], reverse=True),
            start=1,
        ):
            base_hit = base_hits[chunk_id]
            merged.append(
                RecallHit(
                    chunk=base_hit.chunk,
                    score=fused_score / max_score if max_score else 0.0,
                    route="hybrid",
                    rank=index,
                    route_scores=route_scores[chunk_id],
                    metadata={"source_routes": tuple(sorted(route_scores[chunk_id]))},
                )
            )
        return tuple(merged)


def _tokenize(text: str) -> Tuple[str, ...]:
    if not text:
        return ()
    return tuple(token.lower() for token in _TOKEN_PATTERN.findall(text))


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    union = len(left_set | right_set)
    return intersection / float(union or 1)


def _term_overlap(left: Sequence[str], right: Sequence[str]) -> float:
    if not left or not right:
        return 0.0
    right_set = set(right)
    matched = sum(1 for token in left if token in right_set)
    return matched / float(max(len(left), 1))


def _matches_filters(chunk: KnowledgeChunk, filters: RetrievalFilters) -> bool:
    checks = (
        (filters.category, chunk.category),
        (filters.subcategory, chunk.subcategory),
        (filters.difficulty, chunk.difficulty),
        (filters.source_type, chunk.source_type),
        (filters.chunk_type, chunk.chunk_type),
        (filters.version, chunk.version),
    )
    for expected, actual in checks:
        normalized_expected = {_normalize_value(value) for value in expected if value}
        normalized_actual = _normalize_value(actual)
        if normalized_expected and normalized_actual not in normalized_expected:
            return False
    if filters.tags and not {_normalize_value(tag) for tag in filters.tags}.issubset(
        {_normalize_value(tag) for tag in chunk.tags}
    ):
        return False
    for key, expected in filters.extra.items():
        actual = chunk.metadata.get(key)
        if isinstance(expected, (list, tuple, set)):
            normalized_expected = {_normalize_value(value) for value in expected if value}
            if _normalize_value(actual) not in normalized_expected:
                return False
        elif _normalize_value(actual) != _normalize_value(expected):
            return False
    return True


def _count_filter_constraints(filters: RetrievalFilters) -> int:
    total = 0
    for values in filters.as_dict().values():
        if values:
            total += 1
    total += len(filters.extra)
    return total


def _count_filter_matches(chunk: KnowledgeChunk, filters: RetrievalFilters) -> int:
    matches = 0
    checks = (
        (filters.category, chunk.category),
        (filters.subcategory, chunk.subcategory),
        (filters.difficulty, chunk.difficulty),
        (filters.source_type, chunk.source_type),
        (filters.chunk_type, chunk.chunk_type),
        (filters.version, chunk.version),
    )
    for expected, actual in checks:
        normalized_expected = {_normalize_value(value) for value in expected if value}
        if normalized_expected and _normalize_value(actual) in normalized_expected:
            matches += 1
    if filters.tags and {_normalize_value(tag) for tag in filters.tags}.issubset(
        {_normalize_value(tag) for tag in chunk.tags}
    ):
        matches += 1
    for key, expected in filters.extra.items():
        actual = chunk.metadata.get(key)
        if isinstance(expected, (list, tuple, set)):
            normalized_expected = {_normalize_value(value) for value in expected if value}
            if _normalize_value(actual) in normalized_expected:
                matches += 1
        elif _normalize_value(actual) == _normalize_value(expected):
            matches += 1
    return matches


def _normalize_value(value: object) -> str:
    return str(value or "").strip().lower()
