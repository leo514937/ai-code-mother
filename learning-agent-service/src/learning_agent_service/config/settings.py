"""Environment-driven settings for the standalone learning agent service.

The module keeps a small compatibility surface for early integration:
- ``Settings`` / ``ServiceSettings`` remain available.
- ``get_settings`` remains memoized.
- Nested settings classes can be imported directly by infrastructure factories.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional

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


class OpenAISettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    organization: Optional[str] = None
    project: Optional[str] = None
    timeout_seconds: int = 30
    max_retries: int = 2
    responses_model: str = "gpt-5.4"


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
    rerank_top_k: int = 15
    evidence_top_n: int = 6
    evidence_min_n: int = 4
    low_score_threshold: float = 0.18
    topic_consistency_threshold: float = 0.35
    dedup_similarity_threshold: float = 0.82
    rewrite_retry_limit: int = 1

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


ServiceSettings = Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_settings() -> Settings:
    return get_settings()
