from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .canonical import CanonicalTopicResolver
from .models import QuizTarget, Recommendation, RecommendationContext, TopicMasteryRecord


class RecommendationService:
    def __init__(self, resolver: Optional[CanonicalTopicResolver] = None) -> None:
        self._resolver = resolver or CanonicalTopicResolver()

    def recommend(self, context: RecommendationContext) -> Tuple[Recommendation, ...]:
        if not context.learning_mode:
            return ()

        current_topic = self._resolver.canonicalize(context.current_topic) if context.current_topic else None
        candidates: List[Recommendation] = []
        seen = set()

        for topic in context.weak_topics:
            canonical = self._resolver.canonicalize(topic)
            if canonical and canonical != current_topic and canonical not in seen:
                seen.add(canonical)
                candidates.append(
                    Recommendation(
                        topic=canonical,
                        reason="weak topic needs reinforcement",
                        priority=95.0,
                        source="weak_topic",
                    )
                )

        for record in sorted(context.mastery_records, key=lambda item: item.review_priority, reverse=True):
            if record.topic == current_topic or record.topic in seen:
                continue
            seen.add(record.topic)
            candidates.append(
                Recommendation(
                    topic=record.topic,
                    reason="review priority is high",
                    priority=record.review_priority,
                    source="topic_mastery",
                    metadata={"mastery_score": record.mastery_score},
                )
            )

        for topic in context.active_plan_topics:
            canonical = self._resolver.canonicalize(topic)
            if canonical and canonical != current_topic and canonical not in seen:
                seen.add(canonical)
                candidates.append(
                    Recommendation(
                        topic=canonical,
                        reason="active learning plan sequence",
                        priority=70.0,
                        source="learning_plan",
                    )
                )

        candidates.sort(key=lambda item: item.priority, reverse=True)
        return tuple(candidates[: context.requested_limit])


class QuizTargetingService:
    def __init__(self, resolver: Optional[CanonicalTopicResolver] = None) -> None:
        self._resolver = resolver or CanonicalTopicResolver()

    def build_targets(self, context: RecommendationContext, limit: int = 5) -> Tuple[QuizTarget, ...]:
        targets: List[QuizTarget] = []
        seen = set()
        mastery_by_topic: Dict[str, TopicMasteryRecord] = {record.topic: record for record in context.mastery_records}

        for topic in context.weak_topics:
            canonical = self._resolver.canonicalize(topic)
            if canonical and canonical not in seen:
                seen.add(canonical)
                targets.append(
                    QuizTarget(
                        topic=canonical,
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

        for topic in context.active_plan_topics:
            canonical = self._resolver.canonicalize(topic)
            record = mastery_by_topic.get(canonical)
            if canonical and canonical not in seen:
                seen.add(canonical)
                targets.append(
                    QuizTarget(
                        topic=canonical,
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
