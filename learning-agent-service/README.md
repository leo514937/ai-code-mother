# Learning Agent Service

面向“Java + Agent 八股学习客服”的独立 Python 服务。  
这份 README 不再描述“理想方案”，而是按当前 `learning-agent-service` 目录里的真实实现来说明：

- 图编排现在是怎么组织的
- RAG 现在怎么做混合检索和证据治理
- 上下文与记忆现在如何存、如何更新、如何参与回答
- 工具调用链路现在如何规划、执行、归一化
- API、SSE、双模式依赖接线、测试和当前边界分别是什么

## 1. 模块定位

这个服务当前承担的是“学习型 Agent 编排层”，不是通用聊天机器人，也不是 Java 主业务服务本身。

它的职责是：

- 接收学习问答请求
- 基于上下文理解当前意图和主题
- 决定是否需要澄清、检索、工具调用或推荐下一主题
- 通过 SSE 输出结构化事件
- 把短期会话状态、长期掌握度和异步日志写到对应存储

当前对外主入口：

- `POST /internal/v1/chat/stream`
- `POST /internal/v1/quiz/generate`
- `POST /internal/v1/study-plan/generate`
- `GET /internal/v1/session/{session_id}/state`

应用入口：

- `src/learning_agent_service/app.py`
- 根目录 `app.py` 只是薄包装，方便本地 `uvicorn app:app`

## 2. 当前总体分层

当前代码已经按“接入层 / 编排层 / 领域层 / RAG / Memory / Tools / Infrastructure”拆开：

- `api/`
  - FastAPI 路由、请求响应 DTO、SSE 编码、错误映射
- `application/`
  - 服务装配、工作流运行器、主图/子图编排
- `domain/`
  - 三层状态、领域模型、枚举、错误码、协议接口
- `rag/`
  - Query Rewrite、Hybrid Retrieve、Evidence Governance、Citation、Knowledge Governance
- `memory/`
  - Session 更新、记忆晋升、掌握度更新、推荐
- `tools/`
  - ToolPlanner、ToolExecutor、ToolResultNormalizer 及运行时适配层
- `infrastructure/`
  - Redis/Postgres/Qdrant/OpenAI client 工厂、repository、runtime adapter、outbox

当前分层框架图如下：

```text
+----------------------------------------------------------------------------------+
|                               learning-agent-service                             |
+----------------------------------------------------------------------------------+
| API Layer                                                                        |
| - FastAPI routes                                                                 |
| - Request / Response DTO                                                         |
| - SSE envelope / payload validation                                              |
+----------------------------------------------------------------------------------+
| Application Layer                                                                |
| - bootstrap / dependencies                                                       |
| - WorkflowLearningAgentService                                                   |
| - main graph / subgraphs / workflow runner                                       |
+----------------------------------------------------------------------------------+
| Domain Layer                                                                     |
| - PersistentSessionContext                                                       |
| - TurnRuntimeState                                                               |
| - GraphRuntimeMeta                                                               |
| - intent / retrieval / tool / error contracts                                    |
+----------------------------------------------------------------------------------+
| Capability Layer                                                                 |
| - RAG: rewrite / hybrid retrieve / evidence / citation / governance              |
| - Memory: promotion / mastery / recommendation                                   |
| - Tools: planner / executor / normalizer                                         |
+----------------------------------------------------------------------------------+
| Infrastructure Layer                                                             |
| - Redis session store                                                            |
| - Postgres durable repositories / outbox                                         |
| - Qdrant knowledge snapshot loader                                               |
| - OpenAI Responses model gateway                                                 |
+----------------------------------------------------------------------------------+
```

## 3. 图编排结构

### 3.1 主图

当前主图由 `WorkflowLearningAgentService` 装配，入口在：

- `src/learning_agent_service/application/service.py`
- `src/learning_agent_service/application/workflow/runner.py`
- `src/learning_agent_service/application/workflow/builder.py`

