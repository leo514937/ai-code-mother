from __future__ import annotations

import asyncio
import importlib
import unittest
from datetime import datetime

import _bootstrap  # noqa: F401

from learning_agent_service.api.compat import HTTPException
from learning_agent_service.api.contracts import (
    ChatStreamRequest,
    ClarificationOptionPayload,
    EventType,
    QuizGenerateRequest,
    SseEnvelope,
)
from learning_agent_service.api.router import create_api_router


class _RichStreamService:
    def run_stream(self, request: ChatStreamRequest):
        now = datetime(2026, 3, 28, 9, 0, 0)
        return [
            SseEnvelope(
                event_type=EventType.ACK,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={"message": "accepted", "accepted_at": now},
            ),
            SseEnvelope(
                event_type=EventType.RETRIEVAL_STARTED,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "semantic_query": "Spring AOP",
                    "keyword_query": "spring aop",
                    "retrieval_filters": {"category": "Spring"},
                },
            ),
            SseEnvelope(
                event_type=EventType.RETRIEVAL_RESULT,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "retrieval_strategy": "dense+sparse+metadata->rrf->rerank->evidence",
                    "retrieval_hit_count": 6,
                    "evidence_used_count": 4,
                },
            ),
            SseEnvelope(
                event_type=EventType.TOOL_CALL,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "tool_name": "searchKnowledge",
                    "tool_call_id": "call-1",
                    "input_summary": {"topic": "Spring AOP"},
                },
            ),
            SseEnvelope(
                event_type=EventType.TOOL_RESULT,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "tool_name": "searchKnowledge",
                    "tool_call_id": "call-1",
                    "status": "ok",
                    "degraded": False,
                    "retryable": False,
                    "output": {"topic": "Spring AOP"},
                },
            ),
            SseEnvelope(
                event_type=EventType.FINAL,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "answer_text": "Spring AOP is proxy-based.",
                    "citations": [],
                    "used_tools": ["searchKnowledge"],
                    "resolved_topic": "Spring AOP",
                    "retrieval_strategy": "dense+sparse+metadata->rrf->rerank->evidence",
                    "memory_updates": {},
                    "recommendation": None,
                    "confidence": 0.88,
                    "intent": "explain",
                    "requested_output_style": "detailed",
                    "metrics": {"retrieval_hit_count": 6},
                },
            ),
        ]

    def generate_quiz(self, request):
        raise RuntimeError(
            {
                "code": "LEARN-5301",
                "message": "Tool execution timed out",
                "retryable": True,
                "stage": "quiz_generate",
                "degraded_to": "lightweight-quiz",
            }
        )

    def generate_study_plan(self, request):
        raise RuntimeError("study plan unavailable")

    def get_session_state(self, session_id: str):
        raise RuntimeError({"code": "LEARN-5601", "message": "session unavailable", "stage": "session_state"})


