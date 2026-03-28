from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from learning_agent_service.config import Settings, get_settings
from learning_agent_service.domain import ChatTurnCommand, KnowledgeSearchRequest, TurnUnderstandingRequest, TurnUnderstandingResult
from learning_agent_service.domain.enums import IntentType, OutputStyle, TurnDecision
from learning_agent_service.domain.protocols import (
    AnswerComposerPort,
    FinalizerPort,
    MemoryServicePort,
    ModelGatewayPort,
    RAGOrchestratorPort,
    SessionContextPort,
    ToolExecutorPort,
    ToolPlannerPort,
    ToolResultNormalizerPort,
)
from learning_agent_service.infrastructure.db.factories import InfrastructureClients, build_infrastructure_clients
from learning_agent_service.infrastructure.db.openai_client import OpenAIRuntime
from learning_agent_service.infrastructure.db.qdrant import QdrantRuntime
from learning_agent_service.infrastructure.repositories import (
    AdapterStatus,
    DurableLearningPlanStore,
    DurablePreferenceStore,
    DurableTopicMasteryStore,
    LearningPlanRepository,
    NoOpSemanticMemoryStore,
    OutboxAsyncLogStore,
    OutboxRepository,
    RedisSessionContextStore,
    RuntimeComponentMode,
    RuntimeDependencyStatus,
    RuntimeProfile,
    TopicMasteryRepository,
    UserPreferenceRepository,
)
from learning_agent_service.infrastructure.repositories.in_memory import (
    InMemoryAsyncLogStore,
    InMemorySessionContextStore,
    InMemoryTopicMasteryStore,
)
from learning_agent_service.memory.service import MemoryService
from learning_agent_service.rag.models import KnowledgeChunk
from learning_agent_service.rag.heuristics import HeuristicModelGateway
from learning_agent_service.rag.service import DEFAULT_KNOWLEDGE_CHUNKS, HybridRAGOrchestrator
from learning_agent_service.tools.service import (
    AnswerComposer,
    Finalizer,
    ToolExecutor,
    ToolPlanner,
    ToolResultNormalizer,
)


@dataclass(frozen=True)
class RepositoryBundle:
    outbox: Optional[OutboxRepository] = None
    preferences: Optional[UserPreferenceRepository] = None
    learning_plans: Optional[LearningPlanRepository] = None
    topic_mastery: Optional[TopicMasteryRepository] = None


@dataclass(frozen=True)
class UnderstandingDeps:
    model_gateway: ModelGatewayPort
    status: AdapterStatus


@dataclass(frozen=True)
class RagDeps:
    rag_orchestrator: RAGOrchestratorPort
    status: AdapterStatus


@dataclass(frozen=True)
class MemoryDeps:
    session_context_store: SessionContextPort
    mastery_store: object
    async_log_store: object
    memory_service: MemoryServicePort
    preference_store: object | None = None
    learning_plan_store: object | None = None
    semantic_memory_store: object | None = None
    statuses: tuple[AdapterStatus, ...] = ()


@dataclass(frozen=True)
class ToolDeps:
    planner: ToolPlannerPort
    executor: ToolExecutorPort
    result_normalizer: ToolResultNormalizerPort


@dataclass(frozen=True)
class StreamingDeps:
    answer_composer: AnswerComposerPort
    finalizer: FinalizerPort


@dataclass
class ApplicationRuntime:
    settings: Settings
    infrastructure_clients: InfrastructureClients
    repositories: RepositoryBundle
    runtime_dependency_status: RuntimeDependencyStatus
    runtime_profile: RuntimeProfile
    understanding: UnderstandingDeps
    rag: RagDeps
    memory: MemoryDeps
    tools: ToolDeps
    streaming: StreamingDeps

    @property
    def session_context_store(self) -> SessionContextPort:
        return self.memory.session_context_store

    @property
    def mastery_store(self) -> object:
        return self.memory.mastery_store

    @property
    def async_log_store(self) -> object:
        return self.memory.async_log_store

    @property
    def model_gateway(self) -> ModelGatewayPort:
        return self.understanding.model_gateway

    @property
    def rag_orchestrator(self) -> RAGOrchestratorPort:
        return self.rag.rag_orchestrator

    @property
    def memory_service(self) -> MemoryServicePort:
        return self.memory.memory_service

    @property
    def tool_planner(self) -> ToolPlannerPort:
        return self.tools.planner

    @property
    def tool_executor(self) -> ToolExecutorPort:
        return self.tools.executor

    @property
    def tool_result_normalizer(self) -> ToolResultNormalizerPort:
        return self.tools.result_normalizer

    @property
    def answer_composer(self) -> AnswerComposerPort:
        return self.streaming.answer_composer

    @property
    def finalizer(self) -> FinalizerPort:
        return self.streaming.finalizer

