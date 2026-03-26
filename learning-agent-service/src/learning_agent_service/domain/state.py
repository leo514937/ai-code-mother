from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional, TypedDict

from .contracts import ChatTurnCommand, GraphRuntimeMeta, PersistentSessionContext, TurnRuntimeState


class GraphState(TypedDict):
    persistent: PersistentSessionContext
    turn: TurnRuntimeState
    runtime: GraphRuntimeMeta


def build_initial_state(
    command: ChatTurnCommand,
    workflow_version: str = "learn-agent/v1",
    persistent: Optional[PersistentSessionContext] = None,
) -> GraphState:
    request_ts = datetime.now(timezone.utc).isoformat()
    return GraphState(
        persistent=persistent or PersistentSessionContext(),
        turn=TurnRuntimeState(raw_query=command.message),
        runtime=GraphRuntimeMeta(
            trace_id=command.trace_id,
            session_id=command.session_id,
            turn_id=command.turn_id,
            extra={
                "request_ts": request_ts,
                "workflow_version": workflow_version,
                "user_id": command.user_id,
                "response_mode": command.response_mode.value if command.response_mode else None,
                "topic_hint": command.topic_hint,
                "client_context": command.client_context,
            },
        ),
    )


def clone_graph_state(state: GraphState) -> GraphState:
    return deepcopy(state)
