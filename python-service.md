# Python 服务说明

## 1. 服务定位

`learning-agent-service` 是项目里的独立 Python 学习助手服务。

它负责的不是前端页面，而是学习助手背后的“会话推理、流式输出、测验生成、学习计划生成、记忆查询和反馈记录”。

从系统角度看，它有两种入口：

- 浏览器学习助手页面直接访问它的公开 API
- Java 后端通过内部接口转发到它的内部能力

也就是说，它既可以作为独立服务直接工作，也可以作为 Java 侧边栏的后端能力提供者。

## 2. 整体架构中的位置

下面这张图展示了 Python 服务在整个项目中的详细位置和内部边界：

```text
+==============================================================================================================+
|                                 Python Learning Agent Service (FastAPI)                                    |
+--------------------------------------------------------------------------------------------------------------+
|  A. 进程入口                                                                                                |
|                                                                                                              |
|   app.py                                                                                                     |
|      -> create_app()                                                                                         |
|      -> FastAPI / CompatFastAPI / fallback ASGI                                                             |
|                                                                                                              |
|   这一层决定服务能否启动、文档地址是否可用、健康检查是否对外暴露。                                           |
+--------------------------------------------------------------------------------------------------------------+
|  B. API 边界                                                                                                |
|                                                                                                              |
|   浏览器开发代理前缀: /learning-api                                                                          |
|   Python 服务真实路由: /internal/v1/*                                                                        |
|                                                                                                              |
|   /internal/v1/chat/stream                                                                                    |
|   /internal/v1/quiz/generate                                                                                  |
|   /internal/v1/study-plan/generate                                                                            |
|   /internal/v1/session/{session_id}/state                                                                    |
|   /internal/v1/memory/*                                                                                       |
|   /internal/v1/feedback/*                                                                                     |
|                                                                                                              |
|   这一层负责：鉴权、DTO 解析、SSE 封装、错误转换、路由挂载。                                                 |
+--------------------------------------------------------------------------------------------------------------+
|  C. Router 注册层                                                                                            |
|                                                                                                              |
|   router.py                                                                                                  |
|      -> register_chat_routes()                                                                               |
|      -> register_feedback_routes()                                                                            |
|      -> register_memory_routes()                                                                              |
|      -> register_quiz_routes()                                                                                |
|      -> register_session_routes()                                                                             |
|      -> register_study_plan_routes()                                                                          |
|                                                                                                              |
|   它把每个业务域拆成独立路由，让聊天、测验、学习计划、记忆和反馈互不混在一起。                               |
+--------------------------------------------------------------------------------------------------------------+
|  D. Application 层                                                                                            |
|                                                                                                              |
|   application/service.py                                                                                     |
|      -> LearningAgentService                                                                                 |
|                                                                                                              |
|   application/use_cases/chat_workflow.py                                                                     |
|   application/use_cases/quiz_generation.py                                                                   |
|   application/use_cases/study_plan_generation.py                                                            |
|   application/use_cases/session_query.py                                                                    |
|                                                                                                              |
|   这一层负责编排“做什么”，而不是“怎么存、怎么查、怎么连模型”。                                               |
+--------------------------------------------------------------------------------------------------------------+
|  E. Workflow 编排层                                                                                           |
|                                                                                                              |
|   builder.py                                                                                                 |
|      -> runner.py                                                                                            |
|      -> plan_execute.py                                                                                      |
|      -> subgraphs.py                                                                                         |
|      -> adapters.py                                                                                          |
|                                                                                                              |
|   这一层负责把一次聊天拆成多个阶段：理解、检索、工具调用、生成、持久化。                                     |
+--------------------------------------------------------------------------------------------------------------+
|  F. 能力层                                                                                                   |
|                                                                                                              |
|   RAG                                                                                                         |
|      rewrite -> retrieve -> evidence -> citation                                                              |
|                                                                                                              |
|   Memory                                                                                                      |
|      session context -> mastery -> recommendation -> persistence                                             |
|                                                                                                              |
|   Tools                                                                                                       |
|      planner -> executor -> normalizer                                                                       |
|                                                                                                              |
|   这一层是服务真正产出“学习答案、测验题、学习计划和记忆”的地方。                                             |
+--------------------------------------------------------------------------------------------------------------+
|  G. 基础设施层                                                                                                |
|                                                                                                              |
|   Redis                                                                                                       |
|   PostgreSQL                                                                                                  |
|   Qdrant                                                                                                      |
|   OpenAI                                                                                                      |
|   本地回退实现                                                                                                 |
|                                                                                                              |
|   这一层提供持久化、向量检索、模型调用和降级能力。                                                           |
+--------------------------------------------------------------------------------------------------------------+
|  H. 输出与监控                                                                                                |
|                                                                                                              |
|   SSE 事件: ack / retrieval_started / tool_call / final / clarification_card / error                        |
|   健康接口: /health /ready /live /meta /metrics /dependency-status                                            |
|                                                                                                              |
|   这一层让前端、Java BFF 和运维系统都能知道服务当前是否健康、依赖是否齐全、结果是否可流式返回。             |
+==============================================================================================================+
```