默认优先使用 `LangGraphWorkflowRunner`。如果本地没有安装 `langgraph`，会回退到 `SequentialWorkflowRunner`，但两条路径遵守同一套阶段顺序和路由条件。

主图当前实际顺序：

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

ASCII 主流程图如下：

```text
+--------------+
| load_context |
+--------------+
       |
       v
+-----------------+
| understand_turn |
+-----------------+
       |
       +------------------------------+
       | clarify                      |
       v                              |
+------------+                        |
| emit_final |<-----------------------+
+------------+

clear enough
       |
       v
+--------------+
| rag_subgraph |
+--------------+
       |
       +--------------------+
       | need_tool          |
       v                    |
+---------------+           |
| tool_subgraph |           |
+---------------+           |
       |                    |
       +---------+----------+
                 |
                 v
       +----------------+
       | compose_answer |
       +----------------+
                 |
                 v
       +-----------------+
       | persist_session |
       +-----------------+
                 |
                 v
       +----------------+
       | update_mastery |
       +----------------+
                 |
        +--------+--------+
        | recommend       | skip
        v                 |
+----------------+        |
| recommend_next |        |
+----------------+        |
        |                 |
        +--------+--------+
                 |
                 v
           +------------+
           | emit_final |
           +------------+
```

### 3.2 understand_turn 子图

`understand_turn` 是“问题理解子图”，定义在：

- `src/learning_agent_service/application/workflow/subgraphs.py`
- `src/learning_agent_service/application/workflow/adapters.py`

顺序固定为：

```text
parse_intent_slots
-> resolve_reference
-> ambiguity_check
-> rewrite_query
```

ASCII 子图：

```text
+--------------------+
| parse_intent_slots |
+--------------------+
          |
          v
+-------------------+
| resolve_reference |
+-------------------+
          |
          v
+-----------------+
| ambiguity_check |
+-----------------+
          |
          v
+---------------+
| rewrite_query |
+---------------+
```

每个节点的作用：

- `parse_intent_slots`
  - 通过 `container.model_gateway.classify_turn(...)` 识别意图、输出风格、决策类型
  - 当前模型网关支持两种实现：
    - `OpenAIBackedModelGateway`
    - `HeuristicModelGateway`
  - 真实运行时优先走 OpenAI Responses API，如果模型分类偏保守，会和 heuristic 结果合并，避免把中文“出题/学习计划/追问”误压成 `explain`

- `resolve_reference`
  - 处理“这个 / 上一个 / 它 / that / previous”这类追问
  - 候选来源包括：
    - `pending_clarification`
    - `clarification_result`
    - `current_topic`
    - `last_retrieval_topic`
    - `recent_entities`

- `ambiguity_check`
  - 两类低置信会触发澄清：
    - 意图置信度低
    - follow-up 指代未解析清楚
  - 现在不会再返回空卡片；如果历史太 sparse，会补兜底选项，例如：
    - `Use my current question as the topic`
    - `I will specify the exact topic`

- `rewrite_query`
  - 只在需要检索的意图上执行
  - 输出结构化 `RetrievalPlan`

### 3.3 rag_subgraph

`rag_subgraph` 固定三步：

```text
hybrid_retrieve
-> evaluate_evidence
-> citation_builder
```

ASCII 子图：

```text
+-----------------+
| hybrid_retrieve |
+-----------------+
          |
          v
+-------------------+
| evaluate_evidence |
+-------------------+
          |
          v
+------------------+
| citation_builder |
+------------------+
```

对应实现：

- `src/learning_agent_service/rag/service.py`
- `src/learning_agent_service/rag/rewrite.py`
- `src/learning_agent_service/rag/hybrid.py`
- `src/learning_agent_service/rag/evidence.py`
- `src/learning_agent_service/rag/citation.py`

### 3.4 tool_subgraph

工具子图固定三段：

```text
tool_planner
-> tool_executor
-> tool_result_normalizer
```

ASCII 子图：

