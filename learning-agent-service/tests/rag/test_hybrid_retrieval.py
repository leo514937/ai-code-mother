from __future__ import annotations

from types import SimpleNamespace

from learning_agent_service.rag.evidence import EvidenceGovernanceConfig, EvidenceGovernanceService
from learning_agent_service.rag.models import (
    EvidenceItem,
    KnowledgeChunk,
    RecallHit,
    RetrievalFilters,
    RetrievalPlan,
)
from learning_agent_service.rag.retrieval import (
    HeuristicDenseRetriever,
    HeuristicMetadataRetriever,
    HybridRetrieverService,
    ParentChildResolver,
    QdrantOnlineDenseRetriever,
    ReciprocalRankFusion,
)
from learning_agent_service.rag.rewrite import QueryRewriteConfig, QueryRewriteContext, QueryRewriteService


class FixedRetriever:
    def __init__(self, hits):
        self._hits = tuple(hits)

    def retrieve(self, plan):
        return self._hits


class RecordingRetriever:
    def __init__(self, route_name: str, hits):
        self.route_name = route_name
        self._hits = tuple(hits)
        self.calls: list[tuple[str, str, object]] = []

    def retrieve(self, plan):
        self.calls.append((plan.semantic_query, plan.keyword_query, plan.extra.get("query_variant")))
        return self._hits


class ConditionalRetriever:
    def __init__(self, *, match_query: str, hits):
        self.match_query = match_query
        self._hits = tuple(hits)
        self.calls: list[tuple[str, str, object]] = []

    def retrieve(self, plan):
        self.calls.append((plan.semantic_query, plan.keyword_query, plan.extra.get("query_variant")))
        if plan.extra.get("query_variant") == self.match_query or plan.keyword_query == self.match_query:
            return self._hits
        return ()


def _chunk(
    chunk_id: str,
    *,
    text: str,
    document_id: str = "doc-1",
    title: str = "title",
    version: str = "v1",
    chunk_type: str = "concept",
    parent_id: str | None = None,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        title=title,
        summary=text[:32],
        chunk_type=chunk_type,
        version=version,
        parent_id=parent_id,
        tags=("rag",),
    )


def _hit(chunk: KnowledgeChunk, *, route: str, score: float, rank: int = 1) -> RecallHit:
    return RecallHit(
        chunk=chunk,
        score=score,
        route=route,
        rank=rank,
        route_scores={route: score},
        matched_routes=(route,),
    )


def test_query_rewrite_llm_fallback_uses_structured_payload() -> None:
    calls: list[tuple[str, str]] = []

    def fake_llm(context: QueryRewriteContext, base_plan: RetrievalPlan, fallback_reason: str):
        calls.append((context.raw_query, fallback_reason))
        return {
            "semantic_query": "RAG 检索 原理",
            "keyword_query": "RAG 检索",
            "rewritten_queries": ["RAG 检索", "检索 原理"],
            "step_back_query": "什么是RAG",
            "retrieval_filters": {
                "category": ["rag"],
                "chunk_type": ["concept"],
            },
            "filter_confidence": 0.92,
        }

    service = QueryRewriteService(
        QueryRewriteConfig(llm_enabled=True, short_query_max_chars=4, low_confidence_threshold=0.5),
        llm_rewriter=fake_llm,
    )
    plan = service.rewrite_with_llm(
        QueryRewriteContext(raw_query="它", intent="explain", intent_confidence=0.12, resolved_topic="RAG"),
        fallback_reason="empty_recall",
    )

    assert calls == [("它", "empty_recall")]
    assert plan.semantic_query == "RAG 检索 原理"
    assert plan.keyword_query == "RAG 检索"
    assert plan.retrieval_filters.category == ("rag",)
    assert plan.preferred_chunk_types == ("concept", "qa", "roadmap")
    assert plan.extra["rewrite_source"] == "llm"
    assert plan.extra["metadata_filter_mode"] == "hard"


