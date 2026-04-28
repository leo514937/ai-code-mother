from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
except ImportError:  # pragma: no cover - environment without SQLAlchemy
    create_engine = None
    sessionmaker = None

from learning_agent_service.domain import ChatTurnCommand, MemoryStatus, MemoryType, PlanExecutionSummary, StepResult, build_initial_state
from learning_agent_service.infrastructure.db.models import Base
from learning_agent_service.infrastructure.memory import DurableLongTermMemoryStore, LongTermMemoryRepository, QdrantLongTermMemoryIndex
from learning_agent_service.infrastructure.repositories.in_memory import InMemorySessionContextStore, InMemoryTopicMasteryStore
from learning_agent_service.memory.orchestrator import MemoryOrchestrator


class MemoryBackendIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if create_engine is None or sessionmaker is None:
            self.skipTest("SQLAlchemy is required for memory backend integration tests")
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def test_orchestrator_promotes_step_results_into_durable_long_term_memory(self) -> None:
        repository = LongTermMemoryRepository(self.session_factory)
        index = QdrantLongTermMemoryIndex(client=object(), collection_name="user_memory", vector_size=32)
        long_term_store = DurableLongTermMemoryStore(repository=repository, index=index)
        orchestrator = MemoryOrchestrator(
            session_store=InMemorySessionContextStore(),
            mastery_store=InMemoryTopicMasteryStore(),
            long_term_store=long_term_store,
        )

        state = build_initial_state(
            ChatTurnCommand(
                trace_id="trace-1",
                session_id="session-1",
                turn_id="turn-1",
                user_id="user-1",
                message="请帮我整理 LangGraph 记忆机制",
                topic_hint="LangGraph",
            )
        )
        state["persistent"] = state["persistent"].model_copy(
            update={
                "current_topic": "LangGraph",
                "history_summary": "LangGraph -> 记忆机制",
            }
        )
        state["turn"] = state["turn"].model_copy(
            update={
                "final_answer": "已整理完成",
                "step_results": [
                    StepResult(
                        step_id="step-1",
                        status="success",
                        tools_used=["searchKnowledge"],
                        observations=["确认主题为 LangGraph"],
                        result={"summary": "LangGraph workflow"},
                    )
                ],
                "final_task_summary": PlanExecutionSummary(
                    status="completed",
                    completed_steps=1,
                    total_steps=1,
                    key_findings=["LangGraph 适合 workflow/state-machine"],
                    final_decision="完成整理",
                ),
            }
        )

        write_plan = orchestrator.promote_from_state(state)
        self.assertTrue(write_plan.candidates)
        results = list(orchestrator.long_term_store.search("LangGraph", user_id="user-1", limit=10))
        self.assertTrue(results)
        self.assertTrue(any(record.type in {MemoryType.PROCEDURAL, MemoryType.EPISODIC} for record in results))
        self.assertTrue(any(record.status in {MemoryStatus.ACTIVE, MemoryStatus.INFERRED, MemoryStatus.CONFIRMED} for record in results))

        consolidated = orchestrator.consolidate(user_id="user-1")
        self.assertTrue(consolidated)


if __name__ == "__main__":
    unittest.main()
