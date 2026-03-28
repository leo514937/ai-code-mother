# 项目进展文档

## 当前状态
- **Java 后端**: 已启动 (运行在 8123 端口)
- **主前端 (Vue)**: 已启动 (运行中, 代理后端 8123 端口)
- **Python 服务 (Learning Agent Service)**: **未启动**
- **智能助手侧边栏 (Agent Sidebar)**: **未开启** (Java 配置 `agent.sidebar.enabled: false`)

## 待办事项
- [ ] 启动 Python 服务 (`learning-agent-service`)
- [ ] 在 Java 后端 `application.yml` 中开启 `agent.sidebar.enabled: true`
- [ ] 验证前端侧边栏是否正常显示并与 Python 服务通信