@dataclass(frozen=True)
class AppDependencies:
    runtime: ApplicationRuntime

    @property
    def container(self) -> ApplicationRuntime:
        return self.runtime


@dataclass
class OpenAIBackedModelGateway:
    runtime: OpenAIRuntime
    fallback: ModelGatewayPort

    def classify_turn(self, request: TurnUnderstandingRequest) -> TurnUnderstandingResult:
        heuristic_result = self.fallback.classify_turn(request)
        try:
            model_result = self._classify_with_openai(request.command)
        except Exception:
            return heuristic_result
        return self._merge_with_fallback(request.command, heuristic_result, model_result)

    def _classify_with_openai(self, command: ChatTurnCommand) -> TurnUnderstandingResult:
        client = self.runtime.client
        responses = getattr(client, "responses", None)
        if responses is None or not hasattr(responses, "create"):
            raise RuntimeError("OpenAI runtime does not expose Responses API")

        prompt = {
            "message": command.message,
            "topic_hint": command.topic_hint,
            "response_mode": command.response_mode.value if command.response_mode else None,
            "history_summary": command.history_summary,
            "client_context": command.client_context,
        }
        response = responses.create(
            model=self.runtime.default_model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You classify a learning-agent turn. "
                                "Return strict JSON with keys: intent, decision, confidence, requested_output_style, slots."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(prompt, ensure_ascii=False)}],
                },
            ],
            temperature=0,
            max_output_tokens=200,
        )
        payload = json.loads(_extract_response_text(response))

        intent = _safe_intent(payload.get("intent"))
        decision = _safe_decision(payload.get("decision"), intent)
        style = _safe_style(payload.get("requested_output_style"), command.response_mode)
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        slots = payload.get("slots", {})
        if not isinstance(slots, dict):
            slots = {}

        return TurnUnderstandingResult(
            intent=intent,
            decision=decision,
            intent_confidence=max(0.0, min(confidence, 1.0)),
            requested_output_style=style,
            slots=slots,
        )

    def _merge_with_fallback(
        self,
        command: ChatTurnCommand,
        heuristic: TurnUnderstandingResult,
        model_result: TurnUnderstandingResult,
    ) -> TurnUnderstandingResult:
        message = command.message or ""
        contains_cjk = any("\u4e00" <= char <= "\u9fff" for char in message)
        model_is_default_explain = model_result.intent == IntentType.EXPLAIN and model_result.decision in {
            TurnDecision.DIRECT_ANSWER,
            TurnDecision.RETRIEVE_THEN_ANSWER,
        }
        heuristic_is_specific = heuristic.intent not in {None, IntentType.EXPLAIN}
        heuristic_is_better = heuristic.intent_confidence >= model_result.intent_confidence + 0.12

        if heuristic_is_specific and (
            model_is_default_explain
            or heuristic.decision == TurnDecision.TOOL_THEN_ANSWER
            or heuristic.decision == TurnDecision.CLARIFY
            or (contains_cjk and heuristic.intent in {IntentType.QUIZ, IntentType.STUDY_PLAN, IntentType.FOLLOW_UP})
            or heuristic_is_better
        ):
            return heuristic

        merged_slots = dict(heuristic.slots)
        merged_slots.update(model_result.slots)
        return model_result.model_copy(
            update={
                "slots": merged_slots,
                "requested_output_style": model_result.requested_output_style or heuristic.requested_output_style,
            }
        )


