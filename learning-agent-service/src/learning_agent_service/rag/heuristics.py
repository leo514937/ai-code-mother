from __future__ import annotations

import re

from learning_agent_service.domain import TurnUnderstandingRequest, TurnUnderstandingResult
from learning_agent_service.domain.enums import IntentType, OutputStyle, TurnDecision

_CN_INTERVIEW = "\u9762\u8bd5"
_CN_COMPARE = "\u533a\u522b"
_CN_BRIEF = "\u7b80\u5355"
_CN_QUIZ = "\u51fa\u9898"
_CN_STUDY_PLAN = "\u5b66\u4e60\u8def\u7ebf"
_CN_NEXT_TOPIC = "\u63a5\u4e0b\u6765\u5b66"
_CN_CODE = "\u4ee3\u7801"
_CN_SUMMARY = "\u603b\u7ed3"
_CN_ROUTE = "\u8def\u7ebf"
_CN_PLAN = "\u89c4\u5212"
_CN_REVIEW = "\u590d\u4e60"
_CN_QUESTION = "\u9898"
_CN_EXPLAIN = "\u7406\u89e3"
_CN_HOW = "\u600e\u4e48"
_CN_THIS = "\u8fd9\u4e2a"
_CN_THAT = "\u90a3\u4e2a"
_CN_PREVIOUS = "\u4e0a\u4e00\u4e2a"
_CN_IT = "\u5b83"

_QUIZ_COUNT_PATTERN = re.compile(r"(\d+|[一二三四五六七八九十两]+)\s*道?.{0,3}\u9898")


class HeuristicModelGateway:
    def classify_turn(self, request: TurnUnderstandingRequest) -> TurnUnderstandingResult:
        command = request.command
        persistent = request.persistent
        message = command.message.strip()
        lowered = message.lower()
        chinese_plan = any(token in message for token in (_CN_STUDY_PLAN, _CN_ROUTE, _CN_PLAN, _CN_REVIEW, "\u8ba1\u5212"))
        chinese_quiz = any(token in message for token in (_CN_QUIZ, _CN_QUESTION, "\u5237\u9898", "\u81ea\u6d4b", "\u6d4b\u6211"))
        chinese_follow_up = _looks_like_follow_up_query(message, lowered, persistent)

        style = command.response_mode
        if style is None:
            if "interview" in lowered or _CN_INTERVIEW in message:
                style = OutputStyle.INTERVIEW
            elif any(token in lowered for token in ("compare", "difference", "vs")) or _CN_COMPARE in message:
                style = OutputStyle.COMPARISON
            elif any(token in lowered for token in ("brief", "simple")) or _CN_BRIEF in message:
                style = OutputStyle.BRIEF
            else:
                style = OutputStyle.DETAILED

        intent = IntentType.EXPLAIN
        confidence = 0.72
        if any(token in lowered for token in ("quiz", "question", "test me")) or chinese_quiz or _QUIZ_COUNT_PATTERN.search(message):
            intent = IntentType.QUIZ
            confidence = 0.90
        elif any(token in lowered for token in ("study plan", "roadmap", "review plan")) or chinese_plan:
            intent = IntentType.STUDY_PLAN
            confidence = 0.90
        elif any(token in lowered for token in ("next topic", "next step")) or _CN_NEXT_TOPIC in message:
            intent = IntentType.RECOMMEND
            confidence = 0.86
        elif any(token in lowered for token in ("difference", "compare", "vs")) or _CN_COMPARE in message:
            intent = IntentType.COMPARE
            confidence = 0.88
        elif "interview" in lowered or _CN_INTERVIEW in message:
            intent = IntentType.INTERVIEW
            confidence = 0.87
        elif any(token in lowered for token in ("code", "example", "demo")) or _CN_CODE in message:
            intent = IntentType.CODE
            confidence = 0.84
        elif any(token in lowered for token in ("summary", "recap")) or _CN_SUMMARY in message:
            intent = IntentType.SUMMARY
            confidence = 0.82
        elif chinese_follow_up:
            intent = IntentType.FOLLOW_UP
            confidence = 0.58 if persistent.recent_entities else 0.42

        decision = TurnDecision.DIRECT_ANSWER
        if intent in {IntentType.QUIZ, IntentType.STUDY_PLAN, IntentType.RECOMMEND}:
            decision = TurnDecision.TOOL_THEN_ANSWER
        elif intent in {
            IntentType.EXPLAIN,
            IntentType.COMPARE,
            IntentType.INTERVIEW,
            IntentType.CODE,
            IntentType.SUMMARY,
            IntentType.FOLLOW_UP,
        }:
            decision = TurnDecision.RETRIEVE_THEN_ANSWER

        return TurnUnderstandingResult(
            decision=decision,
            intent=intent,
            intent_confidence=confidence,
            requested_output_style=style,
            slots={
                "topic_hint": command.topic_hint,
                "question_type": intent.value,
                "requested_style": style.value if style else None,
            },
        )


def _contains_reference_token(message: str, lowered: str) -> bool:
    return any(token in lowered for token in ("this", "that", "previous", "it")) or any(
        token in message for token in (_CN_THIS, _CN_THAT, _CN_PREVIOUS, _CN_IT)
    )


def _looks_like_follow_up_query(message: str, lowered: str, persistent) -> bool:
    if _contains_reference_token(message, lowered):
        return True
    if not (persistent.current_topic or persistent.recent_entities or persistent.last_retrieval_topic):
        return False
    short_follow_up = len(message) <= 14 and any(token in message for token in (_CN_EXPLAIN, _CN_HOW, _CN_COMPARE))
    return short_follow_up
