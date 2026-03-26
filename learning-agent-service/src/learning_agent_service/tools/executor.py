from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any

from pydantic import ValidationError

from .models import RegisteredTool, ToolExecutionResult, ToolSelection
from .registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self, selection: ToolSelection) -> ToolExecutionResult:
        try:
            registered_tool = self._registry.get(selection.tool_name)
        except KeyError:
            return ToolExecutionResult(
                tool_name=selection.tool_name,
                status="failed",
                error_code="LEARN-5304",
                error_message="Tool not registered",
                retryable=False,
                degraded=False,
            )

        start = time.perf_counter()
        try:
            payload = registered_tool.spec.input_model.model_validate(selection.input_payload)
        except ValidationError as exc:
            return self._error_result(
                selection,
                error_code="LEARN-5302",
                error_message=str(exc),
                retryable=False,
                degraded=False,
                start=start,
            )

        timeout_seconds = self._resolve_timeout_seconds(selection, registered_tool)
        try:
            raw_output = await asyncio.wait_for(
                self._invoke_handler(registered_tool, payload),
                timeout=timeout_seconds,
            )
            validated_output = registered_tool.spec.output_model.model_validate(raw_output)
            return ToolExecutionResult(
                tool_name=selection.tool_name,
                status="ok",
                output=validated_output.model_dump(mode="json"),
                retryable=False,
                degraded=False,
                duration_ms=self._elapsed_ms(start),
            )
        except asyncio.TimeoutError:
            return self._error_result(
                selection,
                error_code="LEARN-5301",
                error_message="Tool execution timed out",
                retryable=registered_tool.spec.retryable,
                degraded=registered_tool.spec.degrade_to is not None,
                degrade_to=registered_tool.spec.degrade_to,
                start=start,
            )
        except ValidationError as exc:
            return self._error_result(
                selection,
                error_code="LEARN-5302",
                error_message=str(exc),
                retryable=False,
                degraded=False,
                start=start,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            return self._error_result(
                selection,
                error_code="LEARN-5300",
                error_message=str(exc),
                retryable=registered_tool.spec.retryable,
                degraded=registered_tool.spec.degrade_to is not None,
                degrade_to=registered_tool.spec.degrade_to,
                start=start,
            )

    async def _invoke_handler(self, registered_tool: RegisteredTool, payload: Any) -> Any:
        result = registered_tool.handler(payload)
        if inspect.isawaitable(result):
            return await result
        return result

    def _resolve_timeout_seconds(
        self,
        selection: ToolSelection,
        registered_tool: RegisteredTool,
    ) -> float:
        timeout_ms = selection.timeout_ms or registered_tool.spec.timeout_ms
        return timeout_ms / 1000.0

    def _error_result(
        self,
        selection: ToolSelection,
        error_code: str,
        error_message: str,
        retryable: bool,
        degraded: bool,
        start: float,
        degrade_to: str = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=selection.tool_name,
            status="failed",
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            degraded=degraded,
            degrade_to=degrade_to or selection.degrade_to,
            duration_ms=self._elapsed_ms(start),
        )

    def _elapsed_ms(self, start: float) -> int:
        return int((time.perf_counter() - start) * 1000)