def build_dependencies(settings: Settings | None = None) -> AppDependencies:
    resolved = settings or get_settings()
    infra = build_infrastructure_clients(
        settings=resolved,
        allow_partial=resolved.allow_in_memory_fallback,
    )
    repositories = _build_repository_bundle(infra)

    understanding = _build_understanding_deps(resolved, infra)
    rag = _build_rag_deps(resolved, infra)
    memory = _build_memory_deps(resolved, infra, repositories)
    tools = _build_tool_deps(rag.rag_orchestrator)
    streaming = _build_streaming_deps(resolved)

    adapter_statuses = (
        understanding.status,
        rag.status,
        *memory.statuses,
        _adapter_status("postgres", infra.postgres is not None, "real"),
        _adapter_status("redis", infra.redis is not None, "real"),
        _adapter_status("qdrant", infra.qdrant is not None, "real"),
        _adapter_status("openai", infra.openai is not None, "real"),
    )
    runtime_dependency_status = RuntimeDependencyStatus(
        adapters=tuple(adapter_statuses),
        bootstrap_errors=tuple(infra.bootstrap_errors),
    )
    runtime_profile = _build_runtime_profile(resolved, runtime_dependency_status)

    runtime = ApplicationRuntime(
        settings=resolved,
        infrastructure_clients=infra,
        repositories=repositories,
        runtime_dependency_status=runtime_dependency_status,
        runtime_profile=runtime_profile,
        understanding=understanding,
        rag=rag,
        memory=memory,
        tools=tools,
        streaming=streaming,
    )
    return AppDependencies(runtime=runtime)


def _build_understanding_deps(
    settings: Settings,
    infra: InfrastructureClients,
) -> UnderstandingDeps:
    model_gateway, status = _build_model_gateway(settings, infra)
    return UnderstandingDeps(model_gateway=model_gateway, status=status)


def _build_rag_deps(
    settings: Settings,
    infra: InfrastructureClients,
) -> RagDeps:
    rag_orchestrator, status = _build_rag_orchestrator(settings, infra)
    return RagDeps(rag_orchestrator=rag_orchestrator, status=status)


def _build_memory_deps(
    settings: Settings,
    infra: InfrastructureClients,
    repositories: RepositoryBundle,
) -> MemoryDeps:
    session_context_store, session_status = _build_session_context_store(settings, infra)
    mastery_store, mastery_status = _build_mastery_store(settings, repositories)
    async_log_store, async_log_status = _build_async_log_store(settings, repositories)
    preference_store, preference_status = _build_preference_store(repositories)
    learning_plan_store, learning_plan_status = _build_learning_plan_store(repositories)
    semantic_memory_store, semantic_status = _build_semantic_memory_store(settings, infra)

    memory_service = MemoryService(
        session_store=session_context_store,
        mastery_store=mastery_store,
        async_log_store=async_log_store,
        settings=settings,
        preference_store=preference_store,
        learning_plan_store=learning_plan_store,
        semantic_memory_store=semantic_memory_store,
    )
    return MemoryDeps(
        session_context_store=session_context_store,
        mastery_store=mastery_store,
        async_log_store=async_log_store,
        memory_service=memory_service,
        preference_store=preference_store,
        learning_plan_store=learning_plan_store,
        semantic_memory_store=semantic_memory_store,
        statuses=(session_status, mastery_status, async_log_status, preference_status, learning_plan_status, semantic_status),
    )


def _build_tool_deps(rag_orchestrator: RAGOrchestratorPort) -> ToolDeps:
    planner = ToolPlanner()
    executor = ToolExecutor(
        search_knowledge_fn=lambda topic, limit=5: rag_orchestrator.search_knowledge(
            KnowledgeSearchRequest(topic=topic, limit=limit)
        ).model_dump(mode="json"),
        get_knowledge_detail_fn=rag_orchestrator.get_knowledge_detail,
    )
    return ToolDeps(
        planner=planner,
        executor=executor,
        result_normalizer=ToolResultNormalizer(),
    )


def _build_streaming_deps(settings: Settings) -> StreamingDeps:
    return StreamingDeps(
        answer_composer=AnswerComposer(),
        finalizer=Finalizer(settings=settings),
    )


