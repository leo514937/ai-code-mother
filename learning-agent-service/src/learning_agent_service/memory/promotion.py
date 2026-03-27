from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .canonical import CanonicalTopicResolver
from .models import (
    DurableFactRequest,
    MemoryPromotionInput,
    MemoryPromotionResult,
    PersistSessionPlan,
    PersistentSessionContext,
    SemanticMemoryFact,
    SessionUpdate,
)


@dataclass(frozen=True)
class PromotionConfig:
    preference_promote_count: int = 3
    behavior_promote_count: int = 2
    weak_topic_negative_threshold: int = 2
    low_quiz_threshold: float = 0.6


@dataclass(frozen=True)
class DurableMemoryWritePlan:
    session_update: SessionUpdate
    preference_patch: Mapping[str, Any]
    semantic_facts: Tuple[SemanticMemoryFact, ...]
    weak_topics: Tuple[str, ...]
    durable_fact_requests: Tuple[DurableFactRequest, ...]
    outbox_events: Tuple[Mapping[str, Any], ...]


class SessionMemoryUpdater:
    def __init__(self, resolver: Optional[CanonicalTopicResolver] = None) -> None:
        self._resolver = resolver or CanonicalTopicResolver()

    def build_update(
        self,
        current: PersistentSessionContext,
        resolved_topic: Optional[str],
        clarification_result: Optional[Mapping[str, Any]] = None,
        learning_mode: Optional[bool] = None,
    ) -> SessionUpdate:
        topic = self._resolver.canonicalize(resolved_topic) if resolved_topic else current.current_topic
        entities = list(current.recent_entities)
        if topic:
            entities.insert(0, topic)
        deduped_entities = tuple(dict.fromkeys(entity for entity in entities if entity))[:5]
        return SessionUpdate(
            current_topic=topic,
            recent_entities=deduped_entities,
            clarification_result=dict(clarification_result or {}),
            last_retrieval_topic=topic or current.last_retrieval_topic,
            learning_mode=current.learning_mode if learning_mode is None else learning_mode,
            history_summary=self._build_history_summary(current.history_summary, topic),
            pending_clarification=None,
        )

    def merge_context(self, current: PersistentSessionContext, update: SessionUpdate) -> PersistentSessionContext:
        extra = dict(current.extra)
        extra.update(dict(update.extra))
        return PersistentSessionContext(
            current_topic=update.current_topic or current.current_topic,
            recent_entities=update.recent_entities or current.recent_entities,
            clarification_result=update.clarification_result or current.clarification_result,
            user_preferences=current.user_preferences,
            last_retrieval_topic=update.last_retrieval_topic or current.last_retrieval_topic,
            active_plan_id=current.active_plan_id,
            learning_mode=current.learning_mode if update.learning_mode is None else update.learning_mode,
            history_summary=update.history_summary or current.history_summary,
            pending_clarification=update.pending_clarification,
            extra=extra,
        )

    def _build_history_summary(self, current_summary: Optional[str], topic: Optional[str]) -> Optional[str]:
        canonical_topic = self._resolver.canonicalize(topic) if topic else ""
        if not canonical_topic:
            return current_summary
        if not current_summary:
            return canonical_topic
        segments = [segment.strip() for segment in current_summary.split(" -> ") if segment.strip()]
        if canonical_topic in segments:
            segments = [segment for segment in segments if segment != canonical_topic]
        segments.append(canonical_topic)
        return " -> ".join(segments[-4:])


