from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from learning_agent_service.config import Settings
from learning_agent_service.domain import GraphState, SseEnvelope, ToolExecutionResult, ToolSelection
from learning_agent_service.domain.enums import OutputStyle, ToolExecutionStatus
from learning_agent_service.tools.executor import ToolExecutor as BaseToolExecutor
from learning_agent_service.tools.models import (
    RegisteredTool,
    SideEffectLevel,
    ToolExecutionResult as BaseExecutionResult,
    ToolSelection as BaseToolSelection,
    ToolSpec,
)
from learning_agent_service.tools.normalizer import ToolResultNormalizer as BaseToolResultNormalizer
from learning_agent_service.tools.planner import ToolPlanner as BaseToolPlanner
from learning_agent_service.tools.registry import ToolRegistry


class TopicPayload(BaseModel):
    topic: str = Field(default="general-topic")
    count: int = Field(default=5)
    difficulty: str = Field(default="intermediate")
    duration_days: int = Field(default=7)
    goal: str = Field(default="systematic-review")


class GenericToolOutput(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)


def _generate_quiz(payload: TopicPayload) -> Dict[str, Any]:
    questions = []
    for idx in range(1, payload.count + 1):
        questions.append(
            {
                "question": "Question {idx}: explain the core idea of {topic}.".format(
                    idx=idx,
                    topic=payload.topic,
                ),
                "answer": "Explain definition, mechanism, use cases, and follow-up questions.",
                "difficulty": payload.difficulty,
                "common_pitfall": "Only reciting the definition without tradeoffs.",
            }
        )
    return {"data": {"topic": payload.topic, "questions": questions}}


def _generate_study_plan(payload: TopicPayload) -> Dict[str, Any]:
    items = []
    for day in range(1, payload.duration_days + 1):
        items.append(
            {
                "day": day,
                "title": "Day {day}: {topic}".format(day=day, topic=payload.topic),
                "objective": "Work toward {goal}.".format(goal=payload.goal),
            }
        )
    return {"data": {"topic": payload.topic, "items": items}}


def _recommend_next_topic(payload: TopicPayload) -> Dict[str, Any]:
    return {
        "data": {
            "topic": payload.topic,
            "next_topic": "next-{topic}".format(topic=payload.topic),
            "reason": "topic-graph",
        }
    }


def _save_learning_record(payload: TopicPayload) -> Dict[str, Any]:
    return {"data": {"saved": True, "topic": payload.topic}}


def _get_knowledge_detail(payload: TopicPayload) -> Dict[str, Any]:
    return {
        "data": {
            "topic": payload.topic,
            "detail": "detail is composed from rag evidence and durable facts",
        }
    }


def _search_knowledge(payload: TopicPayload) -> Dict[str, Any]:
    return {
        "data": {
            "topic": payload.topic,
            "matches": [
                {
                    "chunk_id": "{topic}-match".format(topic=payload.topic.lower().replace(" ", "-")),
                    "title": payload.topic,
                }
            ],
        }
    }


