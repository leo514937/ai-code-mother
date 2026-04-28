from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from learning_agent_service.config import Settings
from learning_agent_service.domain import (
    AnswerComposeRequest,
    AnswerComposeResult,
    NormalizedToolResult,
    SseEnvelope,
    ToolExecutionCommand,
    ToolExecutionResult,
    ToolNormalizationRequest,
    ToolPlanningRequest,
    ToolSelection,
)
from learning_agent_service.domain.enums import IntentType, OutputStyle, ToolExecutionStatus, TurnDecision

from .builtin import build_builtin_tool_registry
from .executor import ToolExecutor as BaseToolExecutor
from .models import ToolExecutionResult as BaseExecutionResult
from .models import ToolSelection as BaseToolSelection
from .normalizer import ToolResultNormalizer as BaseToolResultNormalizer
from .planner import ToolPlanner as BaseToolPlanner
from .registry import ToolRegistry


def build_default_tool_registry(
    *,
    search_knowledge_fn=None,
    get_knowledge_detail_fn=None,
) -> ToolRegistry:
    return build_builtin_tool_registry(
        search_knowledge_fn=search_knowledge_fn,
        get_knowledge_detail_fn=get_knowledge_detail_fn,
    )


def _run_async_safely(coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: Dict[str, Any] = {}
    error: Dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # pragma: no cover
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


def _map_status(result: BaseExecutionResult) -> ToolExecutionStatus:
    if result.status == "ok":
        return ToolExecutionStatus.SUCCESS
    if result.degraded:
        return ToolExecutionStatus.DEGRADED
    return ToolExecutionStatus.FAILED


@dataclass
class ToolPlanner:
    planner: BaseToolPlanner | None = None

    def __post_init__(self) -> None:
        if self.planner is None:
            self.planner = BaseToolPlanner(
                {
                    "quiz": "generateQuiz",
                    "study_plan": "generateStudyPlan",
                    "recommend": "recommendNextTopic",
                    "knowledge": "searchKnowledge",
                    "detail": "getKnowledgeDetail",
                    "save_record": "saveLearningRecord",
                }
            )

    def plan(self, request: ToolPlanningRequest) -> ToolSelection:
        need_tool = request.decision == TurnDecision.TOOL_THEN_ANSWER or request.decision == "tool_then_answer"
        slots = dict(request.slots)
        slots.setdefault("topic", request.current_topic or request.raw_query)
        slots.setdefault("tool_input", {"topic": slots.get("topic")})
        mapped_intent = {
            IntentType.QUIZ.value: "quiz",
            IntentType.STUDY_PLAN.value: "study_plan",
            IntentType.RECOMMEND.value: "recommend",
            IntentType.FOLLOW_UP.value: "detail",
        }.get(request.intent.value if request.intent is not None else "", request.intent.value if request.intent else None)
        selection = self.planner.plan(mapped_intent, need_tool, slots)
        if selection is None:
            return ToolSelection(should_execute=False)
        return ToolSelection(
            tool_name=selection.tool_name,
            should_execute=True,
            input_payload=selection.input_payload,
            reason=selection.reason,
            extra={
                "tool_call_id": str(uuid.uuid4()),
                "timeout_ms": selection.timeout_ms,
                "degrade_to": selection.degrade_to,
            },
        )

    def plan_from_name(self, tool_name: str, input_payload: Dict[str, Any]) -> ToolSelection:
        return ToolSelection(
            tool_name=tool_name,
            should_execute=True,
            input_payload=input_payload,
            reason="direct-endpoint",
            extra={"tool_call_id": str(uuid.uuid4())},
        )


@dataclass
class ToolExecutor:
    search_knowledge_fn: Any = None
    get_knowledge_detail_fn: Any = None
    registry: ToolRegistry | None = None
    executor: BaseToolExecutor | None = None

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = build_default_tool_registry(
                search_knowledge_fn=self.search_knowledge_fn,
                get_knowledge_detail_fn=self.get_knowledge_detail_fn,
            )
        if self.executor is None:
            self.executor = BaseToolExecutor(self.registry)

    def execute(self, command: ToolExecutionCommand) -> ToolExecutionResult:
        selection = command.selection
        if not selection.tool_name or not selection.should_execute:
            return ToolExecutionResult(status=ToolExecutionStatus.SKIPPED)

        base_selection = BaseToolSelection(
            tool_name=selection.tool_name,
            input_payload=selection.input_payload,
            reason=selection.reason,
            degrade_to=(selection.extra or {}).get("degrade_to"),
            timeout_ms=(selection.extra or {}).get("timeout_ms"),
        )
        result = _run_async_safely(self.executor.execute(base_selection))
        extra = {
            "tool_call_id": (selection.extra or {}).get("tool_call_id"),
            "error_code": result.error_code,
            "error_message": result.error_message,
            "retryable": result.retryable,
            "degraded": result.degraded,
            "degrade_to": result.degrade_to,
            "duration_ms": result.duration_ms,
        }
        return ToolExecutionResult(
            status=_map_status(result),
            tool_name=selection.tool_name,
            output_payload=result.output,
            extra=extra,
        )


@dataclass
class ToolResultNormalizer:
    normalizer: BaseToolResultNormalizer | None = None

    def __post_init__(self) -> None:
        if self.normalizer is None:
            self.normalizer = BaseToolResultNormalizer()

    def normalize(self, request: ToolNormalizationRequest) -> NormalizedToolResult:
        result = request.result
        extra = dict(result.extra)
        payload = BaseExecutionResult(
            tool_name=result.tool_name or "",
            status="ok" if result.status == ToolExecutionStatus.SUCCESS else "failed",
            output=result.output_payload,
            error_code=extra.get("error_code"),
            error_message=extra.get("error_message"),
            retryable=bool(extra.get("retryable")),
            degraded=bool(extra.get("degraded")) or result.status == ToolExecutionStatus.DEGRADED,
            degrade_to=extra.get("degrade_to"),
            duration_ms=int(extra.get("duration_ms") or 0),
        )
        normalized = self.normalizer.normalize(payload)
        normalized_status = ToolExecutionStatus.SUCCESS if normalized.ok else result.status
        used_tools = [normalized.tool_name] if normalized.tool_name else []
        return NormalizedToolResult(
            status=normalized_status,
            tool_name=normalized.tool_name,
            normalized_output=normalized.payload,
            used_tools=used_tools,
            extra={
                "errors": normalized.errors,
                "degraded": normalized.degraded,
                "retryable": normalized.retryable,
                "degrade_to": normalized.degrade_to,
            },
        )


@dataclass
class AnswerComposer:
    llm_answerer: Optional[Callable[[AnswerComposeRequest], Mapping[str, Any] | str]] = None
    max_citations: int = 4

    def compose(self, request: AnswerComposeRequest) -> AnswerComposeResult:
        rag_result = request.rag_result
        evidence_status = self._evidence_status(rag_result)
        if evidence_status == "EMPTY":
            answer_text = "当前知识库中没有找到足够依据回答该问题。"
            if request.plan_summary is not None or request.tool_result is not None or request.memory_injection_plan is not None or request.recommendation is not None:
                answer_text = self._append_auxiliary_sections(request, answer_text, include_auxiliary=True)
            return AnswerComposeResult(answer_text=answer_text, confidence=0.05)

        if evidence_status == "OK":
            answer = self._compose_grounded_answer(request)
            if not answer:
                answer = self._grounded_fallback(request)
            return AnswerComposeResult(answer_text=answer, confidence=0.9 if self.llm_answerer is not None else 0.84)

        answer = self._compose_weak_answer(request)
        return AnswerComposeResult(answer_text=answer, confidence=0.58)

    def _compose_grounded_answer(self, request: AnswerComposeRequest) -> str:
        payload = None
        if self.llm_answerer is not None:
            try:
                payload = self.llm_answerer(request)
            except Exception:
                payload = None
        answer_text = self._extract_answer_text(payload)
        if not answer_text:
            answer_text = self._grounded_fallback(request)
        citations = self._collect_citations(request)
        if citations:
            answer_text = self._ensure_citations(answer_text, citations)
        return self._append_auxiliary_sections(request, answer_text, include_auxiliary=True)

    def _compose_weak_answer(self, request: AnswerComposeRequest) -> str:
        rag_result = request.rag_result
        evidence_pack = rag_result.evidence_pack if rag_result else None
        items = list(evidence_pack.items if evidence_pack else [])
        snippets = [item.content.strip() for item in items[:2] if item.content.strip()]
        if snippets:
            body = "根据当前知识库里的有限证据，我只能给出谨慎判断：{snippets}。如果你希望我继续，建议补充具体范围、版本或背景。".format(
                snippets="；".join(snippets)
            )
        else:
            body = "当前知识库中的证据偏弱，建议你补充更具体的上下文或重新表述问题。"
        return self._append_auxiliary_sections(request, body, include_auxiliary=False)

    def _grounded_fallback(self, request: AnswerComposeRequest) -> str:
        rag_result = request.rag_result
        evidence_pack = rag_result.evidence_pack if rag_result else None
        items = list(evidence_pack.items if evidence_pack else [])
        citations = self._collect_citations(request)
        if not items:
            return "当前知识库中没有找到足够依据回答该问题。"
        lead = "根据知识库中的证据，可以得到以下结论："
        bullets: List[str] = []
        for item, citation in zip(items[: self.max_citations], citations or items):
            marker = self._citation_marker(citation)
            snippet = item.content.strip().replace("\n", " ")
            if len(snippet) > 140:
                snippet = snippet[:137].rstrip() + "..."
            bullets.append(f"- {snippet} {marker}".rstrip())
        return "\n".join([lead, *bullets])

    def _append_auxiliary_sections(self, request: AnswerComposeRequest, answer: str, *, include_auxiliary: bool) -> str:
        sections = [answer]
        if include_auxiliary:
            plan_summary = request.plan_summary
            if plan_summary is not None:
                sections.append(
                    "Plan execution: {status} ({completed}/{total})".format(
                        status=plan_summary.status,
                        completed=plan_summary.completed_steps,
                        total=plan_summary.total_steps,
                    )
                )
                if plan_summary.key_findings:
                    sections.extend(plan_summary.key_findings[:2])
                if plan_summary.final_decision:
                    sections.append("Final decision: {decision}".format(decision=plan_summary.final_decision))
            if request.tool_result and request.tool_result.normalized_output:
                sections.append(
                    "Tool result: {payload}".format(
                        payload=request.tool_result.normalized_output.get("data", request.tool_result.normalized_output)
                    )
                )
            memory_plan = request.memory_injection_plan
            if memory_plan and memory_plan.prompt_memories:
                memory_sections: List[str] = []
                for memory in memory_plan.prompt_memories[:3]:
                    summary = memory.summary or str(memory.content)
                    memory_sections.append(str(summary))
                if memory_sections:
                    sections.append("Memory context: {items}".format(items=" | ".join(memory_sections)))
            if request.recommendation is not None:
                sections.append("Recommended next topic: {topic}".format(topic=request.recommendation.topic))
        return "\n\n".join(part for part in sections if part)

    def _evidence_status(self, rag_result) -> str:
        if rag_result is None:
            return "EMPTY"
        pack = getattr(rag_result, "evidence_pack", None)
        if pack is None:
            return str(getattr(rag_result, "evidence_status", "EMPTY") or "EMPTY").upper()
        return str(getattr(pack, "evidence_status", getattr(rag_result, "evidence_status", "EMPTY")) or "EMPTY").upper()

    def _collect_citations(self, request: AnswerComposeRequest) -> List[Any]:
        rag_result = request.rag_result
        citations = list(rag_result.citations if rag_result else [])
        if citations:
            return citations[: self.max_citations]
        evidence_pack = rag_result.evidence_pack if rag_result else None
        if evidence_pack is None:
            return []
        collected = []
        for item in evidence_pack.items[: self.max_citations]:
            collected.append(
                {
                    "chunk_id": getattr(item, "citation_chunk_id", None) or item.chunk_id,
                    "document_id": item.document_id,
                    "title": item.metadata.get("title") if isinstance(item.metadata, Mapping) else None,
                }
            )
        return collected

    def _ensure_citations(self, answer_text: str, citations: Sequence[Any]) -> str:
        if any(token in answer_text for token in ("[", "(", "【")):
            return answer_text
        marker_text = " ".join(self._citation_marker(citation) for citation in citations[: self.max_citations])
        if not marker_text:
            return answer_text
        return f"{answer_text}\n\n证据引用：{marker_text}"

    @staticmethod
    def _extract_answer_text(payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, Mapping):
            for key in ("answer_text", "answer", "text", "output", "content"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    @staticmethod
    def _citation_marker(citation: Any) -> str:
        if isinstance(citation, Mapping):
            chunk_id = str(citation.get("chunk_id") or citation.get("citation_chunk_id") or "").strip()
            title = str(citation.get("title") or "").strip()
        else:
            chunk_id = str(getattr(citation, "chunk_id", "") or getattr(citation, "citation_chunk_id", "") or "").strip()
            title = str(getattr(citation, "title", "") or "").strip()
        if title:
            return f"[{chunk_id}:{title}]" if chunk_id else f"[{title}]"
        return f"[{chunk_id}]" if chunk_id else ""


@dataclass
class Finalizer:
    settings: Settings

    def finalize(self, *args, **kwargs) -> SseEnvelope | None:
        return None
