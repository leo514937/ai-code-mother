from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from learning_agent_service.config import configure_logging, get_settings

from .dependencies import ServiceContainer, build_dependencies
from .service import WorkflowLearningAgentService, create_learning_agent_service


@dataclass
class BootstrapResult:
    container: ServiceContainer
    learning_service: WorkflowLearningAgentService
    logging_backend: Dict[str, Any]


def bootstrap_application(app: Any | None = None) -> BootstrapResult:
    settings = get_settings()
    configure_logging(settings.observability)
    dependencies = build_dependencies(settings=settings)
    learning_service = create_learning_agent_service(dependencies.container)
    if app is not None:
        app.state.settings = settings
        app.state.dependencies = dependencies
        app.state.learning_service = learning_service
    return BootstrapResult(
        container=dependencies.container,
        learning_service=learning_service,
        logging_backend={
            "backend": "stdlib",
            "log_level": settings.observability.log_level,
            "json_logs": settings.observability.json_logs,
        },
    )
