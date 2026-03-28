from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

from learning_agent_service.config import Settings
from learning_agent_service.domain import (
    AnswerComposeRequest,
    AnswerComposeResult,
    NormalizedToolResult,
    SseEnvelope,
    ToolExecutionCommand,
    ToolExecutionResult,
    ToolNormalizationRequest,
    ToolPlanningRequest,
    ToolSelection,
)
from learning_agent_service.domain.enums import IntentType, OutputStyle, ToolExecutionStatus, TurnDecision

from .builtin import build_builtin_tool_registry
from .executor import ToolExecutor as BaseToolExecutor
from .models import ToolExecutionResult as BaseExecutionResult
from .models import ToolSelection as BaseToolSelection
from .normalizer import ToolResultNormalizer as BaseToolResultNormalizer
from .planner import ToolPlanner as BaseToolPlanner
from .registry import ToolRegistry


def build_default_tool_registry(
    *,
    search_knowledge_fn=None,
    get_knowledge_detail_fn=None,
) -> ToolRegistry:
    return build_builtin_tool_registry(
        search_knowledge_fn=search_knowledge_fn,
        get_knowledge_detail_fn=get_knowledge_detail_fn,
    )


def _run_async_safely(coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: Dict[str, Any] = {}
    error: Dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # pragma: no cover
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


def _map_status(result: BaseExecutionResult) -> ToolExecutionStatus:
    if result.status == "ok":
        return ToolExecutionStatus.SUCCESS
    if result.degraded:
        return ToolExecutionStatus.DEGRADED
    return ToolExecutionStatus.FAILED


@dataclass
class ToolPlanner:
    planner: BaseToolPlanner | None = None

    def __post_init__(self) -> None:
        if self.planner is None:
            self.planner = BaseToolPlanner(
                {
                    "quiz": "generateQuiz",
                    "study_plan": "generateStudyPlan",
                    "recommend": "recommendNextTopic",
                    "knowledge": "searchKnowledge",
                    "detail": "getKnowledgeDetail",
                    "save_record": "saveLearningRecord",
                }
            )

    def plan(self, request: ToolPlanningRequest) -> ToolSelection:
        need_tool = request.decision == TurnDecision.TOOL_THEN_ANSWER or request.decision == "tool_then_answer"
        slots = dict(request.slots)
        slots.setdefault("topic", request.current_topic or request.raw_query)
        slots.setdefault("tool_input", {"topic": slots.get("topic")})
        mapped_intent = {
            IntentType.QUIZ.value: "quiz",
            IntentType.STUDY_PLAN.value: "study_plan",
            IntentType.RECOMMEND.value: "recommend",
            IntentType.FOLLOW_UP.value: "detail",
        }.get(request.intent.value if request.intent is not None else "", request.intent.value if request.intent else None)
        selection = self.planner.plan(mapped_intent, need_tool, slots)
        if selection is None:
            return ToolSelection(should_execute=False)
        return ToolSelection(
            tool_name=selection.tool_name,
            should_execute=True,
            input_payload=selection.input_payload,
            reason=selection.reason,
            extra={
                "tool_call_id": str(uuid.uuid4()),
                "timeout_ms": selection.timeout_ms,
                "degrade_to": selection.degrade_to,
            },
        )

    def plan_from_name(self, tool_name: str, input_payload: Dict[str, Any]) -> ToolSelection:
        return ToolSelection(
            tool_name=tool_name,
            should_execute=True,
            input_payload=input_payload,
            reason="direct-endpoint",
            extra={"tool_call_id": str(uuid.uuid4())},
        )


@dataclass
class ToolExecutor:
    search_knowledge_fn: Any = None
    get_knowledge_detail_fn: Any = None
    registry: ToolRegistry | None = None
    executor: BaseToolExecutor | None = None

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = build_default_tool_registry(
                search_knowledge_fn=self.search_knowledge_fn,
                get_knowledge_detail_fn=self.get_knowledge_detail_fn,
            )
        if self.executor is None:
            self.executor = BaseToolExecutor(self.registry)

    def execute(self, command: ToolExecutionCommand) -> ToolExecutionResult:
        selection = command.selection
        if not selection.tool_name or not selection.should_execute:
            return ToolExecutionResult(status=ToolExecutionStatus.SKIPPED)

        base_selection = BaseToolSelection(
            tool_name=selection.tool_name,
            input_payload=selection.input_payload,
            reason=selection.reason,
            degrade_to=(selection.extra or {}).get("degrade_to"),
            timeout_ms=(selection.extra or {}).get("timeout_ms"),
        )
        result = _run_async_safely(self.executor.execute(base_selection))
        extra = {
            "tool_call_id": (selection.extra or {}).get("tool_call_id"),
            "error_code": result.error_code,
            "error_message": result.error_message,
            "retryable": result.retryable,
            "degraded": result.degraded,
            "degrade_to": result.degrade_to,
            "duration_ms": result.duration_ms,
        }
        return ToolExecutionResult(
            status=_map_status(result),
            tool_name=selection.tool_name,
            output_payload=result.output,
            extra=extra,
        )


@dataclass
class ToolResultNormalizer:
    normalizer: BaseToolResultNormalizer | None = None

    def __post_init__(self) -> None:
        if self.normalizer is None:
            self.normalizer = BaseToolResultNormalizer()

    def normalize(self, request: ToolNormalizationRequest) -> NormalizedToolResult:
        result = request.result
        extra = dict(result.extra)
        payload = BaseExecutionResult(
            tool_name=result.tool_name or "",
            status="ok" if result.status == ToolExecutionStatus.SUCCESS else "failed",
            output=result.output_payload,
            error_code=extra.get("error_code"),
            error_message=extra.get("error_message"),
            retryable=bool(extra.get("retryable")),
            degraded=bool(extra.get("degraded")) or result.status == ToolExecutionStatus.DEGRADED,
            degrade_to=extra.get("degrade_to"),
            duration_ms=int(extra.get("duration_ms") or 0),
        )
        normalized = self.normalizer.normalize(payload)
        normalized_status = ToolExecutionStatus.SUCCESS if normalized.ok else result.status
        used_tools = [normalized.tool_name] if normalized.tool_name else []
        return NormalizedToolResult(
            status=normalized_status,
            tool_name=normalized.tool_name,
            normalized_output=normalized.payload,
            used_tools=used_tools,
            extra={
                "errors": normalized.errors,
                "degraded": normalized.degraded,
                "retryable": normalized.retryable,
                "degrade_to": normalized.degrade_to,
            },
        )


@dataclass
class AnswerComposer:
    def compose(self, request: AnswerComposeRequest) -> AnswerComposeResult:
        sections: List[str] = []
        if request.requested_output_style == OutputStyle.INTERVIEW:
            sections.append("Interview-ready answer")
        elif request.requested_output_style == OutputStyle.COMPARISON:
            sections.append("Comparison answer")
        else:
            sections.append("Direct answer")
        rag_result = request.rag_result
        if rag_result and rag_result.evidence_pack and rag_result.evidence_pack.items:
            sections.extend([item.content for item in rag_result.evidence_pack.items[:2]])
        if request.tool_result and request.tool_result.normalized_output:
            sections.append(
                "Tool result: {payload}".format(
                    payload=request.tool_result.normalized_output.get("data", request.tool_result.normalized_output)
                )
            )
        if request.recommendation is not None:
            sections.append("Recommended next topic: {topic}".format(topic=request.recommendation.topic))
        if not sections:
            sections.append("No stable evidence available, fallback to a conservative summary.")
        confidence = 0.82 if rag_result and rag_result.evidence_pack else 0.56
        return AnswerComposeResult(answer_text="\n\n".join(sections), confidence=confidence)


@dataclass
class Finalizer:
    settings: Settings

    def finalize(self, *args, **kwargs) -> SseEnvelope | None:
        return None
