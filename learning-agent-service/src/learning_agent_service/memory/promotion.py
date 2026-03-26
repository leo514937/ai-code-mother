from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .canonical import CanonicalTopicResolver
from .models import (
    MemoryPromotionInput,
    MemoryPromotionResult,
    PersistentSessionContext,
    SemanticMemoryFact,
    SessionUpdate,
)


@dataclass(frozen=True)
class PromotionConfig:
    preference_promote_count: int = 3
    weak_topic_negative_threshold: int = 2


@dataclass(frozen=True)
class DurableMemoryWritePlan:
    session_update: SessionUpdate
    preference_patch: Mapping[str, Any]
    semantic_facts: Tuple[SemanticMemoryFact, ...]
    weak_topics: Tuple[str, ...]
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
            summary_delta=topic,
        )

    def merge_context(self, current: PersistentSessionContext, update: SessionUpdate) -> PersistentSessionContext:
        return PersistentSessionContext(
            current_topic=update.current_topic or current.current_topic,
            recent_entities=update.recent_entities or current.recent_entities,
            clarification_result=update.clarification_result or current.clarification_result,
            user_preferences=current.user_preferences,
            last_retrieval_topic=update.last_retrieval_topic or current.last_retrieval_topic,
            active_plan_id=current.active_plan_id,
            learning_mode=current.learning_mode if update.learning_mode is None else update.learning_mode,
            extra=dict(current.extra),
        )


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
            learning_mode=payload.current_session.learning_mode,
        )

        reasons: List[str] = []
        preference_patch: Dict[str, Any] = {}
        semantic_facts: List[SemanticMemoryFact] = []
        weak_topics: List[str] = []
        outbox_events: List[Mapping[str, Any]] = []

        profile = payload.current_preferences
        counters = dict(profile.answer_style_counter) if profile else {}
        output_style = payload.explicit_signals.preferred_output_style or payload.output_style
        if output_style:
            counters[output_style] = counters.get(output_style, 0) + 1
            preference_patch["answer_style_counter"] = counters
            if counters[output_style] >= self._config.preference_promote_count or payload.explicit_signals.preferred_output_style:
                preference_patch["preferred_output_style"] = output_style
                reasons.append("promoted_output_style")

        if payload.explicit_signals.wants_code_examples:
            preference_patch["prefers_code_examples"] = True
            reasons.append("promoted_code_example_preference")
        if payload.explicit_signals.wants_interview_answer:
            preference_patch["prefers_interview_mode"] = True
            reasons.append("promoted_interview_preference")

        if topic and (payload.explicit_signals.confirmed_plan or payload.explicit_signals.mastered or payload.explicit_signals.confused):
            fact_type = "learning_fact"
            if payload.explicit_signals.confirmed_plan:
                fact_type = "confirmed_plan"
            elif payload.explicit_signals.mastered:
                fact_type = "mastery_signal"
            elif payload.explicit_signals.confused:
                fact_type = "weak_signal"
            semantic_facts.append(
                SemanticMemoryFact(
                    fact_id="%s:%s:%s" % (payload.user_id, payload.turn_id, topic),
                    topic=topic,
                    content=payload.answer_text[:200],
                    fact_type=fact_type,
                    strength=0.8 if payload.explicit_signals.confirmed_plan else 0.6,
                    created_at=now,
                    last_referenced_at=now,
                    metadata={"intent": payload.intent, "tool_name": payload.tool_name},
                )
            )
            reasons.append("promoted_semantic_fact")

        if payload.explicit_signals.confused and topic:
            weak_topics.append(topic)
            reasons.append("topic_marked_weak")
        for weak_topic in payload.explicit_signals.weak_topics:
            weak_topics.append(self._resolver.canonicalize(weak_topic))
        weak_topics = list(dict.fromkeys(topic_name for topic_name in weak_topics if topic_name))

        if payload.explicit_signals.confirmed_plan:
            outbox_events.append({"event_type": "plan_confirmed", "topic": topic, "turn_id": payload.turn_id})

        return MemoryPromotionResult(
            session_update=session_update,
            preference_patch=preference_patch,
            semantic_facts=tuple(semantic_facts),
            weak_topics=tuple(weak_topics),
            reasons=tuple(reasons),
            outbox_events=tuple(outbox_events),
        )

    @staticmethod
    def build_write_plan(result: MemoryPromotionResult) -> DurableMemoryWritePlan:
        return DurableMemoryWritePlan(
            session_update=result.session_update,
            preference_patch=result.preference_patch,
            semantic_facts=result.semantic_facts,
            weak_topics=result.weak_topics,
            outbox_events=result.outbox_events,
        )
