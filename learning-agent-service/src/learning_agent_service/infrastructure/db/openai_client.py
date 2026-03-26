"""Bootstrap-friendly OpenAI client factory for Responses API usage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from learning_agent_service.config.settings import OpenAISettings

from .errors import InfrastructureConfigurationError, require_dependency

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on optional runtime installation.
    OpenAI = None


@dataclass(frozen=True)
class OpenAIRuntime:
    """Holds the shared OpenAI client and the default Responses model name."""

    client: Any
    default_model: str


def build_openai_runtime(settings: OpenAISettings) -> OpenAIRuntime:
    """Create the OpenAI client used by higher-level orchestration layers."""

    if OpenAI is None:
        require_dependency("openai", "model access")
    if not settings.api_key:
        raise InfrastructureConfigurationError(
            "OPENAI_API_KEY or LEARNING_AGENT_OPENAI_API_KEY must be configured before enabling model access"
        )
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        organization=settings.organization,
        project=settings.project,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )
    return OpenAIRuntime(client=client, default_model=settings.responses_model)
