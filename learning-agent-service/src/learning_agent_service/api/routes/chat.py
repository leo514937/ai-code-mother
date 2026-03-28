from __future__ import annotations

try:
    from fastapi import Header
except Exception:  # pragma: no cover - compatibility path.
    def Header(default=None, **_: object):
        return default

from ..compat import APIRouter
from ..contracts import ChatStreamRequest
from ..dependencies import LearningAgentService
from ..errors import raise_http_error
from ..internal_auth import verify_internal_token
from ..sse import build_sse_response


def register_chat_routes(router: APIRouter, service: LearningAgentService) -> None:
    @router.post("/internal/v1/chat/stream")
    async def chat_stream(
        request: ChatStreamRequest,
        x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    ):
        verify_internal_token(x_internal_token)
        try:
            events = service.run_stream(request)
        except RuntimeError as exc:
            raise_http_error(exc, status_code=503, default_code="LEARN-5600", stage="chat_stream")
        return build_sse_response(events)