def test_hyde_generation_triggers_on_weak_query_and_returns_payload() -> None:
    calls: list[tuple[str, str]] = []

    def fake_hyde(context: QueryRewriteContext, base_plan: RetrievalPlan, trigger_reason: str):
        calls.append((context.raw_query, trigger_reason))
        return {
            "hyde_passage": "RAG retrieves evidence and grounds answers.",
            "hyde_title": "RAG retrieval",
            "hyde_keywords": ["RAG", "retrieval", "evidence"],
        }

    service = QueryRewriteService(
        QueryRewriteConfig(hyde_enabled=True, short_query_max_chars=4, low_confidence_threshold=0.5),
        hyde_rewriter=fake_hyde,
    )
    payload = service.build_hyde_payload(
        QueryRewriteContext(raw_query="它", intent="explain", intent_confidence=0.12, resolved_topic="RAG"),
    )

    assert payload is not None
    assert payload["hyde_passage"] == "RAG retrieves evidence and grounds answers."
    assert payload["hyde_source"] == "llm"
    assert payload["hyde_trigger_reason"]
    assert calls == [("它", payload["hyde_trigger_reason"])]


def test_hyde_generation_skips_when_disabled() -> None:
    calls: list[tuple[str, str]] = []

    def fake_hyde(context: QueryRewriteContext, base_plan: RetrievalPlan, trigger_reason: str):
        calls.append((context.raw_query, trigger_reason))
        return {"hyde_passage": "RAG retrieves evidence and grounds answers."}

    service = QueryRewriteService(
        QueryRewriteConfig(hyde_enabled=False, short_query_max_chars=4, low_confidence_threshold=0.5),
        hyde_rewriter=fake_hyde,
    )

    assert service.build_hyde_payload(
        QueryRewriteContext(raw_query="它", intent="explain", intent_confidence=0.12, resolved_topic="RAG"),
    ) is None
    assert calls == []


def test_hyde_generation_skips_normal_query() -> None:
    calls: list[tuple[str, str]] = []

    def fake_hyde(context: QueryRewriteContext, base_plan: RetrievalPlan, trigger_reason: str):
        calls.append((context.raw_query, trigger_reason))
        return {"hyde_passage": "RAG retrieves evidence and grounds answers."}

    service = QueryRewriteService(
        QueryRewriteConfig(hyde_enabled=True, short_query_max_chars=4, low_confidence_threshold=0.5),
        hyde_rewriter=fake_hyde,
    )

    assert service.build_hyde_payload(
        QueryRewriteContext(raw_query="RAG 检索原理是什么", intent="explain", intent_confidence=0.96, resolved_topic="RAG"),
    ) is None
    assert calls == []


def test_hybrid_service_appends_hyde_only_to_sparse_queries() -> None:
    rag = _chunk("rag-concept", text="RAG retrieves evidence and grounds answers.", title="RAG")
    hyde_passage = "RAG retrieves evidence and grounds answers."
    dense = RecordingRetriever("dense", (_hit(rag, route="dense", score=0.91, rank=1),))
    sparse = RecordingRetriever("sparse", (_hit(rag, route="sparse", score=0.82, rank=1),))
    metadata = RecordingRetriever("metadata", (_hit(rag, route="metadata", score=0.7, rank=1),))

    def fake_hyde(context: QueryRewriteContext, base_plan: RetrievalPlan, trigger_reason: str):
        return {"hyde_passage": hyde_passage, "hyde_title": "RAG retrieval"}

    rewrite_service = QueryRewriteService(
        QueryRewriteConfig(hyde_enabled=True, short_query_max_chars=4, low_confidence_threshold=0.5),
        hyde_rewriter=fake_hyde,
    )
    service = HybridRetrieverService(
        dense_retriever=dense,
        sparse_retriever=sparse,
        metadata_retriever=metadata,
        reranker=None,
        config=SimpleNamespace(rerank_top_k=2),
        fusion=ReciprocalRankFusion(),
        parent_child_resolver=ParentChildResolver((rag,)),
        rewrite_service=rewrite_service,
        hyde_enabled=True,
    )
    result = service.retrieve(
        RetrievalPlan(
            semantic_query="RAG retrieval",
            keyword_query="RAG retrieval",
            extra={
                "raw_query": "它",
                "intent": "explain",
                "intent_confidence": 0.12,
                "resolved_topic": "RAG",
            },
        )
    )

    assert result.hits
    assert any(call[1] == hyde_passage for call in sparse.calls)
    assert not any(call[2] == hyde_passage for call in dense.calls)
    assert result.debug_trace is not None
    assert result.debug_trace.metrics["hyde_applied"] is True
    assert result.debug_trace.metrics["hyde_trigger_reason"]


