<template>
  <section class="message-pane">
    <div class="pane-header">
      <div>
        <div class="pane-title">知识库助手</div>
        <div class="pane-subtitle">{{ threadTitle || '请选择或新建一个会话以开始。' }}</div>
      </div>
      <a-spin v-if="loading || isStreaming" size="small" />
    </div>

    <div ref="messageContainer" class="pane-body">
      <div v-if="!hasThread" class="pane-empty">请新建会话以向智能助手提问。</div>
      <div v-else-if="!messages.length" class="pane-empty">暂无消息记录</div>
      <div v-for="message in messages" :key="message.id" class="message-row" :class="message.role">
        <div class="message-bubble" :class="message.role">
          <MarkdownRenderer v-if="message.role === 'assistant'" :content="message.content || ''" />
          <div v-else>{{ message.content }}</div>
          <div v-if="message.status === 'streaming'" class="message-status">生成中...</div>
          <div v-if="message.status === 'error'" class="message-status error">失败</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import type { AgentDisplayMessage } from '../types'

const props = defineProps<{
  messages: AgentDisplayMessage[]
  loading?: boolean
  hasThread?: boolean
  isStreaming?: boolean
  threadTitle?: string
}>()

const messageContainer = ref<HTMLElement>()

const scrollToBottom = async () => {
  await nextTick()
  if (!messageContainer.value) {
    return
  }
  messageContainer.value.scrollTop = messageContainer.value.scrollHeight
}

watch(
  () => props.messages.length,
  async () => {
    await scrollToBottom()
  },
  { immediate: true },
)

watch(
  () => props.isStreaming,
  async () => {
    await scrollToBottom()
  },
)
</script>

<style scoped>
.message-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.pane-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}

.pane-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.pane-subtitle {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}

.pane-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  gap: 12px;
  padding: 16px;
}

.pane-empty {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.message-row {
  display: flex;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 92%;
  border-radius: 16px;
  padding: 12px 14px;
  line-height: 1.6;
  font-size: 13px;
}

.message-bubble.user {
  background: rgb(var(--brand-primary-rgb));
  color: var(--text-inverse);
}

.message-bubble.assistant {
  background: var(--surface-elevated);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.message-status {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}

.message-status.error {
  color: #f87171;
}
</style>
