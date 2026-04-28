from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .canonical import CanonicalTopicResolver
from .models import TopicMasteryRecord


@dataclass(frozen=True)
class MasteryPolicyConfig:
    quiz_super_high_threshold: float = 0.85
    quiz_high_threshold: float = 0.7
    quiz_mid_threshold: float = 0.5
    quiz_low_threshold: float = 0.35
    weak_signal_quiz_threshold: float = 0.6
    review_priority_base_mastery: float = 0.65
    review_priority_low_quiz_threshold: float = 0.6
    review_priority_low_quiz_bonus: float = 22.0
    review_priority_weak_signal_bonus: float = 15.0
    review_priority_low_evidence_threshold: int = 3
    review_priority_low_evidence_bonus: float = 8.0
    review_priority_negative_signal_bonus: float = 5.0
    review_priority_negative_signal_cap: float = 20.0
    review_priority_high_mastery_threshold: float = 0.75
    review_priority_high_mastery_bonus: float = -10.0


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
    def __init__(
        self,
        resolver: Optional[CanonicalTopicResolver] = None,
        config: Optional[MasteryPolicyConfig] = None,
    ) -> None:
        self._resolver = resolver or CanonicalTopicResolver()
        self.config = config or MasteryPolicyConfig()

    def update(self, current: Optional[TopicMasteryRecord], signal: MasteryUpdateInput) -> TopicMasteryRecord:
        topic = self._resolver.canonicalize(signal.topic)
        existing = current or TopicMasteryRecord(topic=topic)
        mastery_score = existing.mastery_score
        confidence_score = existing.confidence_score
        evidence_count = existing.evidence_count
        positive_signals = existing.positive_signals
        negative_signals = existing.negative_signals
        last_quiz_score = existing.last_quiz_score
        weak_signal = bool(
            signal.weak_signal
            or signal.was_confused
            or (signal.quiz_score is not None and signal.quiz_score < self.config.weak_signal_quiz_threshold)
        )

        if signal.quiz_score is not None:
            last_quiz_score = signal.quiz_score
            if signal.quiz_score >= self.config.quiz_super_high_threshold:
                mastery_score += 0.15
                confidence_score += 0.08
                positive_signals += 1
            elif signal.quiz_score >= self.config.quiz_high_threshold:
                mastery_score += 0.08
                confidence_score += 0.05
                positive_signals += 1
            elif signal.quiz_score >= self.config.quiz_mid_threshold:
                mastery_score += 0.02
                confidence_score += 0.02
            elif signal.quiz_score >= self.config.quiz_low_threshold:
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
        elif weak_signal:
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
            weak_signal=weak_signal,
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

    def _review_priority(
        self,
        mastery_score: float,
        quiz_score: Optional[float],
        weak_signal: bool,
        negative_signals: int,
        evidence_count: int,
    ) -> float:
        priority = 20.0 + max(0.0, (self.config.review_priority_base_mastery - mastery_score) * 100.0)
        if quiz_score is not None and quiz_score < self.config.review_priority_low_quiz_threshold:
            priority += self.config.review_priority_low_quiz_bonus
        if weak_signal:
            priority += self.config.review_priority_weak_signal_bonus
        if evidence_count < self.config.review_priority_low_evidence_threshold:
            priority += self.config.review_priority_low_evidence_bonus
        priority += min(negative_signals * self.config.review_priority_negative_signal_bonus, self.config.review_priority_negative_signal_cap)
        if mastery_score >= self.config.review_priority_high_mastery_threshold and negative_signals == 0:
            priority += self.config.review_priority_high_mastery_bonus
        return max(0.0, min(priority, 100.0))