def test_hybrid_service_retries_with_hyde_after_empty_recall() -> None:
    rag = _chunk("rag-concept", text="RAG retrieves evidence and grounds answers.", title="RAG")
    hyde_passage = "RAG retrieves evidence and grounds answers."
    dense = FixedRetriever(())
    metadata = FixedRetriever(())
    sparse = ConditionalRetriever(match_query=hyde_passage, hits=(_hit(rag, route="sparse", score=0.82, rank=1),))

    def fake_hyde(context: QueryRewriteContext, base_plan: RetrievalPlan, trigger_reason: str):
        return {"hyde_passage": hyde_passage, "hyde_title": "RAG retrieval"}

    rewrite_service = QueryRewriteService(
        QueryRewriteConfig(hyde_enabled=True, short_query_max_chars=4, low_confidence_threshold=0.5),
        hyde_rewriter=fake_hyde,
    )
    service = HybridRetrieverService(
        dense_retriever=dense,
        sparse_retriever=sparse,
        metadata_retriever=metadata,
        reranker=None,
        config=SimpleNamespace(rerank_top_k=2),
        fusion=ReciprocalRankFusion(),
        parent_child_resolver=ParentChildResolver((rag,)),
        rewrite_service=rewrite_service,
        hyde_enabled=True,
    )
    result = service.retrieve(
        RetrievalPlan(
            semantic_query="RAG retrieval principle",
            keyword_query="RAG retrieval principle",
            extra={
                "raw_query": "RAG retrieval principle",
                "intent": "explain",
                "intent_confidence": 0.96,
            },
        )
    )

    assert result.hits
    assert result.debug_trace is not None
    assert result.debug_trace.metrics["hyde_applied"] is True
    assert result.debug_trace.metrics["retrieval_hit_count"] == len(result.hits)
    assert any(call[1] == hyde_passage for call in sparse.calls)


def test_hybrid_service_falls_back_when_hyde_payload_invalid() -> None:
    rag = _chunk("rag-concept", text="RAG retrieves evidence and grounds answers.", title="RAG")
    dense = RecordingRetriever("dense", (_hit(rag, route="dense", score=0.91, rank=1),))
    sparse = RecordingRetriever("sparse", (_hit(rag, route="sparse", score=0.82, rank=1),))
    metadata = RecordingRetriever("metadata", (_hit(rag, route="metadata", score=0.7, rank=1),))

    def fake_hyde(context: QueryRewriteContext, base_plan: RetrievalPlan, trigger_reason: str):
        return {}

    rewrite_service = QueryRewriteService(
        QueryRewriteConfig(hyde_enabled=True, short_query_max_chars=4, low_confidence_threshold=0.5),
        hyde_rewriter=fake_hyde,
    )
    service = HybridRetrieverService(
        dense_retriever=dense,
        sparse_retriever=sparse,
        metadata_retriever=metadata,
        reranker=None,
        config=SimpleNamespace(rerank_top_k=2),
        fusion=ReciprocalRankFusion(),
        parent_child_resolver=ParentChildResolver((rag,)),
        rewrite_service=rewrite_service,
        hyde_enabled=True,
    )
    result = service.retrieve(
        RetrievalPlan(
            semantic_query="RAG retrieval",
            keyword_query="RAG retrieval",
            extra={
                "raw_query": "它",
                "intent": "explain",
                "intent_confidence": 0.12,
                "resolved_topic": "RAG",
            },
        )
    )

    assert result.hits
    assert result.debug_trace is not None
    assert result.debug_trace.metrics["hyde_applied"] is False
    assert not any(call[1] == "RAG retrieves evidence and grounds answers." for call in sparse.calls)


