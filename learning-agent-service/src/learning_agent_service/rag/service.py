from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from learning_agent_service.config import Settings
from learning_agent_service.domain import (
    ChatTurnCommand,
    Citation,
    EvidenceItem,
    EvidencePack,
    GraphRuntimeMeta,
    GraphState,
    HybridRecallCandidate,
    HybridRecallResult as DomainHybridRecallResult,
    PersistentSessionContext,
    RagResult,
    ReferenceResolutionResult,
    RetrievalPlan,
    TurnRuntimeState,
    TurnUnderstandingResult,
    WorkflowErrorCode,
    build_error,
)
from learning_agent_service.domain.enums import IntentType, OutputStyle, RagStatus, TurnDecision

from .citation import CitationBuilder
from .evidence import EvidenceGovernanceConfig, EvidenceGovernanceService
from .governance import GovernanceConfig, KnowledgeGovernanceService
from .hybrid import (
    HybridRetrieverConfig,
    HybridRetrieverService,
    InMemoryReranker,
    InMemoryTokenRetriever,
)
from .models import Citation as InternalCitation
from .models import EvidenceItem as InternalEvidenceItem
from .models import EvidencePack as InternalEvidencePack
from .models import KnowledgeChunk, KnowledgeGovernanceDecision, RecallHit, RetrievalFilters
from .models import RetrievalPlan as InternalRetrievalPlan
from .models import latest_version
from .protocols import DenseRetriever, HybridRetriever, MetadataRetriever, Reranker, SparseRetriever
from .rewrite import QueryRewriteContext, QueryRewriteService

_CN_INTERVIEW = "\u9762\u8bd5"
_CN_COMPARE = "\u533a\u522b"
_CN_BRIEF = "\u7b80\u5355"
_CN_QUIZ = "\u51fa\u9898"
_CN_STUDY_PLAN = "\u5b66\u4e60\u8def\u7ebf"
_CN_NEXT_TOPIC = "\u63a5\u4e0b\u6765\u5b66"
_CN_CODE = "\u4ee3\u7801"
_CN_SUMMARY = "\u603b\u7ed3"
_CN_ROUTE = "\u8def\u7ebf"
_CN_PLAN = "\u89c4\u5212"
_CN_REVIEW = "\u590d\u4e60"
_CN_QUESTION = "\u9898"
_CN_EXPLAIN = "\u7406\u89e3"
_CN_HOW = "\u600e\u4e48"
_CN_THIS = "\u8fd9\u4e2a"
_CN_THAT = "\u90a3\u4e2a"
_CN_PREVIOUS = "\u4e0a\u4e00\u4e2a"
_CN_IT = "\u5b83"

_QUIZ_COUNT_PATTERN = re.compile(r"(\d+|[一二三四五六七八九十两]+)\s*道?.{0,3}\u9898")


def _optional_str(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)

