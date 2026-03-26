from __future__ import annotations

import asyncio
import unittest
from datetime import datetime

import _bootstrap  # noqa: F401
from pydantic import ValidationError

from learning_agent_service.api.contracts import (
    ApiResponse,
    ChatStreamRequest,
    Citation,
    FinalPayload,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestion,
    SessionStateResponse,
    SseEnvelope,
    StudyPlanGenerateResponse,
)
from learning_agent_service.api.contracts import EventType
from learning_agent_service.api.router import create_api_router
import app as app_module


class _MockService:
    def run_stream(self, request: ChatStreamRequest):
        return [
            SseEnvelope(
                event_type=EventType.FINAL,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=datetime.utcnow(),
                workflow_version="learn-agent/v1",
                payload={
                    "answer_text": "ok",
                    "citations": [],
                    "used_tools": [],
                    "confidence": 0.9,
                    "memory_updates": {},
                    "metrics": {},
                },
            )
        ]

    def generate_quiz(self, request: QuizGenerateRequest) -> QuizGenerateResponse:
        return QuizGenerateResponse(
            topic=request.topic,
            questions=[QuizQuestion(question="Q1", answer="A1")],
        )

    def generate_study_plan(self, request):
        return StudyPlanGenerateResponse(topic=request.topic, items=[])

    def get_session_state(self, session_id: str) -> SessionStateResponse:
        return SessionStateResponse(session_id=session_id, current_topic="Spring")


class ApiContractsTestCase(unittest.TestCase):
    def test_chat_stream_request_requires_message(self) -> None:
        with self.assertRaises(ValidationError):
            ChatStreamRequest(
                user_id="u1",
                session_id="s1",
                trace_id="t1",
                message="",
            )

    def test_quiz_request_count_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            QuizGenerateRequest(
                user_id="u1",
                session_id="s1",
                topic="JVM",
                count=99,
            )

    def test_final_payload_contract(self) -> None:
        payload = FinalPayload(
            answer_text="线程池的核心作用是复用线程。",
            citations=[Citation(chunk_id="chunk-1", score=0.93)],
            used_tools=["searchKnowledge"],
            confidence=0.88,
            memory_updates={"current_topic": "thread_pool"},
            metrics={"retrieval_hit_count": 5},
        )
        self.assertEqual(payload.citations[0].chunk_id, "chunk-1")
        self.assertEqual(payload.used_tools, ["searchKnowledge"])

    def test_api_response_success_helper(self) -> None:
        response = ApiResponse.success({"ok": True})
        self.assertTrue(response.ok)
        self.assertEqual(response.data, {"ok": True})

    def test_router_and_app_register_expected_routes(self) -> None:
        router = create_api_router(_MockService())
        router_paths = {route.path for route in router.routes}
        self.assertEqual(
            router_paths,
            {
                "/internal/v1/chat/stream",
                "/internal/v1/quiz/generate",
                "/internal/v1/study-plan/generate",
                "/internal/v1/session/{session_id}/state",
            },
        )

        app = app_module.create_app(_MockService())
        app_paths = {route.path for route in app.routes}
        self.assertTrue(router_paths.issubset(app_paths))

    def test_chat_route_returns_streaming_response(self) -> None:
        router = create_api_router(_MockService())
        route = next(route for route in router.routes if route.path == "/internal/v1/chat/stream")
        response = asyncio.run(
            route.endpoint(
                ChatStreamRequest(
                    user_id="u1",
                    session_id="s1",
                    trace_id="t1",
                    turn_id="turn-1",
                    message="帮我解释下 AOP",
                )
            )
        )
        chunks = list(response.body_iterator)
        self.assertTrue(any("event: final" in chunk for chunk in chunks))
