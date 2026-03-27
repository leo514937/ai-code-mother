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
    weak_signal: bool = False
    was_resolved: bool = False
    explicit_mastered: bool = False
    repeated_topic: bool = False
    evidence_delta: int = 1
    supporting_evidence_count: int = 0
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
                confidence_score += 0.08
                positive_signals += 1
            elif signal.quiz_score >= 0.7:
                mastery_score += 0.08
                confidence_score += 0.05
                positive_signals += 1
            elif signal.quiz_score >= 0.5:
                mastery_score += 0.02
                confidence_score += 0.02
            elif signal.quiz_score >= 0.35:
                mastery_score -= 0.10
                confidence_score -= 0.02
                negative_signals += 1
            else:
                mastery_score -= 0.18
                confidence_score -= 0.04
                negative_signals += 1
        elif signal.explicit_mastered:
            mastery_score += 0.12
            confidence_score += 0.05
            positive_signals += 1
        elif signal.weak_signal or signal.was_confused:
            mastery_score -= 0.1
            confidence_score -= 0.02
            negative_signals += 1
        elif signal.signal_type == "study":
            mastery_score += 0.03 if signal.supporting_evidence_count >= 2 else 0.02
            confidence_score += 0.02
        elif signal.signal_type == "review":
            mastery_score += 0.015
            confidence_score += 0.015
        elif signal.signal_type == "retrieval":
            mastery_score += 0.01
            confidence_score += 0.01

        if signal.was_resolved:
            mastery_score += 0.04
            confidence_score += 0.03
            positive_signals += 1

        if signal.repeated_topic and not signal.weak_signal:
            mastery_score += 0.01
            confidence_score += 0.02

        evidence_count += max(signal.evidence_delta, 0)
        confidence_score += min(0.02 * max(signal.supporting_evidence_count, 1), 0.12)

        mastery_score = max(0.0, min(mastery_score, 1.0))
        confidence_score = max(0.0, min(confidence_score, 1.0))
        review_priority = self._review_priority(
            mastery_score=mastery_score,
            quiz_score=last_quiz_score,
            weak_signal=signal.weak_signal or signal.was_confused,
            negative_signals=negative_signals,
            evidence_count=evidence_count,
        )

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
    def _review_priority(
        mastery_score: float,
        quiz_score: Optional[float],
        weak_signal: bool,
        negative_signals: int,
        evidence_count: int,
    ) -> float:
        priority = 20.0 + max(0.0, (0.65 - mastery_score) * 100.0)
        if quiz_score is not None and quiz_score < 0.6:
            priority += 22.0
        if weak_signal:
            priority += 15.0
        if evidence_count < 3:
            priority += 8.0
        priority += min(negative_signals * 5.0, 20.0)
        if mastery_score >= 0.75 and negative_signals == 0:
            priority -= 10.0
        return max(0.0, min(priority, 100.0))
