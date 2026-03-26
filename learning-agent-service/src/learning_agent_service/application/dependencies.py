from __future__ import annotations

from dataclasses import dataclass

from learning_agent_service.config import Settings, get_settings
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
from learning_agent_service.infrastructure.repositories.in_memory import (
    InMemoryAsyncLogStore,
    InMemorySessionContextStore,
    InMemoryTopicMasteryStore,
)
from learning_agent_service.memory.service import MemoryService
from learning_agent_service.rag.service import HeuristicModelGateway, HybridRAGOrchestrator
from learning_agent_service.tools.service import (
    AnswerComposer,
    Finalizer,
    ToolExecutor,
    ToolPlanner,
    ToolResultNormalizer,
)


@dataclass
class ServiceContainer:
    settings: Settings
    session_context_store: SessionContextPort
    mastery_store: InMemoryTopicMasteryStore
    async_log_store: InMemoryAsyncLogStore
    model_gateway: ModelGatewayPort
    rag_orchestrator: RAGOrchestratorPort
    memory_service: MemoryServicePort
    tool_planner: ToolPlannerPort
    tool_executor: ToolExecutorPort
    tool_result_normalizer: ToolResultNormalizerPort
    answer_composer: AnswerComposerPort
    finalizer: FinalizerPort


@dataclass
class AppDependencies:
    container: ServiceContainer


def build_dependencies(settings: Settings | None = None) -> AppDependencies:
    resolved = settings or get_settings()
    session_context_store = InMemorySessionContextStore()
    mastery_store = InMemoryTopicMasteryStore()
    async_log_store = InMemoryAsyncLogStore()
    model_gateway = HeuristicModelGateway()
    rag_orchestrator = HybridRAGOrchestrator(settings=resolved)
    memory_service = MemoryService(
        session_store=session_context_store,
        mastery_store=mastery_store,
        async_log_store=async_log_store,
        settings=resolved,
    )
    tool_planner = ToolPlanner()
    tool_executor = ToolExecutor()
    tool_result_normalizer = ToolResultNormalizer()
    answer_composer = AnswerComposer()
    finalizer = Finalizer(settings=resolved)
    container = ServiceContainer(
        settings=resolved,
        session_context_store=session_context_store,
        mastery_store=mastery_store,
        async_log_store=async_log_store,
        model_gateway=model_gateway,
        rag_orchestrator=rag_orchestrator,
        memory_service=memory_service,
        tool_planner=tool_planner,
        tool_executor=tool_executor,
        tool_result_normalizer=tool_result_normalizer,
        answer_composer=answer_composer,
        finalizer=finalizer,
    )
    return AppDependencies(container=container)
