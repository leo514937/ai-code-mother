from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .memory import (
    MemoryCandidate,
    MemoryInjectionPlan,
    MemoryTrace,
    MemoryRecord,
    MemoryRetrievalPlan,
    MemoryUpdateEvent,
    MemoryWritePlan,
    RetrievedMemoryPack,
)
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
    history_summary: Optional[str] = None
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
    tier: str = "strong"
    citation_chunk_id: Optional[str] = None
    source_chunk_id: Optional[str] = None
    parent_chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidencePack(CoreModel):
    items: List[EvidenceItem] = Field(default_factory=list)
    discard_summary: Dict[str, Any] = Field(default_factory=dict)
    top_scores: List[float] = Field(default_factory=list)
    evidence_status: str = "EMPTY"
    strong_items: List[EvidenceItem] = Field(default_factory=list)
    weak_items: List[EvidenceItem] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class HybridRecallCandidate(CoreModel):
    chunk_id: str
    score: float = 0.0
    content: Optional[str] = None
    document_id: Optional[str] = None
    chunk_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    channels: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)


class HybridRecallResult(CoreModel):
    dense_hits: List[HybridRecallCandidate] = Field(default_factory=list)
    sparse_hits: List[HybridRecallCandidate] = Field(default_factory=list)
    metadata_hits: List[HybridRecallCandidate] = Field(default_factory=list)
    fused_hits: List[HybridRecallCandidate] = Field(default_factory=list)
    reranked_hits: List[HybridRecallCandidate] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    extra: Dict[str, Any] = Field(default_factory=dict)


class RagResult(CoreModel):
    status: RagStatus = RagStatus.EMPTY
    evidence_pack: Optional[EvidencePack] = None
    citations: List[Citation] = Field(default_factory=list)
    evidence_status: str = "EMPTY"
    retrieval_strategy: str = "dense+sparse+metadata->rrf->rerank->evidence"
    metrics: Dict[str, Any] = Field(default_factory=dict)
    extra: Dict[str, Any] = Field(default_factory=dict)