def _build_model_gateway(
    settings: Settings,
    infra: InfrastructureClients,
) -> tuple[ModelGatewayPort, AdapterStatus]:
    fallback = HeuristicModelGateway()
    if settings.prefer_real_adapters and infra.openai is not None:
        return (
            OpenAIBackedModelGateway(runtime=infra.openai, fallback=fallback),
            AdapterStatus(
                name="model_gateway",
                mode="real",
                ready=True,
                details={
                    "backend": "openai_responses",
                    "fallback": "heuristic",
                    "model": infra.openai.default_model,
                },
            ),
        )
    return (
        fallback,
        AdapterStatus(
            name="model_gateway",
            mode="fallback",
            ready=True,
            details={"backend": "heuristic", "reason": "openai_unavailable_or_disabled"},
        ),
    )


def _build_rag_orchestrator(
    settings: Settings,
    infra: InfrastructureClients,
) -> tuple[HybridRAGOrchestrator, AdapterStatus]:
    load_error: Optional[Exception] = None
    if settings.prefer_real_adapters and infra.qdrant is not None:
        chunks: tuple[KnowledgeChunk, ...] = ()
        try:
            chunks = _load_qdrant_knowledge_chunks(infra.qdrant)
        except Exception as exc:  # pragma: no cover - defensive fallback
            load_error = exc
        if chunks:
            return (
                HybridRAGOrchestrator(settings=settings, knowledge_chunks=chunks),
                AdapterStatus(
                    name="rag_runtime",
                    mode="real",
                    ready=True,
                    details={
                        "backend": "qdrant_snapshot",
                        "runtime_mode": "snapshot",
                        "knowledge_collection": infra.qdrant.knowledge_collection,
                        "chunk_count": len(chunks),
                    },
                ),
            )
        if load_error is not None and not settings.allow_in_memory_fallback:
            raise RuntimeError("Qdrant knowledge runtime is unavailable and in-memory fallback is disabled") from load_error
        if not chunks and not settings.allow_in_memory_fallback:
            raise RuntimeError("Qdrant knowledge runtime is unavailable and in-memory fallback is disabled")
    return (
        HybridRAGOrchestrator(settings=settings, knowledge_chunks=DEFAULT_KNOWLEDGE_CHUNKS),
        AdapterStatus(
            name="rag_runtime",
            mode="fallback",
            ready=True,
            details={
                "backend": "in_memory_chunks",
                "runtime_mode": "fallback",
                "reason": "qdrant_unavailable_empty_or_disabled",
                **({"fallback_from": "qdrant", "error": type(load_error).__name__} if load_error is not None else {}),
            },
        ),
    )


def _build_repository_bundle(infra: InfrastructureClients) -> RepositoryBundle:
    if infra.postgres is None:
        return RepositoryBundle()

    session_factory = infra.postgres.session_factory
    return RepositoryBundle(
        outbox=OutboxRepository(session_factory),
        preferences=UserPreferenceRepository(session_factory),
        learning_plans=LearningPlanRepository(session_factory),
        topic_mastery=TopicMasteryRepository(session_factory),
    )


def _load_qdrant_knowledge_chunks(runtime: QdrantRuntime) -> tuple[KnowledgeChunk, ...]:
    client = runtime.client
    scroll = getattr(client, "scroll", None)
    if not callable(scroll):
        return ()

    loaded: list[KnowledgeChunk] = []
    next_offset: Any = None
    while True:
        page = scroll(
            collection_name=runtime.knowledge_collection,
            limit=128,
            with_payload=True,
            with_vectors=False,
            offset=next_offset,
        )
        points, next_offset = _normalize_scroll_page(page)
        for point in points:
            chunk = _point_to_knowledge_chunk(point)
            if chunk is not None:
                loaded.append(chunk)
        if not next_offset:
            break
    return tuple(loaded)


def _normalize_scroll_page(page: Any) -> tuple[Sequence[Any], Any]:
    if isinstance(page, tuple) and len(page) == 2:
        return page[0] or (), page[1]
    points = getattr(page, "points", None)
    next_offset = getattr(page, "next_page_offset", None)
    if points is not None:
        return points or (), next_offset
    if isinstance(page, Mapping):
        return page.get("points", ()) or (), page.get("next_page_offset")
    return (), None