_DEFAULT_ROWS: Tuple[Dict[str, Any], ...] = (
    {
        "chunk_id": "java-threadpool-concept",
        "document_id": "java-threadpool",
        "title": "Java ThreadPool",
        "category": "java",
        "subcategory": "concurrency",
        "chunk_type": "concept",
        "source_type": "document",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("threadpool", "threadpoolexecutor", "corepoolsize"),
        "text": "ThreadPoolExecutor reuses threads and controls throughput with pool size, queue, and rejection policies.",
    },
    {
        "chunk_id": "java-threadpool-interview",
        "document_id": "java-threadpool",
        "title": "Java ThreadPool Interview",
        "category": "java",
        "subcategory": "concurrency",
        "chunk_type": "interview_template",
        "source_type": "interview",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("threadpool", "interview", "rejection"),
        "text": "Answer thread pool questions with purpose, key parameters, execution flow, rejection policy, and tuning tradeoffs.",
    },
    {
        "chunk_id": "spring-aop-concept",
        "document_id": "spring-aop",
        "title": "Spring AOP",
        "category": "java",
        "subcategory": "spring",
        "chunk_type": "concept",
        "source_type": "document",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("aop", "dynamic_proxy", "advice"),
        "text": "Spring AOP applies cross-cutting logic through proxies and centers on advice, pointcuts, join points, and aspects.",
    },
    {
        "chunk_id": "spring-aop-compare",
        "document_id": "spring-aop",
        "title": "Spring AOP vs Dynamic Proxy",
        "category": "java",
        "subcategory": "spring",
        "chunk_type": "comparison",
        "source_type": "faq",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("aop", "jdk_proxy", "cglib"),
        "text": "Spring AOP is a framework abstraction built on dynamic proxy techniques. JDK proxies require interfaces, while CGLIB subclasses concrete classes.",
    },
    {
        "chunk_id": "react-cot-compare",
        "document_id": "agent-reasoning",
        "title": "ReAct vs CoT",
        "category": "agent",
        "subcategory": "reasoning",
        "chunk_type": "comparison",
        "source_type": "document",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("react", "cot", "agent"),
        "text": "CoT emphasizes reasoning steps, while ReAct alternates reasoning and actions, which is more practical for tool-driven agents.",
    },
    {
        "chunk_id": "react-agent-interview",
        "document_id": "agent-react",
        "title": "Agent ReAct Interview",
        "category": "agent",
        "subcategory": "tool_use",
        "chunk_type": "interview_template",
        "source_type": "interview",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("react", "agent", "interview"),
        "text": "In interviews, explain that ReAct helps an agent decide whether to think, retrieve, or call a tool at each step.",
    },
    {
        "chunk_id": "langgraph-concept",
        "document_id": "langgraph",
        "title": "LangGraph",
        "category": "agent",
        "subcategory": "workflow",
        "chunk_type": "concept",
        "source_type": "document",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("langgraph", "state_machine", "workflow"),
        "text": "LangGraph models agent flows as explicit state transitions with branches, retries, and human-in-the-loop checkpoints.",
    },
    {
        "chunk_id": "langchain-langgraph-compare",
        "document_id": "langgraph",
        "title": "LangChain vs LangGraph",
        "category": "agent",
        "subcategory": "framework",
        "chunk_type": "comparison",
        "source_type": "faq",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("langchain", "langgraph", "compare"),
        "text": "LangChain focuses on reusable components and chains, while LangGraph focuses on explicit workflow control and durable state.",
    },
    {
        "chunk_id": "rag-concept",
        "document_id": "agent-rag",
        "title": "RAG",
        "category": "rag",
        "subcategory": "retrieval",
        "chunk_type": "concept",
        "source_type": "document",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("rag", "retrieval", "grounding"),
        "text": "RAG retrieves external evidence and injects it into generation so answers stay closer to the knowledge base.",
    },
    {
        "chunk_id": "tool-use-concept",
        "document_id": "agent-tool-use",
        "title": "Agent Tool Use",
        "category": "agent",
        "subcategory": "tool_use",
        "chunk_type": "concept",
        "source_type": "document",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ("tool_use", "function_calling", "agent"),
        "text": "Agents need tool use when they must fetch fresh knowledge, take actions, or interact with systems outside model weights.",
    },
)


def _build_default_chunks(rows: Sequence[Mapping[str, Any]] = _DEFAULT_ROWS) -> Tuple[KnowledgeChunk, ...]:
    return tuple(
        KnowledgeChunk(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            text=str(row["text"]),
            title=str(row.get("title") or row["chunk_id"]),
            category=_optional_str(row.get("category")),
            subcategory=_optional_str(row.get("subcategory")),
            difficulty=_optional_str(row.get("difficulty")),
            source_type=_optional_str(row.get("source_type")),
            chunk_type=_optional_str(row.get("chunk_type")),
            version=_optional_str(row.get("version")),
            tags=tuple(str(tag) for tag in row.get("tags", ()) if tag),
            metadata=dict(row.get("metadata", {})),
        )
        for row in rows
    )


DEFAULT_KNOWLEDGE_CHUNKS: Tuple[KnowledgeChunk, ...] = _build_default_chunks()


