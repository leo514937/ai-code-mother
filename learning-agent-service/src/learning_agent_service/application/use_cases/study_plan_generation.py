from __future__ import annotations

from typing import Any, Dict, List

from learning_agent_service.domain import ToolExecutionCommand, ToolNormalizationRequest


class StudyPlanGenerationService:
    def __init__(
        self,
        *,
        tool_planner,
        tool_executor,
        tool_result_normalizer,
    ) -> None:
        self._tool_planner = tool_planner
        self._tool_executor = tool_executor
        self._tool_result_normalizer = tool_result_normalizer

    def generate(
        self,
        *,
        user_id: str,
        session_id: str,
        topic: str,
        duration_days: int,
        goal: str,
    ) -> List[Dict[str, Any]]:
        selection = self._tool_planner.plan_from_name(
            "generateStudyPlan",
            {
                "topic": topic,
                "duration_days": duration_days,
                "goal": goal,
            },
        )
        raw = self._tool_executor.execute(ToolExecutionCommand(selection=selection))
        normalized = self._tool_result_normalizer.normalize(ToolNormalizationRequest(result=raw))
        return list(normalized.normalized_output.get("data", {}).get("items", []))
