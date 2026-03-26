from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .models import EvidenceItem, EvidencePack, RecallHit, RetrievalPlan

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+#.:-]+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class EvidenceGovernanceConfig:
    low_score_threshold: float = 0.18
    dedup_similarity_threshold: float = 0.82
    topic_consistency_threshold: float = 0.35
    min_items: int = 4
    max_items: int = 6


class EvidenceGovernanceService:
    def __init__(self, config: EvidenceGovernanceConfig = None) -> None:
        self._config = config or EvidenceGovernanceConfig()

    def evaluate(self, plan: RetrievalPlan, hits: Sequence[RecallHit]) -> EvidencePack:
        original_count = len(hits)
        filtered = self._low_score_filter(hits)
        filtered = self._deduplicate(filtered)
        filtered = self._topic_consistency_filter(plan, filtered)
        filtered = self._version_filter(plan, filtered)
        filtered = self._answer_view_filter(plan, filtered)
        limit = min(plan.max_evidence or self._config.max_items, self._config.max_items)
        filtered = filtered[:limit]

        evidence_items = tuple(
            EvidenceItem(
                chunk=hit.chunk,
                score=hit.score,
                routes=tuple(sorted(hit.route_scores)) if hit.route_scores else (hit.route,),
                reasons=(
                    "passed_low_score_filter",
                    "passed_dedup_filter",
                    "passed_topic_consistency_filter",
                    "passed_version_filter",
                    "passed_answer_view_filter",
                ),
                metadata={"source_routes": tuple(sorted(hit.route_scores))},
            )
            for hit in filtered
        )

        if not evidence_items:
            status = "empty"
        elif len(evidence_items) < self._config.min_items:
            status = "degraded"
        else:
            status = "ok"

        metrics = {
            "evidence_used_count": len(evidence_items),
            "evidence_filtered_out": max(original_count - len(evidence_items), 0),
        }
        rationale = [
            "low_score_filter",
            "deduplication",
            "topic_consistency_filter",
            "version_filter",
            "answer_view_filter",
        ]
        return EvidencePack(
            items=evidence_items,
            status=status,
            filtered_out=max(original_count - len(evidence_items), 0),
            rationale=tuple(rationale),
            metrics=metrics,
        )

    def _low_score_filter(self, hits: Sequence[RecallHit]) -> List[RecallHit]:
        return [hit for hit in hits if hit.score >= self._config.low_score_threshold]

    def _deduplicate(self, hits: Sequence[RecallHit]) -> List[RecallHit]:
        kept: List[RecallHit] = []
        for hit in hits:
            if any(self._text_similarity(hit.chunk.text, other.chunk.text) >= self._config.dedup_similarity_threshold for other in kept):
                continue
            kept.append(hit)
        return kept

    def _topic_consistency_filter(self, plan: RetrievalPlan, hits: Sequence[RecallHit]) -> List[RecallHit]:
        query_tokens = self._tokenize(plan.semantic_query + " " + plan.keyword_query)
        if not query_tokens:
            return list(hits)

        kept = []
        for hit in hits:
            chunk_tokens = self._tokenize(hit.chunk.searchable_text())
            score = self._jaccard(query_tokens, chunk_tokens)
            if score >= self._config.topic_consistency_threshold or hit.chunk.chunk_type in plan.preferred_chunk_types:
                kept.append(hit)
        return kept or list(hits[: self._config.min_items])

    def _version_filter(self, plan: RetrievalPlan, hits: Sequence[RecallHit]) -> List[RecallHit]:
        if plan.retrieval_filters.version:
            allowed = set(plan.retrieval_filters.version)
            return [hit for hit in hits if hit.chunk.version in allowed]

        latest_by_document: Dict[str, str] = {}
        for hit in hits:
            version = hit.chunk.version or ""
            current = latest_by_document.get(hit.chunk.document_id)
            if current is None or version > current:
                latest_by_document[hit.chunk.document_id] = version

        return [
            hit
            for hit in hits
            if not latest_by_document.get(hit.chunk.document_id)
            or (hit.chunk.version or "") == latest_by_document[hit.chunk.document_id]
        ]

    def _answer_view_filter(self, plan: RetrievalPlan, hits: Sequence[RecallHit]) -> List[RecallHit]:
        if not plan.preferred_chunk_types:
            return list(hits)

        preferred = [hit for hit in hits if hit.chunk.chunk_type in plan.preferred_chunk_types]
        fallback = [hit for hit in hits if hit.chunk.chunk_type not in plan.preferred_chunk_types]
        merged = preferred + fallback
        return merged[: self._config.max_items]

    @staticmethod
    def _tokenize(text: str) -> Tuple[str, ...]:
        return tuple(token.lower() for token in _TOKEN_PATTERN.findall(text or ""))

    @classmethod
    def _text_similarity(cls, left: str, right: str) -> float:
        return cls._jaccard(cls._tokenize(left), cls._tokenize(right))

    @staticmethod
    def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
        left_set = set(left)
        right_set = set(right)
        if not left_set or not right_set:
            return 0.0
        return len(left_set & right_set) / float(len(left_set | right_set) or 1)
