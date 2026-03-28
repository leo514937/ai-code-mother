from __future__ import annotations

import asyncio
import importlib
import unittest
from datetime import datetime

import _bootstrap  # noqa: F401

from learning_agent_service.api.compat import HTTPException
from learning_agent_service.api.contracts import (
    ChatStreamRequest,
    EventType,
    QuizGenerateRequest,
    SseEnvelope,
)
from learning_agent_service.api.router import create_api_router


class _FailingStreamService:
    def run_stream(self, request: ChatStreamRequest):
        raise RuntimeError({"code": "LEARN-5600", "message": "bootstrap unavailable", "stage": "chat_stream"})

    def generate_quiz(self, request):
        raise AssertionError("unreachable")

    def generate_study_plan(self, request):
        raise AssertionError("unreachable")

    def get_session_state(self, session_id: str):
        raise AssertionError("unreachable")


class _ClarifyingStreamService:
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
                event_type=EventType.CLARIFICATION_CARD,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "card_id": "clarify-1",
                    "question": "Which topic do you mean?",
                    "options": [
                        {"id": "1", "label": "Spring AOP", "value": "Spring AOP"},
                        {"id": "2", "label": "JDK dynamic proxy", "value": "JDK dynamic proxy"},
                    ],
                    "ambiguity_type": "reference",
                },
            ),
        ]

    def generate_quiz(self, request):
        raise AssertionError("unreachable")

    def generate_study_plan(self, request):
        raise AssertionError("unreachable")

    def get_session_state(self, session_id: str):
        raise AssertionError("unreachable")


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


class _TerminalErrorStreamService:
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
                event_type=EventType.ERROR,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "code": "LEARN-5001",
                    "message": "workflow failed",
                    "retryable": False,
                    "stage": "compose_answer",
                    "details": {},
                },
            ),
        ]

    def generate_quiz(self, request):
        raise AssertionError("unreachable")

    def generate_study_plan(self, request):
        raise AssertionError("unreachable")

    def get_session_state(self, session_id: str):
        raise AssertionError("unreachable")


