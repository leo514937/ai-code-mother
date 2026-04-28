from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import _bootstrap  # noqa: F401
from pydantic import ValidationError

import app as app_module
from learning_agent_service.api import internal_auth
from learning_agent_service.api.contracts import (
    ApiResponse,
    ChatStreamRequest,
    Citation,
    ClarificationCardPayload,
    ClarificationOptionPayload,
    EventType,
    FinalPayload,
    FeedbackReportRequest,
    FeedbackIssueType,
    MemoryActionRequest,
    MemoryUsedSummary,
    RetrievalSummary,
    MemoryRetrievalStartedPayload,
    MemoryPromotionResultPayload,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestion,
    SessionStateResponse,
    SseEnvelope,
    StudyPlanGenerateResponse,
    validate_event_payload,
)
from learning_agent_service.api.router import create_api_router


class _MockService:
    def run_stream(self, request: ChatStreamRequest):
        now = datetime.now(timezone.utc)
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
                event_type=EventType.FINAL,
                trace_id=request.trace_id,
                session_id=request.session_id,
                turn_id=request.turn_id or "turn-1",
                timestamp=now,
                workflow_version="learn-agent/v1",
                payload={
                    "answer_text": "ok",
                    "citations": [],
                    "used_tools": [],
                    "confidence": 0.9,
                    "grounding_status": "not_grounded",
                    "retrieval_summary": {
                        "retrieval_strategy": "dense+sparse+metadata->rrf->rerank->evidence",
                        "retrieval_hit_count": 0,
                        "evidence_used_count": 0,
                        "evidence_status": "EMPTY",
                    },
                    "memory_used_summary": {
                        "used": False,
                        "total_memories": 0,
                    },
                    "memory_updates": {},
                    "metrics": {},
                },
            ),
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


async def _collect_body_chunks(response) -> list[str]:
    chunks = []
    body_iterator = response.body_iterator
    if hasattr(body_iterator, "__aiter__"):
        async for chunk in body_iterator:
            chunks.append(chunk)
    else:
        for chunk in body_iterator:
            chunks.append(chunk)
    return chunks


class ApiContractsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._token_patch = patch.dict(os.environ, {"LEARNING_AGENT_INTERNAL_API_TOKEN": ""}, clear=False)
        self._token_patch.start()
        internal_auth.get_settings.cache_clear()
        self.addCleanup(self._cleanup_internal_token_patch)

    def _cleanup_internal_token_patch(self) -> None:
        self._token_patch.stop()
        internal_auth.get_settings.cache_clear()

    def test_public_event_type_enum_only_contains_runtime_supported_events(self) -> None:
        self.assertEqual(
            {event.value for event in EventType},
            {
                "ack",
                "clarification_card",
                "retrieval_started",
                "retrieval_result",
                "memory_retrieval_started",
                "memory_retrieval_result",
                "memory_promotion_result",
                "tool_call",
                "tool_result",
                "plan_execution_started",
                "plan_step_result",
                "approval_required",
                "plan_replanned",
                "plan_execution_summary",
                "final",
                "error",
            },
        )

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
            grounding_status="grounded",
            retrieval_summary=RetrievalSummary(
                retrieval_strategy="dense+sparse+metadata->rrf->rerank->evidence",
                retrieval_hit_count=5,
                evidence_used_count=4,
                evidence_status="OK",
                evidence_strong_count=3,
            ),
            memory_used_summary=MemoryUsedSummary(
                used=True,
                total_memories=2,
                prompt_memories=[
                    {
                        "memory_id": "mem-1",
                        "memory_type": "preference",
                        "summary": "用户偏好答案带引用",
                    }
                ],
            ),
            memory_updates={"current_topic": "thread_pool"},
            metrics={"retrieval_hit_count": 5},
        )
        self.assertEqual(payload.citations[0].chunk_id, "chunk-1")
        self.assertEqual(payload.used_tools, ["searchKnowledge"])
        self.assertEqual(payload.grounding_status, "grounded")
        self.assertEqual(payload.retrieval_summary.evidence_used_count, 4)
        self.assertEqual(payload.memory_used_summary.prompt_memories[0].memory_type, "preference")

    def test_memory_retrieval_started_payload_contract(self) -> None:
        payload = MemoryRetrievalStartedPayload(
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-1",
            user_id="user-1",
            query="请讲讲 RAG",
            current_topic="RAG",
            retrieval_budget=8,
        )
        validated = validate_event_payload(EventType.MEMORY_RETRIEVAL_STARTED, payload.model_dump(mode="json"))
        self.assertEqual(validated["query"], "请讲讲 RAG")
        self.assertEqual(validated["retrieval_budget"], 8)

    def test_memory_promotion_result_payload_contract(self) -> None:
        payload = MemoryPromotionResultPayload(
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-1",
            candidate_ids=["candidate-1"],
            promoted_ids=["candidate-1"],
            rejected_ids=[],
            governed_actions={"candidate-1": "approve"},
            memory_trace={
                "trace_id": "trace-1",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "decision_reasons": {"candidate-1": "higher_confidence"},
                "conflict_ids": ["mem-1"],
                "deletion_job_ids": ["job-1"],
                "skip_reasons": {},
            },
        )
        validated = validate_event_payload(EventType.MEMORY_PROMOTION_RESULT, payload.model_dump(mode="json"))
        self.assertEqual(validated["governed_actions"]["candidate-1"], "approve")
        self.assertEqual(validated["memory_trace"]["conflict_ids"], ["mem-1"])

    def test_feedback_report_request_contract(self) -> None:
        payload = FeedbackReportRequest(
            user_id="user-1",
            session_id="session-1",
            turn_id="turn-1",
            thread_id="thread-1",
            trace_id="trace-1",
            issue_type=FeedbackIssueType.CITATION_INCORRECT,
            is_helpful=False,
            comment="引用有误",
        )
        self.assertEqual(payload.issue_type, FeedbackIssueType.CITATION_INCORRECT)
        self.assertEqual(payload.comment, "引用有误")

    def test_memory_action_request_contract(self) -> None:
        payload = MemoryActionRequest(
            reason="测试删除",
            superseded_by="mem-2",
            target_memory_id="mem-3",
        )
        self.assertEqual(payload.reason, "测试删除")
        self.assertEqual(payload.superseded_by, "mem-2")

    def test_clarification_payload_uses_structured_options(self) -> None:
        payload = ClarificationCardPayload(
            card_id="clarify-1",
            question="Which topic do you mean?",
            options=[ClarificationOptionPayload(id="1", label="Spring AOP", value="Spring AOP")],
            ambiguity_type="reference",
        )
        self.assertEqual(payload.options[0].label, "Spring AOP")

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
                "/internal/v1/feedback/report",
                "/internal/v1/feedback/samples",
                "/internal/v1/memory/records",
                "/internal/v1/memory/records/{memory_id}",
                "/internal/v1/memory/records/{memory_id}/access-logs",
                "/internal/v1/memory/candidates",
                "/internal/v1/memory/candidates/{candidate_id}/confirm",
                "/internal/v1/memory/candidates/{candidate_id}/reject",
                "/internal/v1/memory/traces",
                "/internal/v1/memory/traces/{trace_id}",
                "/internal/v1/memory/deletion-jobs",
                "/internal/v1/memory/records/{memory_id}/supersede",
                "/internal/v1/memory/records/{memory_id}/delete",
                "/internal/v1/quiz/generate",
                "/internal/v1/study-plan/generate",
                "/internal/v1/session/{session_id}/state",
            },
        )

        app = app_module.create_app(_MockService())
        app_paths = {route.path for route in app.routes}
        self.assertTrue(router_paths.issubset(app_paths))
        self.assertTrue(
            {
                "/health",
                "/meta",
                "/live",
                "/ready",
                "/dependency-status",
                "/metrics",
            }.issubset(app_paths)
        )

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
                    message="帮我解释一下 AOP",
                )
            )
        )
        chunks = asyncio.run(_collect_body_chunks(response))
        self.assertEqual(len(chunks), 2)
        self.assertIn("event: ack", chunks[0])
        self.assertIn("event: final", chunks[1])
