# Java 服务说明

## 1. 服务定位

Java 服务是整个项目里的主后端，负责把前端的业务请求组织起来，并把应用生成、用户、聊天、部署和代理能力统一暴露给 Vue 前端。

它更像一个面向浏览器的 BFF 层，核心职责不是“单纯做 AI 推理”，而是：

- 承接登录、注册、会话和用户态管理
- 承接应用创建、编辑、删除、部署和下载
- 承接代码生成的流式响应
- 承接聊天历史与应用聊天页的主业务
- 承接右侧智能助手侧边栏的线程与消息代理
- 承接静态资源发布和健康检查

如果把项目理解成“两套对话工作区”，那么 Java 服务主要负责的是 **coding 工作区** 的完整链路，以及 **agent sidebar** 这条 Java -> Python 的转发链路。

## 2. 整体架构

下面这张图展示的是 Java 服务在整个项目中的详细位置和内部边界：

```text
+==============================================================================================================+
|                                      Java Backend (Spring Boot)                                            |
+--------------------------------------------------------------------------------------------------------------+
|  A. 外部入口层                                                                                               |
|                                                                                                              |
|   +----------------------+   +----------------------+   +----------------------+   +----------------------+  |
|   | /api/user            |   | /api/app            |   | /api/chatHistory    |   | /api/workflow        |  |
|   | 登录 / 注册 / 会话    |   | 应用管理 / 生成     |   | 聊天历史查询        |   | 通用执行 / SSE       |  |
|   +----------------------+   +----------------------+   +----------------------+   +----------------------+  |
|   +----------------------+   +----------------------+   +----------------------+                            |
|   | /api/agent           |   | /api/health         |   | /api/static         |                            |
|   | 线程 / 消息 / 记忆   |   | 健康检查            |   | 部署资源            |                            |
|   +----------------------+   +----------------------+   +----------------------+                            |
+--------------------------------------------------------------------------------------------------------------+
|  B. Controller 层                                                                                             |
|                                                                                                              |
|   AppController -> /api/app                                                                                   |
|   UserController -> /api/user                                                                                 |
|   ChatHistoryController -> /api/chatHistory                                                                   |
|   WorkflowSseController -> /api/workflow                                                                      |
|   AgentThreadController -> /api/agent                                                                         |
|   HealthController / StaticResourceController -> 基础设施接口                                                 |
|                                                                                                              |
|   这些 Controller 的共同职责是：接收 HTTP 请求、完成参数校验、组装 DTO、返回 JSON 或 SSE。                |
+--------------------------------------------------------------------------------------------------------------+
|  C. Service / 编排层                                                                                          |
|                                                                                                              |
|   AppService / AppBusinessService                                                                             |
|      -> 处理应用 CRUD、部署、下载和代码生成                                                                    |
|   UserService                                                                                                 |
|      -> 处理用户、登录态、权限和会话                                                                          |
|   ChatHistoryService                                                                                          |
|      -> 处理聊天历史读写                                                                                      |
|   WorkflowService                                                                                             |
|      -> 处理通用工作流流式执行                                                                                |
|   AgentThreadService / AgentMessageService / AgentGatewayService                                              |
|      -> 处理线程、消息、反馈、记忆和 Python 转发                                                              |
|                                                                                                              |
|   这一层把“业务规则”和“HTTP 协议”分开，避免 Controller 里堆业务逻辑。                                        |
+--------------------------------------------------------------------------------------------------------------+
|  D. Python 桥接层                                                                                             |
|                                                                                                              |
|   AgentThreadController                                                                                        |
|      -> AgentGatewayService                                                                                   |
|      -> WebClientPythonAgentClient                                                                            |
|      -> PythonAgentEventConverter                                                                             |
|      -> /internal/v1/chat/stream                                                                              |
|                                                                                                              |
|   这里负责把 Java 的线程模型、登录态和用户上下文，翻译成 Python 能理解的内部请求。                           |
+--------------------------------------------------------------------------------------------------------------+
|  E. AI / 业务能力层                                                                                            |
|                                                                                                              |
|   LangChain4j                     LangGraph4j                     DashScope                                 |
|   DeepSeek                        Redis session                  Selenium / WebDriverManager                |
|   COS 对象存储                    AOP 限流 / 统计                Knife4j / Springdoc                         |
|                                                                                                              |
|   这一层提供“怎么生成、怎么检索、怎么转发、怎么截图、怎么发布”的能力。                                       |
+--------------------------------------------------------------------------------------------------------------+
|  F. 数据与基础设施层                                                                                          |
|                                                                                                              |
|   MyBatis-Flex  -> MySQL                                                                                      |
|   Spring Session -> Redis                                                                                     |
|   Caffeine       -> 本地缓存                                                                                  |
|   Prometheus     -> 指标                                                                                      |
|   Actuator       -> 健康状态                                                                                  |
|                                                                                                              |
|   Java 侧的持久化重点是：用户、应用、聊天历史、线程、消息、审计、系统配置。                                  |
+--------------------------------------------------------------------------------------------------------------+
|  G. 外部系统                                                                                                  |
|                                                                                                              |
|   coding 页面           -> Java /api                                                                          |
|   learning 页面         -> Python /learning-api -> /internal/v1/*                                             |
|   agent sidebar 页面    -> Java /api/agent -> Python /internal/v1/*                                           |
|   Java /api/app/chat/gen/code  <->  AI 模型 / 工具 / 存储                                                     |
|                                                                                                              |
|   这部分体现的是：coding 和 sidebar 先到 Java，而 learning 页面直接走 Python 学习链路。                      |
+==============================================================================================================+
```

