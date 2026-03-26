from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .canonical import CanonicalTopicResolver
from .models import TopicMasteryRecord


@dataclass(frozen=True)
class MasteryUpdateInput:
    topic: str
    signal_type: str = "study"
    quiz_score: Optional[float] = None
    was_confused: bool = False
    was_resolved: bool = False
    explicit_mastered: bool = False
    evidence_delta: int = 1
    timestamp: Optional[datetime] = None


class TopicMasteryUpdater:
    def __init__(self, resolver: Optional[CanonicalTopicResolver] = None) -> None:
        self._resolver = resolver or CanonicalTopicResolver()

    def update(self, current: Optional[TopicMasteryRecord], signal: MasteryUpdateInput) -> TopicMasteryRecord:
        topic = self._resolver.canonicalize(signal.topic)
        existing = current or TopicMasteryRecord(topic=topic)
        mastery_score = existing.mastery_score
        confidence_score = existing.confidence_score
        evidence_count = existing.evidence_count
        positive_signals = existing.positive_signals
        negative_signals = existing.negative_signals
        last_quiz_score = existing.last_quiz_score

        if signal.quiz_score is not None:
            last_quiz_score = signal.quiz_score
            if signal.quiz_score >= 0.85:
                mastery_score += 0.15
                positive_signals += 1
            elif signal.quiz_score >= 0.7:
                mastery_score += 0.08
                positive_signals += 1
            elif signal.quiz_score >= 0.5:
                mastery_score += 0.02
            elif signal.quiz_score >= 0.35:
                mastery_score -= 0.10
                negative_signals += 1
            else:
                mastery_score -= 0.18
                negative_signals += 1
        elif signal.explicit_mastered:
            mastery_score += 0.1
            positive_signals += 1
        elif signal.was_confused:
            mastery_score -= 0.1
            negative_signals += 1
        elif signal.signal_type == "study":
            mastery_score += 0.02
        elif signal.signal_type == "retrieval":
            mastery_score += 0.01

        if signal.was_resolved:
            mastery_score += 0.05
            positive_signals += 1

        evidence_count += max(signal.evidence_delta, 0)
        confidence_score += min(0.05 * max(signal.evidence_delta, 1), 0.2)

        mastery_score = max(0.0, min(mastery_score, 1.0))
        confidence_score = max(0.0, min(confidence_score, 1.0))
        review_priority = self._review_priority(mastery_score, last_quiz_score, signal.was_confused, negative_signals)

        return TopicMasteryRecord(
            topic=topic,
            mastery_score=mastery_score,
            confidence_score=confidence_score,
            evidence_count=evidence_count,
            last_seen_at=signal.timestamp or datetime.utcnow(),
            last_quiz_score=last_quiz_score,
            review_priority=review_priority,
            positive_signals=positive_signals,
            negative_signals=negative_signals,
            extra=dict(existing.extra),
        )

    @staticmethod
    def _review_priority(mastery_score: float, quiz_score: Optional[float], was_confused: bool, negative_signals: int) -> float:
        priority = 20.0 + max(0.0, (0.6 - mastery_score) * 100.0)
        if quiz_score is not None and quiz_score < 0.6:
            priority += 20.0
        if was_confused:
            priority += 15.0
        priority += min(negative_signals * 5.0, 20.0)
        return max(0.0, min(priority, 100.0))
