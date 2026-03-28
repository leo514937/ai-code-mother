from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from ...domain.contracts import (
    AnswerComposeRequest,
    ChatTurnCommand,
    CitationBuildRequest,
    ClarificationCard,
    ClarificationOption,
    ErrorPayload,
    EvidenceEvaluationRequest,
    EvidencePack,
    FinalPayload,
    HybridRetrieveRequest,
    MasteryUpdateCommand,
    PersistSessionCommand,
    RagResult,
    RecommendationQuery,
    ReferenceResolutionRequest,
    QueryRewriteRequest,
    RetrievalPlan,
    SseEnvelope,
    ToolExecutionCommand,
    ToolNormalizationRequest,
    ToolPlanningRequest,
    TurnUnderstandingRequest,
    TurnRuntimeState,
)
from ...domain.enums import IntentType, RagStatus, ToolExecutionStatus, TurnDecision
from ...domain.errors import TerminalEvent, WorkflowErrorCode, build_error
from ...domain.state import GraphState
from ...memory.models import MemoryCapabilityError


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
        understanding = self.container.model_gateway.classify_turn(
            TurnUnderstandingRequest(command=command, persistent=state["persistent"])
        )
        state["turn"] = self._apply_understanding(state["turn"], understanding)
        return state

    def resolve_reference(self, state: GraphState) -> GraphState:
        persistent = state["persistent"]
        resolution = self.container.rag_orchestrator.resolve_reference(
            ReferenceResolutionRequest(
                raw_query=state["turn"].raw_query,
                current_topic=persistent.current_topic,
                recent_entities=list(persistent.recent_entities),
                clarification_result=dict(persistent.clarification_result),
                pending_clarification=persistent.pending_clarification,
                history_summary=persistent.history_summary,
                topic_hint=state["runtime"].topic_hint,
            )
        )
        turn = state["turn"]
        state["turn"] = turn.model_copy(
            update={
                "reference_resolution": resolution,
            }
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
        state["turn"] = turn.model_copy(
            update={
                "decision": TurnDecision.CLARIFY,
                "clarification_card": card,
            }
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
        plan = self.container.rag_orchestrator.rewrite_query(
            QueryRewriteRequest(
                raw_query=state["turn"].raw_query,
                intent=state["turn"].intent,
                requested_output_style=state["turn"].requested_output_style,
                reference_resolution=state["turn"].reference_resolution,
                current_topic=state["persistent"].current_topic,
                topic_hint=state["runtime"].topic_hint,
                user_preferences=dict(state["persistent"].user_preferences),
                base_filters={},
            )
        )
        turn = state["turn"]
        state["turn"] = turn.model_copy(update={"retrieval_plan": plan})
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

        hybrid = self.container.rag_orchestrator.hybrid_retrieve(HybridRetrieveRequest(plan=plan))

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

        evidence = self.container.rag_orchestrator.evaluate_evidence(
            EvidenceEvaluationRequest(
                plan=plan,
                hybrid_recall=hybrid,
                intent=state["turn"].intent,
                requested_output_style=state["turn"].requested_output_style,
            )
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

        citation_list = list(self.container.rag_orchestrator.build_citations(CitationBuildRequest(evidence_pack=evidence)))
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
        state["turn"] = state["turn"].model_copy(
            update={
                "tool_plan": self.container.tool_planner.plan(
                    ToolPlanningRequest(
                        raw_query=state["turn"].raw_query,
                        decision=state["turn"].decision,
                        intent=state["turn"].intent,
                        slots=dict(state["turn"].slots),
                        current_topic=state["persistent"].current_topic,
                    )
                )
            }
        )
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
        raw = self.container.tool_executor.execute(ToolExecutionCommand(selection=plan))
        state["turn"] = state["turn"].model_copy(update={"raw_tool_result": raw})
        return state

    def tool_result_normalizer(self, state: GraphState) -> GraphState:
        raw = state["turn"].raw_tool_result
        if raw is None:
            return state
        normalized = self.container.tool_result_normalizer.normalize(ToolNormalizationRequest(result=raw))
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
        runtime = state["runtime"]
        turn = state["turn"]
        persistent = state["persistent"]
        try:
            result = self.container.memory_service.persist_session(
                PersistSessionCommand(
                    trace_id=runtime.trace_id,
                    session_id=runtime.session_id,
                    turn_id=runtime.turn_id,
                    user_id=runtime.user_id,
                    workflow_version=runtime.workflow_version,
                    raw_query=turn.raw_query,
                    answer_text=turn.final_answer or "",
                    resolved_topic=self._resolved_topic(state),
                    intent=turn.intent,
                    requested_output_style=turn.requested_output_style,
                    tool_name=turn.tool_result.tool_name if turn.tool_result else None,
                    quiz_score=self._extract_quiz_score(state),
                    request_ts=runtime.request_ts,
                    persistent=persistent,
                    final_confidence=float(runtime.metrics.get("final_answer_confidence", 0.0) or 0.0),
                )
            )
        except MemoryCapabilityError as exc:
            return self._record_memory_capability_error(state, exc)
        state["persistent"] = result.updated_context
        memory_updates = result.memory_updates.model_copy(
            update={
                "extra": self._build_mastery_memory_extra(
                    state,
                    result.memory_updates.extra,
                )
            }
        )
        state["runtime"] = runtime.model_copy(
            update={
                "memory_updates": memory_updates,
                "session_persisted": True,
            }
        )
        return state

    def update_mastery(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        turn = state["turn"]
        try:
            result = self.container.memory_service.update_mastery(
                MasteryUpdateCommand(
                    trace_id=runtime.trace_id,
                    session_id=runtime.session_id,
                    user_id=runtime.user_id,
                    turn_id=runtime.turn_id,
                    raw_query=turn.raw_query,
                    answer_text=turn.final_answer or "",
                    resolved_topic=self._resolved_topic(state),
                    intent=turn.intent,
                    requested_output_style=turn.requested_output_style,
                    tool_name=turn.tool_result.tool_name if turn.tool_result else None,
                    quiz_score=self._extract_quiz_score(state),
                    request_ts=runtime.request_ts,
                    persistent=state["persistent"],
                    memory_updates=runtime.memory_updates,
                )
            )
        except MemoryCapabilityError as exc:
            return self._record_memory_capability_error(state, exc)
        metrics = dict(runtime.metrics)
        metrics.update(result.metrics_patch)
        memory_updates = runtime.memory_updates.model_copy(
            update={
                "topic_mastery": dict(result.topic_mastery),
                "semantic_memory": dict(result.semantic_index),
            }
        )
        state["runtime"] = runtime.model_copy(update={"metrics": metrics, "memory_updates": memory_updates})
        return state

    def recommend_next(self, state: GraphState) -> GraphState:
        recommendation = self.container.memory_service.recommend_next(
            RecommendationQuery(
                user_id=state["runtime"].user_id,
                current_topic=self._resolved_topic(state),
                recent_topics=list(state["persistent"].recent_entities),
                user_preferences=dict(state["persistent"].user_preferences),
                active_plan_id=state["persistent"].active_plan_id,
                learning_mode=bool(state["persistent"].learning_mode),
            )
        )
        state["turn"] = state["turn"].model_copy(update={"recommendation": recommendation})
        return state

    def compose_answer(self, state: GraphState) -> GraphState:
        turn = state["turn"]
        result = self.container.answer_composer.compose(
            AnswerComposeRequest(
                raw_query=turn.raw_query,
                requested_output_style=turn.requested_output_style,
                rag_result=turn.rag_result,
                tool_result=turn.tool_result,
                recommendation=turn.recommendation,
            )
        )
        runtime = state["runtime"]
        metrics = dict(runtime.metrics)
        metrics["final_answer_confidence"] = result.confidence
        state["runtime"] = runtime.model_copy(update={"metrics": metrics})
        state["turn"] = turn.model_copy(update={"final_answer": result.answer_text})
        return state

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
        understanding,
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
            }
        )

    def _resolved_topic(self, state: GraphState) -> str | None:
        persistent = state["persistent"]
        turn = state["turn"]
        if turn.reference_resolution and turn.reference_resolution.resolved_entity:
            return turn.reference_resolution.resolved_entity
        slot_topic = turn.slots.get("topic")
        if isinstance(slot_topic, str) and slot_topic.strip():
            return slot_topic.strip()
        if persistent.current_topic:
            return persistent.current_topic
        topic_hint = turn.slots.get("topic_hint") or state["runtime"].topic_hint
        if topic_hint:
            return str(topic_hint)
        return turn.raw_query or None

    def _record_memory_capability_error(
        self,
        state: GraphState,
        exc: MemoryCapabilityError,
    ) -> GraphState:
        runtime = state["runtime"]
        errors = list(runtime.errors)
        errors.append(
            build_error(
                self._coerce_workflow_error_code(exc.code),
                stage=exc.stage,
                message=exc.message,
                retryable=exc.retryable,
                degraded_to=exc.degraded_to,
            )
        )
        state["runtime"] = runtime.model_copy(
            update={
                "errors": errors,
                "degrade_to": exc.degraded_to or runtime.degrade_to,
            }
        )
        return state

    @staticmethod
    def _coerce_workflow_error_code(value: object) -> WorkflowErrorCode:
        if isinstance(value, WorkflowErrorCode):
            return value
        try:
            return WorkflowErrorCode(str(value))
        except ValueError:
            return WorkflowErrorCode.INTERNAL_ERROR

    def _extract_quiz_score(self, state: GraphState) -> float | None:
        tool_result = state["turn"].tool_result
        if tool_result is None or tool_result.tool_name != "generateQuiz":
            return None
        data = tool_result.normalized_output.get("data", {})
        score = data.get("score")
        return float(score) if isinstance(score, (int, float)) else None

    def _build_mastery_memory_extra(
        self,
        state: GraphState,
        current_extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        turn = state["turn"]
        runtime = state["runtime"]
        evidence_count = len(turn.citations)
        if turn.evidence_pack is not None:
            evidence_count = max(evidence_count, len(turn.evidence_pack.items))
        evidence_insufficient = any(
            error.code == WorkflowErrorCode.EVIDENCE_INSUFFICIENT for error in runtime.errors
        )
        extra = dict(current_extra)
        extra.update(
            {
                "evidence_count": evidence_count,
                "was_confused": bool(extra.get("was_confused")) or evidence_insufficient,
                "was_resolved": bool(turn.final_answer) and not evidence_insufficient,
                "reference_resolved": bool(
                    turn.reference_resolution is not None and turn.reference_resolution.resolved
                ),
            }
        )
        return extra

    def _build_final_payload(self, state: GraphState) -> FinalPayload:
        turn = state["turn"]
        persistent = state["persistent"]
        runtime = state["runtime"]
        resolved_topic = persistent.current_topic
        if not resolved_topic and turn.reference_resolution:
            resolved_topic = turn.reference_resolution.resolved_entity
        recommendation = turn.recommendation
        memory_updates = runtime.memory_updates.model_dump(mode="json") if runtime.memory_updates else {}
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
            recommendation=recommendation.model_dump(mode="json") if recommendation is not None else None,
            confidence=final_confidence,
            intent=turn.intent,
            requested_output_style=turn.requested_output_style,
            metrics=runtime.metrics,
        )
