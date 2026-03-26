from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from learning_agent_service.api.compat import FastAPI
from learning_agent_service.api.dependencies import LearningAgentService
from learning_agent_service.api.router import create_api_router
from learning_agent_service.application.bootstrap import bootstrap_application


def create_app(service: Optional[LearningAgentService] = None) -> FastAPI:
    app = FastAPI(title="Learning Agent Service", version="0.1.0")
    bound_service = service
    if bound_service is None:
        bootstrap = bootstrap_application(app)
        bound_service = bootstrap.learning_service
    app.state.learning_service = bound_service
    app.include_router(create_api_router(bound_service))
    return app


app = create_app()
