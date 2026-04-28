from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from learning_agent_service.domain.memory import MemoryInjectionPlan, MemoryRecord, RetrievedMemoryPack


@dataclass(frozen=True)
class MemoryInjectionPolicyConfig:
    prompt_limit: int = 4
    state_limit: int = 8
    tool_limit: int = 4
    rag_limit: int = 6
    token_budget: int = 1200


@dataclass
class MemoryInjectionPolicy:
    config: MemoryInjectionPolicyConfig = field(default_factory=MemoryInjectionPolicyConfig)

    def build(self, pack: RetrievedMemoryPack) -> MemoryInjectionPlan:
        prompt = self._dedupe(self._priority_slice(pack.prompt_memories, self.config.prompt_limit))
        state = self._dedupe(self._priority_slice(pack.state_memories, self.config.state_limit))
        tool = self._dedupe(self._priority_slice(pack.tool_memories, self.config.tool_limit))
        rag = self._dedupe(self._priority_slice(pack.rag_memories, self.config.rag_limit))
        hidden_trace = self._dedupe(pack.excluded_memories[:2])
        prompt = self._apply_budget(prompt, budget=self.config.token_budget // 4)
        state = self._apply_budget(state, budget=self.config.token_budget // 3)
        tool = self._apply_budget(tool, budget=self.config.token_budget // 5)
        rag = self._apply_budget(rag, budget=self.config.token_budget // 3)
        return MemoryInjectionPlan(
            prompt_memories=prompt,
            state_memories=state,
            tool_memories=tool,
            rag_memories=rag,
            hidden_trace_memories=hidden_trace,
            token_budget=self.config.token_budget,
        )

    @staticmethod
    def _priority_slice(records: Sequence[MemoryRecord], limit: int) -> List[MemoryRecord]:
        ordered = sorted(records, key=lambda item: (item.importance, item.confidence, item.updated_at), reverse=True)
        return list(ordered[:limit])

    @staticmethod
    def _dedupe(records: Sequence[MemoryRecord]) -> List[MemoryRecord]:
        seen: set[str] = set()
        unique: List[MemoryRecord] = []
        for record in records:
            if record.memory_id in seen:
                continue
            seen.add(record.memory_id)
            unique.append(record)
        return unique

    @staticmethod
    def _apply_budget(records: Sequence[MemoryRecord], *, budget: int) -> List[MemoryRecord]:
        selected: List[MemoryRecord] = []
        total = 0
        for record in records:
            cost = max(8, len(f"{record.summary or ''} {record.content}") // 4 + 1)
            if selected and total + cost > budget:
                break
            selected.append(record)
            total += cost
        return selected
