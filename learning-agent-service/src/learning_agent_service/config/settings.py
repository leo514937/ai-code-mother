"""Environment-driven settings for the standalone learning agent service.

The module keeps a small compatibility surface for early integration:
- ``Settings`` / ``ServiceSettings`` remain available.
- ``get_settings`` remains memoized.
- Nested settings classes can be imported directly by infrastructure factories.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except Exception:  # pragma: no cover - optional at authoring time
    BaseSettings = BaseModel  # type: ignore[misc,assignment]
    SettingsConfigDict = dict  # type: ignore[misc,assignment]


def _env(name: str, default: Any) -> Any:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


class AppSettings(BaseModel):
    service_name: str = "learning-agent-service"
    environment: str = "development"
    debug: bool = False
    workflow_version: str = "learn-agent/v1"
    request_timeout_seconds: float = 30.0
    prefer_real_adapters: bool = True
    allow_in_memory_fallback: bool = True


class PostgresSettings(BaseModel):
    dsn: str = ""
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_pre_ping: bool = True


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    socket_timeout_seconds: int = 5
    key_prefix: str = "learn"
    session_ttl_seconds: int = 86400
    summary_ttl_seconds: int = 86400
    clarification_ttl_seconds: int = 3600
    tool_cache_ttl_seconds: int = 900


class QdrantSettings(BaseModel):
    url: str = "http://localhost:6333"
    api_key: str = ""
    timeout_seconds: int = 5
    prefer_grpc: bool = False
    knowledge_collection: str = "knowledge_chunks"
    user_memory_collection: str = "user_semantic_memory"
    knowledge_vector_name: str = "embedding"
    knowledge_sparse_vector_name: str = "sparse_embedding"


class OpenAISettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    organization: Optional[str] = None
    project: Optional[str] = None
    timeout_seconds: int = 30
    max_retries: int = 2
    responses_model: str = "gpt-5.4"
    embedding_model: str = "text-embedding-3-small"


class ObservabilitySettings(BaseModel):
    log_level: str = "INFO"
    json_logs: bool = True
    include_caller: bool = False
    outbox_batch_size: int = 100
    outbox_poll_interval_seconds: float = 1.0
    outbox_max_attempts: int = 10


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "learning-agent-service"
    environment: str = "development"
    debug: bool = False
    workflow_version: str = "learn-agent/v1"
    api_prefix: str = "/internal/v1"
    default_response_mode: str = "detailed"
    internal_api_token: str = ""
    prefer_real_adapters: bool = True
    allow_in_memory_fallback: bool = True
    workflow_checkpoint_enabled: bool = True
    workflow_checkpoint_sqlite_path: str = "var/langgraph/checkpoints.sqlite"
    enable_online_dense_retrieval: bool = False
    enable_online_sparse_retrieval: bool = False
    enable_bm25_sparse_retrieval: bool = True
    enable_remote_reranker: bool = False
    reranker_provider: str = "heuristic"
    enable_llm_query_rewrite: bool = False
    enable_hyde_sparse_retrieval: bool = False
    llm_query_rewrite_min_query_length: int = 6
    llm_query_rewrite_low_confidence_threshold: float = 0.5
    llm_query_rewrite_model: str = ""
    llm_query_rewrite_temperature: float = 0.0
    hyde_sparse_retrieval_model: str = ""
    hyde_sparse_retrieval_temperature: float = 0.0
    intent_confidence_threshold: float = 0.5
    reference_resolution_confidence_threshold: float = 0.5
    metadata_filter_confidence_threshold: float = 0.5
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    remote_reranker_endpoint: str = ""
    remote_reranker_api_key: str = ""
    remote_reranker_model: str = ""
    remote_reranker_timeout_seconds: float = 10.0
    memory_retrieval_prompt_limit: int = 4
    memory_retrieval_state_limit: int = 6
    memory_retrieval_rag_limit: int = 6
    memory_retrieval_tool_limit: int = 4
    memory_retrieval_token_budget: int = 1200
    memory_retrieval_semantic_top_k: int = 5
    memory_retrieval_episodic_keywords: Tuple[str, ...] = (
        "debug",
        "troubleshoot",
        "troubleshooting",
        "排错",
        "故障",
        "implementation",
        "实现",
        "problem",
    )
    memory_retrieval_procedural_keywords: Tuple[str, ...] = (
        "how-to",
        "how to",
        "workflow",
        "tool",
        "步骤",
        "流程",
        "怎么",
        "如何",
        "debug",
        "implementation",
    )
    memory_injection_prompt_limit: int = 4
    memory_injection_state_limit: int = 8
    memory_injection_tool_limit: int = 4
    memory_injection_rag_limit: int = 6
    memory_injection_token_budget: int = 1200

    app: AppSettings = Field(default_factory=AppSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    dense_top_k: int = 20
    sparse_top_k: int = 20
    metadata_top_k: int = 10
    rrf_k: int = 60
    rrf_dense_weight: float = 1.0
    rrf_sparse_weight: float = 1.0
    rrf_metadata_weight: float = 0.6
    rerank_top_k: int = 15
    evidence_top_n: int = 6
    evidence_min_n: int = 4
    low_score_threshold: float = 0.18
    evidence_strong_score_threshold: float = 0.45
    topic_consistency_threshold: float = 0.35
    dedup_similarity_threshold: float = 0.82
    rewrite_retry_limit: int = 1
    memory_governance_low_confidence_threshold: float = 0.35
    memory_governance_low_stability_threshold: float = 0.45
    memory_conflict_supersede_margin: float = 0.05
    memory_conflict_merge_similarity_threshold: float = 0.65
    memory_promotion_preference_promote_count: int = 3
    memory_promotion_behavior_promote_count: int = 2
    memory_promotion_low_quiz_threshold: float = 0.6
    memory_recommendation_low_mastery_threshold: float = 0.45
    memory_recommendation_review_priority_threshold: float = 60.0
    mastery_quiz_super_high_threshold: float = 0.85
    mastery_quiz_high_threshold: float = 0.7
    mastery_quiz_mid_threshold: float = 0.5
    mastery_quiz_low_threshold: float = 0.35
    mastery_weak_signal_quiz_threshold: float = 0.6
    mastery_review_priority_base_mastery: float = 0.65
    mastery_review_priority_low_quiz_threshold: float = 0.6
    mastery_review_priority_low_quiz_bonus: float = 22.0
    mastery_review_priority_weak_signal_bonus: float = 15.0
    mastery_review_priority_low_evidence_threshold: int = 3
    mastery_review_priority_low_evidence_bonus: float = 8.0
    mastery_review_priority_negative_signal_bonus: float = 5.0
    mastery_review_priority_negative_signal_cap: float = 20.0
    mastery_review_priority_high_mastery_threshold: float = 0.75
    mastery_review_priority_high_mastery_bonus: float = -10.0
    consolidation_minimum_duplicate_group_size: int = 2
    consolidation_max_conflicts: int = 8
    consolidation_confirmed_explicitness: float = 1.0
    consolidation_inferred_explicitness: float = 0.5
    consolidation_recency_window_seconds: int = 60 * 60 * 24 * 7
    orchestrator_confirmed_confidence_threshold: float = 0.8

    def __init__(self, **data: Any) -> None:
        app_name = data.pop("app_name", _env("LEARNING_AGENT_SERVICE_NAME", "learning-agent-service"))
        environment = data.pop("environment", _env("LEARNING_AGENT_ENV", "development"))
        debug = data.pop("debug", _env_bool("LEARNING_AGENT_DEBUG", False))
        workflow_version = data.pop("workflow_version", _env("LEARNING_AGENT_WORKFLOW_VERSION", "learn-agent/v1"))
        internal_api_token = data.pop("internal_api_token", _env("LEARNING_AGENT_INTERNAL_API_TOKEN", "")) or ""
        request_timeout_seconds = float(
            data.pop("request_timeout_seconds", _env("LEARNING_AGENT_REQUEST_TIMEOUT_SECONDS", 30.0))
        )
        prefer_real_adapters = bool(
            data.pop("prefer_real_adapters", _env_bool("LEARNING_AGENT_PREFER_REAL_ADAPTERS", True))
        )
        allow_in_memory_fallback = bool(
            data.pop("allow_in_memory_fallback", _env_bool("LEARNING_AGENT_ALLOW_IN_MEMORY_FALLBACK", True))
        )
        workflow_checkpoint_enabled = bool(
            data.pop(
                "workflow_checkpoint_enabled",
                _env_bool("LEARNING_AGENT_WORKFLOW_CHECKPOINT_ENABLED", True),
            )
        )
        workflow_checkpoint_sqlite_path = (
            data.pop(
                "workflow_checkpoint_sqlite_path",
                _env("LEARNING_AGENT_WORKFLOW_CHECKPOINT_SQLITE_PATH", "var/langgraph/checkpoints.sqlite"),
            )
            or "var/langgraph/checkpoints.sqlite"
        )
        enable_online_dense_retrieval = bool(
            data.pop("enable_online_dense_retrieval", _env_bool("LEARNING_AGENT_ENABLE_ONLINE_DENSE_RETRIEVAL", False))
        )
        enable_online_sparse_retrieval = bool(
            data.pop("enable_online_sparse_retrieval", _env_bool("LEARNING_AGENT_ENABLE_ONLINE_SPARSE_RETRIEVAL", False))
        )
        enable_bm25_sparse_retrieval = bool(
            data.pop("enable_bm25_sparse_retrieval", _env_bool("LEARNING_AGENT_ENABLE_BM25_SPARSE_RETRIEVAL", True))
        )
        enable_remote_reranker = bool(
            data.pop("enable_remote_reranker", _env_bool("LEARNING_AGENT_ENABLE_REMOTE_RERANKER", False))
        )
        reranker_provider = str(data.pop("reranker_provider", _env("LEARNING_AGENT_RERANKER_PROVIDER", "")) or "").strip().lower()
        enable_llm_query_rewrite = bool(
            data.pop("enable_llm_query_rewrite", _env_bool("LEARNING_AGENT_ENABLE_LLM_QUERY_REWRITE", False))
        )
        enable_hyde_sparse_retrieval = bool(
            data.pop("enable_hyde_sparse_retrieval", _env_bool("LEARNING_AGENT_ENABLE_HYDE_SPARSE_RETRIEVAL", False))
        )
        llm_query_rewrite_min_query_length = int(
            data.pop(
                "llm_query_rewrite_min_query_length",
                _env("LEARNING_AGENT_LLM_QUERY_REWRITE_MIN_QUERY_LENGTH", 6),
            )
        )
        llm_query_rewrite_low_confidence_threshold = float(
            data.pop(
                "llm_query_rewrite_low_confidence_threshold",
                _env("LEARNING_AGENT_LLM_QUERY_REWRITE_LOW_CONFIDENCE_THRESHOLD", 0.5),
            )
        )
        llm_query_rewrite_model = data.pop("llm_query_rewrite_model", _env("LEARNING_AGENT_LLM_QUERY_REWRITE_MODEL", "")) or ""
        llm_query_rewrite_temperature = float(
            data.pop(
                "llm_query_rewrite_temperature",
                _env("LEARNING_AGENT_LLM_QUERY_REWRITE_TEMPERATURE", 0.0),
            )
        )
        hyde_sparse_retrieval_model = data.pop(
            "hyde_sparse_retrieval_model",
            _env("LEARNING_AGENT_HYDE_SPARSE_RETRIEVAL_MODEL", ""),
        ) or ""
        hyde_sparse_retrieval_temperature = float(
            data.pop(
                "hyde_sparse_retrieval_temperature",
                _env("LEARNING_AGENT_HYDE_SPARSE_RETRIEVAL_TEMPERATURE", 0.0),
            )
        )
        intent_confidence_threshold = float(
            data.pop(
                "intent_confidence_threshold",
                _env("LEARNING_AGENT_INTENT_CONFIDENCE_THRESHOLD", 0.5),
            )
        )
        reference_resolution_confidence_threshold = float(
            data.pop(
                "reference_resolution_confidence_threshold",
                _env("LEARNING_AGENT_REFERENCE_RESOLUTION_CONFIDENCE_THRESHOLD", 0.5),
            )
        )
        metadata_filter_confidence_threshold = float(
            data.pop(
                "metadata_filter_confidence_threshold",
                _env("LEARNING_AGENT_METADATA_FILTER_CONFIDENCE_THRESHOLD", 0.5),
            )
        )
        bm25_k1 = float(data.pop("bm25_k1", _env("LEARNING_AGENT_BM25_K1", 1.5)))
        bm25_b = float(data.pop("bm25_b", _env("LEARNING_AGENT_BM25_B", 0.75)))
        rrf_dense_weight = float(data.pop("rrf_dense_weight", _env("LEARNING_AGENT_RRF_DENSE_WEIGHT", 1.0)))
        rrf_sparse_weight = float(data.pop("rrf_sparse_weight", _env("LEARNING_AGENT_RRF_SPARSE_WEIGHT", 1.0)))
        rrf_metadata_weight = float(data.pop("rrf_metadata_weight", _env("LEARNING_AGENT_RRF_METADATA_WEIGHT", 0.6)))
        remote_reranker_endpoint = data.pop(
            "remote_reranker_endpoint",
            _env("LEARNING_AGENT_REMOTE_RERANKER_ENDPOINT", ""),
        ) or ""
        remote_reranker_api_key = data.pop(
            "remote_reranker_api_key",
            _env("LEARNING_AGENT_REMOTE_RERANKER_API_KEY", ""),
        ) or ""
        remote_reranker_model = data.pop(
            "remote_reranker_model",
            _env("LEARNING_AGENT_REMOTE_RERANKER_MODEL", ""),
        ) or ""
        remote_reranker_timeout_seconds = float(
            data.pop(
                "remote_reranker_timeout_seconds",
                _env("LEARNING_AGENT_REMOTE_RERANKER_TIMEOUT_SECONDS", 10.0),
            )
        )
        low_score_threshold = float(
            data.pop("low_score_threshold", _env("LEARNING_AGENT_LOW_SCORE_THRESHOLD", 0.18))
        )
        evidence_strong_score_threshold = float(
            data.pop(
                "evidence_strong_score_threshold",
                _env("LEARNING_AGENT_EVIDENCE_STRONG_SCORE_THRESHOLD", 0.45),
            )
        )
        topic_consistency_threshold = float(
            data.pop(
                "topic_consistency_threshold",
                _env("LEARNING_AGENT_TOPIC_CONSISTENCY_THRESHOLD", 0.35),
            )
        )
        dedup_similarity_threshold = float(
            data.pop(
                "dedup_similarity_threshold",
                _env("LEARNING_AGENT_DEDUP_SIMILARITY_THRESHOLD", 0.82),
            )
        )
        rewrite_retry_limit = int(data.pop("rewrite_retry_limit", _env("LEARNING_AGENT_REWRITE_RETRY_LIMIT", 1)))
        memory_retrieval_prompt_limit = int(
            data.pop(
                "memory_retrieval_prompt_limit",
                _env("LEARNING_AGENT_MEMORY_RETRIEVAL_PROMPT_LIMIT", 4),
            )
        )
        memory_retrieval_state_limit = int(
            data.pop(
                "memory_retrieval_state_limit",
                _env("LEARNING_AGENT_MEMORY_RETRIEVAL_STATE_LIMIT", 6),
            )
        )
        memory_retrieval_rag_limit = int(
            data.pop(
                "memory_retrieval_rag_limit",
                _env("LEARNING_AGENT_MEMORY_RETRIEVAL_RAG_LIMIT", 6),
            )
        )
        memory_retrieval_tool_limit = int(
            data.pop(
                "memory_retrieval_tool_limit",
                _env("LEARNING_AGENT_MEMORY_RETRIEVAL_TOOL_LIMIT", 4),
            )
        )
        memory_retrieval_token_budget = int(
            data.pop(
                "memory_retrieval_token_budget",
                _env("LEARNING_AGENT_MEMORY_RETRIEVAL_TOKEN_BUDGET", 1200),
            )
        )
        memory_retrieval_semantic_top_k = int(
            data.pop(
                "memory_retrieval_semantic_top_k",
                _env("LEARNING_AGENT_MEMORY_RETRIEVAL_SEMANTIC_TOP_K", 5),
            )
        )
        memory_retrieval_episodic_keywords = tuple(
            data.pop(
                "memory_retrieval_episodic_keywords",
                _env_csv(
                    "LEARNING_AGENT_MEMORY_RETRIEVAL_EPISODIC_KEYWORDS",
                    (
                        "debug",
                        "troubleshoot",
                        "troubleshooting",
                        "排错",
                        "故障",
                        "implementation",
                        "实现",
                        "problem",
                    ),
                ),
            )
        )
        memory_retrieval_procedural_keywords = tuple(
            data.pop(
                "memory_retrieval_procedural_keywords",
                _env_csv(
                    "LEARNING_AGENT_MEMORY_RETRIEVAL_PROCEDURAL_KEYWORDS",
                    (
                        "how-to",
                        "how to",
                        "workflow",
                        "tool",
                        "步骤",
                        "流程",
                        "怎么",
                        "如何",
                        "debug",
                        "implementation",
                    ),
                ),
            )
        )
        memory_injection_prompt_limit = int(
            data.pop(
                "memory_injection_prompt_limit",
                _env("LEARNING_AGENT_MEMORY_INJECTION_PROMPT_LIMIT", 4),
            )
        )
        memory_injection_state_limit = int(
            data.pop(
                "memory_injection_state_limit",
                _env("LEARNING_AGENT_MEMORY_INJECTION_STATE_LIMIT", 8),
            )
        )
        memory_injection_tool_limit = int(
            data.pop(
                "memory_injection_tool_limit",
                _env("LEARNING_AGENT_MEMORY_INJECTION_TOOL_LIMIT", 4),
            )
        )
        memory_injection_rag_limit = int(
            data.pop(
                "memory_injection_rag_limit",
                _env("LEARNING_AGENT_MEMORY_INJECTION_RAG_LIMIT", 6),
            )
        )
        memory_injection_token_budget = int(
            data.pop(
                "memory_injection_token_budget",
                _env("LEARNING_AGENT_MEMORY_INJECTION_TOKEN_BUDGET", 1200),
            )
        )
        memory_governance_low_confidence_threshold = float(
            data.pop(
                "memory_governance_low_confidence_threshold",
                _env("LEARNING_AGENT_MEMORY_GOVERNANCE_LOW_CONFIDENCE_THRESHOLD", 0.35),
            )
        )
        memory_governance_low_stability_threshold = float(
            data.pop(
                "memory_governance_low_stability_threshold",
                _env("LEARNING_AGENT_MEMORY_GOVERNANCE_LOW_STABILITY_THRESHOLD", 0.45),
            )
        )
        memory_conflict_supersede_margin = float(
            data.pop(
                "memory_conflict_supersede_margin",
                _env("LEARNING_AGENT_MEMORY_CONFLICT_SUPERSEDE_MARGIN", 0.05),
            )
        )
        memory_conflict_merge_similarity_threshold = float(
            data.pop(
                "memory_conflict_merge_similarity_threshold",
                _env("LEARNING_AGENT_MEMORY_CONFLICT_MERGE_SIMILARITY_THRESHOLD", 0.65),
            )
        )
        memory_promotion_preference_promote_count = int(
            data.pop(
                "memory_promotion_preference_promote_count",
                _env("LEARNING_AGENT_MEMORY_PROMOTION_PREFERENCE_PROMOTE_COUNT", 3),
            )
        )
        memory_promotion_behavior_promote_count = int(
            data.pop(
                "memory_promotion_behavior_promote_count",
                _env("LEARNING_AGENT_MEMORY_PROMOTION_BEHAVIOR_PROMOTE_COUNT", 2),
            )
        )
        memory_promotion_low_quiz_threshold = float(
            data.pop(
                "memory_promotion_low_quiz_threshold",
                _env("LEARNING_AGENT_MEMORY_PROMOTION_LOW_QUIZ_THRESHOLD", 0.6),
            )
        )
        memory_recommendation_low_mastery_threshold = float(
            data.pop(
                "memory_recommendation_low_mastery_threshold",
                _env("LEARNING_AGENT_MEMORY_RECOMMENDATION_LOW_MASTERY_THRESHOLD", 0.45),
            )
        )
        memory_recommendation_review_priority_threshold = float(
            data.pop(
                "memory_recommendation_review_priority_threshold",
                _env("LEARNING_AGENT_MEMORY_RECOMMENDATION_REVIEW_PRIORITY_THRESHOLD", 60.0),
            )
        )
        mastery_quiz_super_high_threshold = float(
            data.pop(
                "mastery_quiz_super_high_threshold",
                _env("LEARNING_AGENT_MASTERY_QUIZ_SUPER_HIGH_THRESHOLD", 0.85),
            )
        )
        mastery_quiz_high_threshold = float(
            data.pop(
                "mastery_quiz_high_threshold",
                _env("LEARNING_AGENT_MASTERY_QUIZ_HIGH_THRESHOLD", 0.7),
            )
        )
        mastery_quiz_mid_threshold = float(
            data.pop(
                "mastery_quiz_mid_threshold",
                _env("LEARNING_AGENT_MASTERY_QUIZ_MID_THRESHOLD", 0.5),
            )
        )
        mastery_quiz_low_threshold = float(
            data.pop(
                "mastery_quiz_low_threshold",
                _env("LEARNING_AGENT_MASTERY_QUIZ_LOW_THRESHOLD", 0.35),
            )
        )
        mastery_weak_signal_quiz_threshold = float(
            data.pop(
                "mastery_weak_signal_quiz_threshold",
                _env("LEARNING_AGENT_MASTERY_WEAK_SIGNAL_QUIZ_THRESHOLD", 0.6),
            )
        )
        mastery_review_priority_base_mastery = float(
            data.pop(
                "mastery_review_priority_base_mastery",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_BASE_MASTERY", 0.65),
            )
        )
        mastery_review_priority_low_quiz_threshold = float(
            data.pop(
                "mastery_review_priority_low_quiz_threshold",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_QUIZ_THRESHOLD", 0.6),
            )
        )
        mastery_review_priority_low_quiz_bonus = float(
            data.pop(
                "mastery_review_priority_low_quiz_bonus",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_QUIZ_BONUS", 22.0),
            )
        )
        mastery_review_priority_weak_signal_bonus = float(
            data.pop(
                "mastery_review_priority_weak_signal_bonus",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_WEAK_SIGNAL_BONUS", 15.0),
            )
        )
        mastery_review_priority_low_evidence_threshold = int(
            data.pop(
                "mastery_review_priority_low_evidence_threshold",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_EVIDENCE_THRESHOLD", 3),
            )
        )
        mastery_review_priority_low_evidence_bonus = float(
            data.pop(
                "mastery_review_priority_low_evidence_bonus",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_EVIDENCE_BONUS", 8.0),
            )
        )
        mastery_review_priority_negative_signal_bonus = float(
            data.pop(
                "mastery_review_priority_negative_signal_bonus",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_NEGATIVE_SIGNAL_BONUS", 5.0),
            )
        )
        mastery_review_priority_negative_signal_cap = float(
            data.pop(
                "mastery_review_priority_negative_signal_cap",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_NEGATIVE_SIGNAL_CAP", 20.0),
            )
        )
        mastery_review_priority_high_mastery_threshold = float(
            data.pop(
                "mastery_review_priority_high_mastery_threshold",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_HIGH_MASTERY_THRESHOLD", 0.75),
            )
        )
        mastery_review_priority_high_mastery_bonus = float(
            data.pop(
                "mastery_review_priority_high_mastery_bonus",
                _env("LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_HIGH_MASTERY_BONUS", -10.0),
            )
        )
        consolidation_minimum_duplicate_group_size = int(
            data.pop(
                "consolidation_minimum_duplicate_group_size",
                _env("LEARNING_AGENT_CONSOLIDATION_MINIMUM_DUPLICATE_GROUP_SIZE", 2),
            )
        )
        consolidation_max_conflicts = int(
            data.pop(
                "consolidation_max_conflicts",
                _env("LEARNING_AGENT_CONSOLIDATION_MAX_CONFLICTS", 8),
            )
        )
        consolidation_confirmed_explicitness = float(
            data.pop(
                "consolidation_confirmed_explicitness",
                _env("LEARNING_AGENT_CONSOLIDATION_CONFIRMED_EXPLICITNESS", 1.0),
            )
        )
        consolidation_inferred_explicitness = float(
            data.pop(
                "consolidation_inferred_explicitness",
                _env("LEARNING_AGENT_CONSOLIDATION_INFERRED_EXPLICITNESS", 0.5),
            )
        )
        consolidation_recency_window_seconds = int(
            data.pop(
                "consolidation_recency_window_seconds",
                _env("LEARNING_AGENT_CONSOLIDATION_RECENCY_WINDOW_SECONDS", 60 * 60 * 24 * 7),
            )
        )
        orchestrator_confirmed_confidence_threshold = float(
            data.pop(
                "orchestrator_confirmed_confidence_threshold",
                _env("LEARNING_AGENT_ORCHESTRATOR_CONFIRMED_CONFIDENCE_THRESHOLD", 0.8),
            )
        )
        if not reranker_provider:
            reranker_provider = "remote" if enable_remote_reranker else "heuristic"
        if reranker_provider not in {"heuristic", "remote"}:
            reranker_provider = "heuristic"

        if "app" not in data:
            data["app"] = AppSettings(
                service_name=app_name,
                environment=environment,
                debug=debug,
                workflow_version=workflow_version,
                request_timeout_seconds=request_timeout_seconds,
                prefer_real_adapters=prefer_real_adapters,
                allow_in_memory_fallback=allow_in_memory_fallback,
            )

        if "postgres" not in data:
            data["postgres"] = PostgresSettings(
                dsn=data.pop("postgres_dsn", _env("LEARNING_AGENT_POSTGRES_DSN", "")) or "",
                echo=bool(data.pop("postgres_echo", _env_bool("LEARNING_AGENT_POSTGRES_ECHO", False))),
                pool_size=int(data.pop("postgres_pool_size", _env("LEARNING_AGENT_POSTGRES_POOL_SIZE", 5))),
                max_overflow=int(data.pop("postgres_max_overflow", _env("LEARNING_AGENT_POSTGRES_MAX_OVERFLOW", 10))),
                pool_pre_ping=bool(
                    data.pop("postgres_pool_pre_ping", _env_bool("LEARNING_AGENT_POSTGRES_POOL_PRE_PING", True))
                ),
            )

        if "redis" not in data:
            data["redis"] = RedisSettings(
                url=data.pop("redis_url", _env("LEARNING_AGENT_REDIS_URL", "redis://localhost:6379/0"))
                or "redis://localhost:6379/0",
                socket_timeout_seconds=int(
                    data.pop("redis_socket_timeout_seconds", _env("LEARNING_AGENT_REDIS_SOCKET_TIMEOUT_SECONDS", 5))
                ),
                key_prefix=data.pop("redis_key_prefix", _env("LEARNING_AGENT_REDIS_KEY_PREFIX", "learn")) or "learn",
                session_ttl_seconds=int(
                    data.pop("redis_session_ttl_seconds", _env("LEARNING_AGENT_REDIS_SESSION_TTL_SECONDS", 86400))
                ),
                summary_ttl_seconds=int(
                    data.pop("redis_summary_ttl_seconds", _env("LEARNING_AGENT_REDIS_SUMMARY_TTL_SECONDS", 86400))
                ),
                clarification_ttl_seconds=int(
                    data.pop("redis_clarification_ttl_seconds", _env("LEARNING_AGENT_REDIS_CLARIFICATION_TTL_SECONDS", 3600))
                ),
                tool_cache_ttl_seconds=int(
                    data.pop("redis_tool_cache_ttl_seconds", _env("LEARNING_AGENT_REDIS_TOOL_CACHE_TTL_SECONDS", 900))
                ),
            )

        if "qdrant" not in data:
            data["qdrant"] = QdrantSettings(
                url=data.pop("qdrant_url", _env("LEARNING_AGENT_QDRANT_URL", "http://localhost:6333"))
                or "http://localhost:6333",
                api_key=data.pop("qdrant_api_key", _env("LEARNING_AGENT_QDRANT_API_KEY", "")) or "",
                timeout_seconds=int(
                    data.pop("qdrant_timeout_seconds", _env("LEARNING_AGENT_QDRANT_TIMEOUT_SECONDS", 5))
                ),
                prefer_grpc=bool(data.pop("qdrant_prefer_grpc", _env_bool("LEARNING_AGENT_QDRANT_PREFER_GRPC", False))),
                knowledge_collection=(
                    data.pop("knowledge_collection", _env("LEARNING_AGENT_QDRANT_KNOWLEDGE_COLLECTION", "knowledge_chunks"))
                    or "knowledge_chunks"
                ),
                user_memory_collection=(
                    data.pop(
                        "memory_collection",
                        _env("LEARNING_AGENT_QDRANT_USER_MEMORY_COLLECTION", "user_semantic_memory"),
                    )
                    or "user_semantic_memory"
                ),
                knowledge_vector_name=(
                    data.pop("knowledge_vector_name", _env("LEARNING_AGENT_QDRANT_KNOWLEDGE_VECTOR_NAME", "embedding"))
                    or "embedding"
                ),
                knowledge_sparse_vector_name=(
                    data.pop(
                        "knowledge_sparse_vector_name",
                        _env("LEARNING_AGENT_QDRANT_KNOWLEDGE_SPARSE_VECTOR_NAME", "sparse_embedding"),
                    )
                    or "sparse_embedding"
                ),
            )

        if "openai" not in data:
            data["openai"] = OpenAISettings(
                api_key=(
                    data.pop("openai_api_key", _env("LEARNING_AGENT_OPENAI_API_KEY", ""))
                    or _env("OPENAI_API_KEY", "")
                )
                or "",
                base_url=(
                    data.pop("openai_base_url", _env("LEARNING_AGENT_OPENAI_BASE_URL", ""))
                    or _env("OPENAI_BASE_URL", "")
                )
                or "",
                organization=data.pop("openai_organization", _env("LEARNING_AGENT_OPENAI_ORGANIZATION", None))
                or _env("OPENAI_ORG_ID", None),
                project=data.pop("openai_project", _env("LEARNING_AGENT_OPENAI_PROJECT", None))
                or _env("OPENAI_PROJECT", None),
                timeout_seconds=int(data.pop("openai_timeout_seconds", _env("LEARNING_AGENT_OPENAI_TIMEOUT_SECONDS", 30))),
                max_retries=int(data.pop("openai_max_retries", _env("LEARNING_AGENT_OPENAI_MAX_RETRIES", 2))),
                responses_model=(
                    data.pop("openai_model", _env("LEARNING_AGENT_OPENAI_RESPONSES_MODEL", "gpt-5.4")) or "gpt-5.4"
                ),
                embedding_model=(
                    data.pop("openai_embedding_model", _env("LEARNING_AGENT_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))
                    or "text-embedding-3-small"
                ),
            )

        if "observability" not in data:
            data["observability"] = ObservabilitySettings(
                log_level=data.pop("log_level", _env("LEARNING_AGENT_LOG_LEVEL", "INFO")) or "INFO",
                json_logs=bool(data.pop("json_logs", _env_bool("LEARNING_AGENT_JSON_LOGS", True))),
                include_caller=bool(data.pop("include_caller", _env_bool("LEARNING_AGENT_LOG_INCLUDE_CALLER", False))),
                outbox_batch_size=int(data.pop("outbox_batch_size", _env("LEARNING_AGENT_OUTBOX_BATCH_SIZE", 100))),
                outbox_poll_interval_seconds=float(
                    data.pop("outbox_poll_interval_seconds", _env("LEARNING_AGENT_OUTBOX_POLL_INTERVAL_SECONDS", 1.0))
                ),
                outbox_max_attempts=int(
                    data.pop("outbox_max_attempts", _env("LEARNING_AGENT_OUTBOX_MAX_ATTEMPTS", 10))
                ),
            )

        data.setdefault("app_name", data["app"].service_name)
        data.setdefault("environment", data["app"].environment)
        data.setdefault("debug", data["app"].debug)
        data.setdefault("workflow_version", data["app"].workflow_version)
        data.setdefault("internal_api_token", internal_api_token)
        data.setdefault("prefer_real_adapters", data["app"].prefer_real_adapters)
        data.setdefault("allow_in_memory_fallback", data["app"].allow_in_memory_fallback)
        data.setdefault("workflow_checkpoint_enabled", workflow_checkpoint_enabled)
        data.setdefault("workflow_checkpoint_sqlite_path", workflow_checkpoint_sqlite_path)
        data.setdefault("enable_online_dense_retrieval", enable_online_dense_retrieval)
        data.setdefault("enable_online_sparse_retrieval", enable_online_sparse_retrieval)
        data.setdefault("enable_bm25_sparse_retrieval", enable_bm25_sparse_retrieval)
        data.setdefault("enable_remote_reranker", enable_remote_reranker or reranker_provider == "remote")
        data.setdefault("reranker_provider", reranker_provider)
        data.setdefault("enable_llm_query_rewrite", enable_llm_query_rewrite)
        data.setdefault("enable_hyde_sparse_retrieval", enable_hyde_sparse_retrieval)
        data.setdefault("llm_query_rewrite_min_query_length", llm_query_rewrite_min_query_length)
        data.setdefault("llm_query_rewrite_low_confidence_threshold", llm_query_rewrite_low_confidence_threshold)
        data.setdefault("llm_query_rewrite_model", llm_query_rewrite_model)
        data.setdefault("llm_query_rewrite_temperature", llm_query_rewrite_temperature)
        data.setdefault("hyde_sparse_retrieval_model", hyde_sparse_retrieval_model)
        data.setdefault("hyde_sparse_retrieval_temperature", hyde_sparse_retrieval_temperature)
        data.setdefault("intent_confidence_threshold", intent_confidence_threshold)
        data.setdefault("reference_resolution_confidence_threshold", reference_resolution_confidence_threshold)
        data.setdefault("metadata_filter_confidence_threshold", metadata_filter_confidence_threshold)
        data.setdefault("bm25_k1", bm25_k1)
        data.setdefault("bm25_b", bm25_b)
        data.setdefault("rrf_dense_weight", rrf_dense_weight)
        data.setdefault("rrf_sparse_weight", rrf_sparse_weight)
        data.setdefault("rrf_metadata_weight", rrf_metadata_weight)
        data.setdefault("remote_reranker_endpoint", remote_reranker_endpoint)
        data.setdefault("remote_reranker_api_key", remote_reranker_api_key)
        data.setdefault("remote_reranker_model", remote_reranker_model)
        data.setdefault("remote_reranker_timeout_seconds", remote_reranker_timeout_seconds)
        data.setdefault("low_score_threshold", low_score_threshold)
        data.setdefault("evidence_strong_score_threshold", evidence_strong_score_threshold)
        data.setdefault("topic_consistency_threshold", topic_consistency_threshold)
        data.setdefault("dedup_similarity_threshold", dedup_similarity_threshold)
        data.setdefault("rewrite_retry_limit", rewrite_retry_limit)
        data.setdefault("memory_retrieval_prompt_limit", memory_retrieval_prompt_limit)
        data.setdefault("memory_retrieval_state_limit", memory_retrieval_state_limit)
        data.setdefault("memory_retrieval_rag_limit", memory_retrieval_rag_limit)
        data.setdefault("memory_retrieval_tool_limit", memory_retrieval_tool_limit)
        data.setdefault("memory_retrieval_token_budget", memory_retrieval_token_budget)
        data.setdefault("memory_retrieval_semantic_top_k", memory_retrieval_semantic_top_k)
        data.setdefault("memory_retrieval_episodic_keywords", memory_retrieval_episodic_keywords)
        data.setdefault("memory_retrieval_procedural_keywords", memory_retrieval_procedural_keywords)
        data.setdefault("memory_injection_prompt_limit", memory_injection_prompt_limit)
        data.setdefault("memory_injection_state_limit", memory_injection_state_limit)
        data.setdefault("memory_injection_tool_limit", memory_injection_tool_limit)
        data.setdefault("memory_injection_rag_limit", memory_injection_rag_limit)
        data.setdefault("memory_injection_token_budget", memory_injection_token_budget)
        data.setdefault("memory_governance_low_confidence_threshold", memory_governance_low_confidence_threshold)
        data.setdefault("memory_governance_low_stability_threshold", memory_governance_low_stability_threshold)
        data.setdefault("memory_conflict_supersede_margin", memory_conflict_supersede_margin)
        data.setdefault("memory_conflict_merge_similarity_threshold", memory_conflict_merge_similarity_threshold)
        data.setdefault("memory_promotion_preference_promote_count", memory_promotion_preference_promote_count)
        data.setdefault("memory_promotion_behavior_promote_count", memory_promotion_behavior_promote_count)
        data.setdefault("memory_promotion_low_quiz_threshold", memory_promotion_low_quiz_threshold)
        data.setdefault("memory_recommendation_low_mastery_threshold", memory_recommendation_low_mastery_threshold)
        data.setdefault(
            "memory_recommendation_review_priority_threshold",
            memory_recommendation_review_priority_threshold,
        )
        data.setdefault("mastery_quiz_super_high_threshold", mastery_quiz_super_high_threshold)
        data.setdefault("mastery_quiz_high_threshold", mastery_quiz_high_threshold)
        data.setdefault("mastery_quiz_mid_threshold", mastery_quiz_mid_threshold)
        data.setdefault("mastery_quiz_low_threshold", mastery_quiz_low_threshold)
        data.setdefault("mastery_weak_signal_quiz_threshold", mastery_weak_signal_quiz_threshold)
        data.setdefault("mastery_review_priority_base_mastery", mastery_review_priority_base_mastery)
        data.setdefault("mastery_review_priority_low_quiz_threshold", mastery_review_priority_low_quiz_threshold)
        data.setdefault("mastery_review_priority_low_quiz_bonus", mastery_review_priority_low_quiz_bonus)
        data.setdefault("mastery_review_priority_weak_signal_bonus", mastery_review_priority_weak_signal_bonus)
        data.setdefault("mastery_review_priority_low_evidence_threshold", mastery_review_priority_low_evidence_threshold)
        data.setdefault("mastery_review_priority_low_evidence_bonus", mastery_review_priority_low_evidence_bonus)
        data.setdefault("mastery_review_priority_negative_signal_bonus", mastery_review_priority_negative_signal_bonus)
        data.setdefault("mastery_review_priority_negative_signal_cap", mastery_review_priority_negative_signal_cap)
        data.setdefault("mastery_review_priority_high_mastery_threshold", mastery_review_priority_high_mastery_threshold)
        data.setdefault("mastery_review_priority_high_mastery_bonus", mastery_review_priority_high_mastery_bonus)
        data.setdefault("consolidation_minimum_duplicate_group_size", consolidation_minimum_duplicate_group_size)
        data.setdefault("consolidation_max_conflicts", consolidation_max_conflicts)
        data.setdefault("consolidation_confirmed_explicitness", consolidation_confirmed_explicitness)
        data.setdefault("consolidation_inferred_explicitness", consolidation_inferred_explicitness)
        data.setdefault("consolidation_recency_window_seconds", consolidation_recency_window_seconds)
        data.setdefault("orchestrator_confirmed_confidence_threshold", orchestrator_confirmed_confidence_threshold)
        super().__init__(**data)

    def safe_dump(self) -> Dict[str, Any]:
        if hasattr(self, "model_dump"):
            data = self.model_dump(mode="json")
        else:  # pragma: no cover - compatibility path.
            data = self.dict()  # type: ignore[attr-defined]
        if data.get("openai", {}).get("api_key"):
            data["openai"]["api_key"] = "***"
        if data.get("qdrant", {}).get("api_key"):
            data["qdrant"]["api_key"] = "***"
        if data.get("internal_api_token"):
            data["internal_api_token"] = "***"
        return data

    def policy_settings(self):
        from learning_agent_service.config.policies import PolicySettings, WorkflowUnderstandingPolicyConfig
        from learning_agent_service.memory.consolidation import ConsolidationPolicyConfig
        from learning_agent_service.memory.conflict import MemoryConflictPolicyConfig
        from learning_agent_service.memory.governance import MemoryGovernancePolicyConfig
        from learning_agent_service.memory.injection import MemoryInjectionPolicyConfig
        from learning_agent_service.memory.mastery import MasteryPolicyConfig
        from learning_agent_service.memory.orchestrator import MemoryOrchestratorPolicyConfig
        from learning_agent_service.memory.promotion import PromotionConfig
        from learning_agent_service.memory.retrieval import RetrievalPolicyConfig
        from learning_agent_service.memory.recommend import MemoryRecommendationPolicyConfig
        from learning_agent_service.rag.evidence import EvidenceGovernanceConfig
        from learning_agent_service.rag.hybrid import HybridRetrieverConfig
        from learning_agent_service.rag.retrieval import RRFConfig
        from learning_agent_service.rag.rewrite import QueryRewriteConfig

        return PolicySettings(
            workflow_understanding=WorkflowUnderstandingPolicyConfig(
                intent_confidence_threshold=self.intent_confidence_threshold,
                reference_resolution_confidence_threshold=self.reference_resolution_confidence_threshold,
                metadata_filter_confidence_threshold=self.metadata_filter_confidence_threshold,
            ),
            memory_retrieval=RetrievalPolicyConfig(
                prompt_limit=self.memory_retrieval_prompt_limit,
                state_limit=self.memory_retrieval_state_limit,
                rag_limit=self.memory_retrieval_rag_limit,
                tool_limit=self.memory_retrieval_tool_limit,
                token_budget=self.memory_retrieval_token_budget,
                semantic_top_k=self.memory_retrieval_semantic_top_k,
                episodic_keywords=self.memory_retrieval_episodic_keywords,
                procedural_keywords=self.memory_retrieval_procedural_keywords,
            ),
            memory_injection=MemoryInjectionPolicyConfig(
                prompt_limit=self.memory_injection_prompt_limit,
                state_limit=self.memory_injection_state_limit,
                tool_limit=self.memory_injection_tool_limit,
                rag_limit=self.memory_injection_rag_limit,
                token_budget=self.memory_injection_token_budget,
            ),
            memory_governance=MemoryGovernancePolicyConfig(
                low_confidence_threshold=self.memory_governance_low_confidence_threshold,
                low_stability_threshold=self.memory_governance_low_stability_threshold,
            ),
            memory_conflict=MemoryConflictPolicyConfig(
                supersede_margin=self.memory_conflict_supersede_margin,
                merge_similarity_threshold=self.memory_conflict_merge_similarity_threshold,
            ),
            memory_promotion=PromotionConfig(
                preference_promote_count=self.memory_promotion_preference_promote_count,
                behavior_promote_count=self.memory_promotion_behavior_promote_count,
                low_quiz_threshold=self.memory_promotion_low_quiz_threshold,
            ),
            memory_recommendation=MemoryRecommendationPolicyConfig(
                low_mastery_threshold=self.memory_recommendation_low_mastery_threshold,
                review_priority_threshold=self.memory_recommendation_review_priority_threshold,
            ),
            mastery=MasteryPolicyConfig(
                quiz_super_high_threshold=self.mastery_quiz_super_high_threshold,
                quiz_high_threshold=self.mastery_quiz_high_threshold,
                quiz_mid_threshold=self.mastery_quiz_mid_threshold,
                quiz_low_threshold=self.mastery_quiz_low_threshold,
                weak_signal_quiz_threshold=self.mastery_weak_signal_quiz_threshold,
                review_priority_base_mastery=self.mastery_review_priority_base_mastery,
                review_priority_low_quiz_threshold=self.mastery_review_priority_low_quiz_threshold,
                review_priority_low_quiz_bonus=self.mastery_review_priority_low_quiz_bonus,
                review_priority_weak_signal_bonus=self.mastery_review_priority_weak_signal_bonus,
                review_priority_low_evidence_threshold=self.mastery_review_priority_low_evidence_threshold,
                review_priority_low_evidence_bonus=self.mastery_review_priority_low_evidence_bonus,
                review_priority_negative_signal_bonus=self.mastery_review_priority_negative_signal_bonus,
                review_priority_negative_signal_cap=self.mastery_review_priority_negative_signal_cap,
                review_priority_high_mastery_threshold=self.mastery_review_priority_high_mastery_threshold,
                review_priority_high_mastery_bonus=self.mastery_review_priority_high_mastery_bonus,
            ),
            consolidation=ConsolidationPolicyConfig(
                minimum_duplicate_group_size=self.consolidation_minimum_duplicate_group_size,
                max_conflicts=self.consolidation_max_conflicts,
                confirmed_explicitness=self.consolidation_confirmed_explicitness,
                inferred_explicitness=self.consolidation_inferred_explicitness,
                recency_window_seconds=self.consolidation_recency_window_seconds,
            ),
            orchestrator=MemoryOrchestratorPolicyConfig(
                confirmed_confidence_threshold=self.orchestrator_confirmed_confidence_threshold,
            ),
            evidence_governance=EvidenceGovernanceConfig(
                low_score_threshold=self.low_score_threshold,
                strong_score_threshold=self.evidence_strong_score_threshold,
                dedup_similarity_threshold=self.dedup_similarity_threshold,
                topic_consistency_threshold=self.topic_consistency_threshold,
                min_items=self.evidence_min_n,
                max_items=self.evidence_top_n,
            ),
            hybrid_retriever=HybridRetrieverConfig(
                dense_top_k=self.dense_top_k,
                sparse_top_k=self.sparse_top_k,
                metadata_top_k=self.metadata_top_k,
                rrf_k=self.rrf_k,
                rerank_top_k=self.rerank_top_k,
                metadata_filter_confidence_threshold=self.metadata_filter_confidence_threshold,
            ),
            rrf=RRFConfig(
                k=self.rrf_k,
                route_weights={
                    "dense": self.rrf_dense_weight,
                    "sparse": self.rrf_sparse_weight,
                    "metadata": self.rrf_metadata_weight,
                },
            ),
            query_rewrite=QueryRewriteConfig(
                llm_enabled=self.enable_llm_query_rewrite,
                short_query_max_chars=self.llm_query_rewrite_min_query_length,
                low_confidence_threshold=self.llm_query_rewrite_low_confidence_threshold,
                llm_retry_limit=self.rewrite_retry_limit,
                llm_model=self.llm_query_rewrite_model or self.openai.responses_model,
                llm_temperature=self.llm_query_rewrite_temperature,
                hyde_enabled=self.enable_hyde_sparse_retrieval,
                hyde_model=self.hyde_sparse_retrieval_model or self.openai.responses_model,
                hyde_temperature=self.hyde_sparse_retrieval_temperature,
            ),
        )


ServiceSettings = Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_settings() -> Settings:
    return get_settings()
