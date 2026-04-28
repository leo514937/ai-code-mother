from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401

from learning_agent_service.application.workflow.subgraphs import (
    route_after_mastery,
    route_after_rag,
    route_after_understand,
)
from learning_agent_service.domain import ChatTurnCommand, PersistentSessionContext, RagResult, RetrievalPlan, build_initial_state
from learning_agent_service.domain.enums import RagStatus, TurnDecision


class WorkflowRoutingTestCase(unittest.TestCase):
    def _build_state(self):
        return build_initial_state(
            ChatTurnCommand(
                trace_id="trace-1",
                session_id="session-1",
                turn_id="turn-1",
                user_id="user-1",
                message="Explain Spring AOP",
            ),
            persistent=PersistentSessionContext(),
        )

    def test_route_after_understand_prioritizes_clarify_then_rag_then_tool(self) -> None:
        state = self._build_state()

        clarified = state["turn"].model_copy(update={"decision": TurnDecision.CLARIFY})
        state["turn"] = clarified
        self.assertEqual(route_after_understand(state), "emit_final")

        rag_state = self._build_state()
        rag_state["turn"] = rag_state["turn"].model_copy(
            update={
                "decision": TurnDecision.RETRIEVE_THEN_ANSWER,
                "retrieval_plan": RetrievalPlan(semantic_query="Spring AOP", keyword_query="Spring AOP"),
            }
        )
        self.assertEqual(route_after_understand(rag_state), "rag_subgraph")

        tool_state = self._build_state()
        tool_state["turn"] = tool_state["turn"].model_copy(
            update={
                "decision": TurnDecision.TOOL_THEN_ANSWER,
            }
        )
        self.assertEqual(route_after_understand(tool_state), "tool_subgraph")

    def test_route_after_rag_only_continues_to_tools_when_needed(self) -> None:
        state = self._build_state()
        state["turn"] = state["turn"].model_copy(update={"decision": TurnDecision.TOOL_THEN_ANSWER})
        self.assertEqual(route_after_rag(state), "tool_subgraph")

        state["turn"] = state["turn"].model_copy(update={"decision": TurnDecision.RETRIEVE_THEN_ANSWER})
        self.assertEqual(route_after_rag(state), "compose_answer")

    def test_route_after_mastery_keeps_recommendation_gate_centralized(self) -> None:
        state = self._build_state()
        state["persistent"] = state["persistent"].model_copy(update={"learning_mode": True})
        state["turn"] = state["turn"].model_copy(
            update={
                "rag_result": RagResult(status=RagStatus.OK),
            }
        )
        self.assertEqual(route_after_mastery(state), "recommend_next")

        state["turn"] = state["turn"].model_copy(
            update={
                "rag_result": RagResult(status=RagStatus.EMPTY),
            }
        )
        self.assertEqual(route_after_mastery(state), "emit_final")


if __name__ == "__main__":
    unittest.main()
