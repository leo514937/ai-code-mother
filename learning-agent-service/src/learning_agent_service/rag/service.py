from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from learning_agent_service.config import Settings
from learning_agent_service.domain import (
    ChatTurnCommand,
    Citation,
    EvidenceItem,
    EvidencePack,
    GraphState,
    RagResult,
    ReferenceResolutionResult,
    RetrievalPlan,
    TurnUnderstandingResult,
    WorkflowErrorCode,
    build_error,
)
from learning_agent_service.domain.enums import IntentType, OutputStyle, RagStatus, TurnDecision

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-]+")

MOCK_KNOWLEDGE_BASE: List[Dict[str, Any]] = [
    {
        "chunk_id": "java-threadpool-concept",
        "topic": "Java ThreadPool",
        "category": "Java",
        "subcategory": "Concurrency",
        "chunk_type": "concept",
        "source_type": "doc",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["threadpool", "ThreadPoolExecutor", "corePoolSize"],
        "content": "ThreadPoolExecutor reuses threads and controls throughput with pool size, queue, and rejection policies.",
    },
    {
        "chunk_id": "java-threadpool-interview",
        "topic": "Java ThreadPool",
        "category": "Java",
        "subcategory": "Concurrency",
        "chunk_type": "interview_template",
        "source_type": "interview_template",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["threadpool", "interview", "rejection"],
        "content": "Answer thread pool questions with purpose, key parameters, execution flow, rejection policy, and tuning tradeoffs.",
    },
    {
        "chunk_id": "spring-aop-concept",
        "topic": "Spring AOP",
        "category": "Spring",
        "subcategory": "AOP",
        "chunk_type": "concept",
        "source_type": "doc",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["AOP", "dynamic proxy", "advice"],
        "content": "Spring AOP applies cross-cutting logic through proxies and centers on advice, pointcuts, join points, and aspects.",
    },
    {
        "chunk_id": "spring-aop-compare",
        "topic": "Spring AOP vs Dynamic Proxy",
        "category": "Spring",
        "subcategory": "AOP",
        "chunk_type": "comparison",
        "source_type": "qa",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["AOP", "JDK proxy", "CGLIB"],
        "content": "Spring AOP is a framework abstraction built on dynamic proxy techniques. JDK proxies require interfaces, while CGLIB subclasses concrete classes.",
    },
    {
        "chunk_id": "react-cot-compare",
        "topic": "ReAct vs CoT",
        "category": "Agent",
        "subcategory": "Reasoning",
        "chunk_type": "comparison",
        "source_type": "doc",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["ReAct", "CoT", "Agent"],
        "content": "CoT emphasizes reasoning steps, while ReAct alternates reasoning and actions, which is more practical for tool-driven agents.",
    },
    {
        "chunk_id": "react-agent-interview",
        "topic": "Agent ReAct",
        "category": "Agent",
        "subcategory": "Tool Use",
        "chunk_type": "interview_template",
        "source_type": "interview_template",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["ReAct", "Agent", "interview"],
        "content": "In interviews, explain that ReAct helps an agent decide whether to think, retrieve, or call a tool at each step.",
    },
    {
        "chunk_id": "langgraph-concept",
        "topic": "LangGraph",
        "category": "Agent",
        "subcategory": "Workflow",
        "chunk_type": "concept",
        "source_type": "doc",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["LangGraph", "state machine", "workflow"],
        "content": "LangGraph models agent flows as explicit state transitions with branches, retries, and human-in-the-loop checkpoints.",
    },
    {
        "chunk_id": "langchain-langgraph-compare",
        "topic": "LangChain vs LangGraph",
        "category": "Agent",
        "subcategory": "Framework",
        "chunk_type": "comparison",
        "source_type": "qa",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["LangChain", "LangGraph", "compare"],
        "content": "LangChain focuses on reusable components and chains, while LangGraph focuses on explicit workflow control and durable state.",
    },
    {
        "chunk_id": "rag-concept",
        "topic": "RAG",
        "category": "Agent",
        "subcategory": "Retrieval",
        "chunk_type": "concept",
        "source_type": "doc",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["RAG", "retrieval", "grounding"],
        "content": "RAG retrieves external evidence and injects it into generation so answers stay closer to the knowledge base.",
    },
    {
        "chunk_id": "tool-use-concept",
        "topic": "Tool Use",
        "category": "Agent",
        "subcategory": "Tool Calling",
        "chunk_type": "concept",
        "source_type": "doc",
        "version": "v1",
        "difficulty": "intermediate",
        "tags": ["tool use", "function calling", "agent"],
        "content": "Agents need tool use for fresh knowledge, side effects, and environment interaction that cannot be solved from model weights alone.",
    },
]


