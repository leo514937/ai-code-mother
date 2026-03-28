from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from learning_agent_service.config import Settings
from learning_agent_service.domain import (
    Citation,
    CitationBuildRequest,
    EvidenceEvaluationRequest,
    EvidencePack,
    HybridRecallResult,
    HybridRetrieveRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    QueryRewriteRequest,
    ReferenceResolutionRequest,
    ReferenceResolutionResult,
    RetrievalPlan,
)

from .citation import CitationBuilder
from .defaults import DEFAULT_KNOWLEDGE_CHUNKS
from .domain_adapter import DomainRagAdapter
from .evidence import EvidenceGovernanceConfig, EvidenceGovernanceService
from .governance import GovernanceConfig, KnowledgeGovernanceService
from .hybrid import (
    HybridRetrieverConfig,
    HybridRetrieverService,
    InMemoryReranker,
    InMemoryTokenRetriever,
)
from .models import KnowledgeChunk, KnowledgeGovernanceDecision, latest_version
from .protocols import DenseRetriever, HybridRetriever, MetadataRetriever, Reranker, SparseRetriever
from .reference import ReferenceResolver
from .rewrite import QueryRewriteService
from .search import KnowledgeSearchConfig, KnowledgeSearchFacade


class HybridRAGOrchestrator:
    """Thin typed facade over the concrete RAG capabilities."""

    def __init__(
        self,
        settings: Settings,
        *,
        knowledge_chunks: Optional[Iterable[KnowledgeChunk]] = None,
        rewrite_service: Optional[QueryRewriteService] = None,
        dense_retriever: Optional[DenseRetriever] = None,
        sparse_retriever: Optional[SparseRetriever] = None,
        metadata_retriever: Optional[MetadataRetriever] = None,
        reranker: Optional[Reranker] = None,
        hybrid_retriever: Optional[HybridRetriever] = None,
        evidence_service: Optional[EvidenceGovernanceService] = None,
        citation_builder: Optional[CitationBuilder] = None,
        governance_service: Optional[KnowledgeGovernanceService] = None,
        reference_resolver: Optional[ReferenceResolver] = None,
        runtime_mode: str = "snapshot",
    ) -> None:
        self.settings = settings
        self.runtime_mode = runtime_mode
        self._adapter = DomainRagAdapter()
        self._rewrite = rewrite_service or QueryRewriteService()
        self._governance = governance_service or KnowledgeGovernanceService(GovernanceConfig())

        initial_chunks = tuple(knowledge_chunks or DEFAULT_KNOWLEDGE_CHUNKS)
        self._chunks = self._governance.deduplicate_chunks(initial_chunks)

        self._dense_retriever = dense_retriever or InMemoryTokenRetriever(self._chunks, "dense")
        self._sparse_retriever = sparse_retriever or InMemoryTokenRetriever(self._chunks, "sparse")
        self._metadata_retriever = metadata_retriever or InMemoryTokenRetriever(self._chunks, "metadata")
        self._reranker = reranker or InMemoryReranker()
        self._retriever = hybrid_retriever or HybridRetrieverService(
            dense_retriever=self._dense_retriever,
            sparse_retriever=self._sparse_retriever,
            metadata_retriever=self._metadata_retriever,
            reranker=self._reranker,
            config=HybridRetrieverConfig(
                dense_top_k=settings.dense_top_k,
                sparse_top_k=settings.sparse_top_k,
                metadata_top_k=settings.metadata_top_k,
                rrf_k=settings.rrf_k,
                rerank_top_k=settings.rerank_top_k,
            ),
        )
        self._evidence = evidence_service or EvidenceGovernanceService(
            EvidenceGovernanceConfig(
                low_score_threshold=settings.low_score_threshold,
                dedup_similarity_threshold=settings.dedup_similarity_threshold,
                topic_consistency_threshold=settings.topic_consistency_threshold,
                min_items=settings.evidence_min_n,
                max_items=settings.evidence_top_n,
            )
        )
        self._citation_builder = citation_builder or CitationBuilder()
        self._reference_resolver = reference_resolver or ReferenceResolver()
        self._search = KnowledgeSearchFacade(
            rewrite_service=self._rewrite,
            retriever=self._retriever,
            evidence_service=self._evidence,
            citation_builder=self._citation_builder,
            config=KnowledgeSearchConfig(runtime_mode=runtime_mode),
        )

    @property
    def knowledge_chunks(self) -> Tuple[KnowledgeChunk, ...]:
        return self._chunks

    def resolve_reference(self, request: ReferenceResolutionRequest) -> ReferenceResolutionResult:
        internal_request = self._adapter.build_reference_request(request)
        return self._adapter.to_domain_reference(self._reference_resolver.resolve(internal_request))

    def rewrite_query(self, request: QueryRewriteRequest) -> RetrievalPlan:
        context = self._adapter.build_query_rewrite_context(request)
        return self._adapter.to_domain_plan(self._rewrite.build_plan(context))

    def hybrid_retrieve(self, request: HybridRetrieveRequest) -> HybridRecallResult:
        internal_plan = self._adapter.to_internal_plan(
            request,
            dense_top_k=self.settings.dense_top_k,
            sparse_top_k=self.settings.sparse_top_k,
            metadata_top_k=self.settings.metadata_top_k,
            rerank_top_k=self.settings.rerank_top_k,
            max_evidence=self.settings.evidence_top_n,
        )
        return self._adapter.to_domain_hybrid(self._retriever.retrieve(internal_plan))

    def evaluate_evidence(self, request: EvidenceEvaluationRequest) -> EvidencePack:
        internal_plan = self._adapter.to_internal_plan(
            request,
            dense_top_k=self.settings.dense_top_k,
            sparse_top_k=self.settings.sparse_top_k,
            metadata_top_k=self.settings.metadata_top_k,
            rerank_top_k=self.settings.rerank_top_k,
            max_evidence=self.settings.evidence_top_n,
        )
        internal_hits = self._adapter.to_internal_hits(request.hybrid_recall.reranked_hits)
        if not internal_hits:
            internal_hits = tuple(self._retriever.retrieve(internal_plan).hits)
        evidence = self._evidence.evaluate(internal_plan, internal_hits)
        return self._adapter.to_domain_evidence_pack(evidence, request.plan)

    def build_citations(self, request: CitationBuildRequest) -> Iterable[Citation]:
        internal_pack = self._adapter.to_internal_evidence_pack(request)
        return [self._adapter.to_domain_citation(item) for item in self._citation_builder.build(internal_pack)]

    def search_knowledge(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        internal_request = self._adapter.to_internal_search_request(request)
        return self._adapter.to_domain_search_result(self._search.search(internal_request))

    def get_knowledge_detail(self, topic: str) -> dict:
        result = self.search_knowledge(KnowledgeSearchRequest(topic=topic, limit=1))
        detail = result.matches[0] if result.matches else None
        return {
            "topic": topic,
            "detail": detail,
            "retrieval_strategy": result.retrieval_strategy,
            "runtime_mode": result.extra.get("runtime_mode"),
            "metrics": result.extra.get("metrics", {}),
        }

    def deduplicate_chunks(self, chunks: Iterable[KnowledgeChunk]) -> Tuple[KnowledgeChunk, ...]:
        return self._governance.deduplicate_chunks(tuple(chunks))

    def plan_duplicate_cleanup(
        self,
        document_id: str,
        chunks: Optional[Sequence[KnowledgeChunk]] = None,
    ) -> KnowledgeGovernanceDecision:
        candidate_chunks = tuple(chunks) if chunks is not None else self.active_chunks(document_id=document_id)
        return self._governance.plan_duplicate_cleanup(document_id=document_id, chunks=candidate_chunks)

    def plan_version_switch(
        self,
        document_id: str,
        target_version: str,
        reason: str = "activate newer version",
    ) -> KnowledgeGovernanceDecision:
        return self._governance.plan_version_switch(document_id=document_id, target_version=target_version, reason=reason)

    def plan_rebuild(self, document_id: str, reason: str = "rebuild requested") -> KnowledgeGovernanceDecision:
        return self._governance.plan_rebuild(document_id=document_id, reason=reason)

    def plan_rollback(
        self,
        document_id: str,
        target_version: str,
        reason: str = "rollback to previous active version",
    ) -> KnowledgeGovernanceDecision:
        return self._governance.plan_rollback(document_id=document_id, target_version=target_version, reason=reason)

    def active_chunks(
        self,
        *,
        document_id: Optional[str] = None,
        version: Optional[str] = None,
    ) -> Tuple[KnowledgeChunk, ...]:
        chunks = tuple(chunk for chunk in self._chunks if document_id is None or chunk.document_id == document_id)
        if not chunks:
            return ()
        target_version = version or latest_version(chunks)
        if target_version is None:
            return chunks
        return tuple(chunk for chunk in chunks if chunk.version == target_version)


__all__ = [
    "DEFAULT_KNOWLEDGE_CHUNKS",
    "HybridRAGOrchestrator",
]
