from __future__ import annotations

from ..compat import APIRouter, HTTPException
from ..contracts import QuizGenerateRequest, QuizGenerateResponse
from ..dependencies import LearningAgentService


def register_quiz_routes(router: APIRouter, service: LearningAgentService) -> None:
    @router.post("/internal/v1/quiz/generate")
    async def generate_quiz(request: QuizGenerateRequest) -> QuizGenerateResponse:
        try:
            return service.generate_quiz(request)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
