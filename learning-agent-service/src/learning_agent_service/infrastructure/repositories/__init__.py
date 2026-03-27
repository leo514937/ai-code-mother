"""Repository implementations owned by Workstream A."""

from .clarification import ClarificationRecordRepository
from .knowledge_governance import KnowledgeGovernanceRepository
from .learning_plan import LearningPlanRepository
from .outbox import OutboxRepository
from .preferences import UserPreferenceRepository
from .records import (
    ClarificationRecordEntry,
    KnowledgeDocumentRecord,
    KnowledgeDocumentVersionRecord,
    LearningPlanItemRecord,
    OutboxEventRecord,
    ToolInvocationLogEntry,
    TopicMasteryRecord,
    UserPreferenceProfileRecord,
)
from .runtime_adapters import (
    AdapterStatus,
    DurableTopicMasteryStore,
    OutboxAsyncLogStore,
    RedisSessionContextStore,
    RuntimeDependencyStatus,
)
from .tool_logs import ToolInvocationLogRepository
from .topic_mastery import TopicMasteryRepository

__all__ = [
    "AdapterStatus",
    "ClarificationRecordEntry",
    "ClarificationRecordRepository",
    "DurableTopicMasteryStore",
    "KnowledgeDocumentRecord",
    "KnowledgeDocumentVersionRecord",
    "KnowledgeGovernanceRepository",
    "LearningPlanItemRecord",
    "LearningPlanRepository",
    "OutboxAsyncLogStore",
    "OutboxEventRecord",
    "OutboxRepository",
    "RedisSessionContextStore",
    "RuntimeDependencyStatus",
    "ToolInvocationLogEntry",
    "ToolInvocationLogRepository",
    "TopicMasteryRecord",
    "TopicMasteryRepository",
    "UserPreferenceProfileRecord",
    "UserPreferenceRepository",
]
