from __future__ import annotations

import asyncio
import unittest

import _bootstrap  # noqa: F401
from pydantic import BaseModel

from learning_agent_service.domain import (
    AnswerComposeRequest,
    ChatTurnCommand,
    Citation,
    EvidenceItem,
    EvidencePack,
    RagResult,
    ToolExecutionCommand,
    ToolExecutionResult as DomainToolExecutionResult,
    ToolNormalizationRequest,
    ToolPlanningRequest,
    ToolSelection as DomainToolSelection,
    build_initial_state,
)
from learning_agent_service.domain.enums import IntentType, RagStatus, ToolExecutionStatus, TurnDecision
from learning_agent_service.tools import (
    RegisteredTool,
    SideEffectLevel,
    ToolExecutor,
    ToolPlanner,
    ToolRegistry,
    ToolResultNormalizer,
    ToolSelection,
    ToolSpec,
)
from learning_agent_service.tools.service import (
    ToolExecutor as RuntimeToolExecutor,
    ToolPlanner as RuntimeToolPlanner,
    ToolResultNormalizer as RuntimeToolResultNormalizer,
    build_default_tool_registry,
)


class DummyInput(BaseModel):
    topic: str


class DummyOutput(BaseModel):
    summary: str


class ToolsTestCase(unittest.TestCase):
    def _state(self):
        return build_initial_state(
            ChatTurnCommand(
                trace_id="trace-1",
                session_id="session-1",
                turn_id="turn-1",
                user_id="user-1",
                message="Generate a quiz about JVM",
            )
        )

    def test_tool_planner_maps_intent(self) -> None:
        selection = ToolPlanner().plan(
            intent="quiz",
            need_tool=True,
            slots={"topic": "JVM"},
        )
        self.assertIsNotNone(selection)
        self.assertEqual(selection.tool_name, "generateQuiz")
        self.assertEqual(selection.input_payload["topic"], "JVM")

    def test_registry_registers_and_lists_specs(self) -> None:
        registry = ToolRegistry()
        registry.register(
            RegisteredTool(
                spec=ToolSpec(
                    name="generateQuiz",
                    description="Generate quiz",
                    input_model=DummyInput,
                    output_model=DummyOutput,
                    idempotent=True,
                    retryable=True,
                    side_effect_level=SideEffectLevel.NONE,
                ),
                handler=lambda payload: {"summary": payload.topic},
            )
        )
        self.assertTrue(registry.is_registered("generateQuiz"))
        self.assertEqual(registry.list_specs()[0].name, "generateQuiz")

    def test_executor_and_normalizer_success_path(self) -> None:
        registry = ToolRegistry()
        registry.register(
            RegisteredTool(
                spec=ToolSpec(
                    name="searchKnowledge",
                    description="Search knowledge",
                    input_model=DummyInput,
                    output_model=DummyOutput,
                    idempotent=True,
                    retryable=True,
                    side_effect_level=SideEffectLevel.NONE,
                    timeout_ms=100,
                ),
                handler=lambda payload: {"summary": "topic={topic}".format(topic=payload.topic)},
            )
        )

        executor = ToolExecutor(registry)
        result = asyncio.run(
            executor.execute(
                ToolSelection(tool_name="searchKnowledge", input_payload={"topic": "Redis"})
            )
        )
        normalized = ToolResultNormalizer().normalize(result)

        self.assertEqual(result.status, "ok")
        self.assertTrue(normalized.ok)
        self.assertEqual(normalized.payload["summary"], "topic=Redis")

    def test_executor_timeout_uses_degrade_to(self) -> None:
        async def slow_handler(payload: DummyInput):
            await asyncio.sleep(0.02)
            return {"summary": payload.topic}

        registry = ToolRegistry()
        registry.register(
            RegisteredTool(
                spec=ToolSpec(
                    name="generateQuiz",
                    description="Generate quiz",
                    input_model=DummyInput,
                    output_model=DummyOutput,
                    idempotent=True,
                    retryable=True,
                    side_effect_level=SideEffectLevel.NONE,
                    degrade_to="lightweight_quiz",
                    timeout_ms=1,
                ),
                handler=slow_handler,
            )
        )

        result = asyncio.run(
            ToolExecutor(registry).execute(
                ToolSelection(tool_name="generateQuiz", input_payload={"topic": "Spring"})
            )
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "LEARN-5301")
        self.assertTrue(result.degraded)
        self.assertEqual(result.degrade_to, "lightweight_quiz")

    def test_runtime_tool_planner_returns_domain_selection(self) -> None:
        selection = RuntimeToolPlanner().plan(
            ToolPlanningRequest(
                raw_query="Generate a quiz about JVM",
                decision=TurnDecision.TOOL_THEN_ANSWER,
                intent=IntentType.QUIZ,
                slots={"topic": "JVM"},
                current_topic="JVM",
            )
        )
        self.assertTrue(selection.should_execute)
        self.assertEqual(selection.tool_name, "generateQuiz")
        self.assertEqual(selection.input_payload["topic"], "JVM")
        self.assertTrue(selection.extra["tool_call_id"])

    def test_runtime_tool_executor_uses_shared_executor_stack(self) -> None:
        result = RuntimeToolExecutor(build_default_tool_registry()).execute(
            ToolExecutionCommand(
                selection=DomainToolSelection(
                    tool_name="generateQuiz",
                    should_execute=True,
                    input_payload={"topic": "JVM", "count": 2},
                    reason="test",
                    extra={"tool_call_id": "call-1"},
                )
            )
        )
        self.assertEqual(result.status, ToolExecutionStatus.SUCCESS)
        self.assertEqual(result.output_payload["data"]["topic"], "JVM")
        self.assertEqual(result.extra["tool_call_id"], "call-1")

    def test_runtime_tool_result_normalizer_preserves_error_metadata(self) -> None:
        raw = DomainToolExecutionResult(
            status=ToolExecutionStatus.DEGRADED,
            tool_name="generateQuiz",
            output_payload={},
            extra={
                "error_code": "LEARN-5301",
                "error_message": "Tool execution timed out",
                "retryable": True,
                "degraded": True,
                "degrade_to": "lightweight_quiz",
            },
        )
        normalized = RuntimeToolResultNormalizer().normalize(ToolNormalizationRequest(result=raw))
        self.assertEqual(normalized.status, ToolExecutionStatus.DEGRADED)
        self.assertTrue(normalized.extra["degraded"])
        self.assertEqual(normalized.extra["errors"]["code"], "LEARN-5301")

    def test_answer_composer_refuses_when_evidence_empty(self) -> None:
        empty_pack = EvidencePack(evidence_status="EMPTY")
        rag_result = RagResult(status=RagStatus.EMPTY, evidence_pack=empty_pack, evidence_status="EMPTY")

        from learning_agent_service.tools.service import AnswerComposer

        output = AnswerComposer().compose(
            AnswerComposeRequest(raw_query="什么是RAG", rag_result=rag_result)
        )
        self.assertEqual(output.answer_text, "当前知识库中没有找到足够依据回答该问题。")

    def test_answer_composer_uses_grounded_llm_and_citations_when_evidence_ok(self) -> None:
        calls: list[str] = []

        def fake_llm(request: AnswerComposeRequest):
            calls.append(request.raw_query)
            return {"answer_text": "RAG 依赖检索到的证据。"}

        from learning_agent_service.tools.service import AnswerComposer

        pack = EvidencePack(
            evidence_status="OK",
            items=[
                EvidenceItem(
                    chunk_id="child-1",
                    content="RAG 通过检索证据来约束回答。",
                    score=0.92,
                    document_id="doc-1",
                    chunk_type="concept",
                    citation_chunk_id="child-1",
                    metadata={"title": "RAG 基础"},
                )
            ],
            strong_items=[
                EvidenceItem(
                    chunk_id="child-1",
                    content="RAG 通过检索证据来约束回答。",
                    score=0.92,
                    document_id="doc-1",
                    chunk_type="concept",
                    citation_chunk_id="child-1",
                    metadata={"title": "RAG 基础"},
                )
            ],
        )
        rag_result = RagResult(
            status=RagStatus.OK,
            evidence_pack=pack,
            evidence_status="OK",
            citations=[
                Citation(
                    chunk_id="child-1",
                    document_id="doc-1",
                    source_type="document",
                    version="v1",
                    score=0.92,
                    title="RAG 基础",
                    locator="concept",
                )
            ],
        )
        output = AnswerComposer(llm_answerer=fake_llm).compose(
            AnswerComposeRequest(raw_query="RAG 是什么", rag_result=rag_result)
        )
        self.assertEqual(calls, ["RAG 是什么"])
        self.assertIn("RAG 依赖检索到的证据。", output.answer_text)
        self.assertIn("证据引用", output.answer_text)

    def test_answer_composer_weak_evidence_is_cautious(self) -> None:
        from learning_agent_service.tools.service import AnswerComposer

        weak_pack = EvidencePack(
            evidence_status="WEAK",
            items=[
                EvidenceItem(
                    chunk_id="weak-1",
                    content="RAG 有时候会检索外部证据。",
                    score=0.35,
                    document_id="doc-1",
                    chunk_type="concept",
                    tier="weak",
                )
            ],
            weak_items=[
                EvidenceItem(
                    chunk_id="weak-1",
                    content="RAG 有时候会检索外部证据。",
                    score=0.35,
                    document_id="doc-1",
                    chunk_type="concept",
                    tier="weak",
                )
            ],
        )
        rag_result = RagResult(status=RagStatus.DEGRADED, evidence_pack=weak_pack, evidence_status="WEAK")
        output = AnswerComposer().compose(
            AnswerComposeRequest(raw_query="RAG 是什么", rag_result=rag_result)
        )
        self.assertIn("谨慎判断", output.answer_text)
        self.assertIn("建议补充", output.answer_text)

    def test_builtin_tool_metadata_marks_save_learning_record_as_approval_required(self) -> None:
        registry = build_default_tool_registry()
        spec = registry.get("saveLearningRecord").spec

        self.assertTrue(spec.requires_approval)
        self.assertEqual(spec.allowed_execution_modes, ("plan_execute",))
