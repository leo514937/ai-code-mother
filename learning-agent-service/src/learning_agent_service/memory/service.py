from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from learning_agent_service.config import Settings
from learning_agent_service.domain import GraphState, PersistentSessionContext as DomainPersistentSessionContext
from learning_agent_service.domain.errors import WorkflowErrorCode, build_error
from learning_agent_service.infrastructure.repositories.records import UserPreferenceProfileRecord

from .canonical import CanonicalTopicResolver
from .mastery import MasteryUpdateInput, TopicMasteryUpdater
from .models import (
    ExplicitUserSignals,
    MasteryComputation,
    MemoryPromotionInput,
    PersistSessionPlan,
    PersistentSessionContext as MemoryPersistentSessionContext,
    RecommendationContext,
    RecommendationSnapshot,
    SemanticIndexUpdate,
    TopicMasteryRecord,
    UserPreferenceProfile,
)
from .promotion import MemoryPromotionPolicy
from .protocols import AsyncLogStore, LearningPlanStore, PreferenceStore, SemanticMemoryStore, SessionStore, TopicMasteryStore
from .recommend import RecommendationService


@dataclass
class MemoryService:
    session_store: SessionStore
    mastery_store: TopicMasteryStore
    async_log_store: AsyncLogStore
    settings: Settings
    preference_store: Optional[PreferenceStore] = None
    learning_plan_store: Optional[LearningPlanStore] = None
    semantic_memory_store: Optional[SemanticMemoryStore] = None
    promotion_policy: MemoryPromotionPolicy = field(default_factory=MemoryPromotionPolicy)
    mastery_updater: TopicMasteryUpdater = field(default_factory=TopicMasteryUpdater)
    recommendation_service: RecommendationService = field(default_factory=RecommendationService)
    topic_resolver: CanonicalTopicResolver = field(default_factory=CanonicalTopicResolver)

    def persist_session(self, state: GraphState) -> GraphState:
        persistent = state["persistent"]
        turn = state["turn"]
        runtime = state["runtime"]
        resolved_topic = self._resolve_topic(state)
        current_preferences = self._preference_profile(runtime.user_id, persistent.user_preferences)
        current_mastery = self._load_current_mastery(runtime.user_id, resolved_topic)

        promotion_input = MemoryPromotionInput(
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            user_id=runtime.user_id,
            query=turn.raw_query,
            answer_text=turn.final_answer or "",
            resolved_topic=resolved_topic,
            intent=turn.intent.value if turn.intent else None,
            output_style=turn.requested_output_style.value if turn.requested_output_style else None,
            tool_name=turn.tool_result.tool_name if turn.tool_result else None,
            explicit_signals=self._collect_explicit_signals(state, resolved_topic),
            current_session=self._to_memory_context(persistent),
            current_preferences=current_preferences,
            current_mastery=current_mastery,
            quiz_score=self._extract_quiz_score(state),
            current_time=runtime.request_ts,
            extra={
                "clarification_result": persistent.clarification_result,
                "learning_mode": self._derive_learning_mode(state),
            },
        )
        promotion_result = self.promotion_policy.evaluate(promotion_input)
        write_plan = self.promotion_policy.build_write_plan(self._to_memory_context(persistent), promotion_result)
        updated_context = self._to_domain_context(write_plan.updated_context, persistent)

        runtime_errors = list(runtime.errors)
        try:
            self.session_store.save(updated_context, runtime)
        except Exception as exc:
            runtime_errors.append(
                build_error(
                    WorkflowErrorCode.SESSION_PERSIST_FAILED,
                    stage="persist_session",
                    message=str(exc),
                    retryable=True,
                    degraded_to="in_memory_session_only",
                )
            )
            state["runtime"] = runtime.model_copy(update={"errors": runtime_errors})
            return state

        state["persistent"] = updated_context
        self._persist_preference_patch(runtime.user_id, updated_context, write_plan.preference_patch, runtime_errors)
        self._emit_persist_outbox(state, write_plan, runtime_errors)

        runtime_extra = dict(runtime.extra)
        runtime_extra["memory_updates"] = dict(write_plan.memory_updates)
        runtime_extra["session_persisted"] = True
        state["runtime"] = runtime.model_copy(update={"errors": runtime_errors, "extra": runtime_extra})
        return state

    def update_mastery(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        topic = self._resolve_topic(state)
        if not topic:
            return state

        current = self._load_current_mastery(runtime.user_id, topic)
        computation = self._build_mastery_computation(state, current)
        runtime_errors = list(runtime.errors)

        try:
            saved = self.mastery_store.upsert(
                runtime.user_id,
                computation.topic,
                self._mastery_payload(computation.updated_record, runtime.turn_id),
            )
        except Exception as exc:
            runtime_errors.append(
                build_error(
                    WorkflowErrorCode.MASTERY_UPDATE_FAILED,
                    stage="update_mastery",
                    message=str(exc),
                    retryable=True,
                    degraded_to="skip_mastery_update",
                )
            )
            state["runtime"] = runtime.model_copy(update={"errors": runtime_errors})
            return state

        self._sync_semantic_index(runtime.user_id, computation.semantic_index_updates, runtime, runtime_errors)

        metrics = dict(runtime.metrics)
        metrics.update(dict(computation.metrics_patch))
        metrics["topic_mastery"] = saved
        runtime_extra = dict(runtime.extra)
        memory_updates = dict(runtime_extra.get("memory_updates", {}))
        memory_updates["topic_mastery"] = saved
        runtime_extra["memory_updates"] = memory_updates
        state["runtime"] = runtime.model_copy(update={"metrics": metrics, "errors": runtime_errors, "extra": runtime_extra})
        return state

    def recommend_next(self, state: GraphState) -> GraphState:
        persistent = state["persistent"]
        runtime = state["runtime"]
        mastery_records = tuple(
            self._to_mastery_record(item) for item in self.mastery_store.list_for_user(runtime.user_id)
        )
        active_plan_topics = self._load_active_plan_topics(runtime.user_id, persistent)
        derived_weak_topics = tuple(
            record.topic
            for record in mastery_records
            if record.review_priority >= 60.0 or record.mastery_score < 0.45
        )
        context = RecommendationContext(
            current_topic=self._resolve_topic(state),
            weak_topics=derived_weak_topics,
            mastery_records=mastery_records,
            active_plan_topics=active_plan_topics,
            recent_topics=tuple(persistent.recent_entities),
            preferred_output_style=(
                persistent.user_preferences.get("preferred_output_style")
                or persistent.user_preferences.get("answer_style")
            ),
            learning_mode=bool(persistent.learning_mode),
            requested_limit=1,
        )
        recommendations = self.recommendation_service.recommend(context)
        if not recommendations:
            return state

        snapshot = RecommendationSnapshot(
            topic=recommendations[0].topic,
            reason=recommendations[0].reason,
            source=recommendations[0].source,
            priority=recommendations[0].priority,
            metadata=dict(recommendations[0].metadata),
        )
        turn_extra = dict(state["turn"].extra)
        turn_extra["recommendation"] = {
            "topic": snapshot.topic,
            "reason": snapshot.reason,
            "source": snapshot.source,
            "priority": snapshot.priority,
            "metadata": dict(snapshot.metadata),
        }
        state["turn"] = state["turn"].model_copy(update={"extra": turn_extra})
        return state

    def load_any(self, session_id: str) -> DomainPersistentSessionContext:
        load_any = getattr(self.session_store, "load_any", None)
        if callable(load_any):
            return load_any(session_id)
        sessions = getattr(self.session_store, "sessions", None)
        if isinstance(sessions, dict):
            for (stored_session_id, _), value in sessions.items():
                if stored_session_id == session_id:
                    return value
        return self.session_store.load(session_id, "anonymous")

    def _resolve_topic(self, state: GraphState) -> str:
        turn = state["turn"]
        persistent = state["persistent"]
        candidate = None
        if turn.reference_resolution and turn.reference_resolution.resolved_entity:
            candidate = turn.reference_resolution.resolved_entity
        elif turn.retrieval_plan and turn.retrieval_plan.semantic_query:
            candidate = turn.retrieval_plan.semantic_query
        elif persistent.current_topic:
            candidate = persistent.current_topic
        else:
            candidate = turn.raw_query
        return self.topic_resolver.canonicalize(candidate)

    def _derive_learning_mode(self, state: GraphState) -> bool:
        persistent = state["persistent"]
        turn = state["turn"]
        if persistent.learning_mode:
            return True
        if turn.tool_result and turn.tool_result.tool_name in {"generateQuiz", "generateStudyPlan", "recommendNextTopic"}:
            return True
        return turn.intent is not None

    def _collect_explicit_signals(self, state: GraphState, resolved_topic: str) -> ExplicitUserSignals:
        turn = state["turn"]
        runtime = state["runtime"]
        query = turn.raw_query or ""
        normalized_query = query.lower()
        quiz_score = self._extract_quiz_score(state)
        confusion = self._is_confused_query(normalized_query) or any(
            error.code == WorkflowErrorCode.EVIDENCE_INSUFFICIENT for error in runtime.errors
        )
        return ExplicitUserSignals(
            preferred_output_style=turn.requested_output_style.value if turn.requested_output_style else None,
            wants_code_examples=bool(turn.intent and turn.intent.value == "code"),
            wants_interview_answer=bool(turn.requested_output_style and turn.requested_output_style.value == "interview"),
            confirmed_plan=bool(turn.tool_result and turn.tool_result.tool_name == "generateStudyPlan"),
            mastered=self._is_mastered_query(normalized_query),
            confused=confusion or (quiz_score is not None and quiz_score < 0.6),
            confirmed_output_style=self._is_confirmed_preference_query(normalized_query),
            confirmed_code_examples=self._is_confirmed_behavior_query(normalized_query, "code"),
            confirmed_interview_mode=self._is_confirmed_behavior_query(normalized_query, "interview"),
            repeated_topic_signal=bool(resolved_topic and resolved_topic in state["persistent"].recent_entities),
            low_quiz_score=quiz_score if quiz_score is not None and quiz_score < 0.6 else None,
            weak_topics=(),
        )

    def _persist_preference_patch(
        self,
        user_id: str,
        updated_context: DomainPersistentSessionContext,
        preference_patch: Mapping[str, Any],
        runtime_errors: list,
    ) -> None:
        if self.preference_store is None or not preference_patch:
            return
        try:
            self.preference_store.upsert(
                UserPreferenceProfileRecord(
                    user_id=user_id,
                    answer_style=updated_context.user_preferences.get("preferred_output_style")
                    or updated_context.user_preferences.get("answer_style"),
                    explanation_depth=updated_context.user_preferences.get("preferred_output_style")
                    or updated_context.user_preferences.get("answer_style"),
                    prefer_code_examples=updated_context.user_preferences.get("prefers_code_examples"),
                    extra={
                        "answer_style_counter": dict(updated_context.user_preferences.get("answer_style_counter", {})),
                        "behavior_counters": dict(updated_context.user_preferences.get("behavior_counters", {})),
                        "prefers_interview_mode": bool(
                            updated_context.user_preferences.get("prefers_interview_mode", False)
                        ),
                    },
                )
            )
        except Exception as exc:
            runtime_errors.append(
                build_error(
                    WorkflowErrorCode.ASYNC_LOG_WRITE_FAILED,
                    stage="persist_session.preference_store",
                    message=str(exc),
                    retryable=True,
                    degraded_to="session_only",
                )
            )

    def _emit_persist_outbox(
        self,
        state: GraphState,
        write_plan: PersistSessionPlan,
        runtime_errors: list,
    ) -> None:
        runtime = state["runtime"]
        for request in write_plan.durable_fact_requests:
            self._append_async_log(
                {
                    "event_type": "memory.%s" % request.fact_type,
                    "session_id": runtime.session_id,
                    "turn_id": runtime.turn_id,
                    "trace_id": runtime.trace_id,
                    "payload": dict(request.payload),
                },
                runtime_errors,
                stage="persist_session.outbox",
            )
        for event in write_plan.outbox_events:
            payload = dict(event)
            payload.setdefault("session_id", runtime.session_id)
            payload.setdefault("turn_id", runtime.turn_id)
            payload.setdefault("trace_id", runtime.trace_id)
            self._append_async_log(payload, runtime_errors, stage="persist_session.outbox")
        self._append_async_log(
            {
                "event_type": "persist_session",
                "session_id": runtime.session_id,
                "turn_id": runtime.turn_id,
                "trace_id": runtime.trace_id,
                "topic": write_plan.updated_context.current_topic,
            },
            runtime_errors,
            stage="persist_session.outbox",
        )

    def _build_mastery_computation(
        self,
        state: GraphState,
        current: TopicMasteryRecord,
    ) -> MasteryComputation:
        runtime = state["runtime"]
        turn = state["turn"]
        evidence_count = len(turn.citations)
        if turn.evidence_pack is not None:
            evidence_count = max(evidence_count, len(turn.evidence_pack.items))
        quiz_score = self._extract_quiz_score(state)
        weak_topics = tuple(dict(runtime.extra.get("memory_updates", {})).get("weak_topics", []))
        signal = MasteryUpdateInput(
            topic=current.topic,
            signal_type=self._mastery_signal_type(state),
            quiz_score=quiz_score,
            was_confused=self._is_confused_query((turn.raw_query or "").lower()),
            weak_signal=current.topic in weak_topics or (quiz_score is not None and quiz_score < 0.6),
            was_resolved=bool(turn.final_answer) and not any(
                error.code == WorkflowErrorCode.EVIDENCE_INSUFFICIENT for error in runtime.errors
            ),
            explicit_mastered=self._is_mastered_query((turn.raw_query or "").lower()),
            repeated_topic=current.topic in state["persistent"].recent_entities,
            evidence_delta=max(evidence_count, 1),
            supporting_evidence_count=evidence_count,
            timestamp=runtime.request_ts or datetime.now(timezone.utc),
        )
        updated = self.mastery_updater.update(current, signal)
        signal_summary = {
            "topic": updated.topic,
            "signal_type": signal.signal_type,
            "quiz_score": quiz_score,
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

    def _mastery_signal_type(self, state: GraphState) -> str:
        tool_result = state["turn"].tool_result
        if tool_result and tool_result.tool_name == "generateQuiz":
            return "quiz"
        if state["turn"].reference_resolution and state["turn"].reference_resolution.resolved:
            return "review"
        return "study"

    def _sync_semantic_index(
        self,
        user_id: str,
        updates: Sequence[SemanticIndexUpdate],
        runtime,
        runtime_errors: list,
    ) -> None:
        for update in updates:
            try:
                if self.semantic_memory_store is not None:
                    self.semantic_memory_store.mark_indexed_state(user_id, update.topic, update.indexed)
                else:
                    self._append_async_log(
                        {
                            "event_type": "memory.semantic_index_update",
                            "session_id": runtime.session_id,
                            "turn_id": runtime.turn_id,
                            "trace_id": runtime.trace_id,
                            "payload": {
                                "user_id": user_id,
                                "topic": update.topic,
                                "indexed": update.indexed,
                                "reason": update.reason,
                                "metadata": dict(update.metadata),
                            },
                        },
                        runtime_errors,
                        stage="update_mastery.semantic_index",
                    )
            except Exception as exc:
                runtime_errors.append(
                    build_error(
                        WorkflowErrorCode.ASYNC_LOG_WRITE_FAILED,
                        stage="update_mastery.semantic_index",
                        message=str(exc),
                        retryable=True,
                        degraded_to="skip_semantic_index_update",
                    )
                )

    def _append_async_log(self, entry: Mapping[str, Any], runtime_errors: list, stage: str) -> None:
        try:
            self.async_log_store.append(dict(entry))
        except Exception as exc:
            runtime_errors.append(
                build_error(
                    WorkflowErrorCode.ASYNC_LOG_WRITE_FAILED,
                    stage=stage,
                    message=str(exc),
                    retryable=True,
                    degraded_to="skip_async_log",
                )
            )

    def _load_active_plan_topics(
        self,
        user_id: str,
        persistent: DomainPersistentSessionContext,
    ) -> Tuple[str, ...]:
        plan_topics = tuple(persistent.extra.get("active_plan_topics", []))
        if plan_topics:
            return self.topic_resolver.canonicalize_many(plan_topics)
        if self.learning_plan_store is None or not persistent.active_plan_id:
            return ()

        list_for_plan = getattr(self.learning_plan_store, "list_for_plan", None)
        if callable(list_for_plan):
            try:
                return self.topic_resolver.canonicalize_many(
                    self._extract_plan_topics(list_for_plan(persistent.active_plan_id))
                )
            except Exception:
                return ()

        list_by_plan = getattr(self.learning_plan_store, "list_by_plan", None)
        if callable(list_by_plan):
            try:
                return self.topic_resolver.canonicalize_many(
                    self._extract_plan_topics(list_by_plan(user_id, persistent.active_plan_id))
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

    def _extract_quiz_score(self, state: GraphState) -> Optional[float]:
        tool_result = state["turn"].tool_result
        if not tool_result or tool_result.tool_name != "generateQuiz":
            return None
        data = tool_result.normalized_output.get("data", {})
        score = data.get("score")
        if isinstance(score, (int, float)):
            return float(score)
        return None

    @staticmethod
    def _is_confirmed_preference_query(query: str) -> bool:
        phrases = ("以后都", "以后默认", "默认用", "一直用", "长期用", "always use", "default to")
        return any(phrase in query for phrase in phrases)

    @staticmethod
    def _is_confirmed_behavior_query(query: str, behavior: str) -> bool:
        if behavior == "code":
            phrases = ("以后都给代码", "默认给代码", "always include code", "default to code")
        else:
            phrases = ("以后都按面试", "默认面试回答", "always answer for interview", "default interview")
        return any(phrase in query for phrase in phrases)

    @staticmethod
    def _is_mastered_query(query: str) -> bool:
        phrases = ("我懂了", "明白了", "已经掌握", "会了", "got it", "understood")
        return any(phrase in query for phrase in phrases)

    @staticmethod
    def _is_confused_query(query: str) -> bool:
        phrases = ("不懂", "没懂", "还是不会", "记不住", "总答错", "混淆", "confused", "still unclear")
        return any(phrase in query for phrase in phrases)
