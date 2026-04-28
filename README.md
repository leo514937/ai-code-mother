# AI Code Mother

一个支持代码生成、应用聊天和学习助手的全栈项目。

仓库里目前主要包含三块：
- Java 后端：负责应用生成、登录、聊天和代理转发
- Vue 前端：负责主站界面、应用对话页和学习助手页面
- Python Learning Agent：负责学习助手的独立对话与流式能力

## 快速启动

如果你只想先把项目跑起来，优先执行根目录下的快速启动脚本。

```bash
sh ./quick-start.sh
```

这个脚本会自动做这些事：
- 启动基础依赖服务
- 启动 Java 后端
- 启动 Python Learning Agent
- 启动 Vue 前端
- 自动打开浏览器

默认打开地址：

```text
http://localhost:5173/
```

说明：
- 在 Windows 上建议使用 Git Bash、WSL 或其他 bash 环境执行
- 如果你遇到权限问题，先确认 `up.sh` 能正常执行
- 如果只想先验证基础能力，也可以手动分步启动，见下方说明

## 项目结构

```text
.
├── src/                         # Java 后端
├── yu-ai-code-mother-frontend/  # Vue 前端
├── learning-agent-service/      # Python Learning Agent
├── quick-start.sh               # 一键启动脚本
├── up.sh                        # 基础依赖启动脚本
└── sql/                         # 初始化 SQL
```

## 环境要求

- JDK 21
- Node.js 22 LTS
- Python 3.11
- MySQL 8.x
- Redis 6.x 或更高版本
- 可选：PostgreSQL、Qdrant

如果你要完整使用学习助手能力，还需要准备相应的 AI Key。

## 手动启动

### 1. 启动基础依赖

根目录下的 `up.sh` 会处理 MySQL、Redis、PostgreSQL 和 Qdrant。

```bash
sh ./up.sh
```

说明：
- `up.sh` 会优先尝试重启可用的服务
- 如果本机没有 PostgreSQL 或 Qdrant，也可以先不装，项目仍可先跑基础流程

### 2. 启动 Java 后端

```powershell
cd D:\javacode\ai-code-mother
.\mvnw.cmd spring-boot:run
```

或者使用本机 Maven：

```powershell
cd D:\javacode\ai-code-mother
mvn spring-boot:run
```

后端默认地址：

```text
http://localhost:8123/api
```

### 3. 启动 Vue 前端

```powershell
cd D:\javacode\ai-code-mother\yu-ai-code-mother-frontend
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

### 4. 启动 Python Learning Agent

```powershell
cd D:\javacode\ai-code-mother\learning-agent-service
Copy-Item .env.example .env
pip install -e ".[dev]"
uvicorn app:app --reload --host 127.0.0.1 --port 9000
```

Python 服务默认地址：

```text
http://127.0.0.1:9000
```

## 页面入口

- 首页：`http://localhost:5173/`
- 应用聊天页：`http://localhost:5173/app/chat/:id`
- 学习助手页：`http://localhost:5173/learning`
- 注册页：`http://localhost:5173/user/register`
- 登录页：`http://localhost:5173/user/login`

## 常用地址

- Java 后端健康检查：`http://localhost:8123/api/health/`
- Java 后端文档：`http://localhost:8123/api/doc.html`
- Python Learning Agent 健康检查：`http://127.0.0.1:9000/health`
- Python Learning Agent 文档：`http://127.0.0.1:9000/docs`

## 主要环境变量

### 前端

文件：[yu-ai-code-mother-frontend/.env.development](./yu-ai-code-mother-frontend/.env.development)

```env
VITE_DEPLOY_DOMAIN=http://localhost
VITE_API_BASE_URL=/api
VITE_AGENT_API_BASE_URL=/api/agent
VITE_LEARNING_API_BASE_URL=/learning-api
```

### Java 后端

文件：[src/main/resources/application.yml](./src/main/resources/application.yml)

重点关注：
- MySQL 连接信息
- Redis 连接信息
- `agent.sidebar.enabled`
- `agent.python.base-url`
- `agent.python.internal-token`

### Python Learning Agent

文件：[learning-agent-service/.env.example](./learning-agent-service/.env.example)

重点关注：
- `LEARNING_AGENT_INTERNAL_API_TOKEN`
- `LEARNING_AGENT_PREFER_REAL_ADAPTERS`
- `LEARNING_AGENT_ALLOW_IN_MEMORY_FALLBACK`
- `OPENAI_API_KEY`
- `LEARNING_AGENT_OPENAI_RESPONSES_MODEL`

## 数据库初始化

先执行 Java 后端基础表结构：

```sql
source D:/javacode/ai-code-mother/sql/create_table.sql;
```

如果你要使用右侧智能助手侧边栏，再执行：

```sql
source D:/javacode/ai-code-mother/sql/agent_sidebar_init.sql;
```

## 常见问题

### 1. 一键启动失败

- 先确认你是在 bash 环境里执行 `quick-start.sh`
- 再确认 `up.sh` 可以正常启动 MySQL 和 Redis
- 如果端口被占用，先停掉已有的 `8123`、`5173`、`9000` 端口进程

### 2. 学习助手页面打不开

- 检查 Python 服务是否启动在 `127.0.0.1:9000`
- 检查前端 `VITE_LEARNING_API_BASE_URL`
- 检查 `learning-agent-service/.env` 是否已正确配置

### 3. 右侧智能助手不显示

- 检查 Java 后端中的 `agent.sidebar.enabled`
- 检查 Java 后端是否能连到 Python 服务
- 检查 `agent_sidebar_init.sql` 是否已经执行

## 相关脚本

- [quick-start.sh](./quick-start.sh)
- [up.sh](./up.sh)
