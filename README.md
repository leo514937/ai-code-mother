# AI Code Mother

这份 README 只保留本地开发最需要的内容，并且把 Java 后端、Vue 前端、Python Agent 服务的接入方式统一写清楚。

当前项目推荐按下面的顺序启动：

1. MySQL
2. Redis
3. Java 后端
4. Vue 前端
5. Python Agent 服务

如果你只想跑基础功能，可以先只启动 `MySQL + Redis + Java 后端 + Vue 前端`。
如果你想在前端聊天页看到并使用右侧智能助手侧边栏，还需要继续启动 `learning-agent-service`。

## 1. 环境准备

1. 安装 `JDK 21`
   后端 [pom.xml](D:/javacode/ai-code-mother/pom.xml) 明确要求 `java.version=21`。

2. 安装 `MySQL 8.x`
   Java 后端默认连接：
   - 地址：`localhost:3306`
   - 数据库：`yu_ai_code_mother`

3. 安装 `Redis 6.x` 或更高版本
   Java 后端会用 Redis 做 Session、缓存和限流。
   默认连接：
   - 地址：`localhost:6379`

4. 安装 `Node.js 22 LTS`
   Vue 前端开发需要 Node。
   同时后端在“部署 Vue 应用”时也会调用 `npm install` 和 `npm run build`，所以后端机器最好也能执行 `npm`。

5. 安装 `Python 3.11`
   `learning-agent-service` 需要 Python 3.11。

6. 准备 AI Key
   当前仓库里有两条 AI 相关链路：
   - Java 后端主流程：需要 `DeepSeek / DashScope / Pexels` 等配置
   - Python Agent 服务：推荐准备 `OpenAI API Key`

7. 可选安装 `PostgreSQL` 和 `Qdrant`
   Python Agent 服务支持“轻量回退模式”和“完整模式”。
   - 轻量回退模式：不依赖 PostgreSQL / Qdrant 也能启动
   - 完整模式：再补 PostgreSQL / Qdrant，能力更完整

## 2. 环境配置

1. 初始化 Java 后端数据库

   先在 MySQL 中执行基础表结构：

   ```sql
   source D:/javacode/ai-code-mother/sql/create_table.sql;
   ```

   这会创建：
   - `user`
   - `app`
   - `chat_history`

   如果你要启用前端右侧 Python Agent 侧边栏，再额外执行：

   ```sql
   source D:/javacode/ai-code-mother/sql/agent_sidebar_init.sql;
   ```

   这会创建：
   - `agent_thread`
   - `agent_message`
   - `agent_turn_audit`

2. 修改 Java 后端配置文件

   文件位置：
   [src/main/resources/application.yml](D:/javacode/ai-code-mother/src/main/resources/application.yml)

   当前已经为本地联调预设好了 Agent 侧边栏配置：

   ```yml
   spring:
     datasource:
       url: jdbc:mysql://localhost:3306/yu_ai_code_mother
       username: root
       password: 12345678
     data:
       redis:
         host: localhost
         port: 6379

   server:
     port: 8123
     servlet:
       context-path: /api

   agent:
     sidebar:
       enabled: true
     python:
       base-url: http://127.0.0.1:9000
       internal-token: local-learning-agent-token
   ```

   你需要重点确认：
   - `spring.datasource.username`
   - `spring.datasource.password`
   - `spring.data.redis.host`
   - `spring.data.redis.port`
   - AI Key 是否替换成你自己的真实值

3. 检查 Vue 前端配置

   前端目录：
   [yu-ai-code-mother-frontend](D:/javacode/ai-code-mother/yu-ai-code-mother-frontend)

   默认开发环境已经配置好了：
   - [yu-ai-code-mother-frontend/.env.development](D:/javacode/ai-code-mother/yu-ai-code-mother-frontend/.env.development)
   - [yu-ai-code-mother-frontend/vite.config.ts](D:/javacode/ai-code-mother/yu-ai-code-mother-frontend/vite.config.ts)

   当前默认值：

   ```env
   VITE_DEPLOY_DOMAIN=http://localhost
   VITE_API_BASE_URL=/api
   ```

   并且 Vite 代理已把 `/api` 转发到 `http://localhost:8123`，因此前端不用额外直连 Python 服务，前端只需要请求 Java 后端的 `/api/agent/**` 接口即可。