@dataclass
class HeuristicModelGateway:
    def classify_turn(self, command: ChatTurnCommand, state: GraphState) -> TurnUnderstandingResult:
        message = command.message.strip()
        lowered = message.lower()
        chinese_plan = any(token in message for token in (_CN_STUDY_PLAN, _CN_ROUTE, _CN_PLAN, _CN_REVIEW, "\u8ba1\u5212"))
        chinese_quiz = any(token in message for token in (_CN_QUIZ, _CN_QUESTION, "\u5237\u9898", "\u81ea\u6d4b", "\u6d4b\u6211"))
        chinese_follow_up = _looks_like_follow_up_query(message, lowered, state["persistent"])

        style = command.response_mode
        if style is None:
            if "interview" in lowered or _CN_INTERVIEW in message:
                style = OutputStyle.INTERVIEW
            elif any(token in lowered for token in ("compare", "difference", "vs")) or _CN_COMPARE in message:
                style = OutputStyle.COMPARISON
            elif any(token in lowered for token in ("brief", "simple")) or _CN_BRIEF in message:
                style = OutputStyle.BRIEF
            else:
                style = OutputStyle.DETAILED

        intent = IntentType.EXPLAIN
        confidence = 0.72
        if any(token in lowered for token in ("quiz", "question", "test me")) or chinese_quiz or _QUIZ_COUNT_PATTERN.search(message):
            intent = IntentType.QUIZ
            confidence = 0.90
        elif any(token in lowered for token in ("study plan", "roadmap", "review plan")) or chinese_plan:
            intent = IntentType.STUDY_PLAN
            confidence = 0.90
        elif any(token in lowered for token in ("next topic", "next step")) or _CN_NEXT_TOPIC in message:
            intent = IntentType.RECOMMEND
            confidence = 0.86
        elif any(token in lowered for token in ("difference", "compare", "vs")) or _CN_COMPARE in message:
            intent = IntentType.COMPARE
            confidence = 0.88
        elif "interview" in lowered or _CN_INTERVIEW in message:
            intent = IntentType.INTERVIEW
            confidence = 0.87
        elif any(token in lowered for token in ("code", "example", "demo")) or _CN_CODE in message:
            intent = IntentType.CODE
            confidence = 0.84
        elif any(token in lowered for token in ("summary", "recap")) or _CN_SUMMARY in message:
            intent = IntentType.SUMMARY
            confidence = 0.82
        elif chinese_follow_up:
            intent = IntentType.FOLLOW_UP
            confidence = 0.58 if state["persistent"].recent_entities else 0.42

        decision = TurnDecision.DIRECT_ANSWER
        if intent in {IntentType.QUIZ, IntentType.STUDY_PLAN, IntentType.RECOMMEND}:
            decision = TurnDecision.TOOL_THEN_ANSWER
        elif intent in {
            IntentType.EXPLAIN,
            IntentType.COMPARE,
            IntentType.INTERVIEW,
            IntentType.CODE,
            IntentType.SUMMARY,
            IntentType.FOLLOW_UP,
        }:
            decision = TurnDecision.RETRIEVE_THEN_ANSWER

        return TurnUnderstandingResult(
            decision=decision,
            intent=intent,
            intent_confidence=confidence,
            requested_output_style=style,
            slots={
                "topic_hint": command.topic_hint,
                "question_type": intent.value,
                "requested_style": style.value if style else None,
            },
        )


