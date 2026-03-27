from __future__ import annotations

from ..compat import APIRouter
from ..contracts import SessionStateResponse
from ..dependencies import LearningAgentService
from ..errors import raise_http_error


def register_session_routes(router: APIRouter, service: LearningAgentService) -> None:
    @router.get("/internal/v1/session/{session_id}/state")
    async def get_session_state(session_id: str) -> SessionStateResponse:
        try:
            return service.get_session_state(session_id)
        except RuntimeError as exc:
            raise_http_error(exc, status_code=503, default_code="LEARN-5600", stage="session_state")
