from __future__ import annotations

from datetime import datetime

from ..compat import APIRouter
from ..contracts import ChatStreamRequest, ErrorPayload, EventType, SseEnvelope
from ..dependencies import LearningAgentService
from ..sse import build_sse_response


WORKFLOW_VERSION = "learn-agent/v1"


def _build_service_error(request: ChatStreamRequest, message: str) -> SseEnvelope:
    payload = ErrorPayload(
        code="LEARN-5600",
        message=message,
        retryable=False,
        stage="chat_stream",
    ).model_dump(mode="json")
    return SseEnvelope(
        event_type=EventType.ERROR,
        trace_id=request.trace_id,
        session_id=request.session_id,
        turn_id=request.turn_id or "turn-unknown",
        timestamp=datetime.utcnow(),
        workflow_version=WORKFLOW_VERSION,
        payload=payload,
    )


def register_chat_routes(router: APIRouter, service: LearningAgentService) -> None:
    @router.post("/internal/v1/chat/stream")
    async def chat_stream(request: ChatStreamRequest):
        try:
            events = service.run_stream(request)
        except RuntimeError as exc:
            events = [_build_service_error(request, str(exc))]
        return build_sse_response(events)