Python 服务本身的内部结构则是分层的，不是一个大而全的单文件脚本。

### 2.1 Python 侧关键请求流

下面把 Python 服务内部最重要的三条链路单独画开：

```text
1) 学习助手聊天流

Vue 学习助手页面
  -> /learning-api/internal/v1/chat/stream
  -> 前端代理到 Python /internal/v1/chat/stream
  -> api/routes/chat.py
  -> application/service.py
  -> application/use_cases/chat_workflow.py
  -> workflow/builder.py
  -> workflow/runner.py
  -> RAG / Memory / Tools
  -> SSE 返回给前端

2) 测验生成

Java 或学习页面调用
  -> /internal/v1/quiz/generate
  -> api/routes/quiz.py
  -> application/use_cases/quiz_generation.py
  -> workflow / tools
  -> JSON 返回测验结果

3) 学习计划生成

Java 或学习页面调用
  -> /internal/v1/study-plan/generate
  -> api/routes/study_plan.py
  -> application/use_cases/study_plan_generation.py
  -> workflow / memory / rag
  -> JSON 返回学习计划
```

### 2.2 实现细节流程图

下面这一组图是 Python 服务真正的“落地执行路径”。  
它不是单纯展示模块名字，而是把 RAG、记忆机制、图编排在一次请求里怎么互相配合画出来。

#### 2.2.1 RAG 实现流程

```text
用户问题 / 学习请求
  |
  v
+------------------------------------------------------------+
| 0. 输入接入与上下文整理                                   |
| chat_workflow.py                                          |
| - 原始问题                                                |
| - session 上下文                                          |
| - 当前 topic / 参考对象                                   |
+------------------------------------------------------------+
  |
  v
+----------------------------------------------------------------------------------------+
| 1. Query Rewrite 并行改写                                                              |
+----------------------------------------------------------------------------------------+
| +------------------+  +------------------+  +------------------+  +----------------+ |
| | semantic rewrite |  | keyword rewrite  |  | reference resolve |  | constraints    | |
| | 语义改写         |  | 关键词扩展/压缩  |  | 指代消歧/上下文补全|  | 标签/版本/范围 | |
| | -> semantic_q    |  | -> keyword_q     |  | -> resolved_refs |  | -> filters     | |
| +------------------+  +------------------+  +------------------+  +----------------+ |
|           \                  |                    /                    /              |
|            \                 |                   /                    /               |
|             +---------------------------------------------------------------+         |
|             | rewrite merge + retrieval plan builder                        |         |
|             | - 合并改写结果                                                |         |
|             | - 生成统一检索计划                                            |         |
|             +---------------------------------------------------------------+         |
+----------------------------------------------------------------------------------------+
  |
  v
+----------------------------------------------------------------------------------------+
| 2. Retrieval 并行召回                                                                 |
+----------------------------------------------------------------------------------------+
| +------------------+  +------------------+  +------------------+  +----------------+ |
| | dense retrieval |  | sparse retrieval |  | metadata filter  |  | memory recall  | |
| | 向量相似度       |  | BM25/关键词匹配  |  | 主题/标签/版本   |  | episodic       | |
| | -> vector top-k  |  | -> chunk top-k   |  | -> filtered set  |  | semantic       | |
| |                  |  |                  |  |                  |  | procedural     | |
| +------------------+  +------------------+  +------------------+  +----------------+ |
|           \                  |                    /                    /              |
|            \                 |                   /                    /               |
|             +---------------------------------------------------------------+         |
|             | RRF merge + dedupe + normalize                                |         |
|             | - 融合多路候选                                                |         |
|             | - 去重                                                        |         |
|             | - 统一输出结构                                                |         |
|             +---------------------------------------------------------------+         |
+----------------------------------------------------------------------------------------+
  |
  v
+------------------------------------------------------------+
| 3. Rerank / Evidence / Citation                           |
| - rerank                                                  |
| - evidence select                                         |
| - citation builder                                        |
+------------------------------------------------------------+
  |
  v
+------------------------------------------------------------+
| 4. Answer Compose                                         |
| - 结合证据生成回答                                        |
| - 生成最终 SSE                                            |
+------------------------------------------------------------+
```

