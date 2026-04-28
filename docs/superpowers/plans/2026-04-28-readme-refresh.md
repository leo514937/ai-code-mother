# README Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the root README into a concise project entry doc with a prominent quick-start path.

**Architecture:** Keep the root README focused on onboarding: what the project is, what it needs, how to start it quickly, how to start it manually, and where to look next. Use existing startup scripts as the primary fast path instead of duplicating operational detail.

**Tech Stack:** Markdown, Windows shell scripts, Maven, Vite, Python Uvicorn

---

### Task 1: Reorganize the README structure

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the old long-form content with a concise structure**

```md
# AI Code Mother

一句话介绍、目录结构、依赖环境、快速启动、手动启动、访问地址、常见问题、相关脚本。
```

- [ ] **Step 2: Verify the README still covers the three runtime pieces**

Expected coverage:
- Java 后端
- Vue 前端
- Python Learning Agent

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: refresh readme"
```

### Task 2: Add quick-start guidance

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the one-command quick start**

```md
cd D:\javacode\ai-code-mother
sh ./quick-start.sh
```

- [ ] **Step 2: Document what the quick-start script launches**

Expected list:
- MySQL / Redis / PostgreSQL / Qdrant
- Java 后端
- Python Agent
- Vue 前端

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add quick start"
```