4. 配置 Python Agent 服务

   Python 服务目录：
   [learning-agent-service](D:/javacode/ai-code-mother/learning-agent-service)

   先复制环境变量模板：

   ```powershell
   cd D:\javacode\ai-code-mother\learning-agent-service
   Copy-Item .env.example .env
   ```

   当前模板 [learning-agent-service/.env.example](D:/javacode/ai-code-mother/learning-agent-service/.env.example) 已经与 Java 后端默认配置对齐，重点字段如下：

   ```env
   LEARNING_AGENT_INTERNAL_API_TOKEN=local-learning-agent-token
   LEARNING_AGENT_PREFER_REAL_ADAPTERS=false
   LEARNING_AGENT_ALLOW_IN_MEMORY_FALLBACK=true
   OPENAI_API_KEY=
   OPENAI_BASE_URL=https://api.openai.com/v1
   LEARNING_AGENT_OPENAI_RESPONSES_MODEL=gpt-5.4
   ```

   说明：
   - `LEARNING_AGENT_INTERNAL_API_TOKEN` 必须和 Java 后端中的 `agent.python.internal-token` 保持一致。
   - `LEARNING_AGENT_PREFER_REAL_ADAPTERS=false` 表示优先使用本地回退实现，更适合先把链路跑通。
   - 如果你后面想接 PostgreSQL / Qdrant / OpenAI 的完整能力，再把对应连接串补齐，并把 `LEARNING_AGENT_PREFER_REAL_ADAPTERS` 调整为 `true`。

5. 理解 Java BFF 与 Python Learning API 的关系

   当前项目对 Python Learning API 的接入方式是：
   - 前端只请求 Java 后端 `/api/agent/**`
   - Java 后端再调用 Python 内部接口 `/internal/v1/**`
   - 浏览器不直接请求 Python internal API

   当前新增公开接口如下：

   ```text
   POST /api/agent/threads/{threadId}/messages/stream
   ```

   说明：
   - 前端用户侧只保留聊天流入口，不再提供任何预设测验 / 计划快捷指令。
   - Java 会根据登录用户和 `threadId` 自动补齐 Python 需要的 `user_id`、`session_id`，然后再调用 Python 内部能力。
   - Python 侧业务型 `/internal/v1/**` 接口应使用 `LEARNING_AGENT_INTERNAL_API_TOKEN` 做服务间保护，因此前端不要直接调用 Python。
   - 对前端来说，聊天侧边栏统一走 Java BFF，再由 Java 转发到 Python。

## 3. 所有启动方式

1. 启动基础依赖服务

   必须启动：
   - MySQL
   - Redis

   可选启动：
   - PostgreSQL
   - Qdrant

   其中：
   - Java 后端最低要求是 `MySQL + Redis`
   - Python Agent 在当前默认回退模式下，不强依赖 PostgreSQL / Qdrant

2. 启动 Java 后端

   推荐方式 A：使用 Maven Wrapper

   ```powershell
   cd D:\javacode\ai-code-mother
   .\mvnw.cmd spring-boot:run
   ```

   方式 B：如果你已经全局安装 Maven

   ```powershell
   cd D:\javacode\ai-code-mother
   mvn spring-boot:run
   ```

   方式 C：先打包，再运行 jar

   ```powershell
   cd D:\javacode\ai-code-mother
   .\mvnw.cmd clean package -DskipTests
   java -jar .\target\yu-ai-code-mother-0.0.1-SNAPSHOT.jar
   ```

   方式 D：IDE 直接运行主类

   主类位置：
   [src/main/java/com/yupi/yuaicodemother/YuAiCodeMotherApplication.java](D:/javacode/ai-code-mother/src/main/java/com/yupi/yuaicodemother/YuAiCodeMotherApplication.java)

   说明：
   - IDE 方式可以用，但一定要确保 Maven 依赖已正确导入。
   - 如果 IDE 方式报类路径问题，优先退回方式 A。

3. 启动 Vue 前端

   推荐方式 A：开发模式

   ```powershell
   cd D:\javacode\ai-code-mother\yu-ai-code-mother-frontend
   npm install
   npm run dev
   ```

   方式 B：构建后预览

   ```powershell
   cd D:\javacode\ai-code-mother\yu-ai-code-mother-frontend
   npm install
   npm run build
   npm run preview
   ```

   说明：
   - 本地开发联调优先使用 `npm run dev`
   - 前端不需要直接配置 Python 服务地址，统一走 Java 后端代理接口

