from .chat import register_chat_routes
from .feedback import register_feedback_routes
from .memory import register_memory_routes
from .quiz import register_quiz_routes
from .session import register_session_routes
from .study_plan import register_study_plan_routes

__all__ = [
    "register_chat_routes",
    "register_feedback_routes",
    "register_memory_routes",
    "register_quiz_routes",
    "register_session_routes",
    "register_study_plan_routes",
]