这张图里最重要的三条链路是：

- `coding` 页面走 Java
- `learning` 页面走 Python
- Java 侧边栏先转 Java，再由 Java 调 Python 内部接口

### 2.1 Java 侧关键请求流

下面把 Java 服务里最重要的三条请求链路单独画开：

```text
1) coding 工作区

Vue 前端
  -> /api/app/chat/gen/code
  -> Controller: AppController
  -> Service: AppService / 生成编排
  -> AI / 工具 / 资源层
  -> SSE 返回给前端

2) 应用聊天历史

Vue 前端
  -> /api/chatHistory/app/{appId}
  -> Controller: ChatHistoryController
  -> Service: ChatHistoryService
  -> MySQL
  -> JSON 返回给前端

3) 侧边栏智能助手

Vue 前端
  -> /api/agent/threads/{threadId}/messages/stream
  -> Controller: AgentThreadController
  -> Service: AgentGatewayService
  -> WebClientPythonAgentClient
  -> Python /internal/v1/chat/stream
  -> SSE 透传回前端
```

### 2.2 Java 与 Python 的协同流程图

Java 侧不负责 RAG、记忆机制和图编排的内部实现，它负责的是把浏览器请求稳定地转成 Python 能吃的内部请求，再把结果透传回去。这个协同关系可以画成下面这样：

```text
Vue 应用聊天页
  |
  | 1. 用户在侧边栏输入消息
  v
AgentThreadController
  |
  | 2. 校验登录态 / threadId / 权限 / 请求体
  v
AgentGatewayService
  |
  | 3. 装配 Java 侧线程上下文
  |    - userId
  |    - threadId
  |    - sessionId
  |    - requestId / traceId
  v
WebClientPythonAgentClient
  |
  | 4. 发送内部 HTTP 请求
  |    POST /internal/v1/chat/stream
  |    Header: internal token
  v
Python Learning Agent
  |
  | 5. 返回 SSE 流
  v
PythonAgentEventConverter
  |
  | 6. 转成 Java 统一事件模型
  v
SSE 透传给前端
```

这个流程里 Java 只做四件事：

- 接收浏览器请求
- 补齐线程和登录态上下文
- 调用 Python 内部接口
- 透传 SSE / 错误

## 3. 技术栈

Java 服务当前主要依赖这些技术：

- Java 21
- Spring Boot 3.5.x
- Spring Web / WebFlux
- Spring Session + Redis
- MyBatis-Flex
- LangChain4j
- LangGraph4j
- Knife4j / Springdoc
- Redis、MySQL
- Prometheus / Actuator
- COS 对象存储
- Selenium / WebDriverManager

## 4. 代码结构

Java 后端代码主要集中在这些目录：

- `src/main/java/com/yupi/yuaicodemother/controller`
- `src/main/java/com/yupi/yuaicodemother/agent`
- `src/main/java/com/yupi/yuaicodemother/service`
- `src/main/java/com/yupi/yuaicodemother/model`
- `src/main/java/com/yupi/yuaicodemother/config`
- `src/main/java/com/yupi/yuaicodemother/manager`

其中比较关键的模块是：

- `controller/`：对外 HTTP 接口
- `service/`：核心业务编排
- `agent/`：智能助手线程、消息、记忆、反馈和 Python 代理
- `config/`：配置装配和外部能力接入
- `model/`：实体、DTO、VO、枚举

## 5. 主要职责

### 5.1 用户与会话

Java 服务负责：