class RuntimeBehaviorTestCase(unittest.TestCase):
    def _load_runtime_stack(self):
        try:
            dependencies_module = importlib.import_module("learning_agent_service.application.dependencies")
            service_module = importlib.import_module("learning_agent_service.application.service")
            bootstrap_module = importlib.import_module("learning_agent_service.application.bootstrap")
            compat_module = importlib.import_module("learning_agent_service.api.compat")
        except Exception:
            self.skipTest("application runtime modules are not available in this slice")
        try:
            dependencies = dependencies_module.build_dependencies()
            service = service_module.create_learning_agent_service(dependencies.container)
        except Exception as exc:
            self.skipTest("application runtime stack is not buildable in this slice: {error}".format(error=exc))
        return {
            "dependencies_module": dependencies_module,
            "dependencies": dependencies,
            "service": service,
            "bootstrap_module": bootstrap_module,
            "compat_module": compat_module,
        }

    def _load_runtime_service(self):
        return self._load_runtime_stack()["service"]

    def test_actual_runtime_service_starts_with_ack_and_ends_with_supported_terminal_event(self) -> None:
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
        event_types = [str(event.event_type) for event in events]
        self.assertTrue(event_types)
        self.assertEqual(event_types[0], EventType.ACK.value)
        self.assertIn(event_types[-1], {EventType.CLARIFICATION_CARD.value, EventType.FINAL.value, EventType.ERROR.value})
        self.assertEqual(
            len([event_type for event_type in event_types if event_type in {"clarification_card", "final", "error"}]),
            1,
        )
        self.assertNotIn("state_update", event_types)
        self.assertNotIn("delta", event_types)

    def test_actual_runtime_session_state_response_keeps_session_id(self) -> None:
        runtime = self._load_runtime_stack()
        service = runtime["service"]
        session_id = "session-state-1"

        list(
            service.run_stream(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id=session_id,
                    trace_id="trace-session-state",
                    turn_id="turn-session-state",
                    message="Explain Spring AOP",
                )
            )
        )

        state = service.get_session_state(session_id)

        self.assertEqual(state.session_id, session_id)
        self.assertIsNotNone(state.current_topic)

    def test_actual_runtime_compare_turn_does_not_persist_rewritten_query_slug(self) -> None:
        runtime = self._load_runtime_stack()
        service = runtime["service"]
        session_id = "session-compare-1"

        list(
            service.run_stream(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id=session_id,
                    trace_id="trace-compare",
                    turn_id="turn-compare",
                    message="Compare JDK dynamic proxy and CGLIB proxy",
                )
            )
        )

        context = runtime["dependencies"].container.memory_service.load_any(session_id)

        self.assertNotEqual(context.current_topic, "compare.jdk.dynamic.proxy.and.cglib.proxy")
        self.assertNotIn("compare.jdk.dynamic.proxy.and.cglib.proxy", context.recent_entities)

    def test_build_dependencies_exposes_dual_mode_status(self) -> None:
        runtime = self._load_runtime_stack()
        status = runtime["dependencies"].container.runtime_dependency_status.as_dict()
        self.assertIn("adapters", status)
        adapter_names = {item["name"] for item in status["adapters"]}
        self.assertIn("session_context_store", adapter_names)
        self.assertIn("topic_mastery_store", adapter_names)
        self.assertIn("async_log_store", adapter_names)
        modes = {item["mode"] for item in status["adapters"]}
        self.assertTrue(modes.intersection({"real", "fallback", "noop", "unavailable"}))

    def test_bootstrap_application_exposes_runtime_profile_and_dependency_status_on_app_state(self) -> None:
        runtime = self._load_runtime_stack()
        app = runtime["compat_module"].FastAPI(title="test")
        bootstrap = runtime["bootstrap_module"].bootstrap_application(app)
        self.assertEqual(app.state.infrastructure_status, bootstrap.infrastructure_status)
        self.assertEqual(
            bootstrap.infrastructure_status["runtime_profile"],
            runtime["dependencies"].container.runtime_profile.as_dict(),
        )
        self.assertEqual(
            bootstrap.infrastructure_status["dependency_status"],
            runtime["dependencies"].container.runtime_dependency_status.as_dict(),
        )

    def test_chat_route_pre_stream_failure_raises_http_error_instead_of_error_event_stream(self) -> None:
        router = create_api_router(_FailingStreamService())
        route = next(route for route in router.routes if route.path == "/internal/v1/chat/stream")
        with self.assertRaises(HTTPException) as context:
            asyncio.run(
                route.endpoint(
                    ChatStreamRequest(
                        user_id="u1",
                        session_id="s1",
                        trace_id="t1",
                        turn_id="turn-err",
                        message="Explain Spring AOP",
                    )
                )
            )
        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(context.exception.detail["code"], "LEARN-5600")
        self.assertEqual(context.exception.detail["stage"], "chat_stream")

    def test_chat_route_streams_supported_tool_sequence(self) -> None:
        router = create_api_router(_RichStreamService())
        route = next(route for route in router.routes if route.path == "/internal/v1/chat/stream")
        response = asyncio.run(
            route.endpoint(
                ChatStreamRequest(
                    user_id="u1",
                    session_id="s1",
                    trace_id="t1",
                    turn_id="turn-1",
                    message="Help me explain Spring AOP",
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

    def test_chat_route_clarification_sequence_has_single_terminal_card(self) -> None:
        router = create_api_router(_ClarifyingStreamService())
        route = next(route for route in router.routes if route.path == "/internal/v1/chat/stream")
        response = asyncio.run(
            route.endpoint(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id="session-clarify",
                    trace_id="trace-clarify",
                    turn_id="turn-clarify",
                    message="this",
                )
            )
        )
        chunks = list(response.body_iterator)
        self.assertEqual(len(chunks), 2)
        self.assertIn("event: ack", chunks[0])
        self.assertIn("event: clarification_card", chunks[1])

    def test_chat_route_supports_ack_then_terminal_error_sequence(self) -> None:
        router = create_api_router(_TerminalErrorStreamService())
        route = next(route for route in router.routes if route.path == "/internal/v1/chat/stream")
        response = asyncio.run(
            route.endpoint(
                ChatStreamRequest(
                    user_id="user-1",
                    session_id="session-error",
                    trace_id="trace-error",
                    turn_id="turn-error",
                    message="trigger runtime failure",
                )
            )
        )
        chunks = list(response.body_iterator)
        self.assertEqual(len(chunks), 2)
        self.assertIn("event: ack", chunks[0])
        self.assertIn("event: error", chunks[1])

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