4. 启动 Python Agent 服务

   在服务目录下直接用 uvicorn

   ```powershell
   cd D:\javacode\ai-code-mother\learning-agent-service
   pip install -e ".[dev]"
   Copy-Item .env.example .env
   uvicorn app:app --reload --host 127.0.0.1 --port 9000
   ```


   说明：
   - 只要 Python 服务启动在 `127.0.0.1:9000`，并且 `.env` 中 token 与 Java 后端一致，前端侧边栏里的聊天流和模糊意图能力都能通过 Java 后端转发访问它。

## 4. 启动顺序、验证方式和访问地址

1. 推荐启动顺序

   完整链路建议按这个顺序：

   1. MySQL
   2. Redis
   3. Java 后端
   4. Vue 前端
   5. Python Agent 服务

   如果你只想跑基础页面生成功能：

   1. MySQL
   2. Redis
   3. Java 后端
   4. Vue 前端

2. 基础功能验证方式

   按下面顺序验证：

   1. 打开前端首页：`http://localhost:5173`
   2. 打开注册页：`http://localhost:5173/user/register`
   3. 注册并登录
   4. 创建应用
   5. 输入提示词，测试 AI 代码生成
   6. 查看右侧网页预览是否正常

3. Python Agent 侧边栏验证方式

   完成以下条件后，前端聊天页会显示右侧智能助手侧边栏：

   - Java 后端已启动
   - `agent.sidebar.enabled=true`
   - Python Agent 服务已启动在 `127.0.0.1:9000`
   - Java 与 Python 的 internal token 保持一致
   - `agent_sidebar_init.sql` 已执行

   验证步骤：

   1. 进入某个应用的聊天页，例如：`/app/chat/{id}`
   2. 页面右侧应显示 Agent Sidebar
   3. 点击创建线程或直接发送消息
   4. 观察是否能收到 Python Agent 返回的流式事件

4. 聊天统一入口验证方式

   完成登录并创建线程后，可以继续验证聊天流是否正常接入：

   1. 先在聊天页创建一个线程，拿到对应的 `threadId`
   2. 通过 Java 聊天流接口发送一条普通消息，例如：

   ```http
   POST /api/agent/threads/123/messages/stream
   Content-Type: application/json

   {
     "content": "请帮我分析当前需求，并给出下一步建议。"
   }
   ```

   3. 观察页面是否持续收到 SSE 流式事件，并最终看到 assistant 回复

   说明：
   - 这里的用户入口只应该请求 Java 后端 `http://localhost:8123/api/agent/threads/{threadId}/messages/stream`
   - 不应该直接请求 Python 的 `/internal/v1/chat/stream`、`/internal/v1/quiz/generate`、`/internal/v1/study-plan/generate`、`/internal/v1/session/{session_id}/state`
   - 如果你用 Postman 或 Apifox 验证，请带上 Java 登录态 Cookie，因为聊天流仍然走 Java 的登录校验、权限校验和限流逻辑

5. 常用访问地址

   - Java 后端接口根路径：`http://localhost:8123/api`
   - Java 后端健康检查：`http://localhost:8123/api/health/`
   - Java 后端文档：`http://localhost:8123/api/doc.html`
   - Vue 前端开发地址：`http://localhost:5173`
   - Python Agent 健康检查：`http://127.0.0.1:9000/health`
   - Python Agent 文档：`http://127.0.0.1:9000/docs`

补充说明：

- 当前前端不会直接请求 Python 服务，而是通过 Java 后端的 `/api/agent/**` 接口与 Python Agent 通信。
- 当前前端不会直接调用 `quiz`、`study-plan` 的独立 REST API，而是通过聊天流发送自然语言，由 Python 在聊天工作流里识别意图并触发对应工具。
- Python internal API 应视为服务间接口，只给 Java 后端调用，不给浏览器直接调用。
- 如果你暂时不想显示右侧智能助手侧边栏，可以把 [src/main/resources/application.yml](D:/javacode/ai-code-mother/src/main/resources/application.yml) 中的 `agent.sidebar.enabled` 改回 `false`。
- 如果 Java 后端、Vue 前端、Python Agent 三者都已启动，但侧边栏仍不可用，先检查：
  - Python Agent 是否真的监听在 `127.0.0.1:9000`
  - Java 后端中的 `agent.python.internal-token` 是否与 Python `.env` 一致
  - MySQL 是否已导入 `agent_sidebar_init.sql`