class MemoryPromotionPolicy:
    def __init__(self, config: PromotionConfig = None, resolver: Optional[CanonicalTopicResolver] = None) -> None:
        self._config = config or PromotionConfig()
        self._resolver = resolver or CanonicalTopicResolver()
        self._updater = SessionMemoryUpdater(self._resolver)

    def evaluate(self, payload: MemoryPromotionInput) -> MemoryPromotionResult:
        now = payload.current_time or datetime.utcnow()
        topic = self._resolver.canonicalize(payload.resolved_topic) if payload.resolved_topic else None
        session_update = self._updater.build_update(
            current=payload.current_session,
            resolved_topic=topic,
            clarification_result=payload.extra.get("clarification_result"),
            learning_mode=payload.extra.get("learning_mode", payload.current_session.learning_mode),
        )

        reasons: List[str] = []
        preference_patch: Dict[str, Any] = {}
        durable_fact_requests: List[DurableFactRequest] = []
        semantic_facts: List[SemanticMemoryFact] = []
        weak_topics: List[str] = []
        outbox_events: List[Mapping[str, Any]] = []

        profile = payload.current_preferences
        mastery = payload.current_mastery
        counters = dict(profile.answer_style_counter) if profile else {}
        behavior_counters = dict((profile.extra or {}).get("behavior_counters", {})) if profile else {}

        output_style = payload.explicit_signals.preferred_output_style or payload.output_style
        if output_style:
            counters[output_style] = counters.get(output_style, 0) + 1
            preference_patch["answer_style_counter"] = counters
            if (
                payload.explicit_signals.confirmed_output_style
                or counters[output_style] >= self._config.preference_promote_count
            ):
                preference_patch["preferred_output_style"] = output_style
                reasons.append("promoted_output_style")

        if payload.explicit_signals.wants_code_examples:
            behavior_counters["code_examples"] = int(behavior_counters.get("code_examples", 0)) + 1
            if (
                payload.explicit_signals.confirmed_code_examples
                or behavior_counters["code_examples"] >= self._config.behavior_promote_count
            ):
                preference_patch["prefers_code_examples"] = True
                reasons.append("promoted_code_example_preference")

        if payload.explicit_signals.wants_interview_answer:
            behavior_counters["interview_mode"] = int(behavior_counters.get("interview_mode", 0)) + 1
            if (
                payload.explicit_signals.confirmed_interview_mode
                or behavior_counters["interview_mode"] >= self._config.behavior_promote_count
            ):
                preference_patch["prefers_interview_mode"] = True
                reasons.append("promoted_interview_preference")

        if behavior_counters:
            preference_patch["behavior_counters"] = behavior_counters

        if preference_patch:
            durable_fact_requests.append(
                DurableFactRequest(
                    fact_type="preference_patch",
                    payload={
                        "user_id": payload.user_id,
                        "session_id": payload.session_id,
                        "turn_id": payload.turn_id,
                        "patch": dict(preference_patch),
                    },
                )
            )

        low_quiz_signal = (
            payload.quiz_score is not None and payload.quiz_score < self._config.low_quiz_threshold
        ) or payload.explicit_signals.low_quiz_score is not None
        if topic and (payload.explicit_signals.confused or low_quiz_signal):
            weak_topics.append(topic)
        if mastery and mastery.negative_signals >= self._config.weak_topic_negative_threshold:
            weak_topics.append(mastery.topic)
        for weak_topic in payload.explicit_signals.weak_topics:
            weak_topics.append(self._resolver.canonicalize(weak_topic))
        weak_topics = list(dict.fromkeys(name for name in weak_topics if name))
        if weak_topics:
            reasons.append("topic_marked_weak")
            durable_fact_requests.append(
                DurableFactRequest(
                    fact_type="weak_topic_signal",
                    payload={
                        "user_id": payload.user_id,
                        "session_id": payload.session_id,
                        "turn_id": payload.turn_id,
                        "topics": list(weak_topics),
                    },
                )
            )

        if topic and self._should_promote_semantic_fact(payload, mastery):
            fact_type = self._semantic_fact_type(payload)
            semantic_facts.append(
                SemanticMemoryFact(
                    fact_id="%s:%s:%s" % (payload.user_id, payload.turn_id, topic),
                    topic=topic,
                    content=(payload.answer_text or payload.query)[:240],
                    fact_type=fact_type,
                    strength=self._semantic_strength(payload),
                    created_at=now,
                    last_referenced_at=now,
                    metadata={
                        "intent": payload.intent,
                        "tool_name": payload.tool_name,
                        "quiz_score": payload.quiz_score,
                        "output_style": output_style,
                    },
                )
            )
            reasons.append("promoted_semantic_fact")

        for fact in semantic_facts:
            durable_fact_requests.append(
                DurableFactRequest(
                    fact_type="semantic_memory_fact",
                    payload={
                        "user_id": payload.user_id,
                        "fact_id": fact.fact_id,
                        "topic": fact.topic,
                        "fact_type": fact.fact_type,
                        "strength": fact.strength,
                        "metadata": dict(fact.metadata),
                    },
                )
            )

        if payload.explicit_signals.confirmed_plan:
            outbox_events.append(
                {
                    "event_type": "plan_confirmed",
                    "topic": topic,
                    "turn_id": payload.turn_id,
                    "user_id": payload.user_id,
                }
            )
            durable_fact_requests.append(
                DurableFactRequest(
                    fact_type="learning_plan_confirmation",
                    payload={
                        "user_id": payload.user_id,
                        "session_id": payload.session_id,
                        "turn_id": payload.turn_id,
                        "topic": topic,
                    },
                )
            )

        if payload.extra.get("clarification_result"):
            durable_fact_requests.append(
                DurableFactRequest(
                    fact_type="clarification_result",
                    payload={
                        "user_id": payload.user_id,
                        "session_id": payload.session_id,
                        "turn_id": payload.turn_id,
                        "clarification_result": dict(payload.extra.get("clarification_result", {})),
                    },
                )
            )

        return MemoryPromotionResult(
            session_update=session_update,
            preference_patch=preference_patch,
            semantic_facts=tuple(semantic_facts),
            weak_topics=tuple(weak_topics),
            reasons=tuple(reasons),
            durable_fact_requests=tuple(durable_fact_requests),
            outbox_events=tuple(outbox_events),
            extra={"resolved_topic": topic},
        )

    def build_write_plan(
        self,
        current: PersistentSessionContext,
        result: MemoryPromotionResult,
    ) -> PersistSessionPlan:
        merged_preferences = dict(current.user_preferences)
        merged_preferences.update(dict(result.preference_patch))
        extra = dict(current.extra)
        if result.weak_topics:
            extra["weak_topics"] = list(
                dict.fromkeys(list(extra.get("weak_topics", [])) + list(result.weak_topics))
            )
        updated_context = self._updater.merge_context(
            current,
            result.session_update,
        )
        updated_context = PersistentSessionContext(
            current_topic=updated_context.current_topic,
            recent_entities=updated_context.recent_entities,
            clarification_result=updated_context.clarification_result,
            user_preferences=merged_preferences,
            last_retrieval_topic=updated_context.last_retrieval_topic,
            active_plan_id=updated_context.active_plan_id,
            learning_mode=updated_context.learning_mode,
            history_summary=updated_context.history_summary,
            pending_clarification=updated_context.pending_clarification,
            extra=extra,
        )
        return PersistSessionPlan(
            updated_context=updated_context,
            preference_patch=result.preference_patch,
            semantic_facts=result.semantic_facts,
            weak_topics=result.weak_topics,
            durable_fact_requests=result.durable_fact_requests,
            outbox_events=result.outbox_events,
            memory_updates={
                "current_topic": updated_context.current_topic,
                "recent_entities": list(updated_context.recent_entities),
                "user_preferences": dict(updated_context.user_preferences),
                "promotion_reasons": list(result.reasons),
                "weak_topics": list(result.weak_topics),
                "history_summary": updated_context.history_summary,
            },
        )

    @staticmethod
    def build_write_plan_legacy(result: MemoryPromotionResult) -> DurableMemoryWritePlan:
        return DurableMemoryWritePlan(
            session_update=result.session_update,
            preference_patch=result.preference_patch,
            semantic_facts=result.semantic_facts,
            weak_topics=result.weak_topics,
            durable_fact_requests=result.durable_fact_requests,
            outbox_events=result.outbox_events,
        )

    def _should_promote_semantic_fact(
        self,
        payload: MemoryPromotionInput,
        mastery: Optional[Any],
    ) -> bool:
        if payload.explicit_signals.confirmed_plan or payload.explicit_signals.mastered:
            return True
        if payload.explicit_signals.confused or payload.explicit_signals.repeated_topic_signal:
            return True
        if payload.quiz_score is not None and payload.quiz_score < self._config.low_quiz_threshold:
            return True
        if mastery is not None and getattr(mastery, "negative_signals", 0) >= self._config.weak_topic_negative_threshold:
            return True
        return False

    def _semantic_fact_type(self, payload: MemoryPromotionInput) -> str:
        if payload.explicit_signals.confirmed_plan:
            return "confirmed_plan"
        if payload.explicit_signals.mastered:
            return "mastery_signal"
        if payload.explicit_signals.confused or payload.quiz_score is not None:
            return "weak_signal"
        if payload.explicit_signals.repeated_topic_signal:
            return "repeat_interest"
        return "learning_fact"

    @staticmethod
    def _semantic_strength(payload: MemoryPromotionInput) -> float:
        if payload.explicit_signals.confirmed_plan:
            return 0.9
        if payload.explicit_signals.mastered:
            return 0.85
        if payload.explicit_signals.confused or payload.quiz_score is not None:
            return 0.75
        return 0.65
