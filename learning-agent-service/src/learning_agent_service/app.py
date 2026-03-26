"""Main application entrypoint for the learning agent service."""

from __future__ import annotations

from json import dumps
from typing import Any, Awaitable, Callable, Optional

from learning_agent_service import __version__

FASTAPI_IMPORT_ERROR: Optional[Exception] = None

try:
    from fastapi import FastAPI
    from fastapi.responses import ORJSONResponse
except Exception as exc:  # pragma: no cover - fallback is intentional
    FASTAPI_IMPORT_ERROR = exc
    FastAPI = None  # type: ignore[assignment]
    ORJSONResponse = None  # type: ignore[assignment]

from learning_agent_service.api.router import create_api_router
from learning_agent_service.application.bootstrap import bootstrap_application

AsgiApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]


def _build_fastapi_app() -> Any:
    app = FastAPI(
        title="Learning Agent Service",
        version=__version__,
        default_response_class=ORJSONResponse,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    bootstrap = bootstrap_application(app)
    app.include_router(create_api_router(bootstrap.learning_service))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "learning-agent-service",
            "version": __version__,
            "bootstrap_ready": True,
        }

    @app.get("/meta")
    async def meta() -> dict[str, Any]:
        return {
            "service": "learning-agent-service",
            "version": __version__,
            "settings": app.state.settings.safe_dump(),
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


def create_app() -> Any:
    if FastAPI is None:
        return _build_fallback_asgi()
    return _build_fastapi_app()


app = create_app()
