from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from ...domain.contracts import (
    ChatTurnCommand,
    Citation,
    ClarificationCard,
    ClarificationOption,
    ErrorPayload,
    EvidencePack,
    FinalPayload,
    GraphRuntimeMeta,
    HybridRecallCandidate,
    HybridRecallResult,
    RagResult,
    RetrievalPlan,
    SseEnvelope,
    ToolExecutionResult,
    TurnRuntimeState,
    TurnUnderstandingResult,
)
from ...domain.enums import IntentType, RagStatus, ToolExecutionStatus, TurnDecision
from ...domain.errors import TerminalEvent, WorkflowErrorCode, build_error
from ...domain.state import GraphState, clone_graph_state


class WorkflowNodeAdapter:
    def __init__(self, container) -> None:
        self.container = container

    def load_context(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        loaded = self.container.session_context_store.load(runtime.session_id, runtime.user_id)
        state["persistent"] = loaded.model_copy(
            update={
                "history_summary": loaded.history_summary or runtime.history_summary,
            }
        )
        return state

    def parse_intent_slots(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        command = ChatTurnCommand(
            trace_id=runtime.trace_id,
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            user_id=runtime.user_id,
            message=state["turn"].raw_query,
            response_mode=runtime.response_mode,
            topic_hint=runtime.topic_hint,
            history_summary=runtime.history_summary,
            client_context=runtime.client_context,
        )
        understanding = self.container.model_gateway.classify_turn(command, state)
        state["turn"] = self._apply_understanding(state["turn"], understanding)
        return state

    def resolve_reference(self, state: GraphState) -> GraphState:
        resolver = getattr(self.container.rag_orchestrator, "resolve_reference", None)
        if not callable(resolver):
            return state
        resolution = resolver(state)
        turn = state["turn"]
        state["turn"] = self._apply_understanding(
            turn,
            (turn.understanding_result or TurnUnderstandingResult()).model_copy(
                update={"reference_resolution": resolution}
            ),
        )
        return state

    def ambiguity_check(self, state: GraphState) -> GraphState:
        turn = state["turn"]
        low_intent = turn.intent_confidence < 0.5
        low_reference = turn.intent == IntentType.FOLLOW_UP and (
            turn.reference_resolution is None or turn.reference_resolution.confidence < 0.5
        )
        if not low_intent and not low_reference:
            return state

        card = ClarificationCard(
            card_id="clarify-{turn_id}".format(turn_id=state["runtime"].turn_id),
            question="Which topic do you want to continue with?",
            options=self._build_clarification_options(state),
            ambiguity_type="intent" if low_intent else "reference",
            source_turn_id=state["runtime"].turn_id,
        )
        state["turn"] = self._apply_understanding(
            turn,
            (turn.understanding_result or TurnUnderstandingResult()).model_copy(
                update={
                    "decision": TurnDecision.CLARIFY,
                    "clarification_card": card,
                }
            ),
        )
        return state

    def _build_clarification_options(self, state: GraphState) -> List[ClarificationOption]:
        turn = state["turn"]
        runtime = state["runtime"]
        persistent = state["persistent"]

        options: List[ClarificationOption] = []
        seen_values: List[str] = []

        def add_option(
            *,
            option_id: str,
            label: str,
            value: str,
            description: str | None = None,
        ) -> None:
            normalized_value = (value or "").strip()
            normalized_label = (label or "").strip()
            if not normalized_value or not normalized_label or normalized_value in seen_values:
                return
            seen_values.append(normalized_value)
            options.append(
                ClarificationOption(
                    id=option_id,
                    label=normalized_label,
                    value=normalized_value,
                    description=description,
                )
            )

        if turn.reference_resolution:
            for index, candidate in enumerate(turn.reference_resolution.candidate_entities, start=1):
                add_option(
                    option_id="candidate-{index}".format(index=index),
                    label=candidate,
                    value=candidate,
                    description="Continue with a candidate topic inferred from recent context.",
                )

        if persistent.current_topic:
            add_option(
                option_id="current-topic",
                label=persistent.current_topic,
                value=persistent.current_topic,
                description="Continue with the latest confirmed topic in this session.",
            )

        for index, entity in enumerate(persistent.recent_entities, start=1):
            add_option(
                option_id="recent-{index}".format(index=index),
                label=entity,
                value=entity,
                description="Continue with a recently discussed topic.",
            )

        topic_hint = runtime.topic_hint or turn.slots.get("topic_hint")
        if topic_hint:
            add_option(
                option_id="topic-hint",
                label=str(topic_hint),
                value=str(topic_hint),
                description="Use the topic hint attached to this turn.",
            )

        if len(options) < 3:
            fallback_value = topic_hint or persistent.current_topic or turn.raw_query
            if fallback_value:
                add_option(
                    option_id="current-message",
                    label="Use my current question as the topic",
                    value=str(fallback_value),
                    description="Retry topic resolution from the latest message you just sent.",
                )

        if len(options) < 3:
            add_option(
                option_id="specify-topic",
                label="I will specify the exact topic",
                value="__specify_topic__",
                description="Reply with a concrete topic such as Spring AOP, ReAct, or Java thread pool.",
            )

        return options[:3]

    def rewrite_query(self, state: GraphState) -> GraphState:
        plan = self.container.rag_orchestrator.rewrite_query(state)
        turn = state["turn"]
        state["turn"] = self._apply_understanding(
            turn.model_copy(update={"retrieval_plan": plan}),
            (turn.understanding_result or TurnUnderstandingResult()).model_copy(
                update={"retrieval_plan": plan}
            ),
        )
        return state

    def hybrid_retrieve(self, state: GraphState) -> GraphState:
        plan = state["turn"].retrieval_plan
        if plan is None:
            return state
        state = self._append_event(
            state,
            event_type="retrieval_started",
            payload={
                "semantic_query": plan.semantic_query,
                "keyword_query": plan.keyword_query,
                "retrieval_filters": dict(plan.retrieval_filters),
            },
        )

        orchestrator = self.container.rag_orchestrator
        if callable(getattr(orchestrator, "hybrid_retrieve", None)):
            hybrid = orchestrator.hybrid_retrieve(state)
        else:
            hybrid = self._legacy_hybrid_retrieve(orchestrator, plan)

        runtime = state["runtime"]
        metrics = dict(runtime.metrics)
        metrics.update(hybrid.metrics)
        state["runtime"] = runtime.model_copy(update={"metrics": metrics})
        state["turn"] = state["turn"].model_copy(update={"hybrid_recall": hybrid})
        return state

    def evaluate_evidence(self, state: GraphState) -> GraphState:
        plan = state["turn"].retrieval_plan
        hybrid = state["turn"].hybrid_recall
        if plan is None or hybrid is None:
            empty = EvidencePack()
            state["turn"] = state["turn"].model_copy(
                update={
                    "evidence_pack": empty,
                    "rag_result": RagResult(status=RagStatus.EMPTY, evidence_pack=empty),
                }
            )
            return state

        orchestrator = self.container.rag_orchestrator
        evidence = None
        evaluator = getattr(orchestrator, "evaluate_evidence", None)
        if callable(evaluator):
            evidence = evaluator(state)
        elif callable(getattr(orchestrator, "_evaluate_evidence", None)):
            evidence = orchestrator._evaluate_evidence(
                plan,
                [candidate.raw for candidate in hybrid.reranked_hits],
            )

        evidence = evidence if isinstance(evidence, EvidencePack) else EvidencePack()
        retrieval_strategy = "dense+sparse+metadata->rrf->rerank->evidence"
        status = RagStatus.EMPTY
        if evidence.items:
            status = RagStatus.OK if len(evidence.items) >= 4 else RagStatus.DEGRADED

        runtime = state["runtime"]
        metrics = dict(runtime.metrics)
        metrics.setdefault("retrieval_hit_count", len(hybrid.reranked_hits))
        metrics["evidence_used_count"] = len(evidence.items)
        errors = list(runtime.errors)
        if not evidence.items:
            errors.append(
                build_error(
                    WorkflowErrorCode.EVIDENCE_INSUFFICIENT,
                    stage="evaluate_evidence",
                    message="No stable evidence survived the governance pipeline.",
                    degraded_to="direct_answer_lite",
                )
            )
        state["runtime"] = runtime.model_copy(update={"metrics": metrics, "errors": errors})
        state["turn"] = state["turn"].model_copy(
            update={
                "evidence_pack": evidence,
                "rag_result": RagResult(
                    status=status,
                    evidence_pack=evidence,
                    citations=list(state["turn"].citations),
                    retrieval_strategy=retrieval_strategy,
                    metrics=dict(metrics),
                ),
            }
        )
        return self._append_event(
            state,
            event_type="retrieval_result",
            payload={
                "retrieval_strategy": retrieval_strategy,
                "retrieval_hit_count": int(metrics.get("retrieval_hit_count", 0)),
                "evidence_used_count": int(metrics.get("evidence_used_count", 0)),
            },
        )

    def citation_builder(self, state: GraphState) -> GraphState:
        evidence = state["turn"].evidence_pack
        if evidence is None:
            return state

        orchestrator = self.container.rag_orchestrator
        citations: Iterable[Citation]
        if callable(getattr(orchestrator, "build_citations_from_pack", None)):
            citations = orchestrator.build_citations_from_pack(evidence)
        elif callable(getattr(orchestrator, "build_citations", None)):
            bridge_state = clone_graph_state(state)
            bridge_state["turn"] = bridge_state["turn"].model_copy(
                update={"rag_result": RagResult(evidence_pack=evidence)}
            )
            citations = orchestrator.build_citations(bridge_state)
        else:
            citation_fallback: List[Citation] = []
            for item in evidence.items:
                citation_fallback.append(
                    Citation(
                        chunk_id=item.chunk_id,
                        document_id=item.document_id,
                        source_type=item.metadata.get("source_type"),
                        version=item.metadata.get("version"),
                        score=item.score,
                        title=item.metadata.get("topic"),
                        locator=item.metadata.get("category"),
                    )
                )
            citations = citation_fallback

        citation_list = list(citations)
        rag_result = state["turn"].rag_result or RagResult(
            status=RagStatus.EMPTY,
            evidence_pack=evidence,
        )
        state["turn"] = state["turn"].model_copy(
            update={
                "citations": citation_list,
                "rag_result": rag_result.model_copy(update={"citations": citation_list}),
            }
        )
        return state

    def tool_planner(self, state: GraphState) -> GraphState:
        state["turn"] = state["turn"].model_copy(update={"tool_plan": self.container.tool_planner.plan(state)})
        return state

    def tool_executor(self, state: GraphState) -> GraphState:
        plan = state["turn"].tool_plan
        if plan is None:
            return state
        state = self._append_event(
            state,
            event_type="tool_call",
            payload={
                "tool_name": plan.tool_name or "",
                "tool_call_id": str((plan.extra or {}).get("tool_call_id") or "tool-call"),
                "input_summary": dict(plan.input_payload),
            },
        )
        raw = self.container.tool_executor.execute(plan, state)
        state["turn"] = state["turn"].model_copy(update={"raw_tool_result": raw})
        return state

    def tool_result_normalizer(self, state: GraphState) -> GraphState:
        raw = state["turn"].raw_tool_result
        if raw is None:
            return state
        normalized = self.container.tool_result_normalizer.normalize(raw, state)
        state["turn"] = state["turn"].model_copy(update={"tool_result": normalized})
        tool_plan = state["turn"].tool_plan
        return self._append_event(
            state,
            event_type="tool_result",
            payload={
                "tool_name": normalized.tool_name or "",
                "tool_call_id": str(((tool_plan.extra or {}).get("tool_call_id") if tool_plan else None) or "tool-call"),
                "status": normalized.status.value,
                "degraded": bool(normalized.extra.get("degraded")),
                "retryable": bool(normalized.extra.get("retryable")),
                "error_code": normalized.extra.get("errors", {}).get("code"),
                "error_message": normalized.extra.get("errors", {}).get("message"),
                "degraded_to": normalized.extra.get("degrade_to"),
                "output": dict(normalized.normalized_output),
            },
        )

    def persist_session(self, state: GraphState) -> GraphState:
        return self._call_legacy_memory_handler(self.container.memory_service.persist_session, state)

    def update_mastery(self, state: GraphState) -> GraphState:
        return self._call_legacy_memory_handler(self.container.memory_service.update_mastery, state)

    def recommend_next(self, state: GraphState) -> GraphState:
        return self._call_legacy_memory_handler(self.container.memory_service.recommend_next, state)

    def emit_final(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        terminal = runtime.terminal_event
        if terminal is None:
            terminal = (
                TerminalEvent.CLARIFICATION_CARD
                if state["turn"].decision == TurnDecision.CLARIFY
                else TerminalEvent.FINAL
            )

        if terminal == TerminalEvent.ERROR:
            last_error = runtime.errors[-1] if runtime.errors else build_error(
                WorkflowErrorCode.INTERNAL_ERROR,
                stage="emit_final",
                message="Unknown workflow error",
                is_terminal=True,
            )
            payload = ErrorPayload(
                code=last_error.code.value,
                message=last_error.message,
                retryable=last_error.retryable,
                stage=last_error.stage,
                degraded_to=last_error.degraded_to,
                details=last_error.details,
            ).model_dump(mode="json")
            event_type = TerminalEvent.ERROR.value
        elif terminal == TerminalEvent.CLARIFICATION_CARD:
            payload = (
                state["turn"].clarification_card.model_dump(mode="json")
                if state["turn"].clarification_card is not None
                else {}
            )
            event_type = TerminalEvent.CLARIFICATION_CARD.value
        else:
            payload = self._build_final_payload(state).model_dump(mode="json")
            event_type = TerminalEvent.FINAL.value

        envelope = SseEnvelope(
            event_type=event_type,
            trace_id=runtime.trace_id,
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            timestamp=datetime.now(timezone.utc),
            workflow_version=runtime.workflow_version,
            payload=payload,
        )
        state["runtime"] = runtime.model_copy(
            update={
                "terminal_event": terminal,
                "emitted_events": list(runtime.emitted_events) + [envelope],
            }
        )
        return state

    def _append_event(self, state: GraphState, event_type: str, payload: Dict[str, Any]) -> GraphState:
        runtime = state["runtime"]
        envelope = SseEnvelope(
            event_type=event_type,
            trace_id=runtime.trace_id,
            session_id=runtime.session_id,
            turn_id=runtime.turn_id,
            timestamp=datetime.now(timezone.utc),
            workflow_version=runtime.workflow_version,
            payload=payload,
        )
        state["runtime"] = runtime.model_copy(
            update={"emitted_events": list(runtime.emitted_events) + [envelope]}
        )
        return state

    def _apply_understanding(
        self,
        turn: TurnRuntimeState,
        understanding: TurnUnderstandingResult,
    ) -> TurnRuntimeState:
        return turn.model_copy(
            update={
                "decision": understanding.decision,
                "intent": understanding.intent,
                "intent_confidence": understanding.intent_confidence,
                "requested_output_style": understanding.requested_output_style,
                "reference_resolution": understanding.reference_resolution,
                "retrieval_plan": turn.retrieval_plan or understanding.retrieval_plan,
                "clarification_card": understanding.clarification_card,
                "slots": dict(understanding.slots),
                "understanding_result": understanding,
            }
        )

    def _legacy_hybrid_retrieve(self, orchestrator, plan: RetrievalPlan) -> HybridRecallResult:
        dense_hits = self._convert_hits(orchestrator._dense_retrieve(plan))
        sparse_hits = self._convert_hits(orchestrator._sparse_retrieve(plan))
        metadata_hits = self._convert_hits(orchestrator._metadata_retrieve(plan))
        fused_hits = self._convert_hits(
            orchestrator._rrf_merge(
                [
                    [candidate.raw for candidate in dense_hits],
                    [candidate.raw for candidate in sparse_hits],
                    [candidate.raw for candidate in metadata_hits],
                ],
                getattr(self.container.settings, "rrf_k", 60),
            )
        )
        reranked_hits = self._convert_hits(
            orchestrator._rerank(plan, [candidate.raw for candidate in fused_hits])
        )
        metrics = {
            "dense_hit_count": len(dense_hits),
            "sparse_hit_count": len(sparse_hits),
            "metadata_hit_count": len(metadata_hits),
            "retrieval_hit_count": len(reranked_hits),
            "retrieval_top_score": reranked_hits[0].score if reranked_hits else 0.0,
        }
        return HybridRecallResult(
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            metadata_hits=metadata_hits,
            fused_hits=fused_hits,
            reranked_hits=reranked_hits,
            metrics=metrics,
        )

    def _convert_hits(self, hits: Iterable[Dict[str, Any]]) -> List[HybridRecallCandidate]:
        candidates: List[HybridRecallCandidate] = []
        for item in hits:
            channels = item.get("channels") or ([item["channel"]] if item.get("channel") else [])
            candidates.append(
                HybridRecallCandidate(
                    chunk_id=item["chunk_id"],
                    score=float(item.get("score", 0.0)),
                    content=item.get("content"),
                    document_id=item.get("topic"),
                    chunk_type=item.get("chunk_type"),
                    metadata={
                        "topic": item.get("topic"),
                        "category": item.get("category"),
                        "subcategory": item.get("subcategory"),
                        "source_type": item.get("source_type"),
                        "version": item.get("version"),
                    },
                    channels=list(channels),
                    raw=dict(item),
                )
            )
        return candidates

    def _call_legacy_memory_handler(self, handler, state: GraphState) -> GraphState:
        compat_state = clone_graph_state(state)
        compat_state["runtime"] = self._legacy_runtime_meta(compat_state["runtime"])
        updated = handler(compat_state)
        runtime = state["runtime"]
        updated_runtime = updated["runtime"]
        runtime_extra = dict(runtime.extra)
        for key in ("memory_updates", "session_persisted"):
            if key in updated_runtime.extra:
                runtime_extra[key] = updated_runtime.extra[key]
        state["persistent"] = updated["persistent"]
        turn_extra = dict(state["turn"].extra)
        turn_extra.update(updated["turn"].extra)
        state["turn"] = state["turn"].model_copy(update={"extra": turn_extra})
        state["runtime"] = runtime.model_copy(
            update={
                "metrics": updated_runtime.metrics,
                "errors": updated_runtime.errors,
                "degrade_to": updated_runtime.degrade_to,
                "extra": runtime_extra,
            }
        )
        return state

    def _legacy_runtime_meta(self, runtime: GraphRuntimeMeta) -> GraphRuntimeMeta:
        extra = dict(runtime.extra)
        extra.update(
            {
                "user_id": runtime.user_id,
                "response_mode": runtime.response_mode.value if runtime.response_mode else None,
                "topic_hint": runtime.topic_hint,
                "history_summary": runtime.history_summary,
                "client_context": dict(runtime.client_context),
                "workflow_version": runtime.workflow_version,
                "request_ts": runtime.request_ts.isoformat(),
            }
        )
        return runtime.model_copy(update={"extra": extra})

    def _build_final_payload(self, state: GraphState) -> FinalPayload:
        turn = state["turn"]
        persistent = state["persistent"]
        runtime = state["runtime"]
        resolved_topic = persistent.current_topic
        if not resolved_topic and turn.reference_resolution:
            resolved_topic = turn.reference_resolution.resolved_entity
        recommendation = turn.extra.get("recommendation")
        memory_updates = runtime.extra.get("memory_updates", {})
        final_confidence = runtime.metrics.get("final_answer_confidence", 0.0)
        rag_result = turn.rag_result
        tool_result = turn.tool_result
        return FinalPayload(
            answer_text=turn.final_answer or "",
            citations=list(turn.citations or (rag_result.citations if rag_result else [])),
            used_tools=tool_result.used_tools if tool_result is not None else [],
            resolved_topic=resolved_topic,
            retrieval_strategy=rag_result.retrieval_strategy if rag_result is not None else None,
            memory_updates=memory_updates,
            recommendation=recommendation,
            confidence=final_confidence,
            intent=turn.intent,
            requested_output_style=turn.requested_output_style,
            metrics=runtime.metrics,
        )
