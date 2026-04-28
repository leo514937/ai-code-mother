from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Sequence

from learning_agent_service.domain.memory import (
    MemoryEdge,
    MemoryEdgeType,
    MemoryRecord,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
    MemoryType,
)


class MemoryConflictResolutionStrategy(str, Enum):
    SUPERSEDE_OLD = "SUPERSEDE_OLD"
    MERGE = "MERGE"
    KEEP_BOTH = "KEEP_BOTH"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


@dataclass
class MemoryConflictResolutionResult:
    strategy: MemoryConflictResolutionStrategy
    winner: MemoryRecord
    losers: List[MemoryRecord] = field(default_factory=list)
    merged_record: Optional[MemoryRecord] = None
    requires_confirmation: bool = False
    reason: str = ""
    edges: List[MemoryEdge] = field(default_factory=list)


@dataclass
class MemoryConflictPolicyConfig:
    supersede_margin: float = 0.05
    merge_similarity_threshold: float = 0.65


@dataclass
class MemoryConflictResolver:
    """根据新旧记忆内容决定覆盖、合并、保留还是要求确认。"""

    config: MemoryConflictPolicyConfig = field(default_factory=MemoryConflictPolicyConfig)

    def resolve(self, incoming: MemoryRecord, existing_records: Sequence[MemoryRecord]) -> MemoryConflictResolutionResult:
        conflicts = self._find_conflicts(incoming, existing_records)
        if incoming.sensitivity in {MemorySensitivity.CONFIDENTIAL, MemorySensitivity.RESTRICTED}:
            edges = [
                MemoryEdge(
                    edge_id=f"{incoming.memory_id}:confirmation_required:{record.memory_id}",
                    source_memory_id=record.memory_id,
                    target_memory_id=incoming.memory_id,
                    edge_type=MemoryEdgeType.RELATED_TO,
                    reason="requires_confirmation",
                )
                for record in conflicts
            ]
            return MemoryConflictResolutionResult(
                strategy=MemoryConflictResolutionStrategy.REQUIRE_CONFIRMATION,
                winner=incoming,
                losers=list(conflicts),
                requires_confirmation=True,
                reason="sensitive_memory",
                edges=edges,
            )
        if not conflicts:
            return MemoryConflictResolutionResult(
                strategy=MemoryConflictResolutionStrategy.KEEP_BOTH,
                winner=incoming,
                reason="no_conflicts",
            )

        best_existing = max(conflicts, key=lambda item: (item.confidence, item.importance, item.updated_at))
        if self._should_supersede(incoming, best_existing):
            edges = [
                MemoryEdge(
                    edge_id=f"{loser.memory_id}:superseded_by:{incoming.memory_id}",
                    source_memory_id=loser.memory_id,
                    target_memory_id=incoming.memory_id,
                    edge_type=MemoryEdgeType.SUPERSEDES,
                    reason="higher_confidence_new_memory",
                )
                for loser in conflicts
            ]
            return MemoryConflictResolutionResult(
                strategy=MemoryConflictResolutionStrategy.SUPERSEDE_OLD,
                winner=incoming,
                losers=list(conflicts),
                reason="incoming_memory_has_higher_confidence",
                edges=edges,
            )

        if self._should_merge(incoming, best_existing):
            merged = self._merge_records(incoming, conflicts)
            return MemoryConflictResolutionResult(
                strategy=MemoryConflictResolutionStrategy.MERGE,
                winner=merged,
                losers=list(conflicts),
                merged_record=merged,
                reason="records_are_complementary",
            )

        return MemoryConflictResolutionResult(
            strategy=MemoryConflictResolutionStrategy.KEEP_BOTH,
            winner=incoming,
            losers=list(conflicts),
            reason="retain_parallel_memories",
            edges=[
                MemoryEdge(
                    edge_id=f"{record.memory_id}:related_to:{incoming.memory_id}",
                    source_memory_id=record.memory_id,
                    target_memory_id=incoming.memory_id,
                    edge_type=MemoryEdgeType.RELATED_TO,
                    reason="retain_parallel_memories",
                )
                for record in conflicts
            ],
        )

    def _find_conflicts(
        self,
        incoming: MemoryRecord,
        existing_records: Sequence[MemoryRecord],
    ) -> List[MemoryRecord]:
        conflicts: List[MemoryRecord] = []
        for record in existing_records:
            if record.user_id != incoming.user_id:
                continue
            if record.scope != incoming.scope:
                continue
            if record.type != incoming.type:
                continue
            if incoming.topic and record.topic and record.topic != incoming.topic:
                continue
            if record.status in {MemoryStatus.DELETED, MemoryStatus.EXPIRED, MemoryStatus.SUPERSEDED}:
                continue
            conflicts.append(record)
        return conflicts

    def _should_supersede(self, incoming: MemoryRecord, existing: MemoryRecord) -> bool:
        if incoming.confidence >= existing.confidence + self.config.supersede_margin:
            return True
        if incoming.importance >= existing.importance + self.config.supersede_margin:
            return True
        if incoming.summary and existing.summary and incoming.summary != existing.summary:
            similarity = self._text_similarity(incoming.summary, existing.summary)
            return similarity > 0.8 and incoming.confidence >= existing.confidence
        return False

    def _should_merge(self, incoming: MemoryRecord, existing: MemoryRecord) -> bool:
        if not incoming.summary or not existing.summary:
            return False
        similarity = self._text_similarity(incoming.summary, existing.summary)
        return similarity >= self.config.merge_similarity_threshold and incoming.type in {MemoryType.SEMANTIC, MemoryType.EPISODIC}

    def _merge_records(self, incoming: MemoryRecord, conflicts: Sequence[MemoryRecord]) -> MemoryRecord:
        merged_content = {}
        for record in conflicts:
            if isinstance(record.content, dict):
                merged_content.update(record.content)
        if isinstance(incoming.content, dict):
            merged_content.update(incoming.content)
        merged_topic = incoming.topic or next((record.topic for record in conflicts if record.topic), None)
        merged_summary = incoming.summary or next((record.summary for record in conflicts if record.summary), None)
        merged_tags = list(dict.fromkeys([*(incoming.tags or []), *sum((list(record.tags or []) for record in conflicts), [])]))
        merged_entities = list(
            dict.fromkeys([*(incoming.entities or []), *sum((list(record.entities or []) for record in conflicts), [])])
        )
        merged_confidence = max([incoming.confidence, *[record.confidence for record in conflicts]])
        merged_importance = max([incoming.importance, *[record.importance for record in conflicts]])
        merged_stability = min([incoming.stability, *[record.stability for record in conflicts]])
        merged_valid_until = incoming.valid_until
        for record in conflicts:
            if merged_valid_until is None and record.valid_until is not None:
                merged_valid_until = record.valid_until
        return incoming.model_copy(
            update={
                "topic": merged_topic,
                "summary": merged_summary,
                "content": merged_content,
                "tags": merged_tags,
                "entities": merged_entities,
                "confidence": merged_confidence,
                "importance": merged_importance,
                "stability": merged_stability,
                "valid_until": merged_valid_until,
            }
        )

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        left_tokens = {token for token in left.lower().split() if token}
        right_tokens = {token for token in right.lower().split() if token}
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return overlap / union if union else 0.0
