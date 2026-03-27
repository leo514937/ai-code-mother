from __future__ import annotations

from ..compat import APIRouter
from ..contracts import StudyPlanGenerateRequest, StudyPlanGenerateResponse
from ..dependencies import LearningAgentService
from ..errors import raise_http_error


def register_study_plan_routes(router: APIRouter, service: LearningAgentService) -> None:
    @router.post("/internal/v1/study-plan/generate")
    async def generate_study_plan(
        request: StudyPlanGenerateRequest,
    ) -> StudyPlanGenerateResponse:
        try:
            return service.generate_study_plan(request)
        except RuntimeError as exc:
            raise_http_error(
                exc,
                status_code=503,
                default_code="LEARN-5300",
                stage="study_plan_generate",
            )
