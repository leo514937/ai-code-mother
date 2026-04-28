from __future__ import annotations

import unittest
from datetime import datetime, timezone

import _bootstrap  # noqa: F401

from learning_agent_service.domain import MemoryRecord, MemoryScope, MemoryStatus, MemoryType
from learning_agent_service.domain.memory import RetrievedMemoryPack
from learning_agent_service.memory import (
    InMemoryEntityMemoryStore,
    InMemoryLongTermMemoryStore,
    InMemoryMasteryMemoryStore,
    InMemoryShortTermMemoryStore,
    MemoryInjectionPolicy,
    MemoryInjectionPolicyConfig,
    MemoryPromotionPolicy,
    MemoryRetrievalPolicy,
    RetrievalPolicyConfig,
)
from learning_agent_service.memory.models import ExplicitUserSignals, MemoryPromotionInput, PersistentSessionContext, TopicMasteryRecord, UserPreferenceProfile
from learning_agent_service.infrastructure.repositories.in_memory import InMemorySessionContextStore


class MemoryPolicyTestCase(unittest.TestCase):
    def test_promotion_policy_preserves_session_summary_fields(self) -> None:
        policy = MemoryPromotionPolicy()
        payload = MemoryPromotionInput(
            session_id="session-1",
            turn_id="turn-1",
            user_id="user-1",
            query="以后回答尽量用中文",
            answer_text="好的，我会尽量用中文回答。",
            resolved_topic="LangGraph",
            explicit_signals=ExplicitUserSignals(
                preferred_output_style="detailed",
                confirmed_output_style=True,
            ),
            current_session=PersistentSessionContext(
                current_topic="LangGraph",
                recent_entities=("LangGraph",),
                history_summary="LangGraph",
                open_questions=("如何做路由",),
                confirmed_facts=("用户偏好中文",),
                next_steps=("补充记忆层",),
                summary_version=2,
            ),
            current_preferences=UserPreferenceProfile(user_id="user-1", answer_style_counter={"detailed": 1}),
            current_mastery=TopicMasteryRecord(topic="LangGraph"),
            current_time=datetime.now(timezone.utc),
            extra={
                "open_questions": ["如何做路由"],
                "confirmed_facts": ["用户偏好中文"],
                "next_steps": ["补充记忆层"],
            },
        )

        result = policy.evaluate(payload)
        self.assertIn("open_questions", result.session_update.__dict__)
        self.assertEqual(result.session_update.open_questions[0], "如何做路由")
        write_plan = policy.build_write_plan(payload.current_session, result)
        self.assertIn("open_questions", write_plan.memory_updates)
        self.assertGreaterEqual(result.session_update.summary_version, 3)
        self.assertGreaterEqual(write_plan.updated_context.summary_version, 3)

    def test_retrieval_policy_partitions_memory_by_intent(self) -> None:
        session_store = InMemorySessionContextStore()
        session_store.sessions[("session-1", "user-1")] = PersistentSessionContext(
            current_topic="LangGraph",
            recent_entities=("LangGraph", "RAG"),
            history_summary="LangGraph -> RAG",
            open_questions=("如何做路由",),
            confirmed_facts=("已确认中文偏好",),
            next_steps=("继续实现记忆机制",),
            summary_version=3,
        )

        entity_store = InMemoryEntityMemoryStore()
        entity_store.upsert(
            MemoryRecord(
                memory_id="user-1:pref:1",
                user_id="user-1",
                type=MemoryType.PREFERENCE,
                scope=MemoryScope.USER,
                status=MemoryStatus.CONFIRMED,
                content={"preferred_output_style": "detailed"},
                summary="默认详细回答",
                source_turn_id="turn-1",
                confidence=0.95,
                importance=0.9,
                tags=["preference"],
                entities=["user-1"],
            )
        )

        short_term_store = InMemoryShortTermMemoryStore()
        short_term_store.append_messages("session-1", [{"role": "user", "content": "请讲讲 RAG"}])

        mastery_store = InMemoryMasteryMemoryStore()
        mastery_store.upsert("user-1", "LangGraph", {"topic": "LangGraph", "mastery_score": 0.42, "review_priority": 70})

        long_term_store = InMemoryLongTermMemoryStore()
        long_term_store.upsert(
            MemoryRecord(
                memory_id="user-1:semantic:1",
                user_id="user-1",
                type=MemoryType.SEMANTIC,
                scope=MemoryScope.USER,
                status=MemoryStatus.ACTIVE,
                content={"fact": "LangGraph 适合 workflow/state-machine"},
                summary="LangGraph 适合 workflow/state-machine",
                source_turn_id="turn-1",
                confidence=0.9,
                importance=0.85,
                tags=["semantic", "langgraph"],
                entities=["LangGraph"],
            )
        )
        long_term_store.upsert(
            MemoryRecord(
                memory_id="user-1:procedural:1",
                user_id="user-1",
                type=MemoryType.PROCEDURAL,
                scope=MemoryScope.USER,
                status=MemoryStatus.ACTIVE,
                content={"sop": "先理解，再路由，再执行"},
                summary="先理解，再路由，再执行",
                source_turn_id="turn-1",
                confidence=0.86,
                importance=0.8,
                tags=["procedural", "workflow"],
                entities=["workflow"],
            )
        )

        policy = MemoryRetrievalPolicy()
        pack = policy.retrieve(
            user_id="user-1",
            session_id="session-1",
            project_id=None,
            raw_query="请解释 LangGraph 的 workflow",
            intent="debug",
            current_topic="LangGraph",
            recent_entities=("LangGraph", "RAG"),
            active_plan_id=None,
            learning_mode=True,
            history_summary="LangGraph -> RAG",
            session_store=session_store,
            short_term_store=short_term_store,
            entity_store=entity_store,
            mastery_store=mastery_store,
            long_term_store=long_term_store,
        )

        self.assertTrue(pack.prompt_memories)
        self.assertTrue(pack.state_memories)
        self.assertTrue(pack.rag_memories)
        self.assertTrue(pack.tool_memories)
        self.assertGreater(pack.total_token_estimate, 0)

    def test_injection_policy_prioritizes_prompt_context(self) -> None:
        pack = RetrievedMemoryPack(
            prompt_memories=[
                MemoryRecord(
                    memory_id="mem-prompt-1",
                    user_id="user-1",
                    type=MemoryType.PREFERENCE,
                    scope=MemoryScope.USER,
                    status=MemoryStatus.CONFIRMED,
                    content={"preferred_output_style": "detailed"},
                    summary="优先中文详细回答",
                    source_turn_id="turn-1",
                    confidence=0.95,
                    importance=0.95,
                )
            ],
            state_memories=[
                MemoryRecord(
                    memory_id="mem-state-1",
                    user_id="user-1",
                    type=MemoryType.MASTERY,
                    scope=MemoryScope.USER,
                    status=MemoryStatus.CONFIRMED,
                    content={"topic": "RAG", "mastery_score": 0.42},
                    summary="RAG 仍然薄弱",
                    source_turn_id="turn-1",
                    confidence=0.7,
                    importance=0.8,
                )
            ],
            tool_memories=[
                MemoryRecord(
                    memory_id="mem-tool-1",
                    user_id="user-1",
                    type=MemoryType.PROCEDURAL,
                    scope=MemoryScope.USER,
                    status=MemoryStatus.ACTIVE,
                    content={"sop": "先查日志，再复现"},
                    summary="排错 SOP",
                    source_turn_id="turn-1",
                    confidence=0.75,
                    importance=0.72,
                )
            ],
            rag_memories=[
                MemoryRecord(
                    memory_id="mem-rag-1",
                    user_id="user-1",
                    type=MemoryType.SEMANTIC,
                    scope=MemoryScope.USER,
                    status=MemoryStatus.ACTIVE,
                    content={"fact": "LangGraph 支持 workflow/state-machine"},
                    summary="LangGraph 支持 workflow/state-machine",
                    source_turn_id="turn-1",
                    confidence=0.9,
                    importance=0.88,
                )
            ],
            excluded_memories=[],
            retrieval_reason="unit-test",
            total_token_estimate=120,
            source_memory_ids=["mem-prompt-1", "mem-state-1", "mem-tool-1", "mem-rag-1"],
        )
        injection_policy = MemoryInjectionPolicy()
        plan = injection_policy.build(pack)
        self.assertLessEqual(len(plan.prompt_memories), 4)
        self.assertLessEqual(len(plan.state_memories), 8)
        self.assertGreaterEqual(plan.token_budget, 1200)

    def test_retrieval_policy_uses_custom_keyword_strategy(self) -> None:
        long_term_store = InMemoryLongTermMemoryStore()
        long_term_store.upsert(
            MemoryRecord(
                memory_id="user-1:procedural:custom",
                user_id="user-1",
                type=MemoryType.PROCEDURAL,
                scope=MemoryScope.USER,
                status=MemoryStatus.ACTIVE,
                content={"sop": "先收集证据，再定位问题"},
                summary="先收集证据，再定位问题",
                source_turn_id="turn-1",
                confidence=0.9,
                importance=0.9,
                tags=["custom"],
                entities=["排障"],
            )
        )
        policy = MemoryRetrievalPolicy(
            config=RetrievalPolicyConfig(
                prompt_limit=1,
                state_limit=1,
                rag_limit=1,
                tool_limit=1,
                token_budget=128,
                semantic_top_k=1,
                episodic_keywords=("故障",),
                procedural_keywords=("先收集证据",),
            )
        )
        pack = policy.retrieve(
            user_id="user-1",
            session_id="session-1",
            project_id=None,
            raw_query="请先收集证据并排查",
            intent="操作流程",
            current_topic="排障",
            recent_entities=("排障",),
            active_plan_id=None,
            learning_mode=False,
            history_summary=None,
            long_term_store=long_term_store,
        )

        self.assertTrue(pack.tool_memories)
        self.assertEqual(pack.tool_memories[0].summary, "先收集证据，再定位问题")

    def test_injection_policy_uses_custom_limits(self) -> None:
        pack = RetrievedMemoryPack(
            prompt_memories=[
                MemoryRecord(
                    memory_id=f"prompt-{index}",
                    user_id="user-1",
                    type=MemoryType.PREFERENCE,
                    scope=MemoryScope.USER,
                    status=MemoryStatus.CONFIRMED,
                    content={"index": index},
                    summary=f"prompt-{index}",
                    source_turn_id="turn-1",
                    confidence=0.9,
                    importance=1.0 - index * 0.1,
                )
                for index in range(3)
            ],
            state_memories=[
                MemoryRecord(
                    memory_id=f"state-{index}",
                    user_id="user-1",
                    type=MemoryType.ENTITY,
                    scope=MemoryScope.USER,
                    status=MemoryStatus.CONFIRMED,
                    content={"index": index},
                    summary=f"state-{index}",
                    source_turn_id="turn-1",
                    confidence=0.8,
                    importance=1.0 - index * 0.1,
                )
                for index in range(3)
            ],
            tool_memories=[],
            rag_memories=[],
            excluded_memories=[],
            retrieval_reason="custom",
            total_token_estimate=64,
            source_memory_ids=["prompt-0", "prompt-1", "prompt-2", "state-0", "state-1", "state-2"],
        )
        injection_policy = MemoryInjectionPolicy(
            config=MemoryInjectionPolicyConfig(
                prompt_limit=1,
                state_limit=1,
                tool_limit=1,
                rag_limit=1,
                token_budget=40,
            )
        )
        plan = injection_policy.build(pack)

        self.assertEqual(len(plan.prompt_memories), 1)
        self.assertEqual(len(plan.state_memories), 1)


if __name__ == "__main__":
    unittest.main()
