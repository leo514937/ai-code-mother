from __future__ import annotations

import json
from typing import Iterable, Iterator

from .compat import StreamingResponse
from .contracts import SseEnvelope, validate_event_payload


def build_event_id(session_id: str, turn_id: str, seq: int) -> str:
    return "{session}:{turn}:{seq}".format(session=session_id, turn=turn_id, seq=seq)


def serialize_envelope(envelope: SseEnvelope, seq: int) -> str:
    validated = envelope.model_copy(
        update={"payload": validate_event_payload(envelope.event_type, envelope.payload)}
    )
    body = validated.model_dump(mode="json")
    lines = [
        "id: {event_id}".format(
            event_id=build_event_id(validated.session_id, validated.turn_id, seq),
        ),
        "event: {event_type}".format(event_type=validated.event_type),
        "data: {payload}".format(
            payload=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        ),
        "",
        "",
    ]
    return "\n".join(lines)


def stream_envelopes(events: Iterable[SseEnvelope]) -> Iterator[str]:
    for index, envelope in enumerate(events, start=1):
        yield serialize_envelope(envelope, seq=index)


def build_sse_response(events: Iterable[SseEnvelope]) -> StreamingResponse:
    return StreamingResponse(
        stream_envelopes(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
