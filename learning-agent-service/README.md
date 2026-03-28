# Learning Agent Service

`learning-agent-service` is the standalone Python service for the Java/Agent learning assistant workflow.
This README describes the **current runtime behavior in this folder**, not an aspirational future design.

## Purpose

The service sits between the external chat client and the internal learning workflow. It is responsible for:

- accepting learning-oriented chat requests
- running the workflow orchestration layer
- emitting structured SSE events on the public streaming route
- routing quiz / study-plan requests through the shared tool stack
- loading and persisting session-oriented learning context

Public routes are:

- `POST /internal/v1/chat/stream`
- `POST /internal/v1/quiz/generate`
- `POST /internal/v1/study-plan/generate`
- `GET /internal/v1/session/{session_id}/state`

## Runtime Layout

```text
+--------------------------------------------------------------------------------+
|                         learning-agent-service runtime                         |
+--------------------------------------------------------------------------------+
| API boundary                                                                   |
| - FastAPI router                                                               |
| - HTTP request/response DTOs                                                   |
| - SSE envelope serialization + payload validation                              |
+--------------------------------------------------------------------------------+
| Application layer                                                              |
| - WorkflowLearningAgentService                                                 |
| - Chat / quiz / study-plan / session query use cases                           |
| - Workflow runner                                                              |
+--------------------------------------------------------------------------------+
| Workflow state                                                                 |
| - PersistentSessionContext                                                     |
| - TurnRuntimeState                                                             |
| - GraphRuntimeMeta                                                             |
+--------------------------------------------------------------------------------+
| Capability layer                                                               |
| - RAG: rewrite -> retrieve -> evidence -> citation                             |
| - Memory: persist session -> update mastery -> recommend next                  |
| - Tools: planner -> executor -> normalizer                                     |
+--------------------------------------------------------------------------------+
| Infrastructure                                                                 |
| - Redis / in-memory session store                                              |
| - Postgres / in-memory mastery + outbox                                        |
| - Qdrant snapshot-backed knowledge loading                                     |
| - OpenAI-backed or heuristic turn classification                               |
+--------------------------------------------------------------------------------+
```

## Workflow Overview

The chat workflow is driven by the application service and workflow runner. The current high-level shape is:

```text
load_context
-> understand_turn
-> [clarify] emit_final
-> [need_rag] rag_subgraph
-> [need_tool] tool_subgraph
-> compose_answer
-> persist_session
-> update_mastery
-> recommend_next(optional)
-> emit_final
```

Subgraphs are organized as:

```text
understand_turn:
parse_intent_slots
-> resolve_reference
-> ambiguity_check
-> rewrite_query

rag_subgraph:
hybrid_retrieve
-> evaluate_evidence
-> citation_builder

tool_subgraph:
tool_planner
-> tool_executor
-> tool_result_normalizer
```

## Public SSE Contract

The public streaming contract is defined and validated in:

- `src/learning_agent_service/api/contracts.py`
- `src/learning_agent_service/api/sse.py`

Only these event types are public:

- `ack`
- `retrieval_started`
- `retrieval_result`
- `tool_call`
- `tool_result`
- `clarification_card`
- `final`
- `error`

Dead public events such as `state_update` and `delta` are intentionally not part of the contract.

### SSE lifecycle

Once a request enters a valid SSE session, the lifecycle is:

```text
ack
-> zero or more middle events
-> exactly one terminal event
```

Terminal events are:

- `clarification_card`
- `final`
- `error`

Typical sequences are:

```text
knowledge answer:
ack -> retrieval_started -> retrieval_result -> final

tool-assisted answer:
ack -> retrieval_started -> retrieval_result -> tool_call -> tool_result -> final

clarification:
ack -> clarification_card

in-stream failure:
ack -> error
```

Pre-stream failures are handled differently:

```text
request received
-> service raises before stream is created
-> HTTP error response
```

They do **not** masquerade as partial SSE sessions.

### Envelope shape

Every SSE event uses the same envelope:

```text
event_type
trace_id
session_id
turn_id
timestamp
workflow_version
payload
```

### Clarification payload

`clarification_card.options` is a structured object list, not a string array:

```text
id
label
value
description
```

## HTTP DTO Ownership

The public API boundary keeps one canonical public payload model set for streaming:

- `api/contracts.py` owns HTTP request DTOs and public event validation
- the SSE envelope serializes through one validation map before emitting

