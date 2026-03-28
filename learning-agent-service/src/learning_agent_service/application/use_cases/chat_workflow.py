from __future__ import annotations

from typing import Iterable, Optional

from learning_agent_service.application.workflow import (
    RagSubgraphServices,
    ToolSubgraphServices,
    UnderstandTurnServices,
    WorkflowServices,
    create_workflow_runner,
)
from learning_agent_service.application.workflow.adapters import WorkflowNodeAdapter
from learning_agent_service.domain import ChatTurnCommand, PersistentSessionContext, SseEnvelope


class ChatWorkflowService:
    def __init__(self, container) -> None:
        self._container = container
        self._nodes = WorkflowNodeAdapter(container)
        self._workflow_runner = create_workflow_runner(
            services=self._build_workflow_services(),
            prefer_langgraph=True,
            workflow_version=container.settings.workflow_version,
        )

    def run(
        self,
        command: ChatTurnCommand,
        persistent_context: Optional[PersistentSessionContext] = None,
    ) -> Iterable[SseEnvelope]:
        persistent = persistent_context or self._container.session_context_store.load(
            command.session_id,
            command.user_id,
        )
        return self._workflow_runner.run_stream(command=command, persistent_context=persistent)

    def _build_workflow_services(self) -> WorkflowServices:
        return WorkflowServices(
            load_context=self._nodes.load_context,
            understand_turn=UnderstandTurnServices(
                parse_intent_slots=self._nodes.parse_intent_slots,
                resolve_reference=self._nodes.resolve_reference,
                ambiguity_check=self._nodes.ambiguity_check,
                rewrite_query=self._nodes.rewrite_query,
            ),
            rag_subgraph=RagSubgraphServices(
                hybrid_retrieve=self._nodes.hybrid_retrieve,
                evaluate_evidence=self._nodes.evaluate_evidence,
                citation_builder=self._nodes.citation_builder,
            ),
            tool_subgraph=ToolSubgraphServices(
                tool_planner=self._nodes.tool_planner,
                tool_executor=self._nodes.tool_executor,
                tool_result_normalizer=self._nodes.tool_result_normalizer,
            ),
            compose_answer=self._nodes.compose_answer,
            persist_session=self._nodes.persist_session,
            update_mastery=self._nodes.update_mastery,
            recommend_next=self._nodes.recommend_next,
            emit_final=self._nodes.emit_final,
        )
