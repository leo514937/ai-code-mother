# Learning Agent Service

Standalone Python service scaffold for the Java/Agent learning support system.

## Scope

This workstream establishes only the top-level scaffold:

- Python dependency manifest
- environment sample
- Alembic config
- package version metadata
- main ASGI/FastAPI entrypoint

Feature modules under `api/`, `application/`, `config/`, `domain/`, `infrastructure/`,
`memory/`, `rag/`, `tools/`, and `tests/` are expected to be implemented by other
workstreams.

## Local development

```bash
cd learning-agent-service
pip install -e .[dev]
cp .env.example .env
uvicorn learning_agent_service.app:app --reload --port 9000
```

## App entrypoint behavior

`src/learning_agent_service/app.py` is intentionally defensive so the scaffold remains
usable while other modules are still being implemented.

- If FastAPI is installed, it creates the main application object.
- If downstream bootstrap or API router modules are not ready, it still exposes:
  - `GET /health`
  - `GET /meta`
  - `GET /internal/v1/status`
- If FastAPI itself is not installed yet, it falls back to a minimal ASGI app that returns
  a JSON error explaining the missing dependency.

This keeps the project importable early and allows later integration with the bootstrap
and API layers without rewriting the entrypoint.
