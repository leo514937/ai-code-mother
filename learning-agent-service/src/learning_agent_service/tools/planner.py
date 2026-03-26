from __future__ import annotations

from typing import Dict, Optional

from .models import ToolSelection


class ToolPlanner:
    DEFAULT_INTENT_TOOL_MAP = {
        "knowledge": "searchKnowledge",
        "detail": "getKnowledgeDetail",
        "quiz": "generateQuiz",
        "study_plan": "generateStudyPlan",
        "recommend_next": "recommendNextTopic",
        "save_record": "saveLearningRecord",
    }

    def __init__(self, intent_tool_map: Optional[Dict[str, str]] = None) -> None:
        self._intent_tool_map = dict(self.DEFAULT_INTENT_TOOL_MAP)
        if intent_tool_map:
            self._intent_tool_map.update(intent_tool_map)

    def plan(
        self,
        intent: Optional[str],
        need_tool: bool,
        slots: Optional[Dict[str, object]] = None,
    ) -> Optional[ToolSelection]:
        if not need_tool:
            return None

        slot_data = dict(slots or {})
        tool_name = slot_data.pop("tool_name", None) or self._intent_tool_map.get(intent or "")
        if not tool_name:
            return None

        explicit_payload = slot_data.pop("tool_input", None)
        if isinstance(explicit_payload, dict):
            input_payload = explicit_payload
        else:
            input_payload = slot_data

        return ToolSelection(
            tool_name=tool_name,
            input_payload=input_payload,
            reason="planned_from_intent:{intent}".format(intent=intent or "unknown"),
        )
