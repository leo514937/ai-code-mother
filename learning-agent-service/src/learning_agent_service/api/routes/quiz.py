from __future__ import annotations

from ..compat import APIRouter
from ..contracts import QuizGenerateRequest, QuizGenerateResponse
from ..dependencies import LearningAgentService
from ..errors import raise_http_error
from ..internal_auth import internal_token_header, require_internal_token


def register_quiz_routes(router: APIRouter, service: LearningAgentService) -> None:
    @router.post("/internal/v1/quiz/generate")
    async def generate_quiz(
        request: QuizGenerateRequest,
        x_internal_token: str | None = internal_token_header(),
    ) -> QuizGenerateResponse:
        require_internal_token(x_internal_token)
        try:
            return service.generate_quiz(request)
        except RuntimeError as exc:
            raise_http_error(exc, status_code=503, default_code="LEARN-5300", stage="quiz_generate")
