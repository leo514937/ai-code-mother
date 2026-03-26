from __future__ import annotations

from typing import Iterable, Optional, Protocol

from .contracts import (
    ChatTurnCommand,
    Citation,
    GraphRuntimeMeta,
    NormalizedToolResult,
    PersistentSessionContext,
    RagResult,
    RetrievalPlan,
    SseEnvelope,
    ToolExecutionResult,
    ToolSelection,
    TurnUnderstandingResult,
)
from .state import GraphState


class ModelGatewayPort(Protocol):
    def classify_turn(self, command: ChatTurnCommand, state: GraphState) -> TurnUnderstandingResult:
        ...


class SessionContextPort(Protocol):
    def load(self, session_id: str, user_id: str) -> PersistentSessionContext:
        ...

    def save(self, context: PersistentSessionContext, runtime: GraphRuntimeMeta) -> None:
        ...


class RAGOrchestratorPort(Protocol):
    def rewrite_query(self, state: GraphState) -> RetrievalPlan:
        ...

    def run(self, state: GraphState) -> RagResult:
        ...

    def build_citations(self, state: GraphState) -> Iterable[Citation]:
        ...


class MemoryServicePort(Protocol):
    def persist_session(self, state: GraphState) -> GraphState:
        ...

    def update_mastery(self, state: GraphState) -> GraphState:
        ...

    def recommend_next(self, state: GraphState) -> GraphState:
        ...


class ToolPlannerPort(Protocol):
    def plan(self, state: GraphState) -> ToolSelection:
        ...


class ToolExecutorPort(Protocol):
    def execute(self, selection: ToolSelection, state: GraphState) -> ToolExecutionResult:
        ...


class ToolResultNormalizerPort(Protocol):
    def normalize(self, result: ToolExecutionResult, state: GraphState) -> NormalizedToolResult:
        ...


class AnswerComposerPort(Protocol):
    def compose(self, state: GraphState) -> GraphState:
        ...


class FinalizerPort(Protocol):
    def finalize(self, state: GraphState) -> Optional[SseEnvelope]:
        ...
