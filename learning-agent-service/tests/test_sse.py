from __future__ import annotations

import unittest
from datetime import datetime

import _bootstrap  # noqa: F401
from pydantic import ValidationError

from learning_agent_service.api.contracts import EventType, SseEnvelope
from learning_agent_service.domain import PlanExecutionSummary, PlanStep, StepResult
from learning_agent_service.api.sse import build_event_id, serialize_envelope, stream_envelopes


class SseEncodingTestCase(unittest.TestCase):
    def _envelope(self) -> SseEnvelope:
        return SseEnvelope(
            event_type=EventType.FINAL,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-1",
            timestamp=datetime(2026, 3, 27, 12, 0, 0),
            workflow_version="learn-agent/v1",
            payload={
                "answer_text": "ok",
                "citations": [],
                "used_tools": [],
                "confidence": 0.8,
                "grounding_status": "grounded",
                "retrieval_summary": {
                    "retrieval_strategy": "dense+sparse+metadata->rrf->rerank->evidence",
                    "retrieval_hit_count": 2,
                    "evidence_used_count": 2,
                    "evidence_status": "OK",
                },
                "memory_used_summary": {
                    "used": False,
                    "total_memories": 0,
                },
                "memory_updates": {},
                "metrics": {},
            },
        )

    def test_build_event_id(self) -> None:
        self.assertEqual(build_event_id("s1", "t1", 3), "s1:t1:3")

    def test_serialize_envelope(self) -> None:
        payload = serialize_envelope(self._envelope(), seq=2)
        self.assertIn("id: session-1:turn-1:2", payload)
        self.assertIn("event: final", payload)
        self.assertIn('"workflow_version":"learn-agent/v1"', payload)
        self.assertIn('"grounding_status":"grounded"', payload)

    def test_stream_envelopes_preserves_order(self) -> None:
        chunks = list(stream_envelopes([self._envelope(), self._envelope()]))
        self.assertEqual(len(chunks), 2)
        self.assertIn("session-1:turn-1:1", chunks[0])
        self.assertIn("session-1:turn-1:2", chunks[1])

    def test_serialize_clarification_card_with_structured_options(self) -> None:
        envelope = SseEnvelope(
            event_type=EventType.CLARIFICATION_CARD,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-2",
            timestamp=datetime(2026, 3, 27, 12, 0, 0),
            workflow_version="learn-agent/v1",
            payload={
                "card_id": "clarify-1",
                "question": "Which topic do you mean?",
                "options": [
                    {"id": "1", "label": "Spring AOP", "value": "Spring AOP"},
                    {"id": "2", "label": "JDK Proxy", "value": "JDK Proxy"},
                ],
                "ambiguity_type": "reference",
            },
        )
        chunk = serialize_envelope(envelope, seq=1)
        self.assertIn('"options":[{"id":"1","label":"Spring AOP","value":"Spring AOP","description":null}', chunk)

    def test_serialize_envelope_validates_payload_shape(self) -> None:
        envelope = SseEnvelope(
            event_type=EventType.CLARIFICATION_CARD,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-2",
            timestamp=datetime(2026, 3, 27, 12, 0, 0),
            workflow_version="learn-agent/v1",
            payload={
                "card_id": "clarify-1",
                "question": "Which topic do you mean?",
                "options": ["Spring AOP"],
            },
        )
        with self.assertRaises(ValidationError):
            serialize_envelope(envelope, seq=1)

    def test_serialize_plan_execution_summary_event(self) -> None:
        envelope = SseEnvelope(
            event_type=EventType.PLAN_EXECUTION_SUMMARY,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-3",
            timestamp=datetime(2026, 3, 27, 12, 0, 0),
            workflow_version="learn-agent/v1",
            payload={
                "summary": PlanExecutionSummary(
                    status="completed",
                    completed_steps=1,
                    total_steps=1,
                    key_findings=["已完成"],
                    final_decision="ok",
                ).model_dump(mode="json")
            },
        )
        chunk = serialize_envelope(envelope, seq=3)
        self.assertIn("event: plan_execution_summary", chunk)
        self.assertIn('"status":"completed"', chunk)

    def test_serialize_plan_execution_started_event(self) -> None:
        envelope = SseEnvelope(
            event_type=EventType.PLAN_EXECUTION_STARTED,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-5",
            timestamp=datetime(2026, 3, 27, 12, 0, 0),
            workflow_version="learn-agent/v1",
            payload={
                "plan": [
                    PlanStep(
                        step_id="step-1",
                        goal="执行第一步",
                        allowed_tools=["searchKnowledge"],
                    ).model_dump(mode="json")
                ],
                "total_steps": 1,
                "current_step_index": 0,
                "execution_mode": "plan_execute",
                "risk_level": "low",
            },
        )
        chunk = serialize_envelope(envelope, seq=2)
        self.assertIn("event: plan_execution_started", chunk)
        self.assertIn('"total_steps":1', chunk)

    def test_serialize_plan_step_result_event(self) -> None:
        envelope = SseEnvelope(
            event_type=EventType.PLAN_STEP_RESULT,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-4",
            timestamp=datetime(2026, 3, 27, 12, 0, 0),
            workflow_version="learn-agent/v1",
            payload={
                "step_result": StepResult(
                    step_id="step-1",
                    status="success",
                    tools_used=["generateQuiz"],
                    observations=["已生成题目"],
                    result={"data": {"topic": "JVM"}},
                ).model_dump(mode="json"),
                "current_step_index": 0,
                "total_steps": 1,
            },
        )
        chunk = serialize_envelope(envelope, seq=4)
        self.assertIn("event: plan_step_result", chunk)
        self.assertIn('"tools_used":["generateQuiz"]', chunk)
