from __future__ import annotations

from hmac import compare_digest
from typing import Optional

from learning_agent_service.config import get_settings

from .errors import raise_http_error


def verify_internal_token(token: Optional[str]) -> None:
    settings = get_settings()
    expected_token = settings.internal_api_token
    if not expected_token:
        return
    if token and compare_digest(token, expected_token):
        return
    raise_http_error(
        {
            "message": "Missing or invalid internal token.",
        },
        status_code=401,
        default_code="LEARN-1401",
        stage="internal_auth",
    )