class HybridRAGOrchestrator:
    """Thin adapter over the canonical rewrite/hybrid/evidence/citation modules."""

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
    ) -> None:
        self.settings = settings
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

    @classmethod
    def from_runtime_components(
        cls,
        settings: Settings,
        *,
        rewrite_service: Optional[QueryRewriteService] = None,
        dense_retriever: Optional[DenseRetriever] = None,
        sparse_retriever: Optional[SparseRetriever] = None,
        metadata_retriever: Optional[MetadataRetriever] = None,
        reranker: Optional[Reranker] = None,
        hybrid_retriever: Optional[HybridRetriever] = None,
        evidence_service: Optional[EvidenceGovernanceService] = None,
        citation_builder: Optional[CitationBuilder] = None,
        governance_service: Optional[KnowledgeGovernanceService] = None,
        knowledge_chunks: Optional[Iterable[KnowledgeChunk]] = None,
    ) -> "HybridRAGOrchestrator":
        return cls(
            settings=settings,
            knowledge_chunks=knowledge_chunks,
            rewrite_service=rewrite_service,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
            metadata_retriever=metadata_retriever,
            reranker=reranker,
            hybrid_retriever=hybrid_retriever,
            evidence_service=evidence_service,
            citation_builder=citation_builder,
            governance_service=governance_service,
        )

    @property
    def knowledge_chunks(self) -> Tuple[KnowledgeChunk, ...]:
        return self._chunks

    def rewrite_query(self, state: GraphState) -> RetrievalPlan:
        turn = state["turn"]
        context = QueryRewriteContext(
            raw_query=turn.raw_query,
            intent=self._intent_value(turn.intent, turn.understanding_result),
            resolved_topic=turn.reference_resolution.resolved_entity if turn.reference_resolution else None,
            session_topic=state["persistent"].current_topic or state["runtime"].topic_hint,
            requested_output_style=self._style_value(turn.requested_output_style, turn.understanding_result),
            filters=self._to_internal_filters(turn.retrieval_plan.retrieval_filters if turn.retrieval_plan else {}),
            user_preferences=state["persistent"].user_preferences,
            extra={
                "history_summary": state["persistent"].history_summary or state["runtime"].history_summary,
                "pending_clarification": (
                    state["persistent"].pending_clarification.model_dump(mode="json")
                    if state["persistent"].pending_clarification
                    else None
                ),
            },
        )
        internal_plan = self._rewrite.build_plan(context)
        return self._to_domain_plan(internal_plan)

    def resolve_reference(self, state: GraphState) -> ReferenceResolutionResult:
        turn = state["turn"]
        persistent = state["persistent"]
        message = turn.raw_query.strip()
        lowered = message.lower()
        candidates = self._reference_candidates(persistent)

        if _contains_reference_token(message, lowered):
            if candidates:
                return ReferenceResolutionResult(
                    resolved=True,
                    confidence=0.76,
                    resolved_entity=candidates[0],
                    candidate_entities=candidates[:3],
                )
            return ReferenceResolutionResult(resolved=False, confidence=0.24, candidate_entities=[])

        if turn.intent == IntentType.FOLLOW_UP and persistent.current_topic:
            return ReferenceResolutionResult(
                resolved=True,
                confidence=0.61,
                resolved_entity=persistent.current_topic,
                candidate_entities=candidates[:3],
            )

        return ReferenceResolutionResult(
            resolved=False,
            confidence=0.0,
            candidate_entities=candidates[:3],
        )

    def hybrid_retrieve(self, state: GraphState) -> DomainHybridRecallResult:
        domain_plan = state["turn"].retrieval_plan or self.rewrite_query(state)
        internal_plan = self._to_internal_plan(domain_plan)
        route_hits = self._collect_route_hits(internal_plan)
        fused_hits = self._rrf_merge(route_hits)
        recall = self._retriever.retrieve(internal_plan)
        metrics = dict(recall.metrics)
        metrics["fused_hit_count"] = len(fused_hits)
        return DomainHybridRecallResult(
            dense_hits=self._to_domain_candidates(route_hits.get("dense", ())),
            sparse_hits=self._to_domain_candidates(route_hits.get("sparse", ())),
            metadata_hits=self._to_domain_candidates(route_hits.get("metadata", ())),
            fused_hits=self._to_domain_candidates(fused_hits),
            reranked_hits=self._to_domain_candidates(recall.hits),
            metrics=metrics,
            extra={
                "retrieval_strategy": recall.retrieval_strategy,
                "degraded_routes": list(recall.degraded_routes),
                "query_plan": domain_plan.model_dump(mode="json"),
            },
        )

    def evaluate_evidence(self, state: GraphState) -> EvidencePack:
        domain_plan = state["turn"].retrieval_plan or self.rewrite_query(state)
        internal_plan = self._to_internal_plan(domain_plan)
        hybrid = state["turn"].hybrid_recall
        internal_hits = self._to_internal_hits(hybrid.reranked_hits if hybrid else ())
        if not internal_hits:
            internal_hits = tuple(self._retriever.retrieve(internal_plan).hits)
        internal_pack = self._evidence.evaluate(internal_plan, internal_hits)
        return self._to_domain_evidence_pack(internal_pack, domain_plan)

    def build_citations(self, state: GraphState) -> Iterable[Citation]:
        evidence = state["turn"].evidence_pack
        if evidence is None:
            return []
        return self.build_citations_from_pack(evidence)

    def build_citations_from_pack(self, evidence: EvidencePack) -> Iterable[Citation]:
        internal_pack = self._to_internal_evidence_pack(evidence)
        citations = self._citation_builder.build(internal_pack)
        return [self._to_domain_citation(item) for item in citations]

    def search_knowledge(self, topic: str, limit: int = 5, category: Optional[str] = None) -> Dict[str, Any]:
        state = self._stub_state(topic=topic, category=category)
        plan = self.rewrite_query(state)
        state["turn"] = state["turn"].model_copy(update={"retrieval_plan": plan})
        hybrid = self.hybrid_retrieve(state)
        state["turn"] = state["turn"].model_copy(update={"hybrid_recall": hybrid})
        evidence = self.evaluate_evidence(state)
        citations = list(self.build_citations_from_pack(evidence))
        citation_map = {citation.chunk_id: citation for citation in citations}

        matches: List[Dict[str, Any]] = []
        for item in evidence.items[: max(limit, 0)]:
            citation = citation_map.get(item.chunk_id)
            matches.append(
                {
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                    "title": item.metadata.get("title"),
                    "score": item.score,
                    "content": item.content,
                    "chunk_type": item.chunk_type,
                    "category": item.metadata.get("category"),
                    "subcategory": item.metadata.get("subcategory"),
                    "source_type": item.metadata.get("source_type"),
                    "version": item.metadata.get("version"),
                    "citation": citation.model_dump(mode="json") if citation else None,
                }
            )
        return {
            "topic": topic,
            "retrieval_strategy": self._retrieval_strategy(hybrid),
            "matches": matches,
            "metrics": {
                "retrieval_hit_count": int(hybrid.metrics.get("retrieval_hit_count", len(hybrid.reranked_hits))),
                "evidence_used_count": len(evidence.items),
            },
        }

    def get_knowledge_detail(self, topic: str) -> Dict[str, Any]:
        result = self.search_knowledge(topic, limit=1)
        detail = result["matches"][0] if result["matches"] else None
        return {
            "topic": topic,
            "detail": detail,
            "retrieval_strategy": result["retrieval_strategy"],
            "metrics": result["metrics"],
        }

    def run(self, state: GraphState) -> RagResult:
        plan = state["turn"].retrieval_plan or self.rewrite_query(state)
        state["turn"] = state["turn"].model_copy(update={"retrieval_plan": plan})

        hybrid = state["turn"].hybrid_recall or self.hybrid_retrieve(state)
        state["turn"] = state["turn"].model_copy(update={"hybrid_recall": hybrid})

        evidence = state["turn"].evidence_pack or self.evaluate_evidence(state)
        citations = list(self.build_citations_from_pack(evidence))
        state["turn"] = state["turn"].model_copy(update={"evidence_pack": evidence, "citations": citations})

        metrics = dict(hybrid.metrics)
        metrics.update(dict(evidence.extra.get("metrics", {})))
        metrics.setdefault("retrieval_hit_count", len(hybrid.reranked_hits))
        metrics.setdefault("retrieval_top_score", hybrid.metrics.get("retrieval_top_score", 0.0))
        metrics["evidence_used_count"] = len(evidence.items)

        status = RagStatus.EMPTY
        if evidence.items:
            status = RagStatus.OK if len(evidence.items) >= self.settings.evidence_min_n else RagStatus.DEGRADED

        if not hybrid.reranked_hits:
            state["runtime"].errors.append(
                build_error(
                    WorkflowErrorCode.KNOWLEDGE_NOT_FOUND,
                    stage="hybrid_retrieve",
                    message="Hybrid retrieval returned no matching knowledge chunks.",
                    retryable=True,
                    degraded_to="rewrite_and_retry_once",
                )
            )
        elif not evidence.items:
            state["runtime"].errors.append(
                build_error(
                    WorkflowErrorCode.EVIDENCE_INSUFFICIENT,
                    stage="evaluate_evidence",
                    message="No stable evidence survived the governance pipeline.",
                    retryable=False,
                    degraded_to="direct_answer_lite",
                )
            )

        return RagResult(
            status=status,
            evidence_pack=evidence,
            citations=citations,
            retrieval_strategy=self._retrieval_strategy(hybrid),
            metrics=metrics,
            extra={"hybrid_recall": hybrid.model_dump(mode="json")},
        )

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

    def _stub_state(self, *, topic: str, category: Optional[str] = None) -> GraphState:
        persistent = PersistentSessionContext(current_topic=topic, recent_entities=[topic])
        turn = TurnRuntimeState(
            raw_query=topic,
            intent=IntentType.EXPLAIN,
            requested_output_style=OutputStyle.DETAILED,
            retrieval_plan=RetrievalPlan(
                semantic_query=topic,
                keyword_query=topic,
                retrieval_filters={"category": [category]} if category else {},
            ),
        )
        runtime = GraphRuntimeMeta(
            trace_id="rag-stub-trace",
            session_id="rag-stub-session",
            turn_id="rag-stub-turn",
            workflow_version=self.settings.workflow_version,
            request_ts=datetime.now(timezone.utc),
            user_id="rag-stub-user",
        )
        return {"persistent": persistent, "turn": turn, "runtime": runtime}

    def _reference_candidates(self, persistent: PersistentSessionContext) -> List[str]:
        candidates: List[str] = []
        if persistent.pending_clarification is not None:
            for option in persistent.pending_clarification.options:
                if option.value:
                    candidates.append(option.value)
                elif option.label:
                    candidates.append(option.label)
        if persistent.clarification_result:
            selected = persistent.clarification_result.get("selected_topic") or persistent.clarification_result.get("value")
            if selected:
                candidates.append(str(selected))
        if persistent.current_topic:
            candidates.append(persistent.current_topic)
        if persistent.last_retrieval_topic:
            candidates.append(persistent.last_retrieval_topic)
        candidates.extend(persistent.recent_entities)
        return _unique(candidates)

    def _collect_route_hits(self, plan: InternalRetrievalPlan) -> Dict[str, Tuple[RecallHit, ...]]:
        route_hits: Dict[str, Tuple[RecallHit, ...]] = {}
        for route_name, retriever in (
            ("dense", self._dense_retriever),
            ("sparse", self._sparse_retriever),
            ("metadata", self._metadata_retriever),
        ):
            try:
                route_hits[route_name] = tuple(retriever.retrieve(plan))
            except Exception:
                route_hits[route_name] = ()
        return route_hits

    def _rrf_merge(self, route_hits: Mapping[str, Sequence[RecallHit]]) -> Tuple[RecallHit, ...]:
        merge = getattr(self._retriever, "_rrf_merge", None)
        if callable(merge):
            return tuple(merge(route_hits))

        fused_scores: Dict[str, float] = {}
        base_hits: Dict[str, RecallHit] = {}
        route_scores: Dict[str, Dict[str, float]] = {}
        for route_name, hits in route_hits.items():
            for rank, hit in enumerate(hits, start=1):
                chunk_id = hit.chunk.chunk_id
                fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / float(self.settings.rrf_k + rank)
                base_hits.setdefault(chunk_id, hit)
                route_scores.setdefault(chunk_id, {})[route_name] = hit.score

        if not fused_scores:
            return ()

        max_score = max(fused_scores.values())
        merged: List[RecallHit] = []
        for index, (chunk_id, fused_score) in enumerate(
            sorted(fused_scores.items(), key=lambda item: item[1], reverse=True),
            start=1,
        ):
            base = base_hits[chunk_id]
            merged.append(
                RecallHit(
                    chunk=base.chunk,
                    score=fused_score / max_score if max_score else 0.0,
                    route="hybrid",
                    rank=index,
                    route_scores=dict(route_scores.get(chunk_id, {})),
                    metadata={"source_routes": tuple(sorted(route_scores.get(chunk_id, {})))},
                )
            )
        return tuple(merged)

    def _to_domain_candidates(self, hits: Iterable[RecallHit]) -> List[HybridRecallCandidate]:
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

    def _to_internal_hits(self, candidates: Iterable[HybridRecallCandidate]) -> Tuple[RecallHit, ...]:
        hits: List[RecallHit] = []
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
                        category=_optional_str(metadata.get("category")),
                        subcategory=_optional_str(metadata.get("subcategory")),
                        difficulty=_optional_str(metadata.get("difficulty")),
                        source_type=_optional_str(metadata.get("source_type")),
                        chunk_type=_optional_str(candidate.chunk_type),
                        version=_optional_str(metadata.get("version")),
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

    def _to_domain_evidence_pack(
        self,
        internal_pack: InternalEvidencePack,
        plan: RetrievalPlan,
    ) -> EvidencePack:
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
                for item in internal_pack.items
            ],
            discard_summary={
                "status": internal_pack.status,
                "filtered_out": internal_pack.filtered_out,
                "rationale": list(internal_pack.rationale),
            },
            top_scores=[item.score for item in internal_pack.items],
            extra={
                "metrics": dict(internal_pack.metrics),
                "query_plan": plan.model_dump(mode="json"),
            },
        )

    def _to_internal_evidence_pack(self, evidence: EvidencePack) -> InternalEvidencePack:
        return InternalEvidencePack(
            items=tuple(
                InternalEvidenceItem(
                    chunk=KnowledgeChunk(
                        chunk_id=item.chunk_id,
                        document_id=item.document_id or "unknown-document",
                        text=item.content,
                        title=str(item.metadata.get("title") or item.chunk_id),
                        category=_optional_str(item.metadata.get("category")),
                        subcategory=_optional_str(item.metadata.get("subcategory")),
                        difficulty=_optional_str(item.metadata.get("difficulty")),
                        source_type=_optional_str(item.metadata.get("source_type")),
                        chunk_type=_optional_str(item.chunk_type),
                        version=_optional_str(item.metadata.get("version")),
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

    def _to_domain_plan(self, plan: InternalRetrievalPlan) -> RetrievalPlan:
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

    def _to_internal_plan(self, plan: RetrievalPlan) -> InternalRetrievalPlan:
        return InternalRetrievalPlan(
            semantic_query=plan.semantic_query,
            keyword_query=plan.keyword_query,
            retrieval_filters=self._to_internal_filters(plan.retrieval_filters),
            preferred_chunk_types=tuple(plan.preferred_chunk_types),
            dense_top_k=self.settings.dense_top_k,
            sparse_top_k=self.settings.sparse_top_k,
            metadata_top_k=self.settings.metadata_top_k,
            rerank_top_k=self.settings.rerank_top_k,
            max_evidence=self.settings.evidence_top_n,
            extra=dict(plan.extra),
        )

    def _to_domain_citation(self, citation: InternalCitation) -> Citation:
        return Citation(
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            source_type=citation.source_type,
            version=citation.version,
            score=citation.score,
            title=citation.title,
            locator=str(citation.metadata.get("chunk_type") or ""),
        )

    @staticmethod
    def _to_internal_filters(raw_filters: Mapping[str, Any]) -> RetrievalFilters:
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
    def _intent_value(intent: Optional[IntentType], understanding: Optional[TurnUnderstandingResult]) -> Optional[str]:
        if intent is not None:
            return intent.value
        if understanding is not None and understanding.intent is not None:
            return understanding.intent.value
        return None

    @staticmethod
    def _style_value(style: Optional[OutputStyle], understanding: Optional[TurnUnderstandingResult]) -> Optional[str]:
        if style is not None:
            return style.value
        if understanding is not None and understanding.requested_output_style is not None:
            return understanding.requested_output_style.value
        return None

    @staticmethod
    def _retrieval_strategy(hybrid: DomainHybridRecallResult) -> str:
        strategy = hybrid.extra.get("retrieval_strategy")
        if isinstance(strategy, str) and strategy:
            return strategy if strategy.endswith("->evidence") else strategy + "->evidence"
        return "dense+sparse+metadata->rrf->rerank->evidence"


def _contains_reference_token(message: str, lowered: str) -> bool:
    return any(token in lowered for token in ("this", "that", "previous", "it")) or any(
        token in message for token in (_CN_THIS, _CN_THAT, _CN_PREVIOUS, _CN_IT)
    )


def _looks_like_follow_up_query(message: str, lowered: str, persistent: PersistentSessionContext) -> bool:
    if _contains_reference_token(message, lowered):
        return True
    if not (persistent.current_topic or persistent.recent_entities or persistent.last_retrieval_topic):
        return False
    short_follow_up = len(message) <= 14 and any(token in message for token in (_CN_EXPLAIN, _CN_HOW, _CN_COMPARE))
    return short_follow_up


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
