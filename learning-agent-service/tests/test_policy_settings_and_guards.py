from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import _bootstrap  # noqa: F401

from learning_agent_service.config import Settings
from learning_agent_service.domain.enums import IntentType
from learning_agent_service.domain.guards import evaluate_clarification, validate_memory_record_mutation
from learning_agent_service.domain.memory import MemoryCandidate, MemoryRecord, MemoryScope, MemorySensitivity, MemorySource, MemoryStatus, MemoryTargetStore, MemoryType
from learning_agent_service.memory import (
    ConsolidationPolicyConfig,
    MemoryConflictPolicyConfig,
    MemoryConflictResolver,
    MemoryGovernancePolicy,
    MemoryGovernancePolicyConfig,
    MemoryPromotionPolicy,
    MemoryRecommendationPolicyConfig,
    MemoryOrchestratorPolicyConfig,
    MasteryUpdateInput,
    PromotionConfig,
    RecommendationContext,
    RecommendationService,
    TopicMasteryUpdater,
    MasteryPolicyConfig,
    TopicMasteryRecord,
)
from learning_agent_service.memory.models import ExplicitUserSignals, MemoryPromotionInput, PersistentSessionContext, UserPreferenceProfile


class PolicySettingsAndGuardsTestCase(unittest.TestCase):
    def _build_record(self, *, status: MemoryStatus = MemoryStatus.ACTIVE, confidence: float = 0.9, stability: float = 0.9) -> MemoryRecord:
        return MemoryRecord(
            memory_id="memory-1",
            user_id="user-1",
            session_id="session-1",
            topic="policy",
            type=MemoryType.SEMANTIC,
            scope=MemoryScope.USER,
            status=status,
            source=MemorySource.MODEL_INFERRED,
            confidence=confidence,
            importance=0.8,
            stability=stability,
            sensitivity=MemorySensitivity.PUBLIC,
            summary="策略测试",
            content={"fact": "memory"},
            source_turn_id="turn-1",
        )

    def test_settings_env_values_flow_into_policy_settings(self) -> None:
        env = {
            "LEARNING_AGENT_INTENT_CONFIDENCE_THRESHOLD": "0.72",
            "LEARNING_AGENT_REFERENCE_RESOLUTION_CONFIDENCE_THRESHOLD": "0.81",
            "LEARNING_AGENT_METADATA_FILTER_CONFIDENCE_THRESHOLD": "0.93",
            "LEARNING_AGENT_MEMORY_GOVERNANCE_LOW_CONFIDENCE_THRESHOLD": "0.22",
            "LEARNING_AGENT_MEMORY_GOVERNANCE_LOW_STABILITY_THRESHOLD": "0.33",
            "LEARNING_AGENT_MEMORY_CONFLICT_SUPERSEDE_MARGIN": "0.12",
            "LEARNING_AGENT_MEMORY_CONFLICT_MERGE_SIMILARITY_THRESHOLD": "0.77",
            "LEARNING_AGENT_MEMORY_PROMOTION_PREFERENCE_PROMOTE_COUNT": "4",
            "LEARNING_AGENT_MEMORY_PROMOTION_BEHAVIOR_PROMOTE_COUNT": "5",
            "LEARNING_AGENT_MEMORY_PROMOTION_LOW_QUIZ_THRESHOLD": "0.44",
            "LEARNING_AGENT_MEMORY_RECOMMENDATION_LOW_MASTERY_THRESHOLD": "0.66",
            "LEARNING_AGENT_MEMORY_RECOMMENDATION_REVIEW_PRIORITY_THRESHOLD": "70.0",
            "LEARNING_AGENT_MASTERY_QUIZ_SUPER_HIGH_THRESHOLD": "0.91",
            "LEARNING_AGENT_MASTERY_QUIZ_HIGH_THRESHOLD": "0.82",
            "LEARNING_AGENT_MASTERY_QUIZ_MID_THRESHOLD": "0.73",
            "LEARNING_AGENT_MASTERY_QUIZ_LOW_THRESHOLD": "0.61",
            "LEARNING_AGENT_MASTERY_WEAK_SIGNAL_QUIZ_THRESHOLD": "0.52",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_BASE_MASTERY": "0.44",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_QUIZ_THRESHOLD": "0.41",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_QUIZ_BONUS": "19.5",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_WEAK_SIGNAL_BONUS": "12.5",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_EVIDENCE_THRESHOLD": "5",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_LOW_EVIDENCE_BONUS": "9.5",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_NEGATIVE_SIGNAL_BONUS": "6.5",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_NEGATIVE_SIGNAL_CAP": "18.5",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_HIGH_MASTERY_THRESHOLD": "0.83",
            "LEARNING_AGENT_MASTERY_REVIEW_PRIORITY_HIGH_MASTERY_BONUS": "-8.5",
            "LEARNING_AGENT_CONSOLIDATION_MINIMUM_DUPLICATE_GROUP_SIZE": "3",
            "LEARNING_AGENT_CONSOLIDATION_MAX_CONFLICTS": "4",
            "LEARNING_AGENT_CONSOLIDATION_CONFIRMED_EXPLICITNESS": "1.25",
            "LEARNING_AGENT_CONSOLIDATION_INFERRED_EXPLICITNESS": "0.25",
            "LEARNING_AGENT_CONSOLIDATION_RECENCY_WINDOW_SECONDS": "604800",
            "LEARNING_AGENT_ORCHESTRATOR_CONFIRMED_CONFIDENCE_THRESHOLD": "0.91",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()
            policy = settings.policy_settings()

        self.assertEqual(policy.workflow_understanding.intent_confidence_threshold, 0.72)
        self.assertEqual(policy.workflow_understanding.reference_resolution_confidence_threshold, 0.81)
        self.assertEqual(policy.workflow_understanding.metadata_filter_confidence_threshold, 0.93)
        self.assertEqual(policy.memory_governance.low_confidence_threshold, 0.22)
        self.assertEqual(policy.memory_governance.low_stability_threshold, 0.33)
        self.assertEqual(policy.memory_conflict.supersede_margin, 0.12)
        self.assertEqual(policy.memory_conflict.merge_similarity_threshold, 0.77)
        self.assertEqual(policy.memory_promotion.preference_promote_count, 4)
        self.assertEqual(policy.memory_promotion.behavior_promote_count, 5)
        self.assertEqual(policy.memory_promotion.low_quiz_threshold, 0.44)
        self.assertEqual(policy.memory_recommendation.low_mastery_threshold, 0.66)
        self.assertEqual(policy.memory_recommendation.review_priority_threshold, 70.0)
        self.assertEqual(policy.hybrid_retriever.metadata_filter_confidence_threshold, 0.93)
        self.assertEqual(policy.mastery.quiz_super_high_threshold, 0.91)
        self.assertEqual(policy.mastery.quiz_high_threshold, 0.82)
        self.assertEqual(policy.mastery.quiz_mid_threshold, 0.73)
        self.assertEqual(policy.mastery.quiz_low_threshold, 0.61)
        self.assertEqual(policy.mastery.weak_signal_quiz_threshold, 0.52)
        self.assertEqual(policy.mastery.review_priority_base_mastery, 0.44)
        self.assertEqual(policy.mastery.review_priority_low_quiz_threshold, 0.41)
        self.assertEqual(policy.mastery.review_priority_low_quiz_bonus, 19.5)
        self.assertEqual(policy.mastery.review_priority_weak_signal_bonus, 12.5)
        self.assertEqual(policy.mastery.review_priority_low_evidence_threshold, 5)
        self.assertEqual(policy.mastery.review_priority_low_evidence_bonus, 9.5)
        self.assertEqual(policy.mastery.review_priority_negative_signal_bonus, 6.5)
        self.assertEqual(policy.mastery.review_priority_negative_signal_cap, 18.5)
        self.assertEqual(policy.mastery.review_priority_high_mastery_threshold, 0.83)
        self.assertEqual(policy.mastery.review_priority_high_mastery_bonus, -8.5)
        self.assertEqual(policy.consolidation.minimum_duplicate_group_size, 3)
        self.assertEqual(policy.consolidation.max_conflicts, 4)
        self.assertEqual(policy.consolidation.confirmed_explicitness, 1.25)
        self.assertEqual(policy.consolidation.inferred_explicitness, 0.25)
        self.assertEqual(policy.consolidation.recency_window_seconds, 604800)
        self.assertEqual(policy.orchestrator.confirmed_confidence_threshold, 0.91)

    def test_clarification_guard_uses_configured_thresholds(self) -> None:
        decision = evaluate_clarification(
            intent_confidence=0.61,
            reference_confidence=0.4,
            intent=IntentType.FOLLOW_UP,
            intent_threshold=0.6,
            reference_threshold=0.5,
        )
        self.assertTrue(decision.should_clarify)
        self.assertEqual(decision.reason, "low_reference_confidence")

    def test_memory_mutation_guard_blocks_deleted_records(self) -> None:
        decision = validate_memory_record_mutation(self._build_record(status=MemoryStatus.DELETED))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "reject_deleted_record")

    def test_memory_governance_policy_respects_threshold_config(self) -> None:
        policy = MemoryGovernancePolicy(
            config=MemoryGovernancePolicyConfig(low_confidence_threshold=0.8, low_stability_threshold=0.95)
        )
        candidate = self._build_candidate(confidence=0.7, stability=0.99)
        governed = policy.evaluate(candidate)
        self.assertEqual(governed.governance_action, "reject")
        self.assertFalse(governed.should_promote)

    def test_memory_conflict_resolver_respects_supersede_margin(self) -> None:
        resolver = MemoryConflictResolver(
            config=MemoryConflictPolicyConfig(supersede_margin=0.1, merge_similarity_threshold=0.9)
        )
        incoming = self._build_record(confidence=0.7).model_copy(update={"summary": "incoming"})
        existing = self._build_record(confidence=0.65).model_copy(update={"memory_id": "existing", "summary": "existing"})

        result = resolver.resolve(incoming, [existing])
        self.assertEqual(result.strategy.value, "KEEP_BOTH")

    def test_promotion_and_recommendation_thresholds_are_configurable(self) -> None:
        promotion_policy = MemoryPromotionPolicy(config=PromotionConfig(low_quiz_threshold=0.55))
        payload = MemoryPromotionInput(
            session_id="session-1",
            turn_id="turn-1",
            user_id="user-1",
            query="请继续讲解这个主题",
            answer_text="好的。",
            resolved_topic="policy",
            explicit_signals=ExplicitUserSignals(),
            current_session=PersistentSessionContext(current_topic="policy"),
            current_preferences=UserPreferenceProfile(user_id="user-1"),
            current_mastery=TopicMasteryRecord(topic="policy"),
            quiz_score=0.5,
            current_time=datetime.now(timezone.utc),
        )
        promoted = promotion_policy.evaluate(payload)
        self.assertTrue(promoted.semantic_facts)

        recommendation_service = RecommendationService(config=MemoryRecommendationPolicyConfig(low_mastery_threshold=0.8))
        recommendations = recommendation_service.recommend(
            RecommendationContext(
                current_topic="other",
                mastery_records=(TopicMasteryRecord(topic="policy", mastery_score=0.7, review_priority=10.0),),
                learning_mode=True,
                requested_limit=3,
            )
        )
        self.assertTrue(recommendations)
        self.assertEqual(recommendations[0].source, "mastery_weakness")

    def test_mastery_policy_thresholds_drive_review_priority(self) -> None:
        control_updater = TopicMasteryUpdater(
            config=MasteryPolicyConfig(
                quiz_super_high_threshold=0.9,
                quiz_high_threshold=0.8,
                quiz_mid_threshold=0.7,
                quiz_low_threshold=0.6,
                weak_signal_quiz_threshold=0.4,
                review_priority_base_mastery=0.5,
                review_priority_low_quiz_threshold=0.55,
                review_priority_low_quiz_bonus=10.0,
                review_priority_weak_signal_bonus=7.0,
                review_priority_low_evidence_threshold=2,
                review_priority_low_evidence_bonus=4.0,
                review_priority_negative_signal_bonus=3.0,
                review_priority_negative_signal_cap=6.0,
                review_priority_high_mastery_threshold=0.8,
                review_priority_high_mastery_bonus=-5.0,
            )
        )
        tuned_updater = TopicMasteryUpdater(
            config=MasteryPolicyConfig(
                quiz_super_high_threshold=0.9,
                quiz_high_threshold=0.8,
                quiz_mid_threshold=0.7,
                quiz_low_threshold=0.6,
                weak_signal_quiz_threshold=0.55,
                review_priority_base_mastery=0.5,
                review_priority_low_quiz_threshold=0.55,
                review_priority_low_quiz_bonus=10.0,
                review_priority_weak_signal_bonus=7.0,
                review_priority_low_evidence_threshold=2,
                review_priority_low_evidence_bonus=4.0,
                review_priority_negative_signal_bonus=3.0,
                review_priority_negative_signal_cap=6.0,
                review_priority_high_mastery_threshold=0.8,
                review_priority_high_mastery_bonus=-5.0,
            )
        )
        signal = MasteryUpdateInput(topic="policy", quiz_score=0.5)
        current = TopicMasteryRecord(topic="policy", mastery_score=0.5, confidence_score=0.5, evidence_count=2)
        control = control_updater.update(current, signal)
        tuned = tuned_updater.update(current, signal)
        self.assertGreater(tuned.review_priority, control.review_priority)
        self.assertEqual(round(tuned.review_priority - control.review_priority, 1), 7.0)

    def _build_candidate(self, *, confidence: float, stability: float) -> MemoryCandidate:
        return MemoryCandidate(
            candidate_id="candidate-1",
            should_promote=True,
            memory_type=MemoryType.SEMANTIC,
            target_store=MemoryTargetStore.POSTGRES,
            confidence=confidence,
            importance=0.8,
            stability=stability,
            reason="test",
            source_turn_id="turn-1",
            record=self._build_record(confidence=confidence, stability=stability),
        )


if __name__ == "__main__":
    unittest.main()