- 用户注册
- 用户登录
- 当前登录态查询
- 退出登录
- 基础的管理接口

公开前缀主要是：

- `/api/user`

### 5.2 应用生成与应用管理

Java 服务负责应用的全生命周期，包括：

- 创建应用
- 更新应用
- 删除应用
- 查询应用
- 应用分页列表
- 应用部署
- 应用下载
- 代码生成后的结果管理

公开前缀主要是：

- `/api/app`

### 5.3 聊天历史

Java 服务保存和查询应用聊天历史，支撑前端应用聊天页回放消息和继续对话。

公开前缀主要是：

- `/api/chatHistory`

### 5.4 代码生成 SSE

应用生成页的流式代码生成由 Java 提供 SSE 支持。

公开接口主要是：

- `GET /api/app/chat/gen/code`

它负责把前端提示词转成流式返回，供前端一边生成一边渲染。

### 5.5 智能助手侧边栏

Java 服务还负责右侧智能助手侧边栏的线程管理、消息流、反馈、记忆和审计。

公开前缀主要是：

- `/api/agent`

常见能力包括：

- 创建线程
- 获取线程列表
- 流式发送消息
- 获取消息列表
- 归档线程
- 提交反馈
- 读取记忆记录

其中最关键的是：

- `POST /api/agent/threads/{threadId}/messages/stream`

这条接口会由 Java 再去调用 Python 服务的内部接口。

### 5.6 工作流执行

Java 服务中还有一组工作流接口，用来承接更通用的流式执行能力。

公开前缀主要是：

- `/api/workflow`

### 5.7 健康检查与静态资源

Java 服务还提供：

- 健康检查
- 静态资源访问
- 部署后的资源文件读取

公开前缀主要是：

- `/api/health`
- `/api/static`

## 6. 配置要点

Java 服务的核心配置在：

- [`src/main/resources/application.yml`](./src/main/resources/application.yml)

关键字段主要有：

- `server.port=8123`
- `server.servlet.context-path=/api`
- `spring.datasource.*`
- `spring.data.redis.*`
- `agent.sidebar.enabled`
- `agent.python.base-url`
- `agent.python.internal-token`

其中和 Python 联动最相关的是：

- `agent.sidebar.enabled`
- `agent.python.base-url`
- `agent.python.internal-token`

这三个字段决定了 Java 是否启用右侧侧边栏，以及 Java 是否能正确转发到 Python 服务。

## 7. 典型请求流

### 7.1 coding 工作区

```text
Vue 前端输入提示词
-> Java /api/app/chat/gen/code
-> Java 编排 AI 和业务逻辑
-> Java 以 SSE 形式返回生成进度
-> 前端边收边渲染
```

### 7.2 智能助手侧边栏

```text
Vue 应用聊天页
-> Java /api/agent/threads/{threadId}/messages/stream
-> Java 校验登录态、线程和权限
-> Java 转发到 Python 内部接口
-> Python 返回 SSE
-> Java 透传给前端
```

### 7.3 应用聊天历史

```text
Vue 应用聊天页
-> Java /api/chatHistory/app/{appId}
-> Java 从数据库读取聊天记录
-> 前端回放历史消息
```

## 8. 启动方式

### 8.1 依赖

Java 服务至少需要：

- MySQL
- Redis

如果要用右侧智能助手侧边栏，还需要：

- Python Learning Agent 可达
- Java 中的 `agent.python.internal-token` 与 Python `.env` 一致

### 8.2 本地启动

```powershell
cd D:\javacode\ai-code-mother
.\mvnw.cmd spring-boot:run
```

如果你本机已经装了 Maven，也可以：

```powershell
cd D:\javacode\ai-code-mother
mvn spring-boot:run
```

### 8.3 构建后运行

```powershell
cd D:\javacode\ai-code-mother
.\mvnw.cmd clean package -DskipTests
java -jar .\target\yu-ai-code-mother-0.0.1-SNAPSHOT.jar
```

## 9. 常用访问地址

- Java 后端根路径：`http://localhost:8123/api`
- Java 健康检查：`http://localhost:8123/api/health/`
- Java 文档页面：`http://localhost:8123/api/doc.html`

## 10. 排查建议

如果 Java 服务启动后前端用不了，优先检查：

- MySQL 是否能连上
- Redis 是否能连上
- `application.yml` 里的数据库账号密码是否正确
- `agent.sidebar.enabled` 是否打开
- Python 服务是否真的监听在 `127.0.0.1:9000`
- `agent.python.internal-token` 是否和 Python 一致
