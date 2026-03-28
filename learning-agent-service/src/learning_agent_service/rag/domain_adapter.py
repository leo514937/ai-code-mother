from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Tuple

from learning_agent_service.domain import (
    Citation,
    CitationBuildRequest,
    EvidenceEvaluationRequest,
    EvidenceItem,
    EvidencePack,
    HybridRecallCandidate,
    HybridRecallResult as DomainHybridRecallResult,
    HybridRetrieveRequest,
    KnowledgeSearchRequest as DomainKnowledgeSearchRequest,
    KnowledgeSearchResult as DomainKnowledgeSearchResult,
    QueryRewriteRequest,
    ReferenceResolutionRequest as DomainReferenceResolutionRequest,
    ReferenceResolutionResult,
    RetrievalPlan,
)
from learning_agent_service.domain.enums import IntentType, OutputStyle

from .models import (
    Citation as InternalCitation,
    EvidenceItem as InternalEvidenceItem,
    EvidencePack as InternalEvidencePack,
    HybridRecallResult,
    KnowledgeChunk,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    RecallHit,
    ReferenceResolutionRequest,
    RetrievalFilters,
    RetrievalPlan as InternalRetrievalPlan,
)
from .rewrite import QueryRewriteContext

_CN_COMPARE = "\u533a\u522b"
_CN_EXPLAIN = "\u7406\u89e3"
_CN_EXPLAIN_ALT = "\u89e3\u91ca"
_CN_HOW = "\u600e\u4e48"
_CN_THIS = "\u8fd9\u4e2a"
_CN_THAT = "\u90a3\u4e2a"
_CN_PREVIOUS = "\u4e0a\u4e00\u4e2a"
_CN_IT = "\u5b83"
_EN_FOLLOW_UP_TOKENS = ("explain", "how", "compare")


