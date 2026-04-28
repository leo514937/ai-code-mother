from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from learning_agent_service.domain import (
    GraphState,
    MemoryCandidate,
    MemoryInjectionPlan,
    MemoryRecord,
    MemoryRetrievalPlan,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryTargetStore,
    MemoryEdgeType,
    MemoryType,
    MemoryTrace,
    MemoryWritePlan,
    LongTermMemoryStore,
    RetrievedMemoryPack,
)
from learning_agent_service.domain.contracts import (
    MemoryUpdateSummary,
    PersistentSessionContext as DomainPersistentSessionContext,
    StepResult,
    TurnRuntimeState,
)
from learning_agent_service.domain.enums import IntentType
from learning_agent_service.memory.models import (
    ExplicitUserSignals,
    MemoryPromotionInput,
    MemoryPromotionResult,
    PersistentSessionContext as MemoryPersistentSessionContext,
    PreferenceProfileWrite,
    SemanticMemoryFact,
    TopicMasteryRecord,
    UserPreferenceProfile,
)
from learning_agent_service.memory.injection import MemoryInjectionPolicy
from learning_agent_service.memory.conflict import (
    MemoryConflictResolutionStrategy,
    MemoryConflictResolver,
)
from learning_agent_service.memory.retrieval import MemoryRetrievalPolicy
from learning_agent_service.memory.stores import (
    InMemoryEntityMemoryStore,
    InMemoryLongTermMemoryStore,
    InMemoryMasteryMemoryStore,
    InMemorySensoryMemoryBuffer,
    InMemoryShortTermMemoryStore,
)
from learning_agent_service.memory.summary import SessionSummaryService
from learning_agent_service.memory.promotion import MemoryPromotionPolicy
from learning_agent_service.memory.consolidation import MemoryConsolidationJob