```text
+--------------+
| tool_planner |
+--------------+
        |
        v
+--------------+
| tool_executor |
+--------------+
        |
        v
+------------------------+
| tool_result_normalizer |
+------------------------+
```

对应实现：

- `src/learning_agent_service/tools/service.py`
- `src/learning_agent_service/tools/planner.py`
- `src/learning_agent_service/tools/executor.py`
- `src/learning_agent_service/tools/normalizer.py`

这里的关键点是：聊天主链、独立 Quiz/StudyPlan 接口、测试，全都走同一套工具运行时，不再有旁路实现。

## 4. 三层状态结构

当前领域状态定义在：

- `src/learning_agent_service/domain/contracts.py`
- `src/learning_agent_service/domain/state.py`

现在不是一个膨胀的大 `SessionState`，而是三层：

### 4.1 PersistentSessionContext

跨轮保存，表示“会话持久态”。

核心字段：

- `current_topic`
- `recent_entities`
- `clarification_result`
- `user_preferences`
- `last_retrieval_topic`
- `active_plan_id`
- `learning_mode`
- `history_summary`
- `pending_clarification`
- `extra`

用途：

- 追问指代解析
- 学习模式判断
- 回答风格记忆
- 会话连续性

### 4.2 TurnRuntimeState

只在当前 turn 内流转，表示“单轮运行态”。

核心字段：

- `raw_query`
- `decision`
- `intent`
- `intent_confidence`
- `requested_output_style`
- `slots`
- `reference_resolution`
- `clarification_card`
- `retrieval_plan`
- `hybrid_recall`
- `evidence_pack`
- `citations`
- `answer_plan`
- `tool_plan`
- `raw_tool_result`
- `tool_result`
- `final_answer`

用途：

- 承载每一阶段的中间结果
- 避免把核心执行字段塞进 `runtime.extra`

### 4.3 GraphRuntimeMeta

表示“图运行元数据”。

核心字段：

- `trace_id`
- `session_id`
- `turn_id`
- `workflow_version`
- `request_ts`
- `user_id`
- `response_mode`
- `topic_hint`
- `history_summary`
- `client_context`
- `metrics`
- `errors`
- `degrade_to`
- `terminal_event`
- `emitted_events`

用途：

- SSE 事件拼装
- 指标记录
- 错误与降级跟踪
- trace 贯穿

## 5. RAG 实现细节

### 5.1 Query Rewrite

入口：

- `rag/service.py -> HybridRAGOrchestrator.rewrite_query`
- `rag/rewrite.py -> QueryRewriteService`

当前做法：

- 输入 `raw_query + intent + resolved_topic + session_topic + requested_output_style + filters`
- 生成：
  - `semantic_query`
  - `keyword_query`
  - `retrieval_filters`
  - `preferred_chunk_types`

这一步会处理：

- 代词补全
- 模糊追问补主题
- 从 query 推断 category/source_type/difficulty/chunk_type

例如：

- 对比类问题优先 `comparison / interview_template / qa`
- 代码类问题优先 `code_example / pitfall / qa`
- 学习路线类问题优先 `roadmap / concept / practice_case`

### 5.2 混合检索

入口：

- `rag/service.py -> hybrid_retrieve`
- `rag/hybrid.py -> HybridRetrieverService`

当前实现的三路召回：

- Dense 路由
- Sparse/BM25 风格路由
- Metadata Filter 路由

当前默认参数来自 `config/settings.py`：

- `dense_top_k = 20`
- `sparse_top_k = 20`
- `metadata_top_k = 10`
- `rrf_k = 60`
- `rerank_top_k = 15`

实现方式：

1. 三路分别召回
2. 用 RRF 融合
3. 对 TopN rerank
4. 输出 `HybridRecallResult`

当前 retrieval strategy 字符串统一为：

```text
dense+sparse+metadata->rrf->rerank->evidence
```

### 5.3 Evidence Governance

入口：

- `rag/service.py -> evaluate_evidence`
- `rag/evidence.py -> EvidenceGovernanceService`

