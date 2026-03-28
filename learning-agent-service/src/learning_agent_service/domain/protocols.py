from __future__ import annotations

from typing import Iterable, Optional, Protocol

from .contracts import (
    AnswerComposeRequest,
    AnswerComposeResult,
    ChatTurnCommand,
    Citation,
    CitationBuildRequest,
    ErrorPayload,
    EvidenceEvaluationRequest,
    EvidencePack,
    FinalPayload,
    GraphRuntimeMeta,
    HybridRecallResult,
    HybridRetrieveRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    MasteryUpdateCommand,
    MasteryUpdateResult,
    NormalizedToolResult,
    PersistSessionCommand,
    PersistSessionResult,
    PersistentSessionContext,
    QueryRewriteRequest,
    RecommendationQuery,
    RecommendationResult,
    ReferenceResolutionRequest,
    ReferenceResolutionResult,
    RetrievalPlan,
    SseEnvelope,
    ToolExecutionCommand,
    ToolExecutionResult,
    ToolNormalizationRequest,
    ToolPlanningRequest,
    ToolSelection,
    TurnUnderstandingRequest,
    TurnUnderstandingResult,
)


class ModelGatewayPort(Protocol):
    def classify_turn(self, request: TurnUnderstandingRequest) -> TurnUnderstandingResult:
        ...


class SessionContextPort(Protocol):
    def load(self, session_id: str, user_id: str) -> PersistentSessionContext:
        ...

    def save(self, context: PersistentSessionContext, runtime: GraphRuntimeMeta) -> None:
        ...

    def load_any(self, session_id: str) -> PersistentSessionContext:
        ...


class RAGOrchestratorPort(Protocol):
    def resolve_reference(self, request: ReferenceResolutionRequest) -> ReferenceResolutionResult:
        ...

    def rewrite_query(self, request: QueryRewriteRequest) -> RetrievalPlan:
        ...

    def hybrid_retrieve(self, request: HybridRetrieveRequest) -> HybridRecallResult:
        ...

    def evaluate_evidence(self, request: EvidenceEvaluationRequest) -> EvidencePack:
        ...

    def build_citations(self, request: CitationBuildRequest) -> Iterable[Citation]:
        ...

    def search_knowledge(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        ...

    def get_knowledge_detail(self, topic: str) -> dict:
        ...


class MemoryServicePort(Protocol):
    def persist_session(self, command: PersistSessionCommand) -> PersistSessionResult:
        ...

    def update_mastery(self, command: MasteryUpdateCommand) -> MasteryUpdateResult:
        ...

    def recommend_next(self, query: RecommendationQuery) -> Optional[RecommendationResult]:
        ...

    def load_any(self, session_id: str) -> PersistentSessionContext:
        ...


class ToolPlannerPort(Protocol):
    def plan(self, request: ToolPlanningRequest) -> Optional[ToolSelection]:
        ...

    def plan_from_name(self, tool_name: str, input_payload: dict) -> ToolSelection:
        ...


class ToolExecutorPort(Protocol):
    def execute(self, command: ToolExecutionCommand) -> ToolExecutionResult:
        ...


class ToolResultNormalizerPort(Protocol):
    def normalize(self, request: ToolNormalizationRequest) -> NormalizedToolResult:
        ...


class AnswerComposerPort(Protocol):
    def compose(self, request: AnswerComposeRequest) -> AnswerComposeResult:
        ...


class FinalizerPort(Protocol):
    def finalize(
        self,
        *,
        terminal_event: str,
        payload: FinalPayload | ErrorPayload | dict,
        runtime: GraphRuntimeMeta,
    ) -> Optional[SseEnvelope]:
        ...
