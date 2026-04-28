<template>
  <section class="thread-list">
    <div class="thread-header">
      <div>
        <div class="header-title">智能助手会话</div>
        <div class="header-subtitle">与代码生成主会话相互独立</div>
      </div>
      <a-button
        type="primary"
        size="small"
        :loading="creating"
        :disabled="!canCreate"
        @click="$emit('create')"
      >
        新建
      </a-button>
    </div>

    <div class="thread-body">
      <div v-if="loading && !threads.length" class="thread-empty">加载中...</div>
      <div v-else-if="!threads.length" class="thread-empty">暂无会话记录</div>
      <button
        v-for="thread in threads"
        :key="thread.id"
        class="thread-item"
        :class="{ active: thread.id === activeThreadId }"
        type="button"
        @click="$emit('select', thread.id)"
      >
        <div class="thread-item-main">
          <div class="thread-title">{{ thread.title || '新会话' }}</div>
          <div class="thread-time">{{ thread.lastMessageAt || thread.createTime || '' }}</div>
        </div>
        <a-button
          type="text"
          size="small"
          danger
          :loading="archivingThreadId === thread.id"
          @click.stop="$emit('archive', thread.id)"
        >
          归档
        </a-button>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { AgentThread } from '../types'

defineProps<{
  threads: AgentThread[]
  activeThreadId?: string
  loading?: boolean
  creating?: boolean
  archivingThreadId?: string
  canCreate?: boolean
}>()

defineEmits<{
  (event: 'create'): void
  (event: 'select', threadId: string): void
  (event: 'archive', threadId: string): void
}>()
</script>

<style scoped>
.thread-list {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border-color);
}

.thread-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
}

.header-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.header-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.thread-body {
  display: grid;
  gap: 8px;
  padding: 0 16px 16px;
}

.thread-empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.thread-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid var(--border-color);
  background: var(--surface-elevated);
  text-align: left;
  cursor: pointer;
}

.thread-item.active {
  border-color: rgb(var(--brand-primary-rgb));
  box-shadow: 0 0 0 3px rgba(var(--brand-primary-rgb), 0.14);
}

.thread-item-main {
  min-width: 0;
  flex: 1;
}

.thread-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.thread-time {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