这个流程的关键点是：

- `query rewrite` 不是单一路径，而是语义、关键词、参考对象、约束条件并行处理后再合并
- `retrieval` 不是单一检索，而是 dense、sparse、metadata、memory 四路并行召回
- `memory recall` 主召回通道分三类长期记忆：`episodic`、`semantic`、`procedural`
- 引用信息在回答生成前就已经被选好，不是最后补一段脚注

#### 2.2.2 记忆机制流程

```text
用户新消息 / 工具结果 / 检索结果
  |
  v
+----------------------------------------------------------------------------------+
| L1. 感知层 / Sensory Buffer                                                     |
| - 接收原始输入                                                                  |
| - 暂存本轮 token / 事件                                                         |
| - 保存短暂上下文碎片                                                            |
+----------------------------------------------------------------------------------+
  |
  v
+----------------------------------------------------------------------------------+
| L2. 短期层 / Short-Term Memory                                                  |
| - 当前 turn 的 intent                                                           |
| - slots / recent entities                                                       |
| - 临时工具结果                                                                  |
| - 当前检索计划                                                                  |
+----------------------------------------------------------------------------------+
  |
  v
+----------------------------------------------------------------------------------+
| L3. 会话层 / Session Memory                                                     |
| - current_topic                                                                 |
| - pending_clarification                                                         |
| - user_preferences                                                              |
| - history_summary                                                               |
| - active_plan_id                                                                |
+----------------------------------------------------------------------------------+
  |
  v
+----------------------------------------------------------------------------------------+
| L4. 长期主记忆 / Long-Term Core                                                   |
+----------------------------------------------------------------------------------------+
| +------------------+  +------------------+  +------------------+                    |
| | episodic memory  |  | semantic memory  |  | procedural memory |                   |
| | 会话经历/任务过程 |  | 稳定事实/规则    |  | 操作习惯/步骤      |                   |
| | 某轮问答/某次计划 |  | 概念/知识结论    |  | 固定执行模式       |                   |
| +------------------+  +------------------+  +------------------+                    |
|           \                  |                    /                                  |
|            \                 |                   /                                   |
|             +--------------------------------------------------------------+         |
|             | long-term merge / conflict / supersede                       |         |
|             +--------------------------------------------------------------+         |
+----------------------------------------------------------------------------------------+
  |
  +---------------------------------+---------------------------------+--------------------------------+
  |                                 |                                 |                                |
  v                                 v                                 v
+--------------------------------+ +--------------------------------+ +------------------------------+
| 读路径 / retrieval injection  | | 写路径 / candidate extraction  | | 辅助状态型记忆               |
| - 从长期层召回                | | - 提取可沉淀信息               | | - preference profile         |
| - 注入 prompt/state/tool/rag  | | - 稳定性判断                   | | - entity store              |
| - 参与当前轮回答              | | - 冲突检查 / consolidation     | | - mastery store             |
+--------------------------------+ +--------------------------------+ +------------------------------+
                                   |
                                   v
                        +----------------------------------+
                        | persistence                      |
                        | - Redis session truth            |
                        | - PostgreSQL structured facts    |
                        | - Qdrant semantic memory         |
                        +----------------------------------+
```

这个流程的关键点是：

- 记忆不是一坨混在一起，而是按四层分工：感知、短期、会话、长期
- 长期主记忆再细分成三类：`episodic`、`semantic`、`procedural`
- `preference`、`entity`、`mastery` 在实现上也参与记忆系统，但更接近辅助状态型存储
- 读路径负责“把过去拿回来”，写路径负责“把现在沉淀下去”
- 长期记忆写入前会先做候选筛选、稳定性判断和冲突合并

#### 2.2.3 图编排逻辑