@dataclass(frozen=True)
class MemoryOrchestratorPolicyConfig:
    confirmed_confidence_threshold: float = 0.8


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryOrchestrator:
    session_store: Any
    short_term_store: InMemoryShortTermMemoryStore = field(default_factory=InMemoryShortTermMemoryStore)
    entity_store: InMemoryEntityMemoryStore = field(default_factory=InMemoryEntityMemoryStore)
    long_term_store: LongTermMemoryStore = field(default_factory=InMemoryLongTermMemoryStore)
    trace_repository: Any = None
    mastery_store: Any = None
    sensory_buffer: InMemorySensoryMemoryBuffer = field(default_factory=InMemorySensoryMemoryBuffer)
    retrieval_policy: MemoryRetrievalPolicy = field(default_factory=MemoryRetrievalPolicy)
    injection_policy: MemoryInjectionPolicy = field(default_factory=MemoryInjectionPolicy)
    summary_service: SessionSummaryService = field(default_factory=SessionSummaryService)
    consolidation_job: MemoryConsolidationJob = field(default_factory=MemoryConsolidationJob)
    promotion_policy: MemoryPromotionPolicy = field(default_factory=MemoryPromotionPolicy)
    conflict_resolver: MemoryConflictResolver = field(default_factory=MemoryConflictResolver)
    policy: MemoryOrchestratorPolicyConfig = field(default_factory=MemoryOrchestratorPolicyConfig)

    def retrieve_for_state(self, state: GraphState) -> RetrievedMemoryPack:
        runtime = state["runtime"]
        turn = state["turn"]
        persistent = state["persistent"]
        trace = self._ensure_trace(runtime)
        self.sensory_buffer.ingest(
            runtime.turn_id,
            {
                "raw_query": turn.raw_query,
                "slots": dict(turn.slots),
                "intent": turn.intent.value if turn.intent else None,
                "requested_output_style": turn.requested_output_style.value if turn.requested_output_style else None,
            },
        )
        pack = self.retrieval_policy.retrieve(
            user_id=runtime.user_id,
            session_id=runtime.session_id,
            project_id=None,
            raw_query=turn.raw_query,
            intent=turn.intent.value if turn.intent else None,
            current_topic=persistent.current_topic,
            recent_entities=list(persistent.recent_entities),
            active_plan_id=persistent.active_plan_id,
            learning_mode=bool(persistent.learning_mode),
            history_summary=persistent.history_summary,
            response_mode=runtime.response_mode.value if runtime.response_mode else None,
            session_store=self.session_store,
            short_term_store=self.short_term_store,
            entity_store=self.entity_store,
            mastery_store=self.mastery_store,
            long_term_store=self.long_term_store,
        )
        trace.retrieved = self._unique_extend(trace.retrieved, list(pack.source_memory_ids))
        trace.total_memory_tokens = pack.total_token_estimate
        trace.user_id = runtime.user_id
        trace.extra = {
            **dict(trace.extra),
            "retrieval_policy": self._policy_snapshot()["retrieval"],
            "policy_snapshot": self._policy_snapshot(),
            "retrieval_counts": {
                "prompt": len(pack.prompt_memories),
                "state": len(pack.state_memories),
                "tool": len(pack.tool_memories),
                "rag": len(pack.rag_memories),
                "excluded": len(pack.excluded_memories),
            },
        }
        self._capture_qdrant_state(trace)
        state["runtime"] = runtime.model_copy(update={"memory_trace": trace})
        return pack

    def build_injection_plan(self, pack: RetrievedMemoryPack) -> MemoryInjectionPlan:
        return self.injection_policy.build(pack)

    def attach_to_state(self, state: GraphState, pack: RetrievedMemoryPack, injection: MemoryInjectionPlan) -> GraphState:
        runtime = state["runtime"]
        turn = state["turn"]
        trace = self._ensure_trace(runtime)
        trace.user_id = runtime.user_id
        client_context = dict(runtime.client_context)
        client_context.update(
            {
                "memory_prompt_count": len(injection.prompt_memories),
                "memory_state_count": len(injection.state_memories),
                "memory_tool_count": len(injection.tool_memories),
                "memory_rag_count": len(injection.rag_memories),
                "memory_retrieval_reason": pack.retrieval_reason,
            }
        )
        short_term_window = list(turn.short_term_window)
        short_term_window.extend(
            [
                {
                    "role": "system",
                    "content": mem.summary or str(mem.content),
                    "memory_id": mem.memory_id,
                    "memory_type": mem.type.value,
                }
                for mem in injection.prompt_memories[:2]
            ]
        )
        trace.injected = self._unique_extend(trace.injected, [mem.memory_id for mem in injection.prompt_memories])
        trace.skipped = self._unique_extend(trace.skipped, [mem.memory_id for mem in pack.excluded_memories])
        trace.extra = {
            **dict(trace.extra),
            "retrieval_reason": pack.retrieval_reason,
            "injection_policy": self._policy_snapshot()["injection"],
            "policy_snapshot": self._policy_snapshot(),
            "memory_counts": {
                "prompt": len(injection.prompt_memories),
                "state": len(injection.state_memories),
                "tool": len(injection.tool_memories),
                "rag": len(injection.rag_memories),
            },
        }
        state["turn"] = turn.model_copy(
            update={
                "retrieved_memory_pack": pack,
                "memory_injection_plan": injection,
                "short_term_window": short_term_window,
                "sensory_memory": {
                    **dict(turn.sensory_memory),
                    "retrieval_reason": pack.retrieval_reason,
                    "memory_source_ids": list(pack.source_memory_ids),
                },
            }
        )
        state["runtime"] = runtime.model_copy(
            update={
                "client_context": client_context,
                "history_summary": state["persistent"].history_summary or runtime.history_summary,
                "memory_trace": trace,
            }
        )
        return state

    def promote_from_state(self, state: GraphState) -> MemoryWritePlan:
        runtime = state["runtime"]
        turn = state["turn"]
        persistent = state["persistent"]
        trace = self._ensure_trace(runtime)
        trace.user_id = runtime.user_id
        explicit_signals = self._explicit_signals(turn, persistent)
        promotion_input = MemoryPromotionInput(
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            user_id=runtime.user_id,
            query=turn.raw_query,
            answer_text=turn.final_answer or "",
            resolved_topic=self._resolved_topic(state),
            intent=turn.intent.value if turn.intent else None,
            output_style=turn.requested_output_style.value if turn.requested_output_style else None,
            tool_name=turn.tool_result.tool_name if turn.tool_result else None,
            explicit_signals=explicit_signals,
            current_session=self._to_memory_context(persistent),
            current_preferences=self._current_preferences(persistent, runtime.user_id),
            current_mastery=self._current_mastery(state),
            quiz_score=self._quiz_score(turn),
            current_time=runtime.request_ts,
            extra={
                "clarification_result": dict(persistent.clarification_result),
                "learning_mode": bool(persistent.learning_mode),
                "open_questions": list(persistent.open_questions),
                "confirmed_facts": list(persistent.confirmed_facts),
                "next_steps": list(persistent.next_steps),
                "summary_version": persistent.summary_version,
            },
        )
        promotion_result = self.promotion_policy.evaluate(promotion_input)
        memory_candidates = self._build_candidates(state, promotion_input, promotion_result)
        governed_candidates = promotion_result.extra.get("governed_candidates", []) if promotion_result.extra else []
        memory_candidates.extend(list(governed_candidates))
        memory_candidates = self._dedupe_candidates(memory_candidates)
        memory_candidates = self.promotion_policy.govern_candidates(memory_candidates)
        trace.candidates = self._unique_extend(trace.candidates, [candidate.candidate_id for candidate in memory_candidates])
        trace.promoted = self._unique_extend(
            trace.promoted,
            [candidate.candidate_id for candidate in memory_candidates if candidate.should_promote],
        )
        trace.rejected = self._unique_extend(
            trace.rejected,
            [
                candidate.candidate_id
                for candidate in memory_candidates
                if not candidate.should_promote or candidate.governance_action in {"reject", "defer"}
            ],
        )
        trace.extra = {
            **dict(trace.extra),
            "governance_actions": {candidate.candidate_id: candidate.governance_action for candidate in memory_candidates},
            "memory_write_targets": [candidate.target_store.value for candidate in memory_candidates],
            "policy_snapshot": self._policy_snapshot(),
        }
        write_plan = MemoryWritePlan(
            candidates=memory_candidates,
            write_targets=sorted({candidate.target_store for candidate in memory_candidates}, key=lambda item: item.value),
            outbox_required=bool(promotion_result.outbox_events),
        )
        persistence_trace = self._persist_candidates(memory_candidates)
        trace.decision_reasons.update(persistence_trace.get("decision_reasons", {}))
        trace.conflict_ids = self._unique_extend(trace.conflict_ids, persistence_trace.get("conflict_ids", []))
        trace.deletion_job_ids = self._unique_extend(trace.deletion_job_ids, persistence_trace.get("deletion_job_ids", []))
        trace.skip_reasons.update(persistence_trace.get("skip_reasons", {}))
        trace.conflict_resolutions = list(trace.conflict_resolutions) + list(persistence_trace.get("conflict_resolutions", []))
        trace.qdrant_degraded = bool(trace.qdrant_degraded or persistence_trace.get("qdrant_degraded", False))
        self._capture_qdrant_state(trace)
        trace.extra = {
            **dict(trace.extra),
            "governance_actions": {candidate.candidate_id: candidate.governance_action for candidate in memory_candidates},
            "memory_write_targets": [candidate.target_store.value for candidate in memory_candidates],
            "decision_reasons": dict(trace.decision_reasons),
            "conflict_ids": list(trace.conflict_ids),
            "deletion_job_ids": list(trace.deletion_job_ids),
            "skip_reasons": dict(trace.skip_reasons),
            "qdrant_errors": list(persistence_trace.get("qdrant_errors", [])),
            "qdrant_degraded": trace.qdrant_degraded,
        }
        self.short_term_store.append_messages(
            runtime.session_id,
            [
                {
                    "role": "user",
                    "content": turn.raw_query,
                    "turn_id": runtime.turn_id,
                },
                {
                    "role": "assistant",
                    "content": turn.final_answer or "",
                    "turn_id": runtime.turn_id,
                },
            ],
        )
        self.short_term_store.save_task_context(
            runtime.session_id,
            {
                "current_topic": persistent.current_topic,
                "active_plan_id": persistent.active_plan_id,
                "summary_version": persistent.summary_version,
                "final_task_summary": turn.final_task_summary.model_dump(mode="json") if turn.final_task_summary else None,
            },
        )
        state["turn"] = turn.model_copy(update={"memory_candidates": memory_candidates, "memory_write_plan": write_plan})
        state["runtime"] = runtime.model_copy(update={"memory_trace": trace})
        self._persist_trace(trace)
        return write_plan

    def summarize_session(self, state: GraphState) -> GraphState:
        persistent = state["persistent"]
        turn = state["turn"]
        updated = self.summary_service.summarize(
            persistent,
            current_topic=self._resolved_topic(state),
            open_questions=list(persistent.open_questions),
            confirmed_facts=list(persistent.confirmed_facts),
            next_steps=list(persistent.next_steps),
            extra={"turn_id": state["runtime"].turn_id},
        )
        state["persistent"] = updated
        return state

    def consolidate(self, user_id: Optional[str] = None, scope: MemoryScope = MemoryScope.USER) -> List[MemoryRecord]:
        if user_id is not None and hasattr(self.long_term_store, "list_by_scope"):
            records = list(self.long_term_store.list_by_scope(user_id, scope))
        elif hasattr(self.long_term_store, "records"):
            records = list(getattr(self.long_term_store, "records").values())
        else:
            records = []
        original_records = {record.memory_id: record for record in records}
        records = list(self.consolidation_job.expire_or_supersede(records))
        for record in records:
            original = original_records.get(record.memory_id)
            if original is None or original.status != record.status or original.valid_until != record.valid_until:
                self.long_term_store.upsert(record)
        merged, conflicts, plans = self.consolidation_job.consolidate(records)
        for record in merged:
            self.long_term_store.upsert(record)
        for conflict in conflicts:
            for loser_id in conflict.loser_memory_ids:
                self.long_term_store.supersede(loser_id, conflict.winner_memory_id, conflict.reason)
        return merged

    def _persist_candidates(self, candidates: List[MemoryCandidate]) -> Dict[str, Any]:
        trace_updates: Dict[str, Any] = {
            "decision_reasons": {},
            "conflict_ids": [],
            "deletion_job_ids": [],
            "conflict_resolutions": [],
            "qdrant_errors": [],
            "skip_reasons": {},
            "qdrant_degraded": False,
        }
        for candidate in candidates:
            if not candidate.should_promote:
                trace_updates["skip_reasons"][candidate.candidate_id] = (
                    candidate.skip_reason or candidate.decision_reason or candidate.reason or candidate.governance_action
                )
                continue
            confirmed_threshold = self.policy.confirmed_confidence_threshold
            record = candidate.record.model_copy(
                update={
                    "status": MemoryStatus.CONFIRMED if candidate.confidence >= confirmed_threshold else MemoryStatus.INFERRED,
                    "updated_at": _utcnow(),
                }
            )
            trace_updates["decision_reasons"][candidate.candidate_id] = (
                candidate.decision_reason or candidate.governance_action or candidate.reason
            )
            if candidate.target_store == MemoryTargetStore.REDIS:
                self.short_term_store.save_task_context(record.session_id or record.user_id, dict(record.content))
            elif candidate.target_store in {MemoryTargetStore.POSTGRES, MemoryTargetStore.QDRANT}:
                resolution = self._resolve_conflicts(record)
                if resolution.strategy == MemoryConflictResolutionStrategy.REQUIRE_CONFIRMATION:
                    trace_updates["skip_reasons"][candidate.candidate_id] = resolution.reason
                    trace_updates["conflict_resolutions"].append(
                        {
                            "candidate_id": candidate.candidate_id,
                            "strategy": resolution.strategy.value,
                            "winner_memory_id": resolution.winner.memory_id if resolution.winner else None,
                            "conflict_ids": [item.memory_id for item in resolution.losers],
                            "reason": resolution.reason,
                        }
                    )
                    continue
                record_to_store = resolution.merged_record or resolution.winner
                stored_record = self.long_term_store.upsert(record_to_store)
                trace_updates["conflict_ids"].extend([loser.memory_id for loser in resolution.losers])
                trace_updates["conflict_resolutions"].append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "strategy": resolution.strategy.value,
                        "winner_memory_id": stored_record.memory_id,
                        "conflict_ids": [item.memory_id for item in resolution.losers],
                        "reason": resolution.reason,
                    }
                )
                if bool((stored_record.extra or {}).get("qdrant_degraded")):
                    trace_updates["qdrant_degraded"] = True
                if hasattr(self.long_term_store, "create_edge"):
                    for edge in resolution.edges:
                        self.long_term_store.create_edge(edge)
                if resolution.strategy in {
                    MemoryConflictResolutionStrategy.SUPERSEDE_OLD,
                    MemoryConflictResolutionStrategy.MERGE,
                }:
                    edge_type = (
                        MemoryEdgeType.MERGED_INTO
                        if resolution.strategy == MemoryConflictResolutionStrategy.MERGE
                        else MemoryEdgeType.SUPERSEDES
                    )
                    for loser in resolution.losers:
                        self.long_term_store.supersede(
                            loser.memory_id,
                            stored_record.memory_id,
                            resolution.reason,
                            edge_type=edge_type,
                        )
                if getattr(self.long_term_store, "last_qdrant_error", None):
                    trace_updates["qdrant_degraded"] = True
                    trace_updates.setdefault("qdrant_errors", []).append(str(self.long_term_store.last_qdrant_error))
            else:
                self.entity_store.upsert(record)
        trace_updates["conflict_ids"] = list(dict.fromkeys(trace_updates["conflict_ids"]))
        trace_updates["deletion_job_ids"] = list(dict.fromkeys(trace_updates["deletion_job_ids"]))
        trace_updates["qdrant_errors"] = list(dict.fromkeys(trace_updates["qdrant_errors"]))
        return trace_updates

    def _build_candidates(
        self,
        state: GraphState,
        promotion_input: MemoryPromotionInput,
        promotion_result: MemoryPromotionResult,
    ) -> List[MemoryCandidate]:
        turn = state["turn"]
        persistent = state["persistent"]
        runtime = state["runtime"]
        candidates: List[MemoryCandidate] = []

        if promotion_result.preference_patch:
            candidates.append(
                MemoryCandidate(
                    candidate_id=f"{runtime.user_id}:{runtime.turn_id}:preference",
                    should_promote=True,
                    memory_type=MemoryType.PREFERENCE,
                    target_store=MemoryTargetStore.POSTGRES,
                    confidence=0.92,
                    importance=0.75,
                    reason="用户偏好补丁",
                    source_turn_id=runtime.turn_id,
                    dedupe_key=f"{runtime.user_id}:preference:{promotion_input.resolved_topic or 'global'}",
                    conflict_check_key=f"{runtime.user_id}:preference",
                    record=MemoryRecord(
                        memory_id=f"{runtime.user_id}:{runtime.turn_id}:preference",
                        user_id=runtime.user_id,
                        session_id=runtime.session_id,
                        type=MemoryType.PREFERENCE,
                        scope=MemoryScope.USER,
                        status=MemoryStatus.CONFIRMED,
                        content=dict(promotion_result.preference_patch),
                        summary=(persistent.history_summary or turn.raw_query)[:200],
                        source_turn_id=runtime.turn_id,
                        confidence=0.92,
                        importance=0.75,
                        tags=["preference"],
                        entities=list(persistent.recent_entities),
                    ),
                )
            )

        if promotion_result.session_update.history_summary:
            candidates.append(
                MemoryCandidate(
                    candidate_id=f"{runtime.session_id}:summary:{promotion_result.session_update.summary_version}",
                    should_promote=True,
                    memory_type=MemoryType.SESSION_SUMMARY,
                    target_store=MemoryTargetStore.REDIS,
                    confidence=0.8,
                    importance=0.85,
                    reason="会话摘要更新",
                    source_turn_id=runtime.turn_id,
                    dedupe_key=f"{runtime.session_id}:summary",
                    conflict_check_key=f"{runtime.session_id}:summary",
                    record=MemoryRecord(
                        memory_id=f"{runtime.session_id}:summary:{promotion_result.session_update.summary_version}",
                        user_id=runtime.user_id,
                        session_id=runtime.session_id,
                        type=MemoryType.SESSION_SUMMARY,
                        scope=MemoryScope.SESSION,
                        status=MemoryStatus.ACTIVE,
                        content={
                            "history_summary": promotion_result.session_update.history_summary,
                            "open_questions": list(promotion_result.session_update.open_questions),
                            "confirmed_facts": list(promotion_result.session_update.confirmed_facts),
                            "next_steps": list(promotion_result.session_update.next_steps),
                        },
                        summary=promotion_result.session_update.history_summary,
                        source_turn_id=runtime.turn_id,
                        confidence=0.8,
                        importance=0.85,
                        tags=["session_summary"],
                        entities=list(persistent.recent_entities),
                    ),
                )
            )

        for fact in promotion_result.semantic_facts:
            candidates.append(
                MemoryCandidate(
                    candidate_id=fact.fact_id,
                    should_promote=True,
                    memory_type=MemoryType.SEMANTIC,
                    target_store=MemoryTargetStore.QDRANT,
                    confidence=float(fact.strength),
                    importance=min(1.0, float(fact.strength) + 0.15),
                    reason="语义事实沉淀",
                    source_turn_id=runtime.turn_id,
                    dedupe_key=fact.fact_id,
                    conflict_check_key=f"{runtime.user_id}:{fact.topic}:semantic",
                    record=MemoryRecord(
                        memory_id=fact.fact_id,
                        user_id=runtime.user_id,
                        session_id=runtime.session_id,
                        type=MemoryType.SEMANTIC,
                        scope=MemoryScope.USER,
                        status=MemoryStatus.CONFIRMED,
                        content=dict(fact.metadata),
                        summary=fact.content,
                        source_turn_id=runtime.turn_id,
                        confidence=float(fact.strength),
                        importance=min(1.0, float(fact.strength) + 0.15),
                        tags=[fact.fact_type, fact.topic],
                        entities=[fact.topic],
                    ),
                )
            )

        topic = promotion_input.resolved_topic or persistent.current_topic
        if topic:
            candidates.append(
                MemoryCandidate(
                    candidate_id=f"{runtime.user_id}:{topic}:entity",
                    should_promote=True,
                    memory_type=MemoryType.ENTITY,
                    target_store=MemoryTargetStore.POSTGRES,
                    confidence=0.75,
                    importance=0.8,
                    reason="主题实体更新",
                    source_turn_id=runtime.turn_id,
                    dedupe_key=f"{runtime.user_id}:{topic}:entity",
                    conflict_check_key=f"{runtime.user_id}:{topic}:entity",
                    record=MemoryRecord(
                        memory_id=f"{runtime.user_id}:{topic}:entity",
                        user_id=runtime.user_id,
                        session_id=runtime.session_id,
                        type=MemoryType.ENTITY,
                        scope=MemoryScope.USER,
                        status=MemoryStatus.ACTIVE,
                        content={
                            "current_topic": topic,
                            "learning_mode": persistent.learning_mode,
                            "active_plan_id": persistent.active_plan_id,
                        },
                        summary=topic,
                        source_turn_id=runtime.turn_id,
                        confidence=0.75,
                        importance=0.8,
                        tags=["entity", "topic"],
                        entities=[topic],
                    ),
                )
            )

        if turn.step_results:
            step_summaries = [self._step_brief(step) for step in turn.step_results]
            candidates.append(
                MemoryCandidate(
                    candidate_id=f"{runtime.user_id}:{runtime.turn_id}:procedural",
                    should_promote=True,
                    memory_type=MemoryType.PROCEDURAL,
                    target_store=MemoryTargetStore.POSTGRES,
                    confidence=0.7,
                    importance=0.7,
                    reason="复杂任务步骤经验沉淀",
                    source_turn_id=runtime.turn_id,
                    dedupe_key=f"{runtime.user_id}:{runtime.session_id}:procedural:{topic or 'task'}",
                    conflict_check_key=f"{runtime.user_id}:{topic or 'task'}:procedural",
                    record=MemoryRecord(
                        memory_id=f"{runtime.user_id}:{runtime.turn_id}:procedural",
                        user_id=runtime.user_id,
                        session_id=runtime.session_id,
                        type=MemoryType.PROCEDURAL,
                        scope=MemoryScope.USER,
                        status=MemoryStatus.INFERRED,
                        content={"steps": step_summaries},
                        summary="; ".join(step_summaries[:3]),
                        source_turn_id=runtime.turn_id,
                        confidence=0.7,
                        importance=0.7,
                        tags=["procedural", "plan_execute"],
                        entities=[topic] if topic else [],
                    ),
                )
            )

        if turn.final_task_summary is not None:
            candidates.append(
                MemoryCandidate(
                    candidate_id=f"{runtime.user_id}:{runtime.turn_id}:episodic",
                    should_promote=True,
                    memory_type=MemoryType.EPISODIC,
                    target_store=MemoryTargetStore.POSTGRES,
                    confidence=0.78,
                    importance=0.85,
                    reason="任务情节沉淀",
                    source_turn_id=runtime.turn_id,
                    dedupe_key=f"{runtime.user_id}:{runtime.session_id}:episodic:{runtime.turn_id}",
                    conflict_check_key=f"{runtime.user_id}:{topic or 'task'}:episodic",
                    record=MemoryRecord(
                        memory_id=f"{runtime.user_id}:{runtime.turn_id}:episodic",
                        user_id=runtime.user_id,
                        session_id=runtime.session_id,
                        type=MemoryType.EPISODIC,
                        scope=MemoryScope.SESSION,
                        status=MemoryStatus.ACTIVE,
                        content={
                            "summary": turn.final_task_summary.model_dump(mode="json"),
                            "answer": turn.final_answer,
                        },
                        summary=turn.final_task_summary.final_decision or turn.final_answer or turn.raw_query,
                        source_turn_id=runtime.turn_id,
                        confidence=0.78,
                        importance=0.85,
                        tags=["episodic", "plan_execute"],
                        entities=[topic] if topic else [],
                    ),
                )
            )

        if promotion_result.weak_topics:
            candidates.append(
                MemoryCandidate(
                    candidate_id=f"{runtime.user_id}:{topic or 'mastery'}:mastery",
                    should_promote=True,
                    memory_type=MemoryType.MASTERY,
                    target_store=MemoryTargetStore.POSTGRES,
                    confidence=0.72,
                    importance=0.9,
                    reason="掌握度变化",
                    source_turn_id=runtime.turn_id,
                    dedupe_key=f"{runtime.user_id}:{topic or 'mastery'}:mastery",
                    conflict_check_key=f"{runtime.user_id}:{topic or 'mastery'}:mastery",
                    record=MemoryRecord(
                        memory_id=f"{runtime.user_id}:{topic or 'mastery'}:mastery",
                        user_id=runtime.user_id,
                        session_id=runtime.session_id,
                        type=MemoryType.MASTERY,
                        scope=MemoryScope.USER,
                        status=MemoryStatus.ACTIVE,
                        content={"weak_topics": list(promotion_result.weak_topics)},
                        summary=f"weak:{','.join(promotion_result.weak_topics[:3])}",
                        source_turn_id=runtime.turn_id,
                        confidence=0.72,
                        importance=0.9,
                        tags=["mastery", "weak_topic"],
                        entities=list(promotion_result.weak_topics),
                    ),
                )
            )
        return candidates

    @staticmethod
    def _step_brief(step_result: StepResult) -> str:
        observations = "；".join(step_result.observations[:2]) if step_result.observations else ""
        return f"{step_result.step_id}:{step_result.status}" + (f"({observations})" if observations else "")

    @staticmethod
    def _quiz_score(turn: TurnRuntimeState) -> Optional[float]:
        tool_result = turn.tool_result
        if tool_result is None:
            return None
        payload = tool_result.normalized_output.get("data", {})
        if isinstance(payload, Mapping):
            score = payload.get("score")
            if isinstance(score, (int, float)):
                return float(score)
        return None

    @staticmethod
    def _resolved_topic(state: GraphState) -> Optional[str]:
        persistent = state["persistent"]
        turn = state["turn"]
        if persistent.current_topic:
            return persistent.current_topic
        if turn.reference_resolution and turn.reference_resolution.resolved_entity:
            return turn.reference_resolution.resolved_entity
        return turn.slots.get("topic") or turn.raw_query or None

    @staticmethod
    def _current_preferences(context: DomainPersistentSessionContext, user_id: str) -> Optional[UserPreferenceProfile]:
        preferences = dict(context.user_preferences)
        if not preferences:
            return None
        return UserPreferenceProfile(
            user_id=user_id,
            preferred_output_style=preferences.get("preferred_output_style") or preferences.get("answer_style"),
            answer_style_counter=preferences.get("answer_style_counter", {}),
            prefers_code_examples=bool(preferences.get("prefers_code_examples", False)),
            prefers_interview_mode=bool(preferences.get("prefers_interview_mode", False)),
            extra={key: value for key, value in preferences.items() if key not in {
                "preferred_output_style",
                "answer_style",
                "answer_style_counter",
                "prefers_code_examples",
                "prefers_interview_mode",
            }},
        )

    @staticmethod
    def _current_mastery(state: GraphState) -> Optional[TopicMasteryRecord]:
        topic = MemoryOrchestrator._resolved_topic(state)
        if not topic:
            return None
        runtime = state["runtime"]
        return TopicMasteryRecord(topic=topic, last_seen_at=runtime.request_ts)

    @staticmethod
    def _to_memory_context(context: DomainPersistentSessionContext) -> MemoryPersistentSessionContext:
        return MemoryPersistentSessionContext(
            current_topic=context.current_topic,
            recent_entities=tuple(context.recent_entities),
            clarification_result=dict(context.clarification_result),
            user_preferences=dict(context.user_preferences),
            last_retrieval_topic=context.last_retrieval_topic,
            active_plan_id=context.active_plan_id,
            learning_mode=bool(context.learning_mode),
            history_summary=context.history_summary,
            open_questions=tuple(context.open_questions),
            confirmed_facts=tuple(context.confirmed_facts),
            next_steps=tuple(context.next_steps),
            summary_version=context.summary_version,
            summary_updated_at=context.summary_updated_at,
            pending_clarification=context.pending_clarification.model_dump(mode="json") if context.pending_clarification else None,
            extra=dict(context.extra),
        )

    @staticmethod
    def _explicit_signals(turn: TurnRuntimeState, persistent: DomainPersistentSessionContext) -> ExplicitUserSignals:
        query = turn.raw_query or ""
        normalized = query.lower()
        return ExplicitUserSignals(
            preferred_output_style=turn.requested_output_style.value if turn.requested_output_style else None,
            wants_code_examples="代码" in query or "code" in normalized,
            wants_interview_answer="面试" in query or "interview" in normalized,
            confirmed_plan=bool(turn.plan),
            mastered="掌握" in query or "understood" in normalized,
            confused="不懂" in query or "confused" in normalized,
            confirmed_output_style=False,
            confirmed_code_examples="默认给代码" in query or "default to code" in normalized,
            confirmed_interview_mode="默认面试" in query or "interview" in normalized,
            repeated_topic_signal=bool(persistent.current_topic and persistent.current_topic in persistent.recent_entities),
            low_quiz_score=None,
            focus_topics=tuple(persistent.recent_entities[:3]),
            weak_topics=tuple(),
        )

    @staticmethod
    def _ensure_trace(runtime) -> MemoryTrace:
        trace = runtime.memory_trace
        if trace is None:
            trace = MemoryTrace(
                trace_id=runtime.trace_id,
                user_id=runtime.user_id,
                session_id=runtime.session_id,
                turn_id=runtime.turn_id,
            )
        elif not trace.user_id:
            trace.user_id = runtime.user_id
        return trace

    def _persist_trace(self, trace: Optional[MemoryTrace]) -> None:
        if trace is None or self.trace_repository is None:
            return
        try:
            self.trace_repository.create(trace)
        except Exception:
            return

    def _capture_qdrant_state(self, trace: MemoryTrace) -> None:
        long_term_store = self.long_term_store
        qdrant_error = getattr(long_term_store, "last_qdrant_error", None)
        if qdrant_error is None:
            index = getattr(long_term_store, "index", None)
            qdrant_error = getattr(index, "last_error", None)
        if qdrant_error:
            trace.qdrant_degraded = True
            trace.extra = {**dict(trace.extra), "qdrant_error": str(qdrant_error), "qdrant_degraded": True}

    @staticmethod
    def _unique_extend(items: List[str], values: List[str]) -> List[str]:
        merged = list(items)
        for value in values:
            if value and value not in merged:
                merged.append(value)
        return merged

    def _policy_snapshot(self) -> Dict[str, Any]:
        retrieval = self.retrieval_policy.config
        injection = self.injection_policy.config
        promotion = getattr(self.promotion_policy, "config", None)
        conflict = getattr(self.conflict_resolver, "config", None)
        consolidation = getattr(self.consolidation_job, "config", None)
        return {
            "retrieval": {
                "prompt_limit": retrieval.prompt_limit,
                "state_limit": retrieval.state_limit,
                "rag_limit": retrieval.rag_limit,
                "tool_limit": retrieval.tool_limit,
                "token_budget": retrieval.token_budget,
                "semantic_top_k": retrieval.semantic_top_k,
                "episodic_keywords": list(retrieval.episodic_keywords),
                "procedural_keywords": list(retrieval.procedural_keywords),
            },
            "injection": {
                "prompt_limit": injection.prompt_limit,
                "state_limit": injection.state_limit,
                "tool_limit": injection.tool_limit,
                "rag_limit": injection.rag_limit,
                "token_budget": injection.token_budget,
            },
            "promotion": {
                "preference_promote_count": getattr(promotion, "preference_promote_count", 3),
                "behavior_promote_count": getattr(promotion, "behavior_promote_count", 2),
                "low_quiz_threshold": getattr(promotion, "low_quiz_threshold", 0.6),
            },
            "conflict": {
                "supersede_margin": getattr(conflict, "supersede_margin", 0.05),
                "merge_similarity_threshold": getattr(conflict, "merge_similarity_threshold", 0.65),
            },
            "consolidation": {
                "minimum_duplicate_group_size": getattr(consolidation, "minimum_duplicate_group_size", 2),
                "max_conflicts": getattr(consolidation, "max_conflicts", 8),
                "confirmed_explicitness": getattr(consolidation, "confirmed_explicitness", 1.0),
                "inferred_explicitness": getattr(consolidation, "inferred_explicitness", 0.5),
                "recency_window_seconds": getattr(consolidation, "recency_window_seconds", 60 * 60 * 24 * 7),
            },
            "orchestrator": {
                "confirmed_confidence_threshold": self.policy.confirmed_confidence_threshold,
            },
        }

    @staticmethod
    def _dedupe_candidates(candidates: List[MemoryCandidate]) -> List[MemoryCandidate]:
        merged: List[MemoryCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.candidate_id or candidate.dedupe_key or candidate.record.memory_id
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
        return merged

    def _resolve_conflicts(self, record: MemoryRecord):
        repository = getattr(self.long_term_store, "repository", None)
        if repository is None or not hasattr(repository, "find_potential_conflicts"):
            return self.conflict_resolver.resolve(record, [])
        conflicts = list(
            repository.find_potential_conflicts(
                user_id=record.user_id,
                scope=record.scope,
                topic=record.topic,
                memory_type=record.type,
            )
        )
        conflicts = [item for item in conflicts if item.memory_id != record.memory_id]
        return self.conflict_resolver.resolve(record, conflicts)
