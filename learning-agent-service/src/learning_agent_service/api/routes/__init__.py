from .chat import register_chat_routes
from .quiz import register_quiz_routes
from .session import register_session_routes
from .study_plan import register_study_plan_routes

__all__ = [
    "register_chat_routes",
    "register_quiz_routes",
    "register_session_routes",
    "register_study_plan_routes",
]