```text
+------------------------------------------------------------+
| create_app()                                               |
| FastAPI / CompatFastAPI / fallback ASGI                    |
+------------------------------------------------------------+
  |
  v
+------------------------------------------------------------+
| create_api_router()                                        |
| register: chat / feedback / memory / quiz / session / plan |
+------------------------------------------------------------+
  |
  v
+------------------------------------------------------------+
| LearningAgentService                                       |
| - 统一装配依赖                                             |
| - 统一组织用例                                             |
+------------------------------------------------------------+
  |
  +-----------------------+-----------------------+-----------------------+
  |                       |                       |                       |
  v                       v                       v
chat_workflow          quiz_generation        study_plan_generation
  |                       |                       |
  v                       v                       v
+------------------------------------------------------------+
| workflow builder                                           |
| - build graph                                              |
| - choose branches                                          |
+------------------------------------------------------------+
  |
  v
+------------------------------------------------------------+
| workflow runner                                            |
| - sequential                                               |
| - conditional                                              |
| - parallel                                                 |
+------------------------------------------------------------+
  |
  v
+----------------------------------------------------------------------------------+
| subgraphs                                                                         |
| +--------------+  +--------------+  +--------------+  +------------------------+ |
| | understand   |  | rag          |  | tool         |  | memory                 | |
| | turn         |  | subgraph     |  | subgraph     |  | subgraph               | |
| +--------------+  +--------------+  +--------------+  +------------------------+ |
+----------------------------------------------------------------------------------+
  |
  v
+------------------------------------------------------------+
| SSE envelope                                               |
| client receives stream                                     |
+------------------------------------------------------------+
```

这个流程的关键点是：

- `router` 只负责挂路由，不负责业务推理
- `LearningAgentService` 负责把不同 API 用例统一到同一套依赖和状态上
- `workflow builder` 负责“搭图”，`workflow runner` 负责“跑图”
- `subgraphs` 是真正承载并行与条件分支的地方

#### 2.2.4 一次完整聊天的组合流程

```text
+------------------------------------------------------------+
| HTTP request                                               |
+------------------------------------------------------------+
  |
  v
+------------------------------------------------------------+
| API Router -> Application Service                         |
+------------------------------------------------------------+
  |
  +------------------------+------------------------+------------------------+------------------------+
  |                        |                        |                        |
  v                        v                        v                        v
understand turn         RAG branch               tool branch              memory branch
  |                        |                        |                        |
  +------------------------+------------------------+------------------------+
                              |
                              v
                     +----------------------------------+
                     | compose final answer             |
                     | persist session / memory         |
                     | emit SSE                         |
                     +----------------------------------+
```

## 3. 技术栈

Python 服务主要依赖：

- Python 3.11
- FastAPI
- Uvicorn
- PostgreSQL
- Redis
- Qdrant
- OpenAI
- 轻量内存回退实现
- SSE 流式输出

## 4. 代码结构

Python 服务的核心目录在：

- `learning-agent-service/src/learning_agent_service/api`
- `learning-agent-service/src/learning_agent_service/application`
- `learning-agent-service/src/learning_agent_service/config`
- `learning-agent-service/src/learning_agent_service/domain`
- `learning-agent-service/src/learning_agent_service/infrastructure`
- `learning-agent-service/src/learning_agent_service/memory`
- `learning-agent-service/src/learning_agent_service/rag`
- `learning-agent-service/src/learning_agent_service/tools`

可以把它理解成下面几层：

- `api/`：HTTP 接口、SSE 协议、鉴权、DTO
- `application/`：用例编排和工作流执行
- `domain/`：领域模型
- `infrastructure/`：数据库、向量库、外部模型和适配器
- `memory/`：会话记忆与学习状态
- `rag/`：检索增强生成相关能力
- `tools/`：工具调用与辅助能力

## 5. 核心职责

### 5.1 聊天流

最核心的能力是聊天流接口。

公开接口：

- `POST /internal/v1/chat/stream`

这个接口不是简单返回一段文本，而是按 SSE 逐步输出：

- `ack`
- 中间事件
- `final` / `clarification_card` / `error`

它适合做学习助手的实时问答，也适合做需要中途展示状态的交互。

### 5.2 测验生成

公开接口：

- `POST /internal/v1/quiz/generate`

这个接口负责把学习上下文转成测验题目，属于学习助手的衍生能力。

### 5.3 学习计划生成

公开接口：

- `POST /internal/v1/study-plan/generate`

这个接口负责把学习目标、会话上下文和记忆信息转成学习计划。

### 5.4 会话状态查询

公开接口：

- `GET /internal/v1/session/{session_id}/state`

它用于恢复会话状态、回放上下文和继续推理。

### 5.5 记忆与反馈

Python 服务还维护学习相关的记忆系统和反馈系统。

公开接口包括：

- `/internal/v1/memory/records`
- `/internal/v1/memory/candidates`
- `/internal/v1/memory/traces`
- `/internal/v1/feedback/report`
- `/internal/v1/feedback/samples`