当前治理步骤：

- 低分过滤
- 去重
- 主题一致性过滤
- 版本过滤
- 答案视角过滤

输出 `EvidencePack`，其中包含：

- `items`
- `discard_summary`
- `top_scores`
- `extra.metrics`

当前证据条数控制：

- `evidence_min_n = 4`
- `evidence_top_n = 6`

### 5.4 Citation

入口：

- `rag/citation.py -> CitationBuilder`

当前 `final.citations` 只来源于最终进入 `EvidencePack` 的 chunk，不会引用被过滤掉的召回结果。

### 5.5 知识治理

入口：

- `rag/governance.py`
- `rag/service.py` 中的：
  - `deduplicate_chunks`
  - `plan_duplicate_cleanup`
  - `plan_version_switch`
  - `plan_rebuild`
  - `plan_rollback`

当前支持的离线治理动作：

- 文档去重
- 版本切换
- 按文档重建
- 回滚到指定版本

### 5.6 当前 real/fallback 运行方式

依赖装配在：

- `src/learning_agent_service/application/dependencies.py`

当前 RAG 双模式：

- 若 `prefer_real_adapters=true` 且 Qdrant 可用：
  - 先从 `knowledge_chunks` collection 做一次 snapshot 装载
  - 再交给 `HybridRAGOrchestrator`
- 若 Qdrant 不可用或无数据：
  - 显式 fallback 到内置 `DEFAULT_KNOWLEDGE_CHUNKS`

注意：

- 当前 real 模式是“Qdrant snapshot 驱动”
- 不是“每次查询直接在线调用 Qdrant 向量检索”

这也是当前实现的一个已知边界。

## 6. 上下文与记忆策略

### 6.1 会话上下文

短期上下文的读写适配在：

- `src/learning_agent_service/infrastructure/repositories/runtime_adapters.py`

如果 Redis 可用：

- `RedisSessionContextStore`
  - `state` 保存完整 `PersistentSessionContext`
  - `summary` 保存当前 topic / last retrieval topic 摘要
  - `clarification` 保存澄清结果

如果 Redis 不可用：

- fallback 到 `InMemorySessionContextStore`

### 6.2 persist_session

入口：

- `memory/service.py -> persist_session`

当前做的事情：

1. 解析当前 turn 的主题与显式用户信号
2. 读取当前偏好与当前 mastery
3. 构造 `MemoryPromotionInput`
4. 调用 `MemoryPromotionPolicy.evaluate(...)`
5. 生成 `PersistSessionPlan`
6. 写回 session context
7. 写 preference patch
8. 把 durable fact request / outbox event 送到异步日志
9. 把 `memory_updates` 写到 `runtime.extra`

### 6.3 Memory Promotion

实现：

- `memory/promotion.py -> MemoryPromotionPolicy`

当前晋升规则主要覆盖：

- 回答风格偏好
- 代码示例偏好
- 面试模式偏好
- 弱项信号
- 语义记忆 fact
- 学习计划确认
- 澄清结果

只有满足条件的信号才会进入 durable fact / semantic fact，不会把每一轮都无脑长期记忆化。

### 6.4 update_mastery

入口：

- `memory/service.py -> update_mastery`
- `memory/mastery.py -> TopicMasteryUpdater`

当前维护的掌握度字段包括：

- `topic`
- `mastery_score`
- `confidence_score`
- `evidence_count`
- `last_seen_at`
- `last_quiz_score`
- `review_priority`
- `positive_signals`
- `negative_signals`

信号来源包括：

- 当前是否是 quiz
- quiz score
- 是否 confusion
- 是否 weak topic
- 是否明确解决
- supporting evidence count

这一步只做 mastery 和 semantic index 状态更新，不再和 session 写入混在一个超重节点里。

### 6.5 recommend_next

入口：

- `memory/service.py -> recommend_next`
- `memory/recommend.py -> RecommendationService`

当前读取：