def build_default_tool_registry(
    *,
    search_knowledge_fn=None,
    get_knowledge_detail_fn=None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            spec=ToolSpec(
                name="generateQuiz",
                description="generate quiz questions",
                input_model=TopicPayload,
                output_model=GenericToolOutput,
                idempotent=True,
                retryable=True,
                side_effect_level=SideEffectLevel.NONE,
                degrade_to="lightweight-quiz",
            ),
            handler=_generate_quiz,
        )
    )
    registry.register(
        RegisteredTool(
            spec=ToolSpec(
                name="generateStudyPlan",
                description="generate a study plan",
                input_model=TopicPayload,
                output_model=GenericToolOutput,
                idempotent=True,
                retryable=True,
                side_effect_level=SideEffectLevel.NONE,
                degrade_to="lightweight-study-plan",
            ),
            handler=_generate_study_plan,
        )
    )
    registry.register(
        RegisteredTool(
            spec=ToolSpec(
                name="recommendNextTopic",
                description="recommend next topic",
                input_model=TopicPayload,
                output_model=GenericToolOutput,
                idempotent=True,
                retryable=True,
                side_effect_level=SideEffectLevel.NONE,
            ),
            handler=_recommend_next_topic,
        )
    )
    registry.register(
        RegisteredTool(
            spec=ToolSpec(
                name="saveLearningRecord",
                description="persist learning record",
                input_model=TopicPayload,
                output_model=GenericToolOutput,
                idempotent=False,
                retryable=True,
                side_effect_level=SideEffectLevel.LOW,
                degrade_to="async-retry-queue",
            ),
            handler=_save_learning_record,
        )
    )
    registry.register(
        RegisteredTool(
            spec=ToolSpec(
                name="getKnowledgeDetail",
                description="return a knowledge detail",
                input_model=TopicPayload,
                output_model=GenericToolOutput,
                idempotent=True,
                retryable=False,
                side_effect_level=SideEffectLevel.NONE,
            ),
            handler=(
                (lambda payload: {"data": get_knowledge_detail_fn(payload.topic)})
                if callable(get_knowledge_detail_fn)
                else _get_knowledge_detail
            ),
        )
    )
    registry.register(
        RegisteredTool(
            spec=ToolSpec(
                name="searchKnowledge",
                description="search knowledge hits",
                input_model=TopicPayload,
                output_model=GenericToolOutput,
                idempotent=True,
                retryable=True,
                side_effect_level=SideEffectLevel.NONE,
                degrade_to="rewrite-and-retry",
            ),
            handler=(
                (lambda payload: {"data": search_knowledge_fn(payload.topic, payload.count)})
                if callable(search_knowledge_fn)
                else _search_knowledge
            ),
        )
    )
    return registry


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

    def plan(self, state: GraphState) -> ToolSelection:
        turn = state["turn"]
        understanding = turn.understanding_result
        intent_value = turn.intent.value if turn.intent is not None else None
        if intent_value is None and understanding is not None:
            raw_intent = understanding.intent
            intent_value = raw_intent.value if hasattr(raw_intent, "value") else str(raw_intent)

        decision_value = turn.decision.value
        if understanding is not None and understanding.decision is not None:
            raw_decision = understanding.decision
            decision_value = raw_decision.value if hasattr(raw_decision, "value") else str(raw_decision)

        need_tool = decision_value == "tool_then_answer"
        slots = dict(turn.slots)
        if not slots and understanding is not None:
            slots = dict(understanding.slots)
        slots.setdefault("topic", state["persistent"].current_topic or state["turn"].raw_query)
        slots.setdefault("tool_input", {"topic": slots.get("topic")})
        mapped_intent = {
            "quiz": "quiz",
            "study_plan": "study_plan",
            "recommend": "recommend",
            "follow_up": "detail",
        }.get(intent_value or "", intent_value)
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

    def execute(self, selection: ToolSelection, state: GraphState) -> ToolExecutionResult:
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

    def normalize(self, result: ToolExecutionResult, state: GraphState):
        from learning_agent_service.domain import NormalizedToolResult

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
    def compose(self, state: GraphState) -> GraphState:
        turn = state["turn"]
        rag_result = turn.rag_result
        tool_result = turn.tool_result
        sections: List[str] = []
        if turn.requested_output_style == OutputStyle.INTERVIEW:
            sections.append("Interview-ready answer")
        elif turn.requested_output_style == OutputStyle.COMPARISON:
            sections.append("Comparison answer")
        else:
            sections.append("Direct answer")
        if rag_result and rag_result.evidence_pack and rag_result.evidence_pack.items:
            sections.extend([item.content for item in rag_result.evidence_pack.items[:2]])
        if tool_result and tool_result.normalized_output:
            sections.append(
                "Tool result: {payload}".format(
                    payload=tool_result.normalized_output.get("data", tool_result.normalized_output)
                )
            )
        if not sections:
            sections.append("No stable evidence available, fallback to a conservative summary.")
        runtime = state["runtime"]
        metrics = dict(runtime.metrics)
        metrics["final_answer_confidence"] = 0.82 if rag_result and rag_result.evidence_pack else 0.56
        state["runtime"] = runtime.model_copy(update={"metrics": metrics})
        state["turn"] = turn.model_copy(update={"final_answer": "\n\n".join(sections)})
        return state


@dataclass
class Finalizer:
    settings: Settings

    def finalize(self, state: GraphState) -> Optional[SseEnvelope]:
        return None
