from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import IntentType, OutputStyle, RagStatus, ToolExecutionStatus, TurnDecision
from .errors import ErrorInfo, TerminalEvent, WorkflowErrorCode


class CoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class ChatTurnCommand(CoreModel):
    trace_id: str
    session_id: str
    turn_id: str
    user_id: str
    message: str
    response_mode: Optional[OutputStyle] = None
    topic_hint: Optional[str] = None
    client_context: Dict[str, Any] = Field(default_factory=dict)


class ClarificationOption(CoreModel):
    id: str
    label: str
    value: Optional[str] = None
    description: Optional[str] = None


class ClarificationCard(CoreModel):
    card_id: str
    question: str
    options: List[ClarificationOption] = Field(default_factory=list)
    ambiguity_type: Optional[str] = None
    source_turn_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class ReferenceResolutionResult(CoreModel):
    resolved: bool = False
    confidence: float = 0.0
    resolved_entity: Optional[str] = None
    candidate_entities: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class RetrievalPlan(CoreModel):
    semantic_query: str = ""
    keyword_query: str = ""
    retrieval_filters: Dict[str, Any] = Field(default_factory=dict)
    preferred_chunk_types: List[str] = Field(default_factory=list)
    need_retry_rewrite: bool = False
    reasoning_notes: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class Citation(CoreModel):
    chunk_id: str
    document_id: Optional[str] = None
    source_type: Optional[str] = None
    version: Optional[str] = None
    score: Optional[float] = None
    title: Optional[str] = None
    locator: Optional[str] = None


class EvidenceItem(CoreModel):
    chunk_id: str
    content: str
    score: float = 0.0
    document_id: Optional[str] = None
    chunk_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidencePack(CoreModel):
    items: List[EvidenceItem] = Field(default_factory=list)
    discard_summary: Dict[str, Any] = Field(default_factory=dict)
    top_scores: List[float] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class RagResult(CoreModel):
    status: RagStatus = RagStatus.EMPTY
    evidence_pack: Optional[EvidencePack] = None
    citations: List[Citation] = Field(default_factory=list)
    retrieval_strategy: str = "dense+sparse+metadata->rrf->rerank->evidence"
    metrics: Dict[str, Any] = Field(default_factory=dict)
    extra: Dict[str, Any] = Field(default_factory=dict)


class AnswerPlan(CoreModel):
    sections: List[str] = Field(default_factory=list)
    lead: Optional[str] = None
    ending_prompt: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ToolSelection(CoreModel):
    tool_name: Optional[str] = None
    should_execute: bool = False
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(CoreModel):
    status: ToolExecutionStatus = ToolExecutionStatus.SKIPPED
    tool_name: Optional[str] = None
    output_payload: Dict[str, Any] = Field(default_factory=dict)
    degraded_to: Optional[str] = None
    error: Optional[WorkflowErrorCode] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class NormalizedToolResult(CoreModel):
    status: ToolExecutionStatus = ToolExecutionStatus.SKIPPED
    tool_name: Optional[str] = None
    normalized_output: Dict[str, Any] = Field(default_factory=dict)
    used_tools: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class TurnUnderstandingResult(CoreModel):
    decision: TurnDecision = TurnDecision.DIRECT_ANSWER
    intent: IntentType = IntentType.EXPLAIN
    intent_confidence: float = 0.0
    requested_output_style: Optional[OutputStyle] = None
    reference_resolution: Optional[ReferenceResolutionResult] = None
    retrieval_plan: Optional[RetrievalPlan] = None
    clarification_card: Optional[ClarificationCard] = None
    slots: Dict[str, Any] = Field(default_factory=dict)
    extra: Dict[str, Any] = Field(default_factory=dict)


class PersistentSessionContext(CoreModel):
    current_topic: Optional[str] = None
    recent_entities: List[str] = Field(default_factory=list)
    clarification_result: Dict[str, Any] = Field(default_factory=dict)
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    last_retrieval_topic: Optional[str] = None
    active_plan_id: Optional[str] = None
    learning_mode: bool = False
    extra: Dict[str, Any] = Field(default_factory=dict)


class TurnRuntimeState(CoreModel):
    raw_query: str
    understanding_result: Optional[TurnUnderstandingResult] = None
    retrieval_plan: Optional[RetrievalPlan] = None
    rag_result: Optional[RagResult] = None
    answer_plan: Optional[AnswerPlan] = None
    tool_plan: Optional[ToolSelection] = None
    tool_result: Optional[NormalizedToolResult] = None
    final_answer: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class GraphRuntimeMeta(CoreModel):
    trace_id: str
    session_id: str
    turn_id: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[ErrorInfo] = Field(default_factory=list)
    degrade_to: Optional[str] = None
    terminal_event: Optional[TerminalEvent] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class FinalPayload(CoreModel):
    answer_text: str
    citations: List[Citation] = Field(default_factory=list)
    used_tools: List[str] = Field(default_factory=list)
    resolved_topic: Optional[str] = None
    retrieval_strategy: Optional[str] = None
    memory_updates: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    intent: Optional[IntentType] = None
    requested_output_style: Optional[OutputStyle] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ErrorPayload(CoreModel):
    code: str
    message: str
    retryable: bool = False
    stage: str
    degraded_to: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class SseEnvelope(CoreModel):
    event_type: str
    trace_id: str
    session_id: str
    turn_id: str
    timestamp: datetime
    workflow_version: str
    payload: Dict[str, Any] = Field(default_factory=dict)
