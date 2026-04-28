from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from learning_agent_service.config import Settings
from learning_agent_service.domain import (
    MasteryUpdateCommand,
    MasteryUpdateResult,
    MemoryUpdateSummary,
    MemoryWriteResult,
    MemoryWriteTargetResult,
    PersistSessionCommand,
    PersistSessionResult,
    PersistentSessionContext as DomainPersistentSessionContext,
    RecommendationQuery,
    RecommendationResult,
)
from learning_agent_service.domain.errors import WorkflowErrorCode
from learning_agent_service.domain.guards import validate_memory_write_boundary

from .canonical import CanonicalTopicResolver
from .mastery import MasteryUpdateInput, TopicMasteryUpdater
from .models import (
    AsyncLogEvent,
    ExplicitUserSignals,
    MasteryComputation,
    MemoryCapabilityError,
    MemoryPromotionInput,
    PersistSessionPlan,
    PersistentSessionContext as MemoryPersistentSessionContext,
    PreferenceProfileWrite,
    RecommendationContext,
    SemanticIndexUpdate,
    SessionPersistenceContext,
    TopicMasteryRecord,
    UserPreferenceProfile,
)
from .promotion import MemoryPromotionPolicy
from .protocols import (
    AsyncLogStore,
    LearningPlanStore,
    NoOpSemanticMemoryStore,
    PreferenceStore,
    SemanticMemoryStore,
    SessionStore,
    SupportsListByPlan,
    SupportsListForPlan,
    SupportsLoadAny,
    TopicMasteryStore,
)
from .recommend import RecommendationService


