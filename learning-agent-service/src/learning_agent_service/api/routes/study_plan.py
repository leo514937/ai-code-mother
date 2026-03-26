from __future__ import annotations

from ..compat import APIRouter, HTTPException
from ..contracts import StudyPlanGenerateRequest, StudyPlanGenerateResponse
from ..dependencies import LearningAgentService


def register_study_plan_routes(router: APIRouter, service: LearningAgentService) -> None:
    @router.post("/internal/v1/study-plan/generate")
    async def generate_study_plan(
        request: StudyPlanGenerateRequest,
    ) -> StudyPlanGenerateResponse:
        try:
            return service.generate_study_plan(request)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
