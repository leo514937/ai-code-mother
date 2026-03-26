from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from learning_agent_service.config import Settings
from learning_agent_service.domain import GraphState, PersistentSessionContext
from learning_agent_service.infrastructure.repositories.in_memory import (
    InMemoryAsyncLogStore,
    InMemorySessionContextStore,
    InMemoryTopicMasteryStore,
)

TOPIC_RECOMMENDATIONS = {
    "Java ThreadPool": "JUC AQS",
    "Spring AOP": "JDK Dynamic Proxy and CGLIB",
    "ReAct vs CoT": "Agent Tool Use",
    "RAG": "Hybrid Retrieval and Rerank",
    "LangGraph": "Controlled Agent Workflow Design",
}


@dataclass
class MemoryService:
    session_store: InMemorySessionContextStore
    mastery_store: InMemoryTopicMasteryStore
    async_log_store: InMemoryAsyncLogStore
    settings: Settings

    def persist_session(self, state: GraphState) -> GraphState:
        persistent = state["persistent"]
        turn = state["turn"]
        runtime = state["runtime"]
        understanding = turn.understanding_result
        resolved_topic = persistent.current_topic
        if understanding and understanding.reference_resolution and understanding.reference_resolution.resolved_entity:
            resolved_topic = understanding.reference_resolution.resolved_entity
        elif turn.retrieval_plan and turn.retrieval_plan.semantic_query:
            resolved_topic = turn.retrieval_plan.semantic_query
        elif not resolved_topic:
            resolved_topic = turn.raw_query

        recent_entities = [resolved_topic] if resolved_topic else []
        for entity in persistent.recent_entities:
            if entity and entity not in recent_entities:
                recent_entities.append(entity)
        recent_entities = recent_entities[:5]

        user_preferences = dict(persistent.user_preferences)
        if understanding and understanding.requested_output_style is not None:
            user_preferences["answer_style"] = understanding.requested_output_style.value
        updated_context = persistent.model_copy(
            update={
                "current_topic": resolved_topic,
                "recent_entities": recent_entities,
                "user_preferences": user_preferences,
                "last_retrieval_topic": resolved_topic,
                "learning_mode": persistent.learning_mode or (understanding is not None),
            }
        )
        self.session_store.save(updated_context, runtime)
        state["persistent"] = updated_context

        memory_updates = dict(runtime.extra.get("memory_updates", {}))
        memory_updates.update(
            {
                "current_topic": resolved_topic,
                "recent_entities": recent_entities,
                "user_preferences": user_preferences,
            }
        )
        runtime_extra = dict(runtime.extra)
        runtime_extra["memory_updates"] = memory_updates
        runtime_extra["session_persisted"] = True
        state["runtime"] = runtime.model_copy(update={"extra": runtime_extra})
        self.async_log_store.append(
            {
                "event_type": "persist_session",
                "session_id": runtime.session_id,
                "turn_id": runtime.turn_id,
                "trace_id": runtime.trace_id,
                "topic": resolved_topic,
            }
        )
        return state

    def update_mastery(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        persistent = state["persistent"]
        user_id = str(runtime.extra.get("user_id", "anonymous"))
        topic = persistent.current_topic or state["turn"].raw_query
        record = self.mastery_store.get(user_id, topic)
        delta = 0.08 if state["turn"].tool_result and state["turn"].tool_result.tool_name == "generateQuiz" else 0.02
        mastery_score = min(1.0, max(0.0, float(record["mastery_score"]) + delta))
        confidence_score = min(1.0, max(0.0, float(record["confidence_score"]) + 0.05))
        updated = self.mastery_store.upsert(
            user_id,
            topic,
            {
                "mastery_score": round(mastery_score, 2),
                "confidence_score": round(confidence_score, 2),
                "evidence_count": int(record["evidence_count"]) + 1,
                "last_quiz_score": record.get("last_quiz_score"),
                "review_priority": 20 if mastery_score >= 0.65 else 60,
                "source_turn_id": runtime.turn_id,
            },
        )
        metrics = dict(runtime.metrics)
        metrics["topic_mastery"] = updated
        state["runtime"] = runtime.model_copy(update={"metrics": metrics})
        return state

    def recommend_next(self, state: GraphState) -> GraphState:
        runtime = state["runtime"]
        persistent = state["persistent"]
        current_topic = persistent.current_topic or state["turn"].raw_query
        next_topic = TOPIC_RECOMMENDATIONS.get(current_topic)
        if not next_topic:
            user_id = str(runtime.extra.get("user_id", "anonymous"))
            records = self.mastery_store.list_for_user(user_id)
            weakest = records[0] if records else None
            next_topic = weakest["topic"] if weakest else None
        if next_topic:
            turn_extra = dict(state["turn"].extra)
            turn_extra["recommendation"] = {"topic": next_topic, "reason": "review_priority_or_topic_graph"}
            state["turn"] = state["turn"].model_copy(update={"extra": turn_extra})
        return state

    def load_any(self, session_id: str) -> PersistentSessionContext:
        for (stored_session_id, _), value in self.session_store.sessions.items():
            if stored_session_id == session_id:
                return value
        return PersistentSessionContext()