@dataclass
class MemoryService:
    session_store: SessionStore
    mastery_store: TopicMasteryStore
    async_log_store: AsyncLogStore
    settings: Settings
    preference_store: Optional[PreferenceStore] = None
    learning_plan_store: Optional[LearningPlanStore] = None
    semantic_memory_store: SemanticMemoryStore = field(default_factory=NoOpSemanticMemoryStore)
    promotion_policy: MemoryPromotionPolicy = field(default_factory=MemoryPromotionPolicy)
    mastery_updater: TopicMasteryUpdater = field(default_factory=TopicMasteryUpdater)
    recommendation_service: RecommendationService = field(default_factory=RecommendationService)
    topic_resolver: CanonicalTopicResolver = field(default_factory=CanonicalTopicResolver)

    def __post_init__(self) -> None:
        if self.semantic_memory_store is None:
            self.semantic_memory_store = NoOpSemanticMemoryStore()

    def persist_session(self, command: PersistSessionCommand) -> PersistSessionResult:
        persistent = command.persistent
        resolved_topic = self._resolve_topic(
            command.resolved_topic,
            persistent.current_topic,
            command.raw_query,
        )
        current_preferences = self._preference_profile(command.user_id, persistent.user_preferences)
        current_mastery = self._load_current_mastery(command.user_id, resolved_topic)

        promotion_input = MemoryPromotionInput(
            session_id=command.session_id,
            turn_id=command.turn_id,
            user_id=command.user_id,
            query=command.raw_query,
            answer_text=command.answer_text,
            resolved_topic=resolved_topic,
            intent=command.intent.value if command.intent else None,
            output_style=command.requested_output_style.value if command.requested_output_style else None,
            tool_name=command.tool_name,
            explicit_signals=self._collect_explicit_signals(command, resolved_topic),
            current_session=self._to_memory_context(persistent),
            current_preferences=current_preferences,
            current_mastery=current_mastery,
            quiz_score=command.quiz_score,
            current_time=command.request_ts,
            extra={
                "clarification_result": dict(persistent.clarification_result),
                "learning_mode": self._derive_learning_mode(command),
                "open_questions": list(persistent.open_questions),
                "confirmed_facts": list(persistent.confirmed_facts),
                "next_steps": list(persistent.next_steps),
                "summary_version": persistent.summary_version,
                "summary_updated_at": persistent.summary_updated_at,
            },
        )
        promotion_result = self.promotion_policy.evaluate(promotion_input)
        write_plan = self.promotion_policy.build_write_plan(self._to_memory_context(persistent), promotion_result)
        updated_context = self._to_domain_context(write_plan.updated_context, persistent)
        fallback_topic = self._resolve_topic(
            command.resolved_topic,
            persistent.current_topic,
            command.raw_query,
        )
        raw_query_topic = self.topic_resolver.canonicalize(command.raw_query)
        if (
            not command.resolved_topic
            and not persistent.current_topic
            and fallback_topic == raw_query_topic
        ):
            fallback_topic = (
                self.topic_resolver.canonicalize(persistent.history_summary)
                if persistent.history_summary
                else "general"
            )
        fallback_history_summary = persistent.history_summary or command.raw_query
        if not updated_context.current_topic and fallback_topic:
            updated_context = updated_context.model_copy(update={"current_topic": fallback_topic})
        if not updated_context.history_summary and fallback_history_summary:
            updated_context = updated_context.model_copy(update={"history_summary": fallback_history_summary})

        runtime_context = self._session_runtime_context(command)
        self._validate_memory_boundary(
            code=WorkflowErrorCode.SESSION_PERSIST_FAILED,
            operation="persist_session",
            user_id=command.user_id,
            runtime=runtime_context,
        )
        try:
            self.session_store.save(updated_context, runtime_context)
        except Exception as exc:  # pragma: no cover - delegated to workflow integration
            raise MemoryCapabilityError(
                code=WorkflowErrorCode.SESSION_PERSIST_FAILED,
                stage="persist_session.session_store",
                message=str(exc),
                retryable=True,
                degraded_to="session_not_persisted",
            ) from exc

        diagnostics: Dict[str, Any] = {}
        session_backend = type(self.session_store).__name__
        session_status = "degraded" if self._is_fallback_backend_name(session_backend) else "success"
        target_summaries: list[Dict[str, Any]] = [
            {
                "target": "session_context",
                "status": session_status,
                "retryable": False,
                "reason": (
                    "session_context_persisted"
                    if session_status == "success"
                    else "session_context_persisted_via_fallback_backend"
                ),
                "details": {
                    "backend": session_backend,
                    "session_id": runtime_context.session_id,
                    "user_id": runtime_context.user_id,
                },
            }
        ]
        preference_diagnostics = self._persist_preference_patch(
            command.user_id,
            updated_context,
            write_plan.preference_patch,
        )
        if preference_diagnostics:
            diagnostics["preference_store"] = preference_diagnostics
            target_summaries.append(preference_diagnostics)

        semantic_summary = self._sync_semantic_facts(
            user_id=command.user_id,
            facts=write_plan.semantic_facts,
            runtime=runtime_context,
        )
        target_summaries.append(semantic_summary)
        if semantic_summary.get("failures"):
            diagnostics["semantic_memory"] = {
                "status": semantic_summary.get("status"),
                "failures": list(semantic_summary.get("failures", [])),
            }

        outbox_diagnostics = self._emit_persist_outbox(runtime_context, write_plan)
        if outbox_diagnostics:
            diagnostics["outbox"] = outbox_diagnostics
            target_summaries.append(outbox_diagnostics)

        memory_write = self._build_memory_write_result(
            operation="persist_session",
            runtime=runtime_context,
            planned_targets=("session_context", "preference", "semantic_facts", "outbox"),
            target_summaries=target_summaries,
            decision_reasons=self._collect_write_reasons(promotion_result.reasons, target_summaries),
            extra={
                "promotion_reasons": list(promotion_result.reasons),
                "write_plan_targets": ["session_context", "preference", "semantic_facts", "outbox"],
                "memory_trace_id": runtime_context.trace_id,
                "policy_snapshot": self._policy_snapshot(),
            },
        )

        memory_updates = MemoryUpdateSummary(
            current_topic=updated_context.current_topic,
            updated_preferences=dict(write_plan.preference_patch),
            weak_topics=list(write_plan.weak_topics),
            semantic_memory=semantic_summary,
            open_questions=list(updated_context.open_questions),
            confirmed_facts=list(updated_context.confirmed_facts),
            next_steps=list(updated_context.next_steps),
            summary_version=updated_context.summary_version,
            summary_updated_at=updated_context.summary_updated_at,
            memory_trace_id=runtime_context.trace_id,
            write_status=memory_write.status,
            write_targets=list(memory_write.write_targets),
            decision_reasons=list(memory_write.decision_reasons),
            degraded_parts=list(memory_write.degraded_parts),
            retryable_failures=list(memory_write.retryable_failures),
            permanent_failures=list(memory_write.permanent_failures),
            memory_write=memory_write,
            extra={
                "recent_entities": list(updated_context.recent_entities),
                "history_summary": updated_context.history_summary,
                "promotion_reasons": list(promotion_result.reasons),
                "diagnostics": diagnostics,
                "policy_snapshot": self._policy_snapshot(),
            },
        )
        return PersistSessionResult(
            updated_context=updated_context,
            memory_updates=memory_updates,
            memory_write=memory_write,
        )

    def update_mastery(self, command: MasteryUpdateCommand) -> MasteryUpdateResult:
        topic = self._resolve_topic(
            command.resolved_topic,
            command.persistent.current_topic,
            command.raw_query,
        )
        if not topic:
            return MasteryUpdateResult()

        current = self._load_current_mastery(command.user_id, topic)
        computation = self._build_mastery_computation(command, current)
        runtime_context = self._session_runtime_context_from_mastery(command)
        self._validate_memory_boundary(
            code=WorkflowErrorCode.MASTERY_UPDATE_FAILED,
            operation="update_mastery",
            user_id=command.user_id,
            runtime=runtime_context,
        )

        try:
            saved = self.mastery_store.upsert(
                command.user_id,
                computation.topic,
                self._mastery_payload(computation.updated_record, command.turn_id),
            )
        except Exception as exc:  # pragma: no cover - delegated to workflow integration
            raise MemoryCapabilityError(
                code=WorkflowErrorCode.MASTERY_UPDATE_FAILED,
                stage="update_mastery.mastery_store",
                message=str(exc),
                retryable=True,
                degraded_to="skip_mastery_update",
            ) from exc

        semantic_index = self._sync_semantic_index(
            user_id=command.user_id,
            updates=computation.semantic_index_updates,
            runtime=runtime_context,
        )
        metrics_patch = dict(computation.metrics_patch)
        metrics_patch["topic_mastery"] = saved
        mastery_backend = type(self.mastery_store).__name__
        mastery_status = "degraded" if self._is_fallback_backend_name(mastery_backend) else "success"
        write_result = self._build_memory_write_result(
            operation="update_mastery",
            runtime=runtime_context,
            planned_targets=("topic_mastery", "semantic_index"),
            target_summaries=[
                {
                    "target": "topic_mastery",
                    "status": mastery_status,
                    "retryable": False,
                    "reason": (
                        "topic_mastery_upserted"
                        if mastery_status == "success"
                        else "topic_mastery_upserted_via_fallback_backend"
                    ),
                    "details": {
                        "topic": computation.topic,
                        "backend": mastery_backend,
                    },
                },
                semantic_index,
            ],
            decision_reasons=self._collect_write_reasons(
                tuple(command.memory_updates.decision_reasons)
                + (
                    f"mastery_signal={computation.signal_summary.get('signal_type')}",
                    f"topic={computation.topic}",
                ),
                [semantic_index],
            ),
            extra={
                "topic": computation.topic,
                "metrics_patch": dict(metrics_patch),
                "memory_trace_id": runtime_context.trace_id,
                "policy_snapshot": self._policy_snapshot(),
            },
        )
        return MasteryUpdateResult(
            topic_mastery=saved,
            semantic_index=semantic_index,
            metrics_patch=metrics_patch,
            memory_write=write_result,
        )

    def recommend_next(self, query: RecommendationQuery) -> Optional[RecommendationResult]:
        mastery_records = tuple(
            self._to_mastery_record(item) for item in self.mastery_store.list_for_user(query.user_id)
        )
        active_plan_topics = self._load_active_plan_topics(query.user_id, query.active_plan_id)
        low_mastery_threshold = self.recommendation_service.config.low_mastery_threshold
        review_priority_threshold = self.recommendation_service.config.review_priority_threshold
        derived_weak_topics = tuple(
            record.topic
            for record in mastery_records
            if record.review_priority >= review_priority_threshold or record.mastery_score < low_mastery_threshold
        )
        context = RecommendationContext(
            current_topic=query.current_topic,
            weak_topics=derived_weak_topics,
            mastery_records=mastery_records,
            active_plan_topics=active_plan_topics,
            recent_topics=tuple(query.recent_topics),
            preferred_output_style=(
                query.user_preferences.get("preferred_output_style")
                or query.user_preferences.get("answer_style")
            ),
            learning_mode=bool(query.learning_mode),
            requested_limit=1,
        )
        recommendations = self.recommendation_service.recommend(context)
        if not recommendations:
            return None

        top = recommendations[0]
        return RecommendationResult(
            topic=top.topic,
            reason=top.reason,
            source=top.source,
            priority=top.priority,
            metadata=dict(top.metadata),
        )

    def load_any(self, session_id: str) -> DomainPersistentSessionContext:
        if isinstance(self.session_store, SupportsLoadAny):
            return self.session_store.load_any(session_id)
        return self.session_store.load(session_id, "anonymous")

    def _session_runtime_context(self, command: PersistSessionCommand) -> SessionPersistenceContext:
        return SessionPersistenceContext(
            session_id=command.session_id,
            turn_id=command.turn_id,
            trace_id="%s:%s" % (command.session_id, command.turn_id),
            user_id=command.user_id,
            request_ts=command.request_ts,
        )

    def _session_runtime_context_from_mastery(self, command: MasteryUpdateCommand) -> SessionPersistenceContext:
        return SessionPersistenceContext(
            session_id=command.session_id,
            turn_id=command.turn_id,
            trace_id="%s:%s" % (command.session_id, command.turn_id),
            user_id=command.user_id,
            request_ts=command.request_ts,
        )

    def _resolve_topic(
        self,
        resolved_topic: Optional[str],
        current_topic: Optional[str],
        raw_query: str,
    ) -> str:
        resolved = self._canonicalize_topic_candidate(resolved_topic)
        if resolved:
            return resolved

        if current_topic:
            return self.topic_resolver.canonicalize(current_topic)

        return self._canonicalize_topic_candidate(raw_query)

    def _canonicalize_topic_candidate(self, candidate: Optional[str]) -> str:
        text = (candidate or "").strip()
        if not text:
            return ""

        canonical = self.topic_resolver.canonicalize(text)
        normalized = CanonicalTopicResolver._normalize(text)
        if not normalized:
            return ""

        # When canonicalization only mirrors a long instructional sentence,
        # keep the previous topic instead of polluting session memory with a query slug.
        mirrored = normalized.replace(" ", ".")
        query_markers = {
            "compare",
            "difference",
            "differences",
            "explain",
            "how",
            "what",
            "why",
            "vs",
            "tell",
            "show",
            "describe",
            "介绍",
            "解释",
            "对比",
            "区别",
            "怎么",
            "如何",
            "为什么",
            "面试",
            "总结",
        }
        tokens = normalized.split()
        if canonical == mirrored and (len(tokens) > 4 or any(token in query_markers for token in tokens)):
            return ""
        return canonical

    def _derive_learning_mode(self, command: PersistSessionCommand) -> bool:
        if command.persistent.learning_mode:
            return True
        if command.tool_name in {"generateQuiz", "generateStudyPlan", "recommendNextTopic"}:
            return True
        return command.intent is not None

    def _collect_explicit_signals(
        self,
        command: PersistSessionCommand,
        resolved_topic: str,
    ) -> ExplicitUserSignals:
        query = command.raw_query or ""
        normalized_query = query.lower()
        quiz_score = command.quiz_score
        low_quiz_threshold = self.mastery_updater.config.weak_signal_quiz_threshold
        confusion = self._is_confused_query(query, normalized_query) or (
            quiz_score is not None and quiz_score < low_quiz_threshold
        )
        return ExplicitUserSignals(
            preferred_output_style=command.requested_output_style.value if command.requested_output_style else None,
            wants_code_examples=bool(command.intent and command.intent.value == "code"),
            wants_interview_answer=bool(
                command.requested_output_style and command.requested_output_style.value == "interview"
            ),
            confirmed_plan=bool(command.tool_name == "generateStudyPlan"),
            mastered=self._is_mastered_query(query, normalized_query),
            confused=confusion,
            confirmed_output_style=self._is_confirmed_preference_query(query, normalized_query),
            confirmed_code_examples=self._is_confirmed_behavior_query(query, normalized_query, "code"),
            confirmed_interview_mode=self._is_confirmed_behavior_query(query, normalized_query, "interview"),
            repeated_topic_signal=bool(resolved_topic and resolved_topic in command.persistent.recent_entities),
            low_quiz_score=quiz_score if quiz_score is not None and quiz_score < low_quiz_threshold else None,
            weak_topics=(),
        )

    def _persist_preference_patch(
        self,
        user_id: str,
        updated_context: DomainPersistentSessionContext,
        preference_patch: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if self.preference_store is None or not preference_patch:
            if not preference_patch:
                return {
                    "target": "preference",
                    "status": "skipped",
                    "retryable": False,
                    "reason": "no_preference_patch",
                    "fields": [],
                    "details": {},
                }
            return {
                "target": "preference",
                "status": "permanent_failure",
                "retryable": False,
                "reason": "preference_store_unavailable",
                "fields": sorted(preference_patch.keys()),
                "details": {"backend": "none"},
            }
        try:
            profile = PreferenceProfileWrite(
                user_id=user_id,
                answer_style=updated_context.user_preferences.get("preferred_output_style")
                or updated_context.user_preferences.get("answer_style"),
                explanation_depth=updated_context.user_preferences.get("preferred_output_style")
                or updated_context.user_preferences.get("answer_style"),
                prefer_code_examples=bool(updated_context.user_preferences.get("prefers_code_examples")),
                extra={
                    "answer_style_counter": dict(updated_context.user_preferences.get("answer_style_counter", {})),
                    "behavior_counters": dict(updated_context.user_preferences.get("behavior_counters", {})),
                    "prefers_interview_mode": bool(
                        updated_context.user_preferences.get("prefers_interview_mode", False)
                    ),
                },
            )
            self.preference_store.upsert(profile)
            return {
                "target": "preference",
                "status": "success",
                "retryable": False,
                "reason": "preference_profile_upserted",
                "fields": sorted(preference_patch.keys()),
                "details": {
                    "backend": type(self.preference_store).__name__,
                    "user_id": user_id,
                },
            }
        except Exception as exc:
            return {
                "target": "preference",
                "status": "retryable_failure",
                "retryable": True,
                "reason": "preference_profile_upsert_failed",
                "fields": sorted(preference_patch.keys()),
                "error": str(exc),
                "details": {
                    "backend": type(self.preference_store).__name__,
                    "user_id": user_id,
                },
            }

    def _sync_semantic_facts(
        self,
        *,
        user_id: str,
        facts: Sequence[Any],
        runtime: SessionPersistenceContext,
    ) -> Dict[str, Any]:
        upserted: list[str] = []
        failures: list[str] = []
        if isinstance(self.semantic_memory_store, NoOpSemanticMemoryStore):
            fact_ids = [str(getattr(fact, "fact_id", "")) for fact in facts]
            return {
                "target": "semantic_facts",
                "status": "degraded",
                "retryable": False,
                "reason": "semantic_memory_store_is_noop",
                "upserted_fact_ids": [],
                "rejected_fact_ids": [fact_id for fact_id in fact_ids if fact_id],
                "failures": ["noop_semantic_memory_store"],
                "details": {
                    "backend": type(self.semantic_memory_store).__name__,
                    "user_id": user_id,
                    "session_id": runtime.session_id,
                },
            }
        for fact in facts:
            try:
                self.semantic_memory_store.upsert(user_id, fact)
                upserted.append(fact.fact_id)
            except Exception as exc:
                failures.append("%s: %s" % (fact.fact_id, exc))
                self._append_async_log(
                    AsyncLogEvent(
                        aggregate_type="memory",
                        aggregate_id="%s:%s" % (runtime.session_id, runtime.turn_id),
                        event_type="memory.semantic_fact_failed",
                        dedupe_key="%s:%s:%s" % (runtime.session_id, runtime.turn_id, fact.fact_id),
                        payload={
                            "user_id": user_id,
                            "fact_id": fact.fact_id,
                            "topic": fact.topic,
                            "reason": str(exc),
                        },
                        trace_id=runtime.trace_id,
                    )
                )
        return {
            "target": "semantic_facts",
            "adapter": type(self.semantic_memory_store).__name__,
            "status": "success" if not failures else "retryable_failure",
            "retryable": bool(failures),
            "reason": "semantic_facts_upserted" if not failures else "semantic_facts_partial_failure",
            "upserted_fact_ids": upserted,
            "failures": failures,
            "details": {
                "backend": type(self.semantic_memory_store).__name__,
                "user_id": user_id,
                "session_id": runtime.session_id,
            },
        }

    def _emit_persist_outbox(
        self,
        runtime: SessionPersistenceContext,
        write_plan: PersistSessionPlan,
    ) -> Dict[str, Any]:
        failures: list[str] = []
        events_written = 0
        backend_name = type(self.async_log_store).__name__
        for request in write_plan.durable_fact_requests:
            try:
                self._append_async_log(
                    AsyncLogEvent(
                        aggregate_type="memory",
                        aggregate_id="%s:%s" % (runtime.session_id, runtime.turn_id),
                        event_type="memory.%s" % request.fact_type,
                        dedupe_key="%s:%s:%s" % (runtime.session_id, runtime.turn_id, request.fact_type),
                        payload={
                            "session_id": runtime.session_id,
                            "turn_id": runtime.turn_id,
                            "trace_id": runtime.trace_id,
                            **dict(request.payload),
                        },
                        trace_id=runtime.trace_id,
                    )
                )
                events_written += 1
            except Exception as exc:
                failures.append(str(exc))

        for index, event in enumerate(write_plan.outbox_events):
            event_type = str(event.get("event_type") or "memory.outbox")
            try:
                self._append_async_log(
                    AsyncLogEvent(
                        aggregate_type="memory",
                        aggregate_id="%s:%s" % (runtime.session_id, runtime.turn_id),
                        event_type=event_type,
                        dedupe_key="%s:%s:%s:%s" % (runtime.session_id, runtime.turn_id, event_type, index),
                        payload={
                            "session_id": runtime.session_id,
                            "turn_id": runtime.turn_id,
                            "trace_id": runtime.trace_id,
                            **dict(event),
                        },
                        trace_id=runtime.trace_id,
                    )
                )
                events_written += 1
            except Exception as exc:
                failures.append(str(exc))

        try:
            self._append_async_log(
                AsyncLogEvent(
                    aggregate_type="memory",
                    aggregate_id="%s:%s" % (runtime.session_id, runtime.turn_id),
                    event_type="memory.persist_session",
                    dedupe_key="%s:%s:persist_session" % (runtime.session_id, runtime.turn_id),
                    payload={
                        "session_id": runtime.session_id,
                        "turn_id": runtime.turn_id,
                        "trace_id": runtime.trace_id,
                        "current_topic": write_plan.updated_context.current_topic,
                    },
                    trace_id=runtime.trace_id,
                )
            )
            events_written += 1
        except Exception as exc:
            failures.append(str(exc))

        fallback_backend = self._is_fallback_backend_name(backend_name)
        if fallback_backend and not failures:
            return {
                "target": "outbox",
                "status": "degraded",
                "retryable": False,
                "reason": "outbox_persisted_via_fallback_backend",
                "events_written": events_written,
                "failures": [],
                "details": {
                    "session_id": runtime.session_id,
                    "turn_id": runtime.turn_id,
                    "trace_id": runtime.trace_id,
                    "planned_events": len(write_plan.durable_fact_requests) + len(write_plan.outbox_events) + 1,
                    "backend": backend_name,
                },
            }
        if not failures:
            return {
                "target": "outbox",
                "status": "success",
                "retryable": False,
                "reason": "outbox_events_written",
                "events_written": events_written,
                "failures": [],
                "details": {
                    "session_id": runtime.session_id,
                    "turn_id": runtime.turn_id,
                    "trace_id": runtime.trace_id,
                    "planned_events": len(write_plan.durable_fact_requests) + len(write_plan.outbox_events) + 1,
                },
            }
        return {
            "target": "outbox",
            "status": "pending_compensation",
            "retryable": True,
            "reason": "outbox_events_pending_compensation",
            "events_written": events_written,
            "failures": failures,
            "details": {
                "session_id": runtime.session_id,
                "turn_id": runtime.turn_id,
                "trace_id": runtime.trace_id,
                "planned_events": len(write_plan.durable_fact_requests) + len(write_plan.outbox_events) + 1,
                "backend": backend_name,
            },
        }

    def _build_mastery_computation(
        self,
        command: MasteryUpdateCommand,
        current: TopicMasteryRecord,
    ) -> MasteryComputation:
        memory_extra = dict(command.memory_updates.extra)
        evidence_count = int(memory_extra.get("evidence_count", 0) or 0)
        weak_topics = tuple(command.memory_updates.weak_topics)
        query = command.raw_query or ""
        low_quiz_threshold = self.mastery_updater.config.weak_signal_quiz_threshold
        signal = MasteryUpdateInput(
            topic=current.topic,
            signal_type=self._mastery_signal_type(command),
            quiz_score=command.quiz_score,
            was_confused=bool(memory_extra.get("was_confused", self._is_confused_query(query, query.lower()))),
            weak_signal=current.topic in weak_topics or (
                command.quiz_score is not None and command.quiz_score < low_quiz_threshold
            ),
            was_resolved=bool(memory_extra.get("was_resolved", bool(command.answer_text))),
            explicit_mastered=self._is_mastered_query(query, query.lower()),
            repeated_topic=current.topic in command.persistent.recent_entities,
            evidence_delta=max(evidence_count, 1),
            supporting_evidence_count=max(evidence_count, 0),
            timestamp=command.request_ts,
        )
        updated = self.mastery_updater.update(current, signal)
        signal_summary = {
            "topic": updated.topic,
            "signal_type": signal.signal_type,
            "quiz_score": command.quiz_score,
            "weak_signal": signal.weak_signal,
            "evidence_count": evidence_count,
        }
        return MasteryComputation(
            topic=updated.topic,
            updated_record=updated,
            signal_summary=signal_summary,
            semantic_index_updates=(
                SemanticIndexUpdate(
                    topic=updated.topic,
                    indexed=False,
                    reason="topic_mastery_updated",
                    metadata={"review_priority": updated.review_priority},
                ),
            ),
            metrics_patch={"mastery_signal": signal_summary},
        )

    def _mastery_signal_type(self, command: MasteryUpdateCommand) -> str:
        if command.tool_name == "generateQuiz":
            return "quiz"
        if command.memory_updates.extra.get("reference_resolved"):
            return "review"
        return "study"

    def _sync_semantic_index(
        self,
        *,
        user_id: str,
        updates: Sequence[SemanticIndexUpdate],
        runtime: SessionPersistenceContext,
    ) -> Dict[str, Any]:
        applied: list[Dict[str, Any]] = []
        failures: list[str] = []
        backend_name = type(self.semantic_memory_store).__name__
        fallback_backend = self._is_fallback_backend_name(backend_name)
        if fallback_backend:
            for update in updates:
                applied.append(
                    {
                        "topic": update.topic,
                        "indexed": update.indexed,
                        "reason": update.reason,
                        "metadata": dict(update.metadata),
                    }
                )
            return {
                "target": "semantic_index",
                "adapter": backend_name,
                "status": "degraded",
                "retryable": False,
                "reason": "semantic_index_persisted_via_fallback_backend",
                "updates": applied,
                "failures": [],
                "details": {
                    "backend": backend_name,
                    "user_id": user_id,
                    "session_id": runtime.session_id,
                },
            }
        for update in updates:
            try:
                self.semantic_memory_store.mark_indexed_state(user_id, update.topic, update.indexed)
                applied.append(
                    {
                        "topic": update.topic,
                        "indexed": update.indexed,
                        "reason": update.reason,
                        "metadata": dict(update.metadata),
                    }
                )
            except Exception as exc:
                failures.append("%s: %s" % (update.topic, exc))
                self._append_async_log(
                    AsyncLogEvent(
                        aggregate_type="memory",
                        aggregate_id="%s:%s" % (runtime.session_id, runtime.turn_id),
                        event_type="memory.semantic_index_failed",
                        dedupe_key="%s:%s:semantic-index:%s" % (
                            runtime.session_id,
                            runtime.turn_id,
                            update.topic,
                        ),
                        payload={
                            "user_id": user_id,
                            "topic": update.topic,
                            "indexed": update.indexed,
                            "reason": str(exc),
                        },
                        trace_id=runtime.trace_id,
                    )
                )
        return {
            "target": "semantic_index",
            "adapter": type(self.semantic_memory_store).__name__,
            "status": "success" if not failures else "retryable_failure",
            "retryable": bool(failures),
            "reason": "semantic_index_updated" if not failures else "semantic_index_partial_failure",
            "updates": applied,
            "failures": failures,
            "details": {
                "backend": type(self.semantic_memory_store).__name__,
                "user_id": user_id,
                "session_id": runtime.session_id,
            },
        }

    def _validate_memory_boundary(
        self,
        *,
        code: WorkflowErrorCode,
        operation: str,
        user_id: str,
        runtime: SessionPersistenceContext,
    ) -> None:
        decision = validate_memory_write_boundary(
            user_id=user_id,
            runtime_user_id=runtime.user_id,
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
        )
        if not decision.allowed:
            raise MemoryCapabilityError(
                code=code,
                stage=f"{operation}.boundary_validation",
                message=decision.reason.replace("_", " "),
                retryable=False,
                degraded_to=decision.reason,
            )

    @staticmethod
    def _is_fallback_backend_name(backend_name: str) -> bool:
        return backend_name.startswith("InMemory") or backend_name.startswith("NoOp")

    @staticmethod
    def _collect_write_reasons(*reason_sources: Sequence[Any]) -> list[str]:
        reasons: list[str] = []
        for source in reason_sources:
            for reason in source:
                if reason is None:
                    continue
                if isinstance(reason, Mapping):
                    candidate = reason.get("reason") or reason.get("status") or reason.get("target")
                else:
                    candidate = getattr(reason, "reason", None) if hasattr(reason, "reason") else None
                    if candidate is None:
                        candidate = reason
                text = str(candidate).strip()
                if text and text not in reasons:
                    reasons.append(text)
        return reasons

    def _make_target_result(self, summary: Mapping[str, Any]) -> MemoryWriteTargetResult:
        target = str(summary.get("target") or summary.get("adapter") or summary.get("name") or "unknown")
        status = str(summary.get("status") or "success")
        if status not in {"success", "degraded", "retryable_failure", "permanent_failure", "skipped"}:
            status = "success"
        details = dict(summary.get("details") or {})
        for key, value in summary.items():
            if key in {"target", "status", "retryable", "reason", "error", "details"}:
                continue
            details.setdefault(key, value)
        return MemoryWriteTargetResult(
            target=target,
            status=status,
            reason=str(summary.get("reason")) if summary.get("reason") is not None else None,
            retryable=bool(summary.get("retryable", False)),
            error=str(summary.get("error")) if summary.get("error") is not None else None,
            details=details,
        )

    def _build_memory_write_result(
        self,
        *,
        operation: str,
        runtime: SessionPersistenceContext,
        planned_targets: Sequence[str],
        target_summaries: Sequence[Mapping[str, Any]],
        decision_reasons: Sequence[Any],
        extra: Optional[Mapping[str, Any]] = None,
    ) -> MemoryWriteResult:
        target_results = [self._make_target_result(summary) for summary in target_summaries]
        write_targets = list(dict.fromkeys(str(target) for target in planned_targets if str(target)))
        relevant_results = [result for result in target_results if result.status != "skipped"]
        degraded_parts = [result.target for result in relevant_results if result.status == "degraded"]
        retryable_failures = [result.target for result in relevant_results if result.status == "retryable_failure"]
        permanent_failures = [result.target for result in relevant_results if result.status == "permanent_failure"]
        if relevant_results and all(result.status == "permanent_failure" for result in relevant_results):
            status = "permanent_failure"
        elif permanent_failures:
            status = "degraded"
        elif retryable_failures:
            status = "pending_compensation"
        elif degraded_parts:
            status = "degraded"
        else:
            status = "success"
        return MemoryWriteResult(
            trace_id=runtime.trace_id,
            idempotency_key=runtime.trace_id,
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            user_id=runtime.user_id,
            operation=operation,
            status=status,
            write_targets=write_targets,
            target_results=target_results,
            decision_reasons=self._collect_write_reasons(decision_reasons, (result.reason for result in target_results)),
            degraded_parts=list(dict.fromkeys(degraded_parts)),
            retryable_failures=list(dict.fromkeys(retryable_failures)),
            permanent_failures=list(dict.fromkeys(permanent_failures)),
            compensation_required=bool(retryable_failures),
            extra=dict(extra or {}),
        )

    def _policy_snapshot(self) -> Dict[str, Any]:
        mastery = self.mastery_updater.config
        promotion = self.promotion_policy.config
        recommendation = self.recommendation_service.config
        return {
            "mastery": {
                "quiz_super_high_threshold": mastery.quiz_super_high_threshold,
                "quiz_high_threshold": mastery.quiz_high_threshold,
                "quiz_mid_threshold": mastery.quiz_mid_threshold,
                "quiz_low_threshold": mastery.quiz_low_threshold,
                "weak_signal_quiz_threshold": mastery.weak_signal_quiz_threshold,
                "review_priority_base_mastery": mastery.review_priority_base_mastery,
                "review_priority_low_quiz_threshold": mastery.review_priority_low_quiz_threshold,
                "review_priority_low_quiz_bonus": mastery.review_priority_low_quiz_bonus,
                "review_priority_weak_signal_bonus": mastery.review_priority_weak_signal_bonus,
                "review_priority_low_evidence_threshold": mastery.review_priority_low_evidence_threshold,
                "review_priority_low_evidence_bonus": mastery.review_priority_low_evidence_bonus,
                "review_priority_negative_signal_bonus": mastery.review_priority_negative_signal_bonus,
                "review_priority_negative_signal_cap": mastery.review_priority_negative_signal_cap,
                "review_priority_high_mastery_threshold": mastery.review_priority_high_mastery_threshold,
                "review_priority_high_mastery_bonus": mastery.review_priority_high_mastery_bonus,
            },
            "promotion": {
                "preference_promote_count": promotion.preference_promote_count,
                "behavior_promote_count": promotion.behavior_promote_count,
                "low_quiz_threshold": promotion.low_quiz_threshold,
            },
            "recommendation": {
                "low_mastery_threshold": recommendation.low_mastery_threshold,
                "review_priority_threshold": recommendation.review_priority_threshold,
            },
        }

    def _append_async_log(self, event: AsyncLogEvent) -> None:
        self.async_log_store.append(event.as_mapping())

    def _load_active_plan_topics(self, user_id: str, active_plan_id: Optional[str]) -> Tuple[str, ...]:
        if self.learning_plan_store is None or not active_plan_id:
            return ()
        try:
            if isinstance(self.learning_plan_store, SupportsListByPlan):
                return self.topic_resolver.canonicalize_many(
                    self._extract_plan_topics(self.learning_plan_store.list_by_plan(user_id, active_plan_id))
                )
            if isinstance(self.learning_plan_store, SupportsListForPlan):
                return self.topic_resolver.canonicalize_many(
                    self._extract_plan_topics(self.learning_plan_store.list_for_plan(active_plan_id))
                )
        except Exception:
            return ()
        return ()

    def _extract_plan_topics(self, items: Sequence[Any]) -> Tuple[str, ...]:
        topics = []
        for item in items:
            if isinstance(item, Mapping):
                topic = item.get("topic")
            else:
                topic = getattr(item, "topic", None)
            if topic:
                topics.append(str(topic))
        return tuple(topics)

    def _preference_profile(self, user_id: str, user_preferences: Mapping[str, Any]) -> UserPreferenceProfile:
        stored_preferences = dict(user_preferences)
        if self.preference_store is not None:
            model = self.preference_store.get(user_id)
            if model is not None:
                stored_preferences.update(
                    {
                        "preferred_output_style": getattr(model, "answer_style", None),
                        "answer_style": getattr(model, "answer_style", None),
                        "prefers_code_examples": bool(getattr(model, "prefer_code_examples", False)),
                        **dict(getattr(model, "extra", {}) or {}),
                    }
                )
        counter = stored_preferences.get("answer_style_counter", {})
        return UserPreferenceProfile(
            user_id=user_id,
            preferred_output_style=stored_preferences.get("preferred_output_style")
            or stored_preferences.get("answer_style"),
            answer_style_counter=counter if isinstance(counter, Mapping) else {},
            prefers_code_examples=bool(stored_preferences.get("prefers_code_examples")),
            prefers_interview_mode=bool(stored_preferences.get("prefers_interview_mode")),
            extra={
                key: value
                for key, value in stored_preferences.items()
                if key
                not in {
                    "preferred_output_style",
                    "answer_style",
                    "answer_style_counter",
                    "prefers_code_examples",
                    "prefers_interview_mode",
                }
            },
        )

    def _load_current_mastery(self, user_id: str, topic: str) -> TopicMasteryRecord:
        payload = self.mastery_store.get(user_id, topic or "")
        return self._to_mastery_record(payload)

    def _to_memory_context(self, context: DomainPersistentSessionContext) -> MemoryPersistentSessionContext:
        pending = context.pending_clarification.model_dump(mode="json") if context.pending_clarification else None
        return MemoryPersistentSessionContext(
            current_topic=context.current_topic,
            recent_entities=tuple(context.recent_entities),
            clarification_result=dict(context.clarification_result),
            user_preferences=dict(context.user_preferences),
            last_retrieval_topic=context.last_retrieval_topic,
            active_plan_id=context.active_plan_id,
            learning_mode=context.learning_mode,
            history_summary=context.history_summary,
            open_questions=tuple(context.open_questions),
            confirmed_facts=tuple(context.confirmed_facts),
            next_steps=tuple(context.next_steps),
            summary_version=context.summary_version,
            summary_updated_at=context.summary_updated_at,
            pending_clarification=pending,
            extra=dict(context.extra),
        )

    def _to_domain_context(
        self,
        context: MemoryPersistentSessionContext,
        current: DomainPersistentSessionContext,
    ) -> DomainPersistentSessionContext:
        return current.model_copy(
            update={
                "current_topic": context.current_topic,
                "recent_entities": list(context.recent_entities),
                "clarification_result": dict(context.clarification_result),
                "user_preferences": dict(context.user_preferences),
                "last_retrieval_topic": context.last_retrieval_topic,
                "active_plan_id": context.active_plan_id,
                "learning_mode": bool(context.learning_mode) if context.learning_mode is not None else False,
                "history_summary": context.history_summary,
                "open_questions": list(context.open_questions),
                "confirmed_facts": list(context.confirmed_facts),
                "next_steps": list(context.next_steps),
                "summary_version": context.summary_version,
                "summary_updated_at": context.summary_updated_at,
                "pending_clarification": None,
                "extra": dict(context.extra),
            }
        )

    def _to_mastery_record(self, payload: Mapping[str, Any]) -> TopicMasteryRecord:
        last_seen_at = payload.get("last_seen_at")
        if isinstance(last_seen_at, str):
            try:
                last_seen_at = datetime.fromisoformat(last_seen_at)
            except ValueError:
                last_seen_at = None
        return TopicMasteryRecord(
            topic=self.topic_resolver.canonicalize(str(payload.get("topic", ""))),
            mastery_score=float(payload.get("mastery_score", 0.5)),
            confidence_score=float(payload.get("confidence_score", 0.3)),
            evidence_count=int(payload.get("evidence_count", 0)),
            last_seen_at=last_seen_at,
            last_quiz_score=payload.get("last_quiz_score"),
            review_priority=float(payload.get("review_priority", 20.0)),
            positive_signals=int(payload.get("positive_signals", 0)),
            negative_signals=int(payload.get("negative_signals", 0)),
            extra={
                key: value
                for key, value in dict(payload).items()
                if key
                not in {
                    "topic",
                    "mastery_score",
                    "confidence_score",
                    "evidence_count",
                    "last_seen_at",
                    "last_quiz_score",
                    "review_priority",
                    "positive_signals",
                    "negative_signals",
                }
            },
        )

    def _mastery_payload(self, record: TopicMasteryRecord, source_turn_id: str) -> Dict[str, Any]:
        return {
            "mastery_score": round(record.mastery_score, 2),
            "confidence_score": round(record.confidence_score, 2),
            "evidence_count": record.evidence_count,
            "last_seen_at": record.last_seen_at,
            "last_quiz_score": record.last_quiz_score,
            "review_priority": int(record.review_priority),
            "source_turn_id": source_turn_id,
            "positive_signals": record.positive_signals,
            "negative_signals": record.negative_signals,
        }

    @staticmethod
    def _is_confirmed_preference_query(query: str, normalized_query: str) -> bool:
        phrases = ("以后都", "以后默认", "默认用", "一直用", "长期用", "always use", "default to")
        return any(phrase in query or phrase in normalized_query for phrase in phrases)

    @staticmethod
    def _is_confirmed_behavior_query(query: str, normalized_query: str, behavior: str) -> bool:
        if behavior == "code":
            phrases = ("以后都给代码", "默认给代码", "always include code", "default to code")
        else:
            phrases = ("以后都按面试", "默认面试回答", "always answer for interview", "default interview")
        return any(phrase in query or phrase in normalized_query for phrase in phrases)

    @staticmethod
    def _is_mastered_query(query: str, normalized_query: str) -> bool:
        phrases = ("我懂了", "明白了", "已经掌握", "会了", "got it", "understood")
        return any(phrase in query or phrase in normalized_query for phrase in phrases)

    @staticmethod
    def _is_confused_query(query: str, normalized_query: str) -> bool:
        phrases = ("不懂", "没懂", "还是不会", "记不住", "总答错", "混淆", "confused", "still unclear")
        return any(phrase in query or phrase in normalized_query for phrase in phrases)
