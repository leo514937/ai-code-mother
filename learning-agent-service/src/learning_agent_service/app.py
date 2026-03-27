"""Main application entrypoint for the learning agent service."""

from __future__ import annotations

from json import dumps
from typing import Any, Awaitable, Callable, Optional

from learning_agent_service import __version__
from learning_agent_service.api.compat import FastAPI as CompatFastAPI
from learning_agent_service.api.dependencies import LearningAgentService
from learning_agent_service.config import get_settings

FASTAPI_IMPORT_ERROR: Optional[Exception] = None

try:
    from fastapi import FastAPI
    from fastapi.responses import ORJSONResponse
except Exception as exc:  # pragma: no cover - fallback is intentional
    FASTAPI_IMPORT_ERROR = exc
    FastAPI = None  # type: ignore[assignment]
    ORJSONResponse = None  # type: ignore[assignment]

from learning_agent_service.api.router import create_api_router

AsgiApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]


def _build_fastapi_app(service: Optional[LearningAgentService] = None, app_cls: Any = None) -> Any:
    app_factory = app_cls or FastAPI or CompatFastAPI
    kwargs = {
        "title": "Learning Agent Service",
        "version": __version__,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
    }
    if ORJSONResponse is not None:
        kwargs["default_response_class"] = ORJSONResponse
    app = app_factory(**kwargs)
    if service is None:
        from learning_agent_service.application.bootstrap import bootstrap_application

        bootstrap = bootstrap_application(app)
        service = bootstrap.learning_service
    else:
        app.state.settings = get_settings()
        app.state.bootstrap_errors = []
        app.state.infrastructure_status = {}
    app.state.learning_service = service
    app.include_router(create_api_router(service))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        bootstrap_errors = list(getattr(app.state, "bootstrap_errors", []))
        return {
            "status": "ok",
            "service": "learning-agent-service",
            "version": __version__,
            "bootstrap_ready": not bootstrap_errors,
            "bootstrap_errors": bootstrap_errors,
            "infrastructure": getattr(app.state, "infrastructure_status", {}),
        }

    @app.get("/meta")
    async def meta() -> dict[str, Any]:
        return {
            "service": "learning-agent-service",
            "version": __version__,
            "settings": app.state.settings.safe_dump(),
            "infrastructure": getattr(app.state, "infrastructure_status", {}),
        }

    return app


def _build_fallback_asgi() -> AsgiApp:
    message = {
        "code": "DEPENDENCY_MISSING",
        "message": "FastAPI is not installed; install project dependencies to run the service.",
        "details": str(FASTAPI_IMPORT_ERROR) if FASTAPI_IMPORT_ERROR else None,
        "service": "learning-agent-service",
        "version": __version__,
    }
    payload = dumps(message).encode("utf-8")

    async def fallback_app(
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[Any]],
        send: Callable[..., Awaitable[Any]],
    ) -> None:
        if scope["type"] != "http":
            raise RuntimeError("Fallback ASGI app only supports HTTP.")

        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    return fallback_app


def create_app(service: Optional[LearningAgentService] = None) -> Any:
    if FastAPI is None and service is None:
        return _build_fallback_asgi()
    return _build_fastapi_app(service=service, app_cls=FastAPI or CompatFastAPI)


app = create_app()
