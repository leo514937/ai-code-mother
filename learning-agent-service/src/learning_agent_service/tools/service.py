from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from learning_agent_service.config import Settings
from learning_agent_service.domain import GraphState, SseEnvelope, ToolExecutionResult, ToolSelection
from learning_agent_service.domain.enums import OutputStyle, ToolExecutionStatus
from learning_agent_service.tools import RegisteredTool, SideEffectLevel, ToolRegistry, ToolSpec
from learning_agent_service.tools.normalizer import ToolResultNormalizer as BaseToolResultNormalizer
from learning_agent_service.tools.planner import ToolPlanner as BaseToolPlanner


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
                "question": "Question {idx}: explain the core idea of {topic}.".format(idx=idx, topic=payload.topic),
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
    return {"data": {"topic": payload.topic, "next_topic": "next-{topic}".format(topic=payload.topic), "reason": "topic-graph"}}


def _save_learning_record(payload: TopicPayload) -> Dict[str, Any]:
    return {"data": {"saved": True, "topic": payload.topic}}


def _get_knowledge_detail(payload: TopicPayload) -> Dict[str, Any]:
    return {"data": {"topic": payload.topic, "detail": "detail is composed from rag evidence and durable facts"}}


def _search_knowledge(payload: TopicPayload) -> Dict[str, Any]:
    return {"data": {"topic": payload.topic, "matches": [payload.topic]}}


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
        understanding = state["turn"].understanding_result
        intent = understanding.intent.value if understanding else None
        need_tool = bool(understanding and understanding.decision.value == "tool_then_answer")
        slots = dict(understanding.slots if understanding else {})
        slots.setdefault("topic", state["persistent"].current_topic or state["turn"].raw_query)
        slots.setdefault("tool_input", {"topic": slots.get("topic")})
        mapped_intent = {
            "quiz": "quiz",
            "study_plan": "study_plan",
            "recommend": "recommend",
            "follow_up": "detail",
        }.get(intent or "", intent)
        selection = self.planner.plan(mapped_intent, need_tool, slots)
        if selection is None:
            return ToolSelection(should_execute=False)
        return ToolSelection(
            tool_name=selection.tool_name,
            should_execute=True,
            input_payload=selection.input_payload,
            reason=selection.reason,
            extra={"tool_call_id": str(uuid.uuid4())},
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
    registry: ToolRegistry | None = None

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = self._build_registry()

    def execute(self, selection: ToolSelection, state: GraphState) -> ToolExecutionResult:
        if not selection.tool_name:
            return ToolExecutionResult(status=ToolExecutionStatus.SKIPPED)
        try:
            registered = self.registry.get(selection.tool_name)
        except KeyError:
            return ToolExecutionResult(status=ToolExecutionStatus.FAILED, tool_name=selection.tool_name, extra={"message": "tool-not-registered"})
        payload = registered.spec.input_model.model_validate(selection.input_payload)
        output = registered.handler(payload)
        validated = registered.spec.output_model.model_validate(output)
        return ToolExecutionResult(
            status=ToolExecutionStatus.SUCCESS,
            tool_name=selection.tool_name,
            output_payload=validated.model_dump(mode="json"),
            extra={"tool_call_id": selection.extra.get("tool_call_id") if selection.extra else None},
        )

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(RegisteredTool(spec=ToolSpec(name="generateQuiz", description="generate quiz questions", input_model=TopicPayload, output_model=GenericToolOutput, idempotent=True, retryable=True, side_effect_level=SideEffectLevel.NONE, degrade_to="lightweight-quiz"), handler=_generate_quiz))
        registry.register(RegisteredTool(spec=ToolSpec(name="generateStudyPlan", description="generate a study plan", input_model=TopicPayload, output_model=GenericToolOutput, idempotent=True, retryable=True, side_effect_level=SideEffectLevel.NONE, degrade_to="lightweight-study-plan"), handler=_generate_study_plan))
        registry.register(RegisteredTool(spec=ToolSpec(name="recommendNextTopic", description="recommend next topic", input_model=TopicPayload, output_model=GenericToolOutput, idempotent=True, retryable=True, side_effect_level=SideEffectLevel.NONE), handler=_recommend_next_topic))
        registry.register(RegisteredTool(spec=ToolSpec(name="saveLearningRecord", description="persist learning record", input_model=TopicPayload, output_model=GenericToolOutput, idempotent=False, retryable=True, side_effect_level=SideEffectLevel.LOW, degrade_to="async-retry-queue"), handler=_save_learning_record))
        registry.register(RegisteredTool(spec=ToolSpec(name="getKnowledgeDetail", description="return a knowledge detail", input_model=TopicPayload, output_model=GenericToolOutput, idempotent=True, retryable=False, side_effect_level=SideEffectLevel.NONE), handler=_get_knowledge_detail))
        registry.register(RegisteredTool(spec=ToolSpec(name="searchKnowledge", description="search knowledge hits", input_model=TopicPayload, output_model=GenericToolOutput, idempotent=True, retryable=True, side_effect_level=SideEffectLevel.NONE), handler=_search_knowledge))
        return registry


@dataclass
class ToolResultNormalizer:
    normalizer: BaseToolResultNormalizer | None = None

    def __post_init__(self) -> None:
        if self.normalizer is None:
            self.normalizer = BaseToolResultNormalizer()

    def normalize(self, result: ToolExecutionResult, state: GraphState):
        from learning_agent_service.domain import NormalizedToolResult
        from learning_agent_service.tools.models import ToolExecutionResult as PayloadModel

        payload = PayloadModel(
            tool_name=result.tool_name,
            status="ok" if result.status == ToolExecutionStatus.SUCCESS else result.status.value,
            output=result.output_payload,
            error_code=result.error.value if result.error else None,
            error_message=result.error.value if result.error else None,
            degraded=bool(result.degraded_to),
            degrade_to=result.degraded_to,
        )
        normalized = self.normalizer.normalize(payload)
        return NormalizedToolResult(
            status=ToolExecutionStatus.SUCCESS if normalized.ok else ToolExecutionStatus.FAILED,
            tool_name=normalized.tool_name,
            normalized_output=normalized.payload,
            used_tools=[normalized.tool_name] if normalized.tool_name else [],
            extra={"degraded": normalized.degraded, "retryable": normalized.retryable, "degrade_to": normalized.degrade_to},
        )


@dataclass
class AnswerComposer:
    def compose(self, state: GraphState) -> GraphState:
        turn = state["turn"]
        understanding = turn.understanding_result
        rag_result = turn.rag_result
        tool_result = turn.tool_result
        sections: List[str] = []
        if understanding:
            if understanding.requested_output_style == OutputStyle.INTERVIEW:
                sections.append("Interview-ready answer")
            elif understanding.requested_output_style == OutputStyle.COMPARISON:
                sections.append("Comparison answer")
            else:
                sections.append("Direct answer")
        if rag_result and rag_result.evidence_pack and rag_result.evidence_pack.items:
            sections.extend([item.content for item in rag_result.evidence_pack.items[:2]])
        if tool_result and tool_result.normalized_output:
            sections.append("Tool result: {payload}".format(payload=tool_result.normalized_output.get("data", tool_result.normalized_output)))
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

    def finalize(self, state: GraphState) -> SseEnvelope | None:
        return None
