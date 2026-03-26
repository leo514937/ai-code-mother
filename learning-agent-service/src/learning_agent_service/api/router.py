from __future__ import annotations

from typing import Optional

from .compat import APIRouter
from .dependencies import LearningAgentService, UnavailableLearningAgentService
from .routes.chat import register_chat_routes
from .routes.quiz import register_quiz_routes
from .routes.session import register_session_routes
from .routes.study_plan import register_study_plan_routes


def create_api_router(
    service: Optional[LearningAgentService] = None,
) -> APIRouter:
    router = APIRouter()
    bound_service = service or UnavailableLearningAgentService()
    register_chat_routes(router, bound_service)
    register_quiz_routes(router, bound_service)
    register_study_plan_routes(router, bound_service)
    register_session_routes(router, bound_service)
    return router