这些能力帮助服务把对话里的有价值信息沉淀下来，而不是每一轮都从零开始。

## 6. 内部运行模型

Python 服务的运行逻辑可以分成五层：

### 6.1 API 边界

这一层负责：

- 请求校验
- DTO 解析
- 鉴权
- SSE 封装
- 错误转换

### 6.2 Application 层

这一层负责：

- 聊天用例
- 测验用例
- 学习计划用例
- 会话查询用例
- 工作流服务装配

### 6.3 Workflow 层

这一层负责：

- 运行聊天推理图
- 组织子图
- 维护 turn 级别的执行状态
- 串联检索、工具调用和回答生成

### 6.4 Capability 层

这一层负责把能力拆成几个可组合的模块：

- RAG
- Memory
- Tools

### 6.5 Infrastructure 层

这一层负责对接：

- Redis
- PostgreSQL
- Qdrant
- OpenAI
- 本地回退实现

## 7. 运行时特性

### 7.1 SSE 约定

聊天流的典型生命周期是：

```text
ack
-> 中间事件若干
-> 一个终态事件
```

常见终态包括：

- `final`
- `clarification_card`
- `error`

这意味着前端可以边收边渲染，而不是等服务一次性返回整段结果。

### 7.2 运行模式

服务支持几种典型运行模式：

- `full`
- `partial`
- `dev_fallback`

这让它可以在本地开发、半依赖环境和完整环境里分别工作。

### 7.3 依赖策略

从环境角度看，Python 服务更偏向“可降级运行”：

- Redis 用于会话与短期状态
- PostgreSQL 用于持久化结构化数据
- Qdrant 用于检索索引
- OpenAI 用于模型调用

如果其中一部分不可用，服务可以根据配置走回退路径。

## 8. 配置要点

Python 服务配置模板在：

- [`learning-agent-service/.env.example`](./learning-agent-service/.env.example)

重点字段：

- `LEARNING_AGENT_INTERNAL_API_TOKEN`
- `LEARNING_AGENT_PREFER_REAL_ADAPTERS`
- `LEARNING_AGENT_ALLOW_IN_MEMORY_FALLBACK`
- `LEARNING_AGENT_POSTGRES_DSN`
- `LEARNING_AGENT_REDIS_URL`
- `LEARNING_AGENT_QDRANT_URL`
- `OPENAI_API_KEY`
- `LEARNING_AGENT_OPENAI_RESPONSES_MODEL`

其中最关键的是：

- `LEARNING_AGENT_INTERNAL_API_TOKEN` 必须和 Java 后端的 `agent.python.internal-token` 一致
- `LEARNING_AGENT_PREFER_REAL_ADAPTERS=false` 适合先跑通开发链路
- `LEARNING_AGENT_ALLOW_IN_MEMORY_FALLBACK=true` 适合依赖没完全配齐时先启动

## 9. 启动方式

### 9.1 安装依赖

```powershell
cd D:\javacode\ai-code-mother\learning-agent-service
pip install -e ".[dev]"
```

### 9.2 复制环境变量

```powershell
cd D:\javacode\ai-code-mother\learning-agent-service
Copy-Item .env.example .env
```

### 9.3 启动服务

```powershell
cd D:\javacode\ai-code-mother\learning-agent-service
uvicorn app:app --reload --host 127.0.0.1 --port 9000
```

### 9.4 根目录一键启动

如果你想和 Java、前端一起启动，直接用根目录脚本：

```bash
sh ./quick-start.sh
```

## 10. 常用访问地址

- Python 服务健康检查：`http://127.0.0.1:9000/health`
- Python 服务文档：`http://127.0.0.1:9000/docs`
- Python 服务运行状态：`http://127.0.0.1:9000/ready`
- Python 服务元信息：`http://127.0.0.1:9000/meta`

## 11. 测试

当前测试可以用标准 unittest 方式跑：

```bash
python -m unittest discover -s learning-agent-service/tests -p "test_*.py"
```

建议重点关注这些测试方向：

- SSE 协议是否稳定
- 聊天流是否按预期返回终态
- 记忆和反馈接口是否可用
- 回退模式下服务是否还能启动

## 12. 排查建议

如果 Python 服务启动异常，优先看这几项：

- `app:app` 是否能正常导入
- `learning-agent-service/.env` 是否存在
- `LEARNING_AGENT_INTERNAL_API_TOKEN` 是否配置正确
- PostgreSQL / Redis / Qdrant 是否可访问
- OpenAI Key 是否缺失
- `pip install -e ".[dev]"` 是否成功