class DomainRagAdapter:
    def build_query_rewrite_context(self, request: QueryRewriteRequest) -> QueryRewriteContext:
        return QueryRewriteContext(
            raw_query=request.raw_query,
            intent=self._intent_value(request.intent),
            resolved_topic=request.reference_resolution.resolved_entity if request.reference_resolution else None,
            session_topic=request.current_topic or request.topic_hint,
            requested_output_style=self._style_value(request.requested_output_style),
            filters=self.to_internal_filters(request.base_filters),
            user_preferences=request.user_preferences,
            extra={},
        )

    def build_reference_request(self, request: DomainReferenceResolutionRequest) -> ReferenceResolutionRequest:
        values = []
        if request.pending_clarification is not None:
            for option in request.pending_clarification.options:
                if option.value:
                    values.append(option.value)
                elif option.label:
                    values.append(option.label)
        message = request.raw_query.strip()
        lowered_message = message.lower()
        return ReferenceResolutionRequest(
            message=message,
            lowered_message=lowered_message,
            current_topic=request.current_topic,
            last_retrieval_topic=request.clarification_result.get("last_retrieval_topic"),
            recent_entities=tuple(request.recent_entities),
            pending_clarification_values=tuple(values),
            clarification_result=dict(request.clarification_result),
            follow_up_intent=self._looks_like_follow_up_query(request, message, lowered_message),
        )

    def to_domain_reference(self, resolution) -> ReferenceResolutionResult:
        return ReferenceResolutionResult(
            resolved=resolution.resolved,
            confidence=resolution.confidence,
            resolved_entity=resolution.resolved_entity,
            candidate_entities=list(resolution.candidate_entities),
            extra=dict(resolution.metadata),
        )

    def to_domain_plan(self, plan: InternalRetrievalPlan) -> RetrievalPlan:
        filters = plan.retrieval_filters
        return RetrievalPlan(
            semantic_query=plan.semantic_query,
            keyword_query=plan.keyword_query,
            retrieval_filters={
                "category": list(filters.category),
                "subcategory": list(filters.subcategory),
                "difficulty": list(filters.difficulty),
                "source_type": list(filters.source_type),
                "chunk_type": list(filters.chunk_type),
                "version": list(filters.version),
                "tags": list(filters.tags),
                "extra": dict(filters.extra),
            },
            preferred_chunk_types=list(plan.preferred_chunk_types),
            reasoning_notes=["rewrite_query_for_retrieval"],
            extra=dict(plan.extra),
        )

    def to_internal_plan(
        self,
        request: RetrievalPlan | HybridRetrieveRequest | EvidenceEvaluationRequest,
        *,
        dense_top_k: int,
        sparse_top_k: int,
        metadata_top_k: int,
        rerank_top_k: int,
        max_evidence: int,
    ) -> InternalRetrievalPlan:
        plan = request.plan if hasattr(request, "plan") else request
        return InternalRetrievalPlan(
            semantic_query=plan.semantic_query,
            keyword_query=plan.keyword_query,
            retrieval_filters=self.to_internal_filters(plan.retrieval_filters),
            preferred_chunk_types=tuple(plan.preferred_chunk_types),
            dense_top_k=dense_top_k,
            sparse_top_k=sparse_top_k,
            metadata_top_k=metadata_top_k,
            rerank_top_k=rerank_top_k,
            max_evidence=max_evidence,
            extra=dict(plan.extra),
        )

    def to_domain_hybrid(self, recall: HybridRecallResult) -> DomainHybridRecallResult:
        source_hits = tuple(recall.hits)
        return DomainHybridRecallResult(
            dense_hits=self._to_domain_candidates(hit for hit in source_hits if "dense" in hit.route_scores),
            sparse_hits=self._to_domain_candidates(hit for hit in source_hits if "sparse" in hit.route_scores),
            metadata_hits=self._to_domain_candidates(hit for hit in source_hits if "metadata" in hit.route_scores),
            fused_hits=self._to_domain_candidates(source_hits),
            reranked_hits=self._to_domain_candidates(source_hits),
            metrics=dict(recall.metrics),
            extra={
                "retrieval_strategy": recall.retrieval_strategy,
                "degraded_routes": list(recall.degraded_routes),
                "query_plan": self.to_domain_plan(recall.query_plan).model_dump(mode="json")
                if recall.query_plan is not None
                else None,
            },
        )

    def to_internal_hits(self, candidates: Iterable[HybridRecallCandidate]) -> Tuple[RecallHit, ...]:
        hits = []
        for index, candidate in enumerate(candidates, start=1):
            metadata = dict(candidate.metadata)
            raw = dict(candidate.raw)
            hits.append(
                RecallHit(
                    chunk=KnowledgeChunk(
                        chunk_id=candidate.chunk_id,
                        document_id=candidate.document_id or "unknown-document",
                        text=candidate.content or "",
                        title=str(metadata.get("title") or candidate.chunk_id),
                        category=self._optional_str(metadata.get("category")),
                        subcategory=self._optional_str(metadata.get("subcategory")),
                        difficulty=self._optional_str(metadata.get("difficulty")),
                        source_type=self._optional_str(metadata.get("source_type")),
                        chunk_type=self._optional_str(candidate.chunk_type),
                        version=self._optional_str(metadata.get("version")),
                        tags=tuple(str(tag) for tag in metadata.get("tags", []) if tag),
                        metadata=dict(raw.get("metadata", {})),
                    ),
                    score=float(candidate.score),
                    route=str(raw.get("route") or "hybrid"),
                    rank=int(raw.get("rank") or index),
                    route_scores=dict(raw.get("route_scores", {})),
                    metadata=dict(raw.get("metadata", {})),
                )
            )
        return tuple(hits)

    def to_domain_evidence_pack(self, evidence: InternalEvidencePack, plan: RetrievalPlan) -> EvidencePack:
        return EvidencePack(
            items=[
                EvidenceItem(
                    chunk_id=item.chunk.chunk_id,
                    content=item.chunk.text,
                    score=item.score,
                    document_id=item.chunk.document_id,
                    chunk_type=item.chunk.chunk_type,
                    metadata={
                        "title": item.chunk.title,
                        "category": item.chunk.category,
                        "subcategory": item.chunk.subcategory,
                        "difficulty": item.chunk.difficulty,
                        "source_type": item.chunk.source_type,
                        "version": item.chunk.version,
                        "tags": list(item.chunk.tags),
                        "routes": list(item.routes),
                        "reasons": list(item.reasons),
                        **dict(item.metadata),
                    },
                )
                for item in evidence.items
            ],
            discard_summary={
                "status": evidence.status,
                "filtered_out": evidence.filtered_out,
                "rationale": list(evidence.rationale),
            },
            top_scores=[item.score for item in evidence.items],
            extra={
                "metrics": dict(evidence.metrics),
                "query_plan": plan.model_dump(mode="json"),
            },
        )

    def to_internal_evidence_pack(self, request: CitationBuildRequest | EvidencePack) -> InternalEvidencePack:
        evidence = request.evidence_pack if hasattr(request, "evidence_pack") else request
        return InternalEvidencePack(
            items=tuple(
                InternalEvidenceItem(
                    chunk=KnowledgeChunk(
                        chunk_id=item.chunk_id,
                        document_id=item.document_id or "unknown-document",
                        text=item.content,
                        title=str(item.metadata.get("title") or item.chunk_id),
                        category=self._optional_str(item.metadata.get("category")),
                        subcategory=self._optional_str(item.metadata.get("subcategory")),
                        difficulty=self._optional_str(item.metadata.get("difficulty")),
                        source_type=self._optional_str(item.metadata.get("source_type")),
                        chunk_type=self._optional_str(item.chunk_type),
                        version=self._optional_str(item.metadata.get("version")),
                        tags=tuple(str(tag) for tag in item.metadata.get("tags", []) if tag),
                        metadata={},
                    ),
                    score=item.score,
                    routes=tuple(str(route) for route in item.metadata.get("routes", []) if route),
                    reasons=tuple(str(reason) for reason in item.metadata.get("reasons", []) if reason),
                    metadata={},
                )
                for item in evidence.items
            ),
            status=str(evidence.discard_summary.get("status", "empty")),
            filtered_out=int(evidence.discard_summary.get("filtered_out", 0)),
            rationale=tuple(str(reason) for reason in evidence.discard_summary.get("rationale", [])),
            metrics=dict(evidence.extra.get("metrics", {})),
        )

    def to_domain_citation(self, citation: InternalCitation) -> Citation:
        return Citation(
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            source_type=citation.source_type,
            version=citation.version,
            score=citation.score,
            title=citation.title,
            locator=str(citation.metadata.get("chunk_type") or ""),
        )

    def to_internal_search_request(self, request: DomainKnowledgeSearchRequest) -> KnowledgeSearchRequest:
        category = request.category
        if category is None:
            category_filters = request.retrieval_filters.get("category") if request.retrieval_filters else None
            if isinstance(category_filters, str):
                category = category_filters
            elif category_filters:
                category = str(list(category_filters)[0])
        return KnowledgeSearchRequest(
            query=request.topic,
            limit=request.limit,
            category=category,
            query_context={"retrieval_filters": dict(request.retrieval_filters)},
        )

    def to_domain_search_result(self, result: KnowledgeSearchResult) -> DomainKnowledgeSearchResult:
        matches = []
        citations = []
        for match in result.matches:
            citation = self.to_domain_citation(match.citation) if match.citation is not None else None
            if citation is not None:
                citations.append(citation)
            matches.append(
                {
                    "chunk_id": match.chunk.chunk_id,
                    "document_id": match.chunk.document_id,
                    "title": match.chunk.title,
                    "score": match.score,
                    "content": match.chunk.text,
                    "chunk_type": match.chunk.chunk_type,
                    "category": match.chunk.category,
                    "subcategory": match.chunk.subcategory,
                    "source_type": match.chunk.source_type,
                    "version": match.chunk.version,
                    "citation": citation.model_dump(mode="json") if citation is not None else None,
                }
            )
        domain_plan = self.to_domain_plan(result.plan)
        return DomainKnowledgeSearchResult(
            matches=matches,
            evidence_pack=self.to_domain_evidence_pack(result.evidence, domain_plan),
            citations=citations,
            retrieval_strategy=self.retrieval_strategy(result.retrieval_strategy),
            extra={
                "runtime_mode": result.runtime_mode,
                "metrics": dict(result.metrics),
                "retrieval_plan": domain_plan.model_dump(mode="json"),
            },
        )

    @staticmethod
    def to_internal_filters(raw_filters: Mapping[str, Any]) -> RetrievalFilters:
        def coerce(value: Any) -> Tuple[str, ...]:
            if not value:
                return ()
            if isinstance(value, str):
                return (value,)
            return tuple(str(item) for item in value if item)

        return RetrievalFilters(
            category=coerce(raw_filters.get("category")),
            subcategory=coerce(raw_filters.get("subcategory")),
            difficulty=coerce(raw_filters.get("difficulty")),
            source_type=coerce(raw_filters.get("source_type")),
            chunk_type=coerce(raw_filters.get("chunk_type")),
            version=coerce(raw_filters.get("version")),
            tags=coerce(raw_filters.get("tags")),
            extra=dict(raw_filters.get("extra", {})),
        )

    @staticmethod
    def retrieval_strategy(strategy: Optional[str]) -> str:
        if isinstance(strategy, str) and strategy:
            return strategy if strategy.endswith("->evidence") else strategy + "->evidence"
        return "dense+sparse+metadata->rrf->rerank->evidence"

    @staticmethod
    def _to_domain_candidates(hits: Iterable[RecallHit]) -> list[HybridRecallCandidate]:
        return [
            HybridRecallCandidate(
                chunk_id=hit.chunk.chunk_id,
                score=hit.score,
                content=hit.chunk.text,
                document_id=hit.chunk.document_id,
                chunk_type=hit.chunk.chunk_type,
                metadata={
                    "title": hit.chunk.title,
                    "category": hit.chunk.category,
                    "subcategory": hit.chunk.subcategory,
                    "difficulty": hit.chunk.difficulty,
                    "source_type": hit.chunk.source_type,
                    "version": hit.chunk.version,
                    "tags": list(hit.chunk.tags),
                },
                channels=list(sorted(hit.route_scores)) or [hit.route],
                raw={
                    "route": hit.route,
                    "rank": hit.rank,
                    "route_scores": dict(hit.route_scores),
                    "metadata": dict(hit.metadata),
                },
            )
            for hit in hits
        ]

    @staticmethod
    def _intent_value(intent: Optional[IntentType]) -> Optional[str]:
        return intent.value if intent is not None else None

    @staticmethod
    def _style_value(style: Optional[OutputStyle]) -> Optional[str]:
        return style.value if style is not None else None

    @staticmethod
    def _optional_str(value: Any) -> Optional[str]:
        if value is None or value == "":
            return None
        return str(value)

    @staticmethod
    def _looks_like_follow_up_query(
        request: DomainReferenceResolutionRequest,
        message: str,
        lowered_message: str,
    ) -> bool:
        if DomainRagAdapter._contains_reference_token(message, lowered_message):
            return True
        has_context = bool(
            request.current_topic
            or request.recent_entities
            or request.clarification_result.get("last_retrieval_topic")
            or request.topic_hint
            or request.history_summary
        )
        if not has_context:
            return False
        short_cn_follow_up = len(message) <= 14 and any(
            token in message for token in (_CN_EXPLAIN, _CN_EXPLAIN_ALT, _CN_HOW, _CN_COMPARE)
        )
        short_en_follow_up = len(lowered_message.split()) <= 4 and any(
            token in lowered_message for token in _EN_FOLLOW_UP_TOKENS
        )
        return short_cn_follow_up or short_en_follow_up

    @staticmethod
    def _contains_reference_token(message: str, lowered_message: str) -> bool:
        return any(token in lowered_message for token in ("this", "that", "previous", "it")) or any(
            token in message for token in (_CN_THIS, _CN_THAT, _CN_PREVIOUS, _CN_IT)
        )