- `topic_mastery`
- `weak_topics`
- `active_plan_topics`
- `recent_entities`
- `preferred_output_style`

推荐优先级大致是：

1. active plan 的下一主题
2. 显性弱项 / 低掌握度主题
3. review priority 高的主题
4. active plan 回填主题

### 6.6 存储真相边界

当前边界是明确的：

- Redis
  - 短期会话真相源
- Postgres
  - 持久结构化事实真相源
  - 包括 topic mastery、preference、outbox 等
- Qdrant
  - 检索索引
  - 不作为业务事实真相源

## 7. 工具调用实现

### 7.1 统一工具链

当前工具运行时统一为：

```text
ToolPlanner -> ToolExecutor -> ToolResultNormalizer
```

实现文件：

- `tools/planner.py`
- `tools/executor.py`
- `tools/normalizer.py`
- `tools/service.py`

### 7.2 ToolPlanner

Planner 根据：

- `intent`
- `decision`
- `slots`

决定是否调用工具以及调用哪个工具。

当前默认映射：

- `quiz -> generateQuiz`
- `study_plan -> generateStudyPlan`
- `recommend -> recommendNextTopic`
- `knowledge -> searchKnowledge`
- `detail -> getKnowledgeDetail`
- `save_record -> saveLearningRecord`

### 7.3 ToolExecutor

Executor 基于 `ToolRegistry` 执行注册工具，当前特性：

- 输入参数用 Pydantic 校验
- 支持 timeout
- 支持 retryable / degrade_to
- 统一返回结构化 `ToolExecutionResult`

### 7.4 ToolResultNormalizer

Normalizer 把底层执行结果统一成 `NormalizedToolResult`，供主图后续阶段和 SSE 使用。

### 7.5 当前已接工具

当前 registry 中的工具包括：

- `searchKnowledge`
- `getKnowledgeDetail`
- `generateQuiz`
- `generateStudyPlan`
- `recommendNextTopic`
- `saveLearningRecord`

其中：

- `searchKnowledge` 和 `getKnowledgeDetail` 会复用主 RAG 逻辑
- `generateQuiz`、`generateStudyPlan` 当前仍是轻量 mock-style 生成器，便于后续替换成真实实现

## 8. SSE 与 API 合同

SSE 合同定义在：

- `src/learning_agent_service/api/contracts.py`
- `src/learning_agent_service/api/sse.py`

当前事件类型：

- `ack`
- `state_update`
- `clarification_card`
- `retrieval_started`
- `retrieval_result`
- `tool_call`
- `tool_result`
- `delta`
- `final`
- `error`

当前实际主链常见序列：

- 普通知识问答
  - `ack -> retrieval_started -> retrieval_result -> final`
- 工具型请求
  - `ack -> retrieval_started -> retrieval_result -> tool_call -> tool_result -> final`
- 模糊追问
  - `ack -> clarification_card`

SSE envelope 固定字段：

- `event_type`
- `trace_id`
- `session_id`
- `turn_id`
- `timestamp`
- `workflow_version`
- `payload`

`clarification_card.options` 现在是结构化对象，而不是简单字符串数组。

## 9. Dual Mode 依赖装配

装配入口：

- `src/learning_agent_service/application/dependencies.py`

当前装配逻辑：

### 9.1 Model Gateway

- 若 OpenAI 可用且启用真实适配器：
  - 使用 `OpenAIBackedModelGateway`
  - 再和 `HeuristicModelGateway` 做合并，避免中文意图退化
- 否则：
  - fallback 到 `HeuristicModelGateway`

### 9.2 Session Store

- Redis 可用：
  - `RedisSessionContextStore`
- 否则：
  - `InMemorySessionContextStore`

### 9.3 Mastery Store

- Postgres repo 可用：
  - `DurableTopicMasteryStore`
- 否则：
  - `InMemoryTopicMasteryStore`

### 9.4 Async Log Store

- Postgres outbox 可用：
  - `OutboxAsyncLogStore`
