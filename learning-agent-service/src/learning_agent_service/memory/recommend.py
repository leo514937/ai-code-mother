from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .canonical import CanonicalTopicResolver
from .models import QuizTarget, Recommendation, RecommendationContext, TopicMasteryRecord


@dataclass(frozen=True)
class MemoryRecommendationPolicyConfig:
    low_mastery_threshold: float = 0.45
    review_priority_threshold: float = 60.0


class RecommendationService:
    def __init__(
        self,
        resolver: Optional[CanonicalTopicResolver] = None,
        config: Optional[MemoryRecommendationPolicyConfig] = None,
    ) -> None:
        self._resolver = resolver or CanonicalTopicResolver()
        self.config = config or MemoryRecommendationPolicyConfig()

    def recommend(self, context: RecommendationContext) -> Tuple[Recommendation, ...]:
        if not context.learning_mode:
            return ()

        current_topic = self._resolver.canonicalize(context.current_topic) if context.current_topic else None
        recent_topics = self._resolver.canonicalize_many(context.recent_topics)
        recent_exclusions = set(recent_topics[:2])
        candidates: List[Recommendation] = []
        seen = set()

        active_plan_topics = self._resolver.canonicalize_many(context.active_plan_topics)
        next_plan_topic = self._next_plan_topic(active_plan_topics, current_topic, recent_exclusions)
        if next_plan_topic is not None:
            seen.add(next_plan_topic)
            candidates.append(
                Recommendation(
                    topic=next_plan_topic,
                    reason="next topic in the active learning plan",
                    priority=92.0,
                    source="learning_plan",
                    metadata={"preferred_output_style": context.preferred_output_style},
                )
            )

        for topic in self._derive_weak_topics(context):
            if topic == current_topic or topic in seen:
                continue
            seen.add(topic)
            candidates.append(
                Recommendation(
                    topic=topic,
                    reason="topic needs reinforcement based on mastery signals",
                    priority=88.0,
                    source="mastery_weakness",
                    metadata={"preferred_output_style": context.preferred_output_style},
                )
            )

        for record in sorted(context.mastery_records, key=lambda item: item.review_priority, reverse=True):
            if record.topic == current_topic or record.topic in seen:
                continue
            if record.topic in recent_exclusions and record.review_priority < 80.0:
                continue
            seen.add(record.topic)
            candidates.append(
                Recommendation(
                    topic=record.topic,
                    reason="review priority is high",
                    priority=record.review_priority,
                    source="topic_mastery",
                    metadata={
                        "mastery_score": record.mastery_score,
                        "preferred_output_style": context.preferred_output_style,
                    },
                )
            )

        for topic in active_plan_topics:
            if topic == current_topic or topic in seen:
                continue
            seen.add(topic)
            candidates.append(
                Recommendation(
                    topic=topic,
                    reason="keep progressing through the active learning plan",
                    priority=72.0,
                    source="learning_plan_backfill",
                    metadata={"preferred_output_style": context.preferred_output_style},
                )
            )

        candidates.sort(key=lambda item: item.priority, reverse=True)
        return tuple(candidates[: context.requested_limit])

    def _derive_weak_topics(self, context: RecommendationContext) -> Tuple[str, ...]:
        topics = list(self._resolver.canonicalize_many(context.weak_topics))
        for record in context.mastery_records:
            if record.mastery_score < self.config.low_mastery_threshold or record.review_priority >= self.config.review_priority_threshold:
                topics.append(record.topic)
        return self._resolver.canonicalize_many(topics)

    def _next_plan_topic(
        self,
        active_plan_topics: Sequence[str],
        current_topic: Optional[str],
        recent_exclusions: set[str],
    ) -> Optional[str]:
        if not active_plan_topics:
            return None
        if current_topic and current_topic in active_plan_topics:
            current_index = active_plan_topics.index(current_topic)
            for topic in active_plan_topics[current_index + 1 :]:
                if topic not in recent_exclusions:
                    return topic
        for topic in active_plan_topics:
            if topic != current_topic and topic not in recent_exclusions:
                return topic
        return None


class QuizTargetingService:
    def __init__(
        self,
        resolver: Optional[CanonicalTopicResolver] = None,
        config: Optional[MemoryRecommendationPolicyConfig] = None,
    ) -> None:
        self._resolver = resolver or CanonicalTopicResolver()
        self.config = config or MemoryRecommendationPolicyConfig()

    def build_targets(self, context: RecommendationContext, limit: int = 5) -> Tuple[QuizTarget, ...]:
        targets: List[QuizTarget] = []
        seen = set()
        mastery_by_topic: Dict[str, TopicMasteryRecord] = {record.topic: record for record in context.mastery_records}

        weak_topics = list(self._resolver.canonicalize_many(context.weak_topics))
        if not weak_topics:
            weak_topics = [
                record.topic
                for record in context.mastery_records
                if record.review_priority >= self.config.review_priority_threshold or record.mastery_score < self.config.low_mastery_threshold
            ]

        for topic in self._resolver.canonicalize_many(weak_topics):
            if topic and topic not in seen:
                seen.add(topic)
                targets.append(
                    QuizTarget(
                        topic=topic,
                        reason="explicit weak topic",
                        difficulty_hint="beginner",
                        priority=95.0,
                    )
                )

        for record in sorted(context.mastery_records, key=lambda item: item.review_priority, reverse=True):
            if record.topic in seen:
                continue
            seen.add(record.topic)
            targets.append(
                QuizTarget(
                    topic=record.topic,
                    reason="review priority driven quiz target",
                    difficulty_hint=self._difficulty_hint(record),
                    priority=record.review_priority,
                    metadata={"mastery_score": record.mastery_score},
                )
            )

        for topic in self._resolver.canonicalize_many(context.active_plan_topics):
            record = mastery_by_topic.get(topic)
            if topic and topic not in seen:
                seen.add(topic)
                targets.append(
                    QuizTarget(
                        topic=topic,
                        reason="active plan coverage",
                        difficulty_hint=self._difficulty_hint(record),
                        priority=60.0,
                    )
                )

        targets.sort(key=lambda item: item.priority, reverse=True)
        return tuple(targets[:limit])

    @staticmethod
    def _difficulty_hint(record: Optional[TopicMasteryRecord]) -> str:
        if record is None:
            return "beginner"
        if record.mastery_score >= 0.75:
            return "advanced"
        if record.mastery_score >= 0.4:
            return "intermediate"
        return "beginner"