@dataclass
class HeuristicModelGateway:
    def classify_turn(self, command: ChatTurnCommand, state: GraphState) -> TurnUnderstandingResult:
        message = command.message.strip()
        lowered = message.lower()
        intent = IntentType.EXPLAIN
        confidence = 0.72
        style = command.response_mode
        if style is None:
            if "interview" in lowered:
                style = OutputStyle.INTERVIEW
            elif any(keyword in lowered for keyword in ["compare", "difference", "vs"]):
                style = OutputStyle.COMPARISON
            elif any(keyword in lowered for keyword in ["brief", "simple"]):
                style = OutputStyle.BRIEF
            else:
                style = OutputStyle.DETAILED

        if any(keyword in lowered for keyword in ["quiz", "question", "test me"]):
            intent = IntentType.QUIZ
            confidence = 0.9
        elif any(keyword in lowered for keyword in ["study plan", "plan", "roadmap"]):
            intent = IntentType.STUDY_PLAN
            confidence = 0.9
        elif any(keyword in lowered for keyword in ["next topic", "what next", "next step"]):
            intent = IntentType.RECOMMEND
            confidence = 0.86
        elif any(keyword in lowered for keyword in ["difference", "compare", "vs"]):
            intent = IntentType.COMPARE
            confidence = 0.88
        elif any(keyword in lowered for keyword in ["interview"]):
            intent = IntentType.INTERVIEW
            confidence = 0.87
        elif any(keyword in lowered for keyword in ["code", "example", "demo"]):
            intent = IntentType.CODE
            confidence = 0.84
        elif any(keyword in lowered for keyword in ["summary", "recap"]):
            intent = IntentType.SUMMARY
            confidence = 0.82
        elif any(keyword in lowered for keyword in ["this", "that", "previous", "it"]):
            intent = IntentType.FOLLOW_UP
            confidence = 0.58 if state["persistent"].recent_entities else 0.42

        need_tool = intent in {IntentType.QUIZ, IntentType.STUDY_PLAN, IntentType.RECOMMEND}
        need_rag = intent in {
            IntentType.EXPLAIN,
            IntentType.COMPARE,
            IntentType.INTERVIEW,
            IntentType.CODE,
            IntentType.SUMMARY,
            IntentType.FOLLOW_UP,
        }
        decision = TurnDecision.DIRECT_ANSWER
        if need_tool:
            decision = TurnDecision.TOOL_THEN_ANSWER
        elif need_rag:
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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def rewrite_query(self, state: GraphState) -> RetrievalPlan:
        turn = state["turn"]
        persistent = state["persistent"]
        understanding = turn.understanding_result
        resolved_entity = None
        if understanding and understanding.reference_resolution and understanding.reference_resolution.resolved:
            resolved_entity = understanding.reference_resolution.resolved_entity
        base_query = resolved_entity or persistent.current_topic or turn.raw_query.strip()
        intent = understanding.intent if understanding else IntentType.EXPLAIN
        preferred_chunk_types = self._preferred_chunk_types(intent)
        return RetrievalPlan(
            semantic_query=base_query,
            keyword_query=" ".join(self._tokenize(base_query)),
            retrieval_filters={
                "category": self._guess_category(base_query),
                "subcategory": None,
                "difficulty": "intermediate",
                "source_type": "interview_template" if intent == IntentType.INTERVIEW else None,
                "chunk_type": preferred_chunk_types,
                "version": "v1",
            },
            preferred_chunk_types=preferred_chunk_types,
            reasoning_notes=["rewrite_query_for_retrieval"],
        )

    def run(self, state: GraphState) -> RagResult:
        plan = state["turn"].retrieval_plan or self.rewrite_query(state)
        dense_hits = self._dense_retrieve(plan)[: self.settings.dense_top_k]
        sparse_hits = self._sparse_retrieve(plan)[: self.settings.sparse_top_k]
        metadata_hits = self._metadata_retrieve(plan)[: self.settings.metadata_top_k]
        fused = self._rrf_merge([dense_hits, sparse_hits, metadata_hits], self.settings.rrf_k)
        reranked = self._rerank(plan, fused)[: self.settings.rerank_top_k]
        evidence_pack = self._evaluate_evidence(plan, reranked)
        metrics = {
            "retrieval_hit_count": len(reranked),
            "retrieval_top_score": reranked[0]["score"] if reranked else 0.0,
            "evidence_used_count": len(evidence_pack.items),
        }
        if not evidence_pack.items:
            state["runtime"].errors.append(
                build_error(
                    WorkflowErrorCode.EVIDENCE_INSUFFICIENT,
                    stage="evaluate_evidence",
                    message="No stable evidence survived the governance pipeline.",
                    retryable=False,
                    degraded_to="direct_answer_lite",
                )
            )
            return RagResult(status=RagStatus.EMPTY, evidence_pack=evidence_pack, metrics=metrics)
        status = RagStatus.OK if len(evidence_pack.items) >= self.settings.evidence_min_n else RagStatus.DEGRADED
        return RagResult(status=status, evidence_pack=evidence_pack, citations=self.build_citations_from_pack(evidence_pack), metrics=metrics)

    def build_citations(self, state: GraphState) -> Iterable[Citation]:
        rag_result = state["turn"].rag_result
        if not rag_result or not rag_result.evidence_pack:
            return []
        return self.build_citations_from_pack(rag_result.evidence_pack)

    def build_citations_from_pack(self, evidence_pack: EvidencePack) -> Iterable[Citation]:
        citations: List[Citation] = []
        for item in evidence_pack.items:
            citations.append(
                Citation(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    source_type=item.metadata.get("source_type"),
                    version=item.metadata.get("version"),
                    score=item.score,
                    title=item.metadata.get("topic"),
                    locator=item.metadata.get("category"),
                )
            )
        return citations

    def resolve_reference(self, state: GraphState) -> ReferenceResolutionResult:
        raw_query = state["turn"].raw_query.lower()
        recent_entities = state["persistent"].recent_entities
        if any(token in raw_query for token in ["this", "that", "previous", "it"]):
            if recent_entities:
                return ReferenceResolutionResult(
                    resolved=True,
                    confidence=0.76,
                    resolved_entity=recent_entities[0],
                    candidate_entities=recent_entities[:3],
                )
            return ReferenceResolutionResult(resolved=False, confidence=0.2, candidate_entities=[])
        topic = state["persistent"].current_topic
        if topic:
            return ReferenceResolutionResult(resolved=True, confidence=0.61, resolved_entity=topic, candidate_entities=[topic])
        return ReferenceResolutionResult(resolved=False, confidence=0.0, candidate_entities=[])

    def _dense_retrieve(self, plan: RetrievalPlan) -> List[Dict[str, Any]]:
        query_tokens = set(self._tokenize(plan.semantic_query))
        hits: List[Dict[str, Any]] = []
        for item in MOCK_KNOWLEDGE_BASE:
            content_tokens = set(self._tokenize(item["content"] + " " + item["topic"]))
            intersection = len(query_tokens & content_tokens)
            union = max(len(query_tokens | content_tokens), 1)
            hits.append({**item, "score": intersection / union, "channel": "dense"})
        return sorted(hits, key=lambda entry: entry["score"], reverse=True)

    def _sparse_retrieve(self, plan: RetrievalPlan) -> List[Dict[str, Any]]:
        query_tokens = self._tokenize(plan.keyword_query)
        hits: List[Dict[str, Any]] = []
        for item in MOCK_KNOWLEDGE_BASE:
            haystack = " ".join([item["topic"], item["content"], " ".join(item.get("tags", []))]).lower()
            score = sum(1.0 for token in query_tokens if token and token in haystack)
            hits.append({**item, "score": score / max(len(query_tokens), 1), "channel": "sparse"})
        return sorted(hits, key=lambda entry: entry["score"], reverse=True)

    def _metadata_retrieve(self, plan: RetrievalPlan) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for item in MOCK_KNOWLEDGE_BASE:
            score = 0.0
            filters = plan.retrieval_filters
            if filters.get("category") and item["category"] == filters["category"]:
                score += 0.4
            if filters.get("version") and item["version"] == filters["version"]:
                score += 0.2
            preferred_types = filters.get("chunk_type") or []
            if preferred_types and item["chunk_type"] in preferred_types:
                score += 0.4
            if score > 0:
                hits.append({**item, "score": score, "channel": "metadata"})
        return sorted(hits, key=lambda entry: entry["score"], reverse=True)

    def _rrf_merge(self, result_sets: Sequence[Sequence[Dict[str, Any]]], rrf_k: int) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for results in result_sets:
            for rank, item in enumerate(results, start=1):
                key = item["chunk_id"]
                score = 1.0 / (rrf_k + rank)
                existing = merged.setdefault(key, {**item, "score": 0.0, "channels": []})
                existing["score"] += score
                existing["channels"].append(item.get("channel"))
        return sorted(merged.values(), key=lambda entry: entry["score"], reverse=True)

    def _rerank(self, plan: RetrievalPlan, hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        preferred = set(plan.preferred_chunk_types)
        reranked: List[Dict[str, Any]] = []
        for item in hits:
            boosted = dict(item)
            if boosted.get("chunk_type") in preferred:
                boosted["score"] += 0.2
            if plan.retrieval_filters.get("source_type") and boosted.get("source_type") == plan.retrieval_filters.get("source_type"):
                boosted["score"] += 0.1
            reranked.append(boosted)
        return sorted(reranked, key=lambda entry: entry["score"], reverse=True)

    def _evaluate_evidence(self, plan: RetrievalPlan, hits: Sequence[Dict[str, Any]]) -> EvidencePack:
        discarded: Dict[str, Any] = {
            "low_score": 0,
            "duplicate": 0,
            "topic_mismatch": 0,
            "version_filtered": 0,
            "perspective_filtered": 0,
        }
        preferred_types = set(plan.preferred_chunk_types)
        query_tokens = set(self._tokenize(plan.semantic_query))
        filtered: List[Dict[str, Any]] = []
        seen_topics = set()
        for item in hits:
            if item["score"] < self.settings.low_score_threshold:
                discarded["low_score"] += 1
                continue
            fingerprint = (item.get("topic"), item.get("chunk_type"))
            if fingerprint in seen_topics:
                discarded["duplicate"] += 1
                continue
            topic_tokens = set(self._tokenize(item.get("topic", "")))
            overlap = len(query_tokens & topic_tokens) / max(len(query_tokens | topic_tokens), 1)
            if query_tokens and overlap < self.settings.topic_consistency_threshold and item.get("topic") != plan.semantic_query:
                discarded["topic_mismatch"] += 1
                continue
            if item.get("version") != plan.retrieval_filters.get("version"):
                discarded["version_filtered"] += 1
                continue
            if preferred_types and item.get("chunk_type") not in preferred_types and len(filtered) >= self.settings.evidence_min_n:
                discarded["perspective_filtered"] += 1
                continue
            seen_topics.add(fingerprint)
            filtered.append(item)
            if len(filtered) >= self.settings.evidence_top_n:
                break
        return EvidencePack(
            items=[
                EvidenceItem(
                    chunk_id=item["chunk_id"],
                    content=item["content"],
                    score=round(float(item["score"]), 4),
                    document_id=item.get("topic"),
                    chunk_type=item.get("chunk_type"),
                    metadata={
                        "topic": item.get("topic"),
                        "category": item.get("category"),
                        "subcategory": item.get("subcategory"),
                        "source_type": item.get("source_type"),
                        "version": item.get("version"),
                    },
                )
                for item in filtered
            ],
            discard_summary=discarded,
            top_scores=[round(float(item["score"]), 4) for item in filtered],
            extra={"retrieval_plan": plan.model_dump()},
        )

    def _preferred_chunk_types(self, intent: IntentType) -> List[str]:
        mapping = {
            IntentType.EXPLAIN: ["concept", "qa", "roadmap"],
            IntentType.COMPARE: ["comparison", "interview_template", "qa"],
            IntentType.INTERVIEW: ["interview_template", "comparison", "qa"],
            IntentType.CODE: ["code_example", "pitfall", "qa"],
            IntentType.STUDY_PLAN: ["roadmap", "concept", "practice_case"],
            IntentType.FOLLOW_UP: ["concept", "comparison", "qa"],
            IntentType.SUMMARY: ["qa", "concept", "roadmap"],
        }
        return mapping.get(intent, ["concept", "qa"])

    def _guess_category(self, query: str) -> str | None:
        lowered = query.lower()
        if any(token in lowered for token in ["spring", "aop"]):
            return "Spring"
        if any(token in lowered for token in ["java", "jvm", "thread", "concurrency"]):
            return "Java"
        if any(token in lowered for token in ["agent", "langgraph", "langchain", "rag", "react", "tool"]):
            return "Agent"
        return None

    def _tokenize(self, text: str) -> List[str]:
        return [token.lower() for token in TOKEN_PATTERN.findall(text or "")]
