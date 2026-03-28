from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .models import KnowledgeChunk


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


def build_default_chunks(rows: Sequence[Mapping[str, Any]] = _DEFAULT_ROWS) -> Tuple[KnowledgeChunk, ...]:
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


DEFAULT_KNOWLEDGE_CHUNKS: Tuple[KnowledgeChunk, ...] = build_default_chunks()