def _point_to_knowledge_chunk(point: Any) -> Optional[KnowledgeChunk]:
    payload = getattr(point, "payload", None)
    if payload is None and isinstance(point, Mapping):
        payload = point.get("payload")
    if not isinstance(payload, Mapping):
        return None

    chunk_id = payload.get("chunk_id") or getattr(point, "id", None) or (
        point.get("id") if isinstance(point, Mapping) else None
    )
    text = payload.get("text") or payload.get("content")
    document_id = payload.get("document_id") or payload.get("doc_id") or payload.get("source_id")
    if not chunk_id or not text or not document_id:
        return None

    return KnowledgeChunk(
        chunk_id=str(chunk_id),
        document_id=str(document_id),
        text=str(text),
        title=str(payload.get("title") or chunk_id),
        category=_optional_str(payload.get("category")),
        subcategory=_optional_str(payload.get("subcategory")),
        difficulty=_optional_str(payload.get("difficulty")),
        source_type=_optional_str(payload.get("source_type")),
        chunk_type=_optional_str(payload.get("chunk_type")),
        version=_optional_str(payload.get("version")),
        tags=tuple(str(tag) for tag in payload.get("tags", ()) if tag),
        metadata={
            key: value
            for key, value in payload.items()
            if key
            not in {
                "chunk_id",
                "document_id",
                "doc_id",
                "source_id",
                "text",
                "content",
                "title",
                "category",
                "subcategory",
                "difficulty",
                "source_type",
                "chunk_type",
                "version",
                "tags",
            }
        },
    )


def _build_session_context_store(
    settings: Settings,
    infra: InfrastructureClients,
) -> tuple[SessionContextPort, AdapterStatus]:
    if settings.prefer_real_adapters and infra.redis is not None:
        return (
            RedisSessionContextStore(infra.redis),
            AdapterStatus(
                name="session_context_store",
                mode="real",
                ready=True,
                details={"backend": "redis", "truth_boundary": "short_term_session", "supports_load_any": True},
            ),
        )
    if not settings.allow_in_memory_fallback:
        raise RuntimeError("Redis session context store is unavailable and in-memory fallback is disabled")
    return (
        InMemorySessionContextStore(),
        AdapterStatus(
            name="session_context_store",
            mode="fallback",
            ready=True,
            details={"backend": "in_memory", "reason": "redis_unavailable_or_disabled", "supports_load_any": True},
        ),
    )


def _build_mastery_store(settings: Settings, repositories: RepositoryBundle) -> tuple[object, AdapterStatus]:
    if settings.prefer_real_adapters and repositories.topic_mastery is not None:
        return (
            DurableTopicMasteryStore(repositories.topic_mastery),
            AdapterStatus(
                name="topic_mastery_store",
                mode="real",
                ready=True,
                details={"backend": "postgres", "truth_boundary": "durable_fact"},
            ),
        )
    if not settings.allow_in_memory_fallback:
        raise RuntimeError("Postgres topic mastery store is unavailable and in-memory fallback is disabled")
    return (
        InMemoryTopicMasteryStore(),
        AdapterStatus(
            name="topic_mastery_store",
            mode="fallback",
            ready=True,
            details={"backend": "in_memory", "reason": "postgres_unavailable_or_disabled"},
        ),
    )


def _build_async_log_store(settings: Settings, repositories: RepositoryBundle) -> tuple[object, AdapterStatus]:
    if settings.prefer_real_adapters and repositories.outbox is not None:
        return (
            OutboxAsyncLogStore(repositories.outbox),
            AdapterStatus(
                name="async_log_store",
                mode="real",
                ready=True,
                details={"backend": "postgres_outbox", "path": "outbox", "payload_shape": "typed_or_legacy_mapping"},
            ),
        )
    if not settings.allow_in_memory_fallback:
        raise RuntimeError("Outbox async log store is unavailable and in-memory fallback is disabled")
    return (
        InMemoryAsyncLogStore(),
        AdapterStatus(
            name="async_log_store",
            mode="fallback",
            ready=True,
            details={"backend": "in_memory", "reason": "postgres_outbox_unavailable_or_disabled"},
        ),
    )