- 否则：
  - `InMemoryAsyncLogStore`

### 9.5 RAG Runtime

- Qdrant 可用：
  - 从 Qdrant collection 读取知识 chunk snapshot
- 否则：
  - fallback 到 `DEFAULT_KNOWLEDGE_CHUNKS`

运行时依赖状态会通过：

- `/health`
- `/meta`

暴露给外部。

## 10. Answer 生成与终态输出

当前 `compose_answer` 在：

- `src/learning_agent_service/tools/service.py -> AnswerComposer`

当前实现还是 MVP 风格：

- 根据 `requested_output_style` 选一个开头
- 把前几个证据片段拼到正文
- 如果有工具结果，再追加 `Tool result`
- 根据是否有稳定证据设置 `final_answer_confidence`

当前不是一个重 prompt 的长链生成器，而是“结构化工作流 + 轻量答案组装”。

最终 SSE 终结点在：

- `application/workflow/adapters.py -> emit_final`

它统一负责：

- `final`
- `clarification_card`
- `error`

不会再由 runner 在外面临时拼终态事件。

## 11. 当前实现的关键文件索引

如果你要继续维护或接入，最值得先看的文件：

- 工作流总入口
  - `src/learning_agent_service/application/service.py`
- 主图 / LangGraph / 顺序回退
  - `src/learning_agent_service/application/workflow/runner.py`
  - `src/learning_agent_service/application/workflow/builder.py`
  - `src/learning_agent_service/application/workflow/subgraphs.py`
  - `src/learning_agent_service/application/workflow/adapters.py`
- 三层状态
  - `src/learning_agent_service/domain/contracts.py`
  - `src/learning_agent_service/domain/state.py`
- 依赖装配
  - `src/learning_agent_service/application/dependencies.py`
- RAG
  - `src/learning_agent_service/rag/service.py`
  - `src/learning_agent_service/rag/rewrite.py`
  - `src/learning_agent_service/rag/hybrid.py`
  - `src/learning_agent_service/rag/evidence.py`
  - `src/learning_agent_service/rag/citation.py`
- Memory
  - `src/learning_agent_service/memory/service.py`
  - `src/learning_agent_service/memory/promotion.py`
  - `src/learning_agent_service/memory/mastery.py`
  - `src/learning_agent_service/memory/recommend.py`
- Tools
  - `src/learning_agent_service/tools/service.py`
  - `src/learning_agent_service/tools/planner.py`
  - `src/learning_agent_service/tools/executor.py`
  - `src/learning_agent_service/tools/normalizer.py`

## 12. 测试覆盖范围

当前测试已经覆盖：

- SSE 合同校验
- 聊天流式事件顺序
- 中文学习计划路由到工具链
- 中文刷题路由到工具链
- 模糊追问触发澄清卡片，且 options 非空
- dual mode 依赖状态暴露
- API 错误码透传

命令：

```bash
python -m unittest discover -s learning-agent-service/tests -p "test_*.py"
```

## 13. 当前已知边界

这份实现已经能跑通主链，但还不是最终形态。当前要明确的边界有：

- real RAG 还是 snapshot 模式，不是在线向量检索模式
- AnswerComposer 还是轻量拼装，不是完整大模型回答模板
- 工具实现里 `generateQuiz / generateStudyPlan` 目前是可插拔 mock 版本
- 真实 Redis/Postgres/Qdrant/OpenAI 联机环境还需要单独做端到端集成验收

## 14. 本地运行

```bash
cd learning-agent-service
pip install -e .[dev]
cp .env.example .env
uvicorn learning_agent_service.app:app --reload --port 9000
```

## 15. 一句话总结当前实现

当前 `learning-agent-service` 已经是一个“主图 + 子图 + 混合检索 + 记忆晋升 + 统一工具栈 + 结构化 SSE”的学习型 Agent 服务骨架，适合继续往真实知识库、真实工具实现和真实联机基础设施方向演进。
