from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from .models import ChunkType, RetrievalFilters, RetrievalPlan, coerce_tuple

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+#.:-]+|[\u4e00-\u9fff]+")

INTENT_CHUNK_MAP = {
    "explain": (ChunkType.CONCEPT.value, ChunkType.QA.value, ChunkType.ROADMAP.value),
    "compare": (ChunkType.COMPARISON.value, ChunkType.INTERVIEW_TEMPLATE.value, ChunkType.QA.value),
    "interview": (ChunkType.INTERVIEW_TEMPLATE.value, ChunkType.COMPARISON.value, ChunkType.QA.value),
    "code": (ChunkType.CODE_EXAMPLE.value, ChunkType.PITFALL.value, ChunkType.QA.value),
    "plan": (ChunkType.ROADMAP.value, ChunkType.CONCEPT.value, ChunkType.PRACTICE_CASE.value),
}

_CATEGORY_HINTS = {
    "java": ("java", "jvm", "spring", "redis", "mysql", "并发", "线程池", "锁", "事务"),
    "agent": ("agent", "langgraph", "react", "tool", "memory", "workflow"),
    "rag": ("rag", "retrieval", "embedding", "rerank", "qdrant", "chunk"),
}

_SOURCE_HINTS = {
    "interview": ("面试", "interview"),
    "practice": ("练习", "题", "quiz"),
    "faq": ("区别", "为什么", "怎么"),
}


@dataclass(frozen=True)
class QueryRewriteContext:
    raw_query: str
    intent: Optional[str] = None
    resolved_topic: Optional[str] = None
    session_topic: Optional[str] = None
    requested_output_style: Optional[str] = None
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    user_preferences: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)


class QueryRewriteService:
    def build_plan(self, context: QueryRewriteContext) -> RetrievalPlan:
        semantic_query = self._build_semantic_query(context)
        keyword_query = self._build_keyword_query(context, semantic_query)
        preferred_chunk_types = self._preferred_chunk_types(context)
        filters = self._build_filters(context, preferred_chunk_types)
        extra = {
            "raw_query": context.raw_query,
            "rewrite_applied": semantic_query != context.raw_query,
            "resolved_topic": context.resolved_topic,
            "session_topic": context.session_topic,
        }
        return RetrievalPlan(
            semantic_query=semantic_query,
            keyword_query=keyword_query,
            retrieval_filters=filters,
            preferred_chunk_types=preferred_chunk_types,
            extra=extra,
        )

    def _build_semantic_query(self, context: QueryRewriteContext) -> str:
        query = (context.raw_query or "").strip()
        topic = context.resolved_topic or context.session_topic or ""
        if not query:
            return topic

        vague_prefixes = (
            "这个",
            "这个怎么",
            "上一个",
            "那个",
            "它",
            "它和",
            "面试怎么答",
        )
        if topic and any(query.startswith(prefix) for prefix in vague_prefixes):
            return (topic + " " + query).strip()

        if topic and topic.lower() not in query.lower():
            return (topic + " " + query).strip()
        return query

    def _build_keyword_query(self, context: QueryRewriteContext, semantic_query: str) -> str:
        tokens = []
        if context.resolved_topic:
            tokens.extend(_TOKEN_PATTERN.findall(context.resolved_topic))
        tokens.extend(_TOKEN_PATTERN.findall(semantic_query))
        seen = set()
        ordered = []
        for token in tokens:
            normalized = token.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(token)
        return " ".join(ordered[:10])

    def _preferred_chunk_types(self, context: QueryRewriteContext) -> Tuple[str, ...]:
        intent = (context.intent or "").strip().lower()
        requested_style = (context.requested_output_style or "").strip().lower()
        if requested_style in ("interview", "面试", "interview_answer"):
            return INTENT_CHUNK_MAP["interview"]
        if requested_style in ("code", "代码", "example"):
            return INTENT_CHUNK_MAP["code"]
        return INTENT_CHUNK_MAP.get(intent, INTENT_CHUNK_MAP["explain"])

    def _build_filters(self, context: QueryRewriteContext, preferred_chunk_types: Tuple[str, ...]) -> RetrievalFilters:
        base = context.filters
        semantic_query = self._build_semantic_query(context).lower()

        category = list(base.category)
        if not category:
            inferred_category = self._infer_mapping_value(semantic_query, _CATEGORY_HINTS)
            if inferred_category:
                category.append(inferred_category)

        source_type = list(base.source_type)
        if not source_type:
            inferred_source = self._infer_mapping_value(semantic_query, _SOURCE_HINTS)
            if inferred_source:
                source_type.append(inferred_source)

        chunk_type = list(base.chunk_type)
        if not chunk_type:
            chunk_type.extend(preferred_chunk_types)

        difficulty = list(base.difficulty)
        if not difficulty:
            if any(keyword in semantic_query for keyword in ("深入", "高级", "原理")):
                difficulty.append("advanced")
            elif any(keyword in semantic_query for keyword in ("速通", "入门", "简单")):
                difficulty.append("beginner")

        return RetrievalFilters(
            category=coerce_tuple(category),
            subcategory=base.subcategory,
            difficulty=coerce_tuple(difficulty),
            source_type=coerce_tuple(source_type),
            chunk_type=coerce_tuple(chunk_type),
            version=base.version,
            tags=base.tags,
            extra=dict(base.extra),
        )

    @staticmethod
    def _infer_mapping_value(text: str, mapping: Mapping[str, Tuple[str, ...]]) -> Optional[str]:
        for value, keywords in mapping.items():
            if any(keyword in text for keyword in keywords):
                return value
        return None