def test_hybrid_service_records_rrf_and_rerank_trace() -> None:
    rag = _chunk("rag-concept", text="RAG retrieves evidence and grounds answers.", title="RAG")
    aop = _chunk("spring-aop", text="Spring AOP uses proxies.", title="Spring AOP", document_id="spring-aop")

    dense = FixedRetriever((_hit(rag, route="dense", score=0.91, rank=1), _hit(aop, route="dense", score=0.25, rank=2)))
    sparse = FixedRetriever((_hit(rag, route="sparse", score=0.82, rank=1),))
    metadata = FixedRetriever((_hit(rag, route="metadata", score=0.7, rank=1),))

    service = HybridRetrieverService(
        dense_retriever=dense,
        sparse_retriever=sparse,
        metadata_retriever=metadata,
        reranker=None,
        config=SimpleNamespace(rerank_top_k=2),
        fusion=ReciprocalRankFusion(),
        parent_child_resolver=ParentChildResolver((rag, aop)),
    )
    result = service.retrieve(
        RetrievalPlan(
            semantic_query="RAG retrieval",
            keyword_query="RAG retrieval",
            preferred_chunk_types=("concept",),
            extra={"raw_query": "RAG"},
        )
    )

    assert result.hits
    assert result.hits[0].rrf_score > 0
    assert result.hits[0].rerank_score is not None
    assert result.fused_hits[0].matched_routes
    assert result.debug_trace is not None
    assert result.debug_trace.reranked_hits
    assert result.debug_trace.metrics["retrieval_hit_count"] == len(result.hits)
    assert result.debug_trace.metrics["policy_snapshot"]["rerank_top_k"] == 2
    assert result.debug_trace.extra["policy_snapshot"]["rerank_top_k"] == 2


def test_multi_query_variants_participate_in_retrieval() -> None:
    rag = _chunk("rag-concept", text="RAG retrieves evidence and grounds answers.", title="RAG")
    dense = RecordingRetriever("dense", (_hit(rag, route="dense", score=0.91, rank=1),))
    sparse = RecordingRetriever("sparse", (_hit(rag, route="sparse", score=0.82, rank=1),))
    metadata = RecordingRetriever("metadata", (_hit(rag, route="metadata", score=0.7, rank=1),))

    service = HybridRetrieverService(
        dense_retriever=dense,
        sparse_retriever=sparse,
        metadata_retriever=metadata,
        reranker=None,
        config=SimpleNamespace(rerank_top_k=2),
        fusion=ReciprocalRankFusion(),
        parent_child_resolver=ParentChildResolver((rag,)),
    )
    result = service.retrieve(
        RetrievalPlan(
            semantic_query="RAG retrieval",
            keyword_query="RAG retrieval",
            step_back_query="什么是RAG",
            rewritten_queries=("RAG 检索", "检索 原理"),
            supplemental_queries=("RAG 检索",),
            extra={"raw_query": "RAG"},
        )
    )

    assert result.hits
    assert any(call[0] == "什么是RAG" for call in dense.calls)
    assert any(call[0] == "RAG 检索" for call in dense.calls)
    assert any(call[1] == "什么是RAG" for call in sparse.calls)
    assert any(call[1] == "检索 原理" for call in sparse.calls)


def test_metadata_soft_filter_does_not_mis_kill_related_chunk() -> None:
    chunk = _chunk("rag-concept", text="RAG retrieval uses evidence and grounding.", title="RAG")
    retriever = HeuristicMetadataRetriever((chunk,))

    hits = retriever.retrieve(
        RetrievalPlan(
            semantic_query="RAG retrieval",
            keyword_query="RAG retrieval",
            retrieval_filters=RetrievalFilters(category=("java",)),
            metadata_filter_mode="soft",
            extra={"raw_query": "RAG"},
        )
    )

    assert hits
    assert hits[0].chunk.chunk_id == "rag-concept"
    assert hits[0].score > 0