Where reuse is practical, the API layer imports shared domain payload models instead of redefining parallel SSE payloads.

## RAG Behavior

Current RAG is a structured pipeline, not a single opaque call:

```text
raw query
-> query rewrite
-> hybrid retrieve
-> evidence governance
-> citation build
```

### Query rewrite

The rewrite stage produces:

- `semantic_query`
- `keyword_query`
- `retrieval_filters`
- `preferred_chunk_types`

It incorporates:

- current query text
- detected intent
- resolved reference/topic
- session topic
- requested output style

### Hybrid retrieval

The current retriever uses three retrieval routes:

- dense-style route
- sparse/BM25-style route
- metadata filter route

Then it runs:

- RRF fusion
- rerank
- evidence selection

The canonical strategy string on the public boundary is:

```text
dense+sparse+metadata->rrf->rerank->evidence
```

### Metadata-aware retrieval

Metadata filtering is part of the actual pipeline. Current retrieval filters may include fields such as:

- `category`
- `subcategory`
- `difficulty`
- `source_type`
- `chunk_type`
- `version`
- `tags`

### Current runtime mode

The current "real" RAG mode is **Qdrant snapshot-backed**, not per-request online vector querying:

```text
Qdrant available
-> load knowledge snapshot from collection
-> run hybrid retrieval in-process
```

If Qdrant is unavailable or empty, the service falls back to bundled default chunks.

## Memory Behavior

The service currently works with three state layers:

### 1. PersistentSessionContext

Cross-turn session context, including:

- `current_topic`
- `recent_entities`
- `clarification_result`
- `user_preferences`
- `last_retrieval_topic`
- `active_plan_id`
- `learning_mode`
- `history_summary`
- `pending_clarification`

### 2. TurnRuntimeState

Per-turn execution state, including:

- intent and confidence
- slots
- reference resolution
- retrieval plan / recall / evidence / citations
- tool plan / raw tool result / normalized tool result
- final answer / recommendation

### 3. GraphRuntimeMeta

Execution metadata, including:

- trace/session/turn identifiers
- workflow version
- metrics
- errors
- terminal event
- emitted events
- memory update summary

### Storage boundaries

The current truth boundaries are:

- Redis: short-term session truth
- Postgres: durable structured facts
- Qdrant: retrieval index, not business truth

## Tool Calling

The shared runtime tool stack is:

```text
ToolPlanner -> ToolExecutor -> ToolResultNormalizer
```

This same stack is used by:

- the chat workflow
- the standalone quiz endpoint
- the standalone study-plan endpoint

Current registered tools include:

- `searchKnowledge`
- `getKnowledgeDetail`
- `generateQuiz`
- `generateStudyPlan`
- `recommendNextTopic`
- `saveLearningRecord`

`searchKnowledge` and `getKnowledgeDetail` are wired to the RAG capability layer.
`generateQuiz` and `generateStudyPlan` are still lightweight built-in generators that can be replaced later.

## Runtime Profiles and Dual Mode

Dependency assembly lives in `src/learning_agent_service/application/dependencies.py`.

The runtime advertises a profile such as:

- `full`
- `partial`
- `dev_fallback`

And exposes adapter-level modes like:

- `real`
- `fallback`
- `noop`
- `unavailable`

At startup, the app stores infrastructure status on application state. The status includes:

```text
runtime_profile
dependency_status
```

## Testing

The current test suite emphasizes the real public contract:

- public SSE event enum only contains supported events
- chat stream route serializes canonical SSE events
- pre-stream failures return HTTP errors instead of partial SSE streams
- clarification uses structured options
- tool tests use the canonical runtime planner/executor/normalizer DTO flow
- runtime smoke tests verify the actual service starts with `ack` and ends with one supported terminal event
- bootstrap tests verify dependency status and runtime profile exposure

Run the suite with:

```bash
python -m unittest discover -s learning-agent-service/tests -p "test_*.py"
```

## Current Integration Assumptions

This folder is aligned to the public API/SSE boundary, but some deeper runtime behavior still depends on other modules evolving independently. In particular:

- the public contract is strict even if internal workflow paths degrade to `ack -> error`
- actual runtime smoke tests avoid assuming every internal branch is healthy in every workspace state
- richer event-order coverage is exercised through deterministic service stubs at the API boundary

## Local Run

```bash
cd learning-agent-service
pip install -e .[dev]
cp .env.example .env
uvicorn learning_agent_service.app:app --reload --port 9000
```
