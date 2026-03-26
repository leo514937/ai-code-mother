from __future__ import annotations

from typing import Iterable, Protocol

from .contracts import (
    ChatStreamRequest,
    QuizGenerateRequest,
    QuizGenerateResponse,
    SessionStateResponse,
    SseEnvelope,
    StudyPlanGenerateRequest,
    StudyPlanGenerateResponse,
)


class LearningAgentService(Protocol):
    def run_stream(self, request: ChatStreamRequest) -> Iterable[SseEnvelope]:
        ...

    def generate_quiz(self, request: QuizGenerateRequest) -> QuizGenerateResponse:
        ...

    def generate_study_plan(
        self,
        request: StudyPlanGenerateRequest,
    ) -> StudyPlanGenerateResponse:
        ...

    def get_session_state(self, session_id: str) -> SessionStateResponse:
        ...


class UnavailableLearningAgentService:
    def _raise(self) -> None:
        raise RuntimeError("Learning agent service is not configured.")

    def run_stream(self, request: ChatStreamRequest) -> Iterable[SseEnvelope]:
        self._raise()
        return []

    def generate_quiz(self, request: QuizGenerateRequest) -> QuizGenerateResponse:
        self._raise()
        raise AssertionError("unreachable")

    def generate_study_plan(
        self,
        request: StudyPlanGenerateRequest,
    ) -> StudyPlanGenerateResponse:
        self._raise()
        raise AssertionError("unreachable")

    def get_session_state(self, session_id: str) -> SessionStateResponse:
        self._raise()
        raise AssertionError("unreachable")