class AnswerPlan(CoreModel):
    sections: List[str] = Field(default_factory=list)
    lead: Optional[str] = None
    ending_prompt: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class PlanStep(CoreModel):
    step_id: str = ""
    goal: str = ""
    expected_output: Optional[str] = None
    allowed_tools: List[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "low"
    requires_approval: bool = False


class StepResult(CoreModel):
    step_id: str = ""
    status: Literal["success", "failed", "skipped", "need_approval"] = "skipped"
    tools_used: List[str] = Field(default_factory=list)
    observations: List[str] = Field(default_factory=list)
    result: Dict[str, Any] | str | None = None
    error: Optional[str] = None
    next_action: Optional[str] = None


class PlanExecutionSummary(CoreModel):
    status: Literal["completed", "partial", "failed", "need_approval"] = "partial"
    completed_steps: int = 0
    total_steps: int = 0
    key_findings: List[str] = Field(default_factory=list)
    final_decision: Optional[str] = None


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


class TurnUnderstandingRequest(CoreModel):
    command: ChatTurnCommand
    persistent: "PersistentSessionContext"


class ReferenceResolutionRequest(CoreModel):
    raw_query: str
    current_topic: Optional[str] = None
    recent_entities: List[str] = Field(default_factory=list)
    clarification_result: Dict[str, Any] = Field(default_factory=dict)
    pending_clarification: Optional[ClarificationCard] = None
    history_summary: Optional[str] = None
    topic_hint: Optional[str] = None


class QueryRewriteRequest(CoreModel):
    raw_query: str
    intent: Optional[IntentType] = None
    requested_output_style: Optional[OutputStyle] = None
    reference_resolution: Optional[ReferenceResolutionResult] = None
    current_topic: Optional[str] = None
    topic_hint: Optional[str] = None
    intent_confidence: float = 0.0
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    base_filters: Dict[str, Any] = Field(default_factory=dict)


class HybridRetrieveRequest(CoreModel):
    plan: RetrievalPlan


class EvidenceEvaluationRequest(CoreModel):
    plan: RetrievalPlan
    hybrid_recall: HybridRecallResult
    intent: Optional[IntentType] = None
    requested_output_style: Optional[OutputStyle] = None


class CitationBuildRequest(CoreModel):
    evidence_pack: EvidencePack


class KnowledgeSearchRequest(CoreModel):
    topic: str
    limit: int = 5
    category: Optional[str] = None
    retrieval_filters: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResult(CoreModel):
    matches: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_pack: Optional[EvidencePack] = None
    citations: List[Citation] = Field(default_factory=list)
    retrieval_strategy: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ToolPlanningRequest(CoreModel):
    raw_query: str
    decision: TurnDecision
    intent: Optional[IntentType] = None
    slots: Dict[str, Any] = Field(default_factory=dict)
    current_topic: Optional[str] = None


class ToolExecutionCommand(CoreModel):
    selection: ToolSelection


class ToolNormalizationRequest(CoreModel):
    result: ToolExecutionResult


class PersistSessionCommand(CoreModel):
    trace_id: str = ""
    session_id: str
    turn_id: str
    user_id: str
    workflow_version: str = "learn-agent/v1"
    raw_query: str
    answer_text: str
    resolved_topic: Optional[str] = None
    intent: Optional[IntentType] = None
    requested_output_style: Optional[OutputStyle] = None
    tool_name: Optional[str] = None
    quiz_score: Optional[float] = None
    request_ts: datetime
    persistent: "PersistentSessionContext"
    final_confidence: float = 0.0


class MemoryUpdateSummary(CoreModel):
    current_topic: Optional[str] = None
    updated_preferences: Dict[str, Any] = Field(default_factory=dict)
    weak_topics: List[str] = Field(default_factory=list)
    topic_mastery: Dict[str, Any] = Field(default_factory=dict)
    semantic_memory: Dict[str, Any] = Field(default_factory=dict)
    open_questions: List[str] = Field(default_factory=list)
    confirmed_facts: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    summary_version: int = 0
    summary_updated_at: Optional[datetime] = None
    memory_trace_id: Optional[str] = None
    write_status: str = "success"
    write_targets: List[str] = Field(default_factory=list)
    decision_reasons: List[str] = Field(default_factory=list)
    degraded_parts: List[str] = Field(default_factory=list)
    retryable_failures: List[str] = Field(default_factory=list)
    permanent_failures: List[str] = Field(default_factory=list)
    memory_write: Optional["MemoryWriteResult"] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class MemoryWriteTargetResult(CoreModel):
    target: str
    status: Literal["success", "degraded", "retryable_failure", "permanent_failure", "skipped"] = "success"
    reason: Optional[str] = None
    retryable: bool = False
    error: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class MemoryWriteResult(CoreModel):
    trace_id: str = ""
    idempotency_key: str = ""
    session_id: str = ""
    turn_id: str = ""
    user_id: str = ""
    operation: str = ""
    status: Literal["success", "partial_success", "degraded", "pending_compensation", "permanent_failure"] = "success"
    write_targets: List[str] = Field(default_factory=list)
    target_results: List[MemoryWriteTargetResult] = Field(default_factory=list)
    decision_reasons: List[str] = Field(default_factory=list)
    degraded_parts: List[str] = Field(default_factory=list)
    retryable_failures: List[str] = Field(default_factory=list)
    permanent_failures: List[str] = Field(default_factory=list)
    compensation_required: bool = False
    extra: Dict[str, Any] = Field(default_factory=dict)


class PersistSessionResult(CoreModel):
    updated_context: "PersistentSessionContext"
    memory_updates: MemoryUpdateSummary = Field(default_factory=MemoryUpdateSummary)
    memory_write: Optional[MemoryWriteResult] = None


class MasteryUpdateCommand(CoreModel):
    trace_id: str = ""
    session_id: str
    user_id: str
    turn_id: str
    raw_query: str
    answer_text: str
    resolved_topic: Optional[str] = None
    intent: Optional[IntentType] = None
    requested_output_style: Optional[OutputStyle] = None
    tool_name: Optional[str] = None
    quiz_score: Optional[float] = None
    request_ts: datetime
    persistent: "PersistentSessionContext"
    memory_updates: MemoryUpdateSummary = Field(default_factory=MemoryUpdateSummary)


class MasteryUpdateResult(CoreModel):
    topic_mastery: Dict[str, Any] = Field(default_factory=dict)
    semantic_index: Dict[str, Any] = Field(default_factory=dict)
    metrics_patch: Dict[str, Any] = Field(default_factory=dict)
    memory_write: Optional[MemoryWriteResult] = None


class RecommendationResult(CoreModel):
    topic: str
    reason: str
    source: str
    priority: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RecommendationQuery(CoreModel):
    user_id: str
    current_topic: Optional[str] = None
    recent_topics: List[str] = Field(default_factory=list)
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    active_plan_id: Optional[str] = None
    learning_mode: bool = False


class RetrievalSummary(CoreModel):
    semantic_query: Optional[str] = None
    keyword_query: Optional[str] = None
    retrieval_filters: Dict[str, Any] = Field(default_factory=dict)
    retrieval_strategy: Optional[str] = None
    retrieval_hit_count: int = 0
    evidence_used_count: int = 0
    evidence_status: str = "EMPTY"
    evidence_strong_count: int = 0
    evidence_weak_count: int = 0


class MemoryUsedItemSummary(CoreModel):
    memory_id: str = ""
    memory_type: Optional[str] = None
    scope: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 0.0


class MemoryUsedSummary(CoreModel):
    used: bool = False
    total_memories: int = 0
    retrieval_reason: Optional[str] = None
    total_token_estimate: int = 0
    prompt_memories: List[MemoryUsedItemSummary] = Field(default_factory=list)
    state_memories: List[MemoryUsedItemSummary] = Field(default_factory=list)
    tool_memories: List[MemoryUsedItemSummary] = Field(default_factory=list)
    rag_memories: List[MemoryUsedItemSummary] = Field(default_factory=list)


class AnswerComposeRequest(CoreModel):
    raw_query: str
    requested_output_style: Optional[OutputStyle] = None
    rag_result: Optional[RagResult] = None
    tool_result: Optional[NormalizedToolResult] = None
    recommendation: Optional[RecommendationResult] = None
    plan_summary: Optional[PlanExecutionSummary] = None
    memory_injection_plan: Optional[MemoryInjectionPlan] = None


class AnswerComposeResult(CoreModel):
    answer_text: str
    confidence: float = 0.0


class PersistentSessionContext(CoreModel):
    current_topic: Optional[str] = None
    recent_entities: List[str] = Field(default_factory=list)
    clarification_result: Dict[str, Any] = Field(default_factory=dict)
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    last_retrieval_topic: Optional[str] = None
    active_plan_id: Optional[str] = None
    learning_mode: bool = False
    history_summary: Optional[str] = None
    open_questions: List[str] = Field(default_factory=list)
    confirmed_facts: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    summary_version: int = 0
    summary_updated_at: Optional[datetime] = None
    pending_clarification: Optional[ClarificationCard] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class TurnRuntimeState(CoreModel):
    raw_query: str
    decision: TurnDecision = TurnDecision.DIRECT_ANSWER
    intent: Optional[IntentType] = None
    intent_confidence: float = 0.0
    requested_output_style: Optional[OutputStyle] = None
    task_complexity: Literal["simple", "complex"] = "simple"
    execution_mode: Literal["auto", "simple", "plan_execute"] = "auto"
    risk_level: Literal["low", "medium", "high"] = "low"
    slots: Dict[str, Any] = Field(default_factory=dict)
    reference_resolution: Optional[ReferenceResolutionResult] = None
    clarification_card: Optional[ClarificationCard] = None
    retrieval_plan: Optional[RetrievalPlan] = None
    hybrid_recall: Optional[HybridRecallResult] = None
    evidence_pack: Optional[EvidencePack] = None
    citations: List[Citation] = Field(default_factory=list)
    answer_plan: Optional[AnswerPlan] = None
    tool_plan: Optional[ToolSelection] = None
    raw_tool_result: Optional[ToolExecutionResult] = None
    tool_result: Optional[NormalizedToolResult] = None
    plan: List[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    current_step: Optional[PlanStep] = None
    step_results: List[StepResult] = Field(default_factory=list)
    need_replan: bool = False
    replan_reason: Optional[str] = None
    need_human_approval: bool = False
    approval_request: Dict[str, Any] = Field(default_factory=dict)
    final_task_summary: Optional[PlanExecutionSummary] = None
    sensory_memory: Dict[str, Any] = Field(default_factory=dict)
    short_term_window: List[Dict[str, Any]] = Field(default_factory=list)
    retrieved_memory_pack: Optional[RetrievedMemoryPack] = None
    memory_candidates: List[MemoryCandidate] = Field(default_factory=list)
    memory_write_plan: Optional[MemoryWritePlan] = None
    memory_injection_plan: Optional[MemoryInjectionPlan] = None
    final_answer: Optional[str] = None
    rag_result: Optional[RagResult] = None
    recommendation: Optional[RecommendationResult] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class GraphRuntimeMeta(CoreModel):
    trace_id: str
    session_id: str
    turn_id: str
    workflow_version: str
    request_ts: datetime
    user_id: str
    response_mode: Optional[OutputStyle] = None
    topic_hint: Optional[str] = None
    history_summary: Optional[str] = None
    client_context: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[ErrorInfo] = Field(default_factory=list)
    degrade_to: Optional[str] = None
    terminal_event: Optional[TerminalEvent] = None
    emitted_events: List[SseEnvelope] = Field(default_factory=list)
    memory_updates: MemoryUpdateSummary = Field(default_factory=MemoryUpdateSummary)
    memory_trace: Optional[MemoryTrace] = None
    session_persisted: bool = False
    extra: Dict[str, Any] = Field(default_factory=dict)


class FinalPayload(CoreModel):
    answer_text: str
    citations: List[Citation] = Field(default_factory=list)
    used_tools: List[str] = Field(default_factory=list)
    resolved_topic: Optional[str] = None
    retrieval_strategy: Optional[str] = None
    grounding_status: Literal["grounded", "weakly_grounded", "not_grounded"] = "not_grounded"
    retrieval_summary: Optional[RetrievalSummary] = None
    memory_used_summary: Optional[MemoryUsedSummary] = None
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


GraphRuntimeMeta.model_rebuild()
TurnUnderstandingRequest.model_rebuild()
PersistSessionResult.model_rebuild()
MasteryUpdateResult.model_rebuild()
MemoryUpdateSummary.model_rebuild()
MemoryWriteTargetResult.model_rebuild()
MemoryWriteResult.model_rebuild()