def test_qdrant_dense_fallback_when_adapter_missing() -> None:
    rag = _chunk("rag-concept", text="RAG retrieves evidence and grounds answers.", title="RAG")
    fallback = HeuristicDenseRetriever((rag,))
    retriever = QdrantOnlineDenseRetriever(
        client=object(),
        collection_name="knowledge_chunks",
        vector_name="embedding",
        embedding_adapter=None,
        fallback=fallback,
        enabled=True,
    )

    hits = retriever.retrieve(
        RetrievalPlan(
            semantic_query="RAG retrieval",
            keyword_query="RAG retrieval",
            extra={"raw_query": "RAG"},
        )
    )

    assert hits
    assert hits[0].chunk.chunk_id == "rag-concept"


def test_evidence_governance_records_rejected_reasons() -> None:
    good = _chunk("good", text="Stable answer about RAG.", title="Good")
    duplicate = _chunk("duplicate", text="Stable answer about RAG.", title="Dup")
    old = _chunk("old", text="Old answer about RAG.", title="Old", version="v0")
    low = _chunk("low", text="Low score answer.", title="Low")

    hits = (
        _hit(good, route="dense", score=0.92),
        _hit(duplicate, route="sparse", score=0.89),
        _hit(old, route="metadata", score=0.81),
        _hit(low, route="dense", score=0.01),
    )
    plan = RetrievalPlan(
        semantic_query="RAG",
        keyword_query="RAG",
        retrieval_filters=RetrievalFilters(version=("v1",)),
        preferred_chunk_types=("concept",),
    )
    pack = EvidenceGovernanceService(EvidenceGovernanceConfig(min_items=1, max_items=3)).evaluate(plan, hits)

    reasons = {item.rejected_reason for item in pack.rejected_items}
    assert {"duplicate", "old_version", "low_score"} <= reasons
    assert pack.debug_trace is not None
    assert pack.debug_trace.evidence_rejected


def test_parent_child_resolver_falls_back_when_parent_missing() -> None:
    parent = _chunk("parent", text="parent text", title="Parent")
    child = _chunk("child", text="child text", title="Child", parent_id="parent")
    orphan = _chunk("orphan", text="orphan text", title="Orphan", parent_id="missing-parent")

    resolver = ParentChildResolver((parent, child, orphan))
    assert resolver.resolve_chunk(child).chunk_id == "parent"
    assert resolver.resolve_chunk(orphan) is orphan


def test_parent_child_citation_traces_child() -> None:
    parent = _chunk("parent", text="parent text about RAG", title="Parent")
    child = _chunk("child", text="child text about RAG grounding", title="Child", parent_id="parent")

    dense = FixedRetriever((_hit(child, route="dense", score=0.95),))
    service = HybridRetrieverService(
        dense_retriever=dense,
        sparse_retriever=FixedRetriever(()),
        metadata_retriever=FixedRetriever(()),
        reranker=None,
        config=SimpleNamespace(rerank_top_k=1),
        fusion=ReciprocalRankFusion(),
        parent_child_resolver=ParentChildResolver((parent, child)),
    )
    result = service.retrieve(
        RetrievalPlan(
            semantic_query="RAG grounding",
            keyword_query="RAG grounding",
            extra={"raw_query": "RAG grounding"},
        )
    )

    pack = EvidenceGovernanceService(EvidenceGovernanceConfig(min_items=1, max_items=1)).evaluate(
        RetrievalPlan(
            semantic_query="RAG grounding",
            keyword_query="RAG grounding",
            extra={"raw_query": "RAG grounding"},
        ),
        result.reranked_hits,
    )

    assert pack.items
    assert pack.items[0].chunk.chunk_id == "parent"
    assert pack.items[0].citation_chunk_id == "child"
