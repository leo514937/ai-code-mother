from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from learning_agent_service.domain.memory import (
    EntityMemoryStore,
    LongTermMemoryStore,
    MasteryMemoryStore,
    MemoryRecord,
    MemoryRetrievalPlan,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    RetrievedMemoryPack,
    SessionMemoryStore,
    ShortTermMemoryStore,
)
from learning_agent_service.domain.guards import allow_memory_injection_status


@dataclass(frozen=True)
class RetrievalPolicyConfig:
    prompt_limit: int = 4
    state_limit: int = 6
    rag_limit: int = 6
    tool_limit: int = 4
    token_budget: int = 1200
    semantic_top_k: int = 5
    episodic_keywords: tuple[str, ...] = (
        "debug",
        "troubleshoot",
        "troubleshooting",
        "排错",
        "故障",
        "implementation",
        "实现",
        "problem",
    )
    procedural_keywords: tuple[str, ...] = (
        "how-to",
        "how to",
        "workflow",
        "tool",
        "步骤",
        "流程",
        "怎么",
        "如何",
        "debug",
        "implementation",
    )


@dataclass
class MemoryRetrievalPolicy:
    config: RetrievalPolicyConfig = field(default_factory=RetrievalPolicyConfig)

    def retrieve(
        self,
        *,
        user_id: str,
        session_id: str,
        project_id: Optional[str],
        raw_query: str,
        intent: Optional[str],
        current_topic: Optional[str],
        recent_entities: Sequence[str],
        active_plan_id: Optional[str],
        learning_mode: bool,
        history_summary: Optional[str],
        response_mode: Optional[str] = None,
        retrieval_budget: Optional[int] = None,
        session_store: Optional[SessionMemoryStore] = None,
        short_term_store: Optional[ShortTermMemoryStore] = None,
        entity_store: Optional[EntityMemoryStore] = None,
        mastery_store: Optional[MasteryMemoryStore] = None,
        long_term_store: Optional[LongTermMemoryStore] = None,
    ) -> RetrievedMemoryPack:
        plan = MemoryRetrievalPlan(
            user_id=user_id,
            session_id=session_id,
            project_id=project_id,
            raw_query=raw_query or "",
            intent=intent,
            current_topic=current_topic,
            recent_entities=list(recent_entities),
            active_plan_id=active_plan_id,
            learning_mode=learning_mode,
            history_summary=history_summary,
            retrieval_budget=retrieval_budget or self.config.token_budget,
            response_mode=response_mode,
        )
        prompt_memories: list[MemoryRecord] = []
        state_memories: list[MemoryRecord] = []
        tool_memories: list[MemoryRecord] = []
        rag_memories: list[MemoryRecord] = []
        excluded_memories: list[MemoryRecord] = []
        source_memory_ids: list[str] = []
        budget_left = plan.retrieval_budget

        if session_store is not None:
            try:
                session_context = session_store.load(session_id, user_id)
            except Exception:
                session_context = None
            if session_context is not None:
                session_record = self._build_session_record(session_context, user_id, session_id)
                prompt_memories.append(session_record)
                source_memory_ids.append(session_record.memory_id)
                budget_left -= self._estimate_tokens(session_record)

        if short_term_store is not None:
            for item in short_term_store.get_window(session_id, limit=self.config.state_limit):
                record = self._coerce_record(item, user_id=user_id, session_id=session_id)
                if record is None:
                    continue
                if self._status_allows_injection(record.status):
                    state_memories.append(record)
                    source_memory_ids.append(record.memory_id)
                    budget_left -= self._estimate_tokens(record)
                else:
                    excluded_memories.append(record)

        if entity_store is not None:
            entity_candidates = []
            if current_topic:
                entity_candidates.extend(entity_store.search(user_id, current_topic, limit=self.config.state_limit))
            if active_plan_id:
                entity_candidates.extend(entity_store.search(user_id, active_plan_id, limit=self.config.state_limit))
            for entity in entity_candidates:
                record = self._coerce_record(entity, user_id=user_id, session_id=session_id)
                if record is None:
                    continue
                if self._status_allows_injection(record.status):
                    state_memories.append(record)
                    source_memory_ids.append(record.memory_id)
                    budget_left -= self._estimate_tokens(record)

        if mastery_store is not None and current_topic:
            mastery_payload = mastery_store.get(user_id, current_topic)
            mastery_record = self._build_mastery_record(mastery_payload, user_id=user_id, session_id=session_id, topic=current_topic)
            state_memories.append(mastery_record)
            source_memory_ids.append(mastery_record.memory_id)
            budget_left -= self._estimate_tokens(mastery_record)

        if long_term_store is not None:
            semantic_query = " ".join(
                part
                for part in [raw_query, current_topic, history_summary, " ".join(recent_entities)]
                if part
            )
            candidate_records = list(long_term_store.search(semantic_query, user_id=user_id, limit=self.config.semantic_top_k))
            if not candidate_records:
                candidate_records = list(long_term_store.list_by_scope(user_id, MemoryScope.USER))[: self.config.semantic_top_k]
            for record in candidate_records:
                if not self._status_allows_injection(record.status):
                    excluded_memories.append(record)
                    continue
                if self._should_retrieve_episodic(intent, raw_query):
                    if record.type.value == "episodic":
                        rag_memories.append(record)
                        source_memory_ids.append(record.memory_id)
                        budget_left -= self._estimate_tokens(record)
                if self._should_retrieve_procedural(intent, raw_query):
                    if record.type.value == "procedural":
                        tool_memories.append(record)
                        source_memory_ids.append(record.memory_id)
                        budget_left -= self._estimate_tokens(record)
                if record.type.value == "preference":
                    prompt_memories.append(record)
                    source_memory_ids.append(record.memory_id)
                    budget_left -= self._estimate_tokens(record)
                if record.type.value == "semantic":
                    rag_memories.append(record)
                    source_memory_ids.append(record.memory_id)
                    budget_left -= self._estimate_tokens(record)

        prompt_memories = self._truncate(prompt_memories, self.config.prompt_limit, budget_left)
        state_memories = self._truncate(state_memories, self.config.state_limit, budget_left)
        tool_memories = self._truncate(tool_memories, self.config.tool_limit, budget_left)
        rag_memories = self._truncate(rag_memories, self.config.rag_limit, budget_left)

        retrieval_reason = "session+entity+mastery+long-term"
        if self._should_retrieve_episodic(intent, raw_query):
            retrieval_reason += "|episodic"
        if self._should_retrieve_procedural(intent, raw_query):
            retrieval_reason += "|procedural"
        if raw_query and len(raw_query.strip()) > 0:
            retrieval_reason += "|semantic"

        return RetrievedMemoryPack(
            prompt_memories=prompt_memories,
            state_memories=state_memories,
            tool_memories=tool_memories,
            rag_memories=rag_memories,
            excluded_memories=excluded_memories,
            retrieval_reason=retrieval_reason,
            total_token_estimate=sum(self._estimate_tokens(record) for record in prompt_memories + state_memories + tool_memories + rag_memories),
            source_memory_ids=list(dict.fromkeys(source_memory_ids)),
        )

    @staticmethod
    def _status_allows_injection(status: MemoryStatus) -> bool:
        return allow_memory_injection_status(status)

    def _should_retrieve_episodic(self, intent: Optional[str], raw_query: str) -> bool:
        query = f"{intent or ''} {raw_query}".lower()
        return any(keyword in query for keyword in self.config.episodic_keywords)

    def _should_retrieve_procedural(self, intent: Optional[str], raw_query: str) -> bool:
        query = f"{intent or ''} {raw_query}".lower()
        return any(keyword in query for keyword in self.config.procedural_keywords)

    @staticmethod
    def _estimate_tokens(record: MemoryRecord) -> int:
        text = " ".join(
            [
                record.summary or "",
                str(record.content),
                " ".join(record.tags),
                " ".join(record.entities),
            ]
        )
        return max(8, len(text) // 4 + 1)

    def _truncate(self, records: list[MemoryRecord], limit: int, budget_left: int) -> list[MemoryRecord]:
        selected: list[MemoryRecord] = []
        remaining = budget_left
        for record in sorted(records, key=lambda item: (item.importance, item.confidence, item.updated_at), reverse=True):
            if len(selected) >= limit:
                break
            cost = self._estimate_tokens(record)
            if remaining - cost < 0 and selected:
                continue
            selected.append(record)
            remaining -= cost
        return selected

    @staticmethod
    def _coerce_record(item: Any, *, user_id: str, session_id: str) -> Optional[MemoryRecord]:
        if isinstance(item, MemoryRecord):
            return item
        if isinstance(item, Mapping):
            payload = dict(item)
        elif hasattr(item, "model_dump"):
            payload = item.model_dump(mode="json")
        else:
            return None
        if "role" in payload and "content" in payload and "memory_id" not in payload:
            return MemoryRecord(
                memory_id=f"{session_id}:short-term:{len(payload.get('content', ''))}",
                user_id=user_id,
                session_id=session_id,
                type=MemoryType.SHORT_TERM,
                scope=MemoryScope.SESSION,
                status=MemoryStatus.ACTIVE,
                content={
                    "role": payload.get("role"),
                    "content": payload.get("content"),
                    "turn_id": payload.get("turn_id"),
                },
                summary=str(payload.get("content") or "")[:240],
                source_turn_id=str(payload.get("turn_id") or session_id),
                confidence=0.55,
                importance=0.55,
                tags=["short_term"],
                entities=[str(payload.get("content") or "")[:40]] if payload.get("content") else [],
            )
        payload.setdefault("user_id", user_id)
        payload.setdefault("session_id", session_id)
        payload.setdefault("source_turn_id", "")
        return MemoryRecord.model_validate(payload)

    @staticmethod
    def _build_session_record(context: Any, user_id: str, session_id: str) -> MemoryRecord:
        return MemoryRecord(
            memory_id=f"{session_id}:session-summary",
            user_id=user_id,
            session_id=session_id,
            type=MemoryType.SESSION_SUMMARY,
            scope=MemoryScope.SESSION,
            content={
                "current_topic": getattr(context, "current_topic", None),
                "recent_entities": list(getattr(context, "recent_entities", []) or []),
                "history_summary": getattr(context, "history_summary", None),
                "open_questions": list(getattr(context, "open_questions", []) or []),
                "confirmed_facts": list(getattr(context, "confirmed_facts", []) or []),
                "next_steps": list(getattr(context, "next_steps", []) or []),
            },
            summary=getattr(context, "history_summary", None),
            source_turn_id=session_id,
            confidence=0.8,
            importance=0.8,
            tags=["session_summary"],
            entities=list(getattr(context, "recent_entities", []) or []),
        )

    @staticmethod
    def _build_mastery_record(payload: Mapping[str, Any], *, user_id: str, session_id: str, topic: str) -> MemoryRecord:
        return MemoryRecord(
            memory_id=f"{user_id}:{topic}:mastery",
            user_id=user_id,
            session_id=session_id,
            type=MemoryType.MASTERY,
            scope=MemoryScope.USER,
            status=MemoryStatus.CONFIRMED,
            content=dict(payload),
            summary=f"{topic} mastery",
            source_turn_id=session_id,
            confidence=float(payload.get("confidence_score", 0.5) or 0.5),
            importance=float(payload.get("review_priority", 20) or 20),
            tags=["mastery", topic],
            entities=[topic],
        )
