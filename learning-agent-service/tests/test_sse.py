from __future__ import annotations

import unittest
from datetime import datetime

import _bootstrap  # noqa: F401

from learning_agent_service.api.contracts import EventType, SseEnvelope
from learning_agent_service.api.sse import build_event_id, serialize_envelope, stream_envelopes


class SseEncodingTestCase(unittest.TestCase):
    def _envelope(self) -> SseEnvelope:
        return SseEnvelope(
            event_type=EventType.FINAL,
            trace_id="trace-1",
            session_id="session-1",
            turn_id="turn-1",
            timestamp=datetime(2026, 3, 27, 12, 0, 0),
            workflow_version="learn-agent/v1",
            payload={
                "answer_text": "ok",
                "citations": [],
                "used_tools": [],
                "confidence": 0.8,
                "memory_updates": {},
                "metrics": {},
            },
        )

    def test_build_event_id(self) -> None:
        self.assertEqual(build_event_id("s1", "t1", 3), "s1:t1:3")

    def test_serialize_envelope(self) -> None:
        payload = serialize_envelope(self._envelope(), seq=2)
        self.assertIn("id: session-1:turn-1:2", payload)
        self.assertIn("event: final", payload)
        self.assertIn('"workflow_version":"learn-agent/v1"', payload)

    def test_stream_envelopes_preserves_order(self) -> None:
        chunks = list(stream_envelopes([self._envelope(), self._envelope()]))
        self.assertEqual(len(chunks), 2)
        self.assertIn("session-1:turn-1:1", chunks[0])
        self.assertIn("session-1:turn-1:2", chunks[1])
