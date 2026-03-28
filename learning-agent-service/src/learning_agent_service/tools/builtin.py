from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field

from .models import RegisteredTool, SideEffectLevel, ToolSpec
from .registry import ToolRegistry


class QuizToolInput(BaseModel):
    topic: str = Field(default="general-topic")
    count: int = Field(default=5)
    difficulty: str = Field(default="intermediate")


class StudyPlanToolInput(BaseModel):
    topic: str = Field(default="general-topic")
    duration_days: int = Field(default=7)
    goal: str = Field(default="systematic-review")


class RecommendationToolInput(BaseModel):
    topic: str = Field(default="general-topic")


class LearningRecordToolInput(BaseModel):
    topic: str = Field(default="general-topic")
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    result: Optional[str] = None


class KnowledgeDetailToolInput(BaseModel):
    topic: str = Field(default="general-topic")


class KnowledgeSearchToolInput(BaseModel):
    topic: str = Field(default="general-topic")
    count: int = Field(default=5)


class GenericToolOutput(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)


def _generate_quiz(payload: QuizToolInput) -> Dict[str, Any]:
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


def _generate_study_plan(payload: StudyPlanToolInput) -> Dict[str, Any]:
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


def _recommend_next_topic(payload: RecommendationToolInput) -> Dict[str, Any]:
    return {
        "data": {
            "topic": payload.topic,
            "next_topic": "next-{topic}".format(topic=payload.topic),
            "reason": "topic-graph",
        }
    }


def _save_learning_record(payload: LearningRecordToolInput) -> Dict[str, Any]:
    return {
        "data": {
            "saved": True,
            "topic": payload.topic,
            "user_id": payload.user_id,
            "session_id": payload.session_id,
            "result": payload.result,
        }
    }


def _get_knowledge_detail(payload: KnowledgeDetailToolInput) -> Dict[str, Any]:
    return {
        "data": {
            "topic": payload.topic,
            "detail": "detail is composed from rag evidence and durable facts",
        }
    }


def _search_knowledge(payload: KnowledgeSearchToolInput) -> Dict[str, Any]:
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


def build_builtin_tool_registry(
    *,
    search_knowledge_fn: Optional[Callable[[str, int], Any]] = None,
    get_knowledge_detail_fn: Optional[Callable[[str], Any]] = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            spec=ToolSpec(
                name="generateQuiz",
                description="generate quiz questions",
                input_model=QuizToolInput,
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
                input_model=StudyPlanToolInput,
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
                input_model=RecommendationToolInput,
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
                input_model=LearningRecordToolInput,
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
                input_model=KnowledgeDetailToolInput,
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
                input_model=KnowledgeSearchToolInput,
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