def _build_preference_store(
    repositories: RepositoryBundle,
) -> tuple[Optional[DurablePreferenceStore], AdapterStatus]:
    repository = repositories.preferences
    if repository is not None:
        return (
            DurablePreferenceStore(repository),
            AdapterStatus(
                name="preference_store",
                mode="real",
                ready=True,
                details={"backend": "postgres", "wired": True},
            ),
        )
    return (
        None,
        AdapterStatus(
            name="preference_store",
            mode="unavailable",
            ready=False,
            details={"backend": "none", "wired": False},
        ),
    )


def _build_learning_plan_store(
    repositories: RepositoryBundle,
) -> tuple[Optional[DurableLearningPlanStore], AdapterStatus]:
    repository = repositories.learning_plans
    if repository is not None:
        return (
            DurableLearningPlanStore(repository),
            AdapterStatus(
                name="learning_plan_store",
                mode="real",
                ready=True,
                details={"backend": "postgres", "wired": True},
            ),
        )
    return (
        None,
        AdapterStatus(
            name="learning_plan_store",
            mode="unavailable",
            ready=False,
            details={"backend": "none", "wired": False},
        ),
    )


def _build_semantic_memory_store(
    settings: Settings,
    infra: InfrastructureClients,
) -> tuple[NoOpSemanticMemoryStore, AdapterStatus]:
    requested_backend = "qdrant" if settings.prefer_real_adapters and infra.qdrant is not None else "none"
    return (
        NoOpSemanticMemoryStore(),
        AdapterStatus(
            name="semantic_memory_store",
            mode="noop",
            ready=True,
            details={
                "backend": "noop",
                "requested_backend": requested_backend,
                "reason": "explicit_noop_adapter_until_real_semantic_memory_backend_is_integrated",
            },
        ),
    )


def _build_runtime_profile(settings: Settings, runtime_status: RuntimeDependencyStatus) -> RuntimeProfile:
    component_modes = tuple(
        RuntimeComponentMode(
            name=adapter.name,
            mode=adapter.mode,
            ready=adapter.ready,
            details=dict(adapter.details),
        )
        for adapter in runtime_status.adapters
    )
    if not settings.prefer_real_adapters:
        profile_name = "dev_fallback"
    elif all(component.mode == "real" and component.ready for component in component_modes):
        profile_name = "full"
    else:
        profile_name = "partial"
    return RuntimeProfile(
        name=profile_name,
        components=component_modes,
        bootstrap_errors=runtime_status.bootstrap_errors,
    )


def _adapter_status(name: str, available: bool, mode: str) -> AdapterStatus:
    resolved_mode = mode if available else "unavailable"
    return AdapterStatus(
        name=name,
        mode=resolved_mode,
        ready=available,
        details={},
    )


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    def walk(value: Any) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, Mapping):
            for key in ("output_text", "text", "content"):
                candidate = value.get(key)
                result = walk(candidate)
                if result:
                    return result
            for child in value.values():
                result = walk(child)
                if result:
                    return result
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in value:
                result = walk(child)
                if result:
                    return result
        return None

    if hasattr(response, "model_dump"):
        dumped = response.model_dump()
        text = walk(dumped)
        if text:
            return text
    text = walk(response)
    if text:
        return text
    raise RuntimeError("No textual classification output returned by OpenAI runtime")


def _safe_intent(value: Any) -> IntentType:
    try:
        return IntentType(str(value))
    except Exception:
        return IntentType.EXPLAIN


def _safe_style(value: Any, fallback: Optional[OutputStyle]) -> Optional[OutputStyle]:
    if value is None:
        return fallback
    try:
        return OutputStyle(str(value))
    except Exception:
        return fallback


def _safe_decision(value: Any, intent: IntentType) -> TurnDecision:
    try:
        return TurnDecision(str(value))
    except Exception:
        if intent in {IntentType.QUIZ, IntentType.STUDY_PLAN, IntentType.RECOMMEND}:
            return TurnDecision.TOOL_THEN_ANSWER
        if intent in {
            IntentType.EXPLAIN,
            IntentType.COMPARE,
            IntentType.INTERVIEW,
            IntentType.CODE,
            IntentType.SUMMARY,
            IntentType.FOLLOW_UP,
        }:
            return TurnDecision.RETRIEVE_THEN_ANSWER
        return TurnDecision.DIRECT_ANSWER


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