class RuntimeBehaviorTestCase(unittest.TestCase):
    def _load_runtime_stack(self):
        try:
            dependencies_module = importlib.import_module("learning_agent_service.application.dependencies")
            service_module = importlib.import_module("learning_agent_service.application.service")
            bootstrap_module = importlib.import_module("learning_agent_service.application.bootstrap")
            compat_module = importlib.import_module("learning_agent_service.api.compat")
        except Exception:
            self.skipTest("application runtime modules are not available in this slice")
        dependencies = dependencies_module.build_dependencies()
        service = service_module.create_learning_agent_service(dependencies.container)
        return {
            "dependencies_module": dependencies_module,
            "dependencies": dependencies,
            "service": service,
            "bootstrap_module": bootstrap_module,
            "compat_module": compat_module,
        }

    def _load_runtime_service(self):
        return self._load_runtime_stack()["service"]

    def test_chat_route_streams_rich_event_sequence(self) -> None:
        router = create_api_router(_RichStreamService())
        route = next(route for route in router.routes if route.path == "/internal/v1/chat/stream")
        response = asyncio.run(
            route.endpoint(
                ChatStreamRequest(
                    user_id="u1",
                    session_id="s1",
                    trace_id="t1",
                    turn_id="turn-1",
                    message="帮我解释下 Spring AOP",
                )
            )
        )
        chunks = list(response.body_iterator)
        self.assertEqual(len(chunks), 6)
        self.assertIn("event: ack", chunks[0])
        self.assertIn("event: retrieval_started", chunks[1])
        self.assertIn("event: retrieval_result", chunks[2])
        self.assertIn("event: tool_call", chunks[3])
        self.assertIn("event: tool_result", chunks[4])
        self.assertIn("event: final", chunks[5])

    def test_actual_runtime_service_streams_ack_then_final(self) -> None:
        service = self._load_runtime_service()
        events = list(
            service.run_stream(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id="session-1",
                    trace_id="trace-1",
                    turn_id="turn-1",
                    message="Explain Spring AOP",
                )
            )
        )
        self.assertEqual(events[0].event_type, EventType.ACK)
        self.assertEqual(events[-1].event_type, EventType.FINAL)
        self.assertIn(EventType.RETRIEVAL_STARTED, [event.event_type for event in events])
        self.assertIn(EventType.RETRIEVAL_RESULT, [event.event_type for event in events])

    def test_actual_runtime_service_can_emit_clarification_card(self) -> None:
        service = self._load_runtime_service()
        events = list(
            service.run_stream(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id="session-2",
                    trace_id="trace-2",
                    turn_id="turn-2",
                    message="this",
                )
            )
        )
        self.assertEqual(events[-1].event_type, EventType.CLARIFICATION_CARD)
        self.assertTrue(events[-1].payload["options"])
        option = ClarificationOptionPayload.model_validate(events[-1].payload["options"][0])
        self.assertTrue(option.label)

    def test_actual_runtime_service_routes_chinese_study_plan_prompt_to_tool_path(self) -> None:
        service = self._load_runtime_service()
        events = list(
            service.run_stream(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id="session-3",
                    trace_id="trace-3",
                    turn_id="turn-3",
                    message="帮我做一个7天JVM学习计划",
                )
            )
        )
        event_types = [event.event_type for event in events]
        self.assertIn(EventType.TOOL_CALL, event_types)
        self.assertIn(EventType.TOOL_RESULT, event_types)
        tool_call = next(event for event in events if event.event_type == EventType.TOOL_CALL)
        self.assertEqual(tool_call.payload["tool_name"], "generateStudyPlan")
        final = events[-1]
        self.assertEqual(final.event_type, EventType.FINAL)
        self.assertIn("generateStudyPlan", final.payload.get("used_tools", []))

    def test_actual_runtime_service_routes_chinese_quiz_prompt_to_tool_path(self) -> None:
        service = self._load_runtime_service()
        events = list(
            service.run_stream(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id="session-4",
                    trace_id="trace-4",
                    turn_id="turn-4",
                    message="给我出5道Java并发面试题",
                )
            )
        )
        event_types = [event.event_type for event in events]
        self.assertIn(EventType.TOOL_CALL, event_types)
        self.assertIn(EventType.TOOL_RESULT, event_types)
        tool_call = next(event for event in events if event.event_type == EventType.TOOL_CALL)
        self.assertEqual(tool_call.payload["tool_name"], "generateQuiz")
        final = events[-1]
        self.assertEqual(final.event_type, EventType.FINAL)
        self.assertIn("generateQuiz", final.payload.get("used_tools", []))

    def test_build_dependencies_exposes_dual_mode_status(self) -> None:
        runtime = self._load_runtime_stack()
        status = runtime["dependencies"].container.runtime_dependency_status.as_dict()
        self.assertIn("adapters", status)
        adapter_names = {item["name"] for item in status["adapters"]}
        self.assertIn("session_context_store", adapter_names)
        self.assertIn("topic_mastery_store", adapter_names)
        self.assertIn("async_log_store", adapter_names)
        modes = {item["mode"] for item in status["adapters"]}
        self.assertTrue(modes.intersection({"real", "fallback"}))

    def test_bootstrap_application_exposes_runtime_dependency_status_on_app_state(self) -> None:
        runtime = self._load_runtime_stack()
        app = runtime["compat_module"].FastAPI(title="test")
        bootstrap = runtime["bootstrap_module"].bootstrap_application(app)
        self.assertEqual(
            app.state.infrastructure_status,
            bootstrap.infrastructure_status,
        )
        self.assertEqual(
            bootstrap.infrastructure_status,
            runtime["dependencies"].container.runtime_dependency_status.as_dict(),
        )
        self.assertTrue(app.state.infrastructure_status["adapters"])

    def test_quiz_route_preserves_structured_error_taxonomy(self) -> None:
        router = create_api_router(_RichStreamService())
        route = next(route for route in router.routes if route.path == "/internal/v1/quiz/generate")
        with self.assertRaises(HTTPException) as context:
            asyncio.run(
                route.endpoint(
                    QuizGenerateRequest(
                        user_id="u1",
                        session_id="s1",
                        topic="JVM",
                        count=5,
                    )
                )
            )
        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(context.exception.detail["code"], "LEARN-5301")
        self.assertEqual(context.exception.detail["degraded_to"], "lightweight-quiz")
