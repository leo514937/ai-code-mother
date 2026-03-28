<template>
  <aside class="agent-sidebar">
    <AgentThreadList
      :threads="threads"
      :active-thread-id="activeThreadId"
      :loading="loadingThreads"
      :creating="creatingThread"
      :archiving-thread-id="archivingThreadId"
      @create="handleCreateThread"
      @select="handleSelectThread"
      @archive="handleArchiveThread"
    />

    <AgentMessagePane
      :messages="displayMessages"
      :loading="loadingMessages"
      :has-thread="Boolean(activeThreadId)"
      :is-streaming="isStreaming"
      :thread-title="activeThread?.title"
    />

    <AgentClarificationCard
      :card="clarificationCard"
      :disabled="isStreaming"
      @select="handleQuickReply"
    />

    <AgentEventTimeline :items="timeline" :busy="isStreaming" />

    <div class="sidebar-composer">
      <a-alert v-if="sidebarError" type="error" show-icon :message="sidebarError" />
      <a-textarea
        v-model:value="draft"
        :auto-size="{ minRows: 3, maxRows: 5 }"
        :disabled="!appId || isStreaming"
        placeholder="请描述你的需求、背景或其他实施细节..."
        @keydown.enter="handleInputEnter"
      />
      <div class="composer-actions">
        <div class="composer-hint">Enter 发送, Shift + Enter 换行</div>
        <a-button type="primary" :loading="isStreaming" @click="handleSubmit">发送</a-button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { message } from 'ant-design-vue'
import { ref, toRef, watch } from 'vue'
import AgentClarificationCard from './AgentClarificationCard.vue'
import AgentEventTimeline from './AgentEventTimeline.vue'
import AgentMessagePane from './AgentMessagePane.vue'
import AgentThreadList from './AgentThreadList.vue'
import { useAgentStream } from '../composables/useAgentStream'
import { useAgentThreads } from '../composables/useAgentThreads'
import type { AgentDisplayMessage, AgentSseEvent } from '../types'
import { buildDisplayMessages, extractEventPrimaryText } from '../utils/agentEventReducer'

const props = defineProps<{
  appId?: string | number
}>()

const draft = ref('')
const displayMessages = ref<AgentDisplayMessage[]>([])
const sidebarError = ref('')

const {
  threads,
  activeThreadId,
  activeThread,
  messageRecords,
  loadingThreads,
  loadingMessages,
  creatingThread,
  archivingThreadId,
  refreshThreads,
  createThread,
  archiveThread,
  selectThread,
} = useAgentThreads({
  appId: toRef(props, 'appId'),
})

const {
  isStreaming,
  timeline,
  clarificationCard,
  hydrateFromRecords,
  errorMessage,
  resetStreamState,
  sendMessage,
  stopStream,
} = useAgentStream()

watch(
  () => props.appId,
  () => {
    stopStream()
    resetStreamState()
    draft.value = ''
    sidebarError.value = ''
  },
)

watch(
  messageRecords,
  (records) => {
    displayMessages.value = buildDisplayMessages(records)
    hydrateFromRecords(records)
  },
  { immediate: true },
)

watch(errorMessage, (nextErrorMessage) => {
  if (nextErrorMessage) {
    sidebarError.value = nextErrorMessage
  }
})

const appendOptimisticPair = (content: string) => {
  const assistantId = `assistant-${Date.now()}`
  displayMessages.value = [
    ...displayMessages.value,
    {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      status: 'done',
    },
    {
      id: assistantId,
      role: 'assistant',
      content: '',
      status: 'streaming',
    },
  ]
  return assistantId
}

const patchAssistantMessage = (
  assistantId: string,
  content: string,
  status: AgentDisplayMessage['status'],
) => {
  displayMessages.value = displayMessages.value.map((item) => {
    if (item.id !== assistantId) {
      return item
    }
    return {
      ...item,
      content,
      status,
    }
  })
}

const ensureThread = async () => {
  if (activeThreadId.value) {
    return activeThreadId.value
  }
  const thread = await createThread()
  return thread.id
}

const handleCreateThread = async () => {
  try {
    sidebarError.value = ''
    stopStream()
    await createThread()
  } catch (error) {
    const errorMessageText = error instanceof Error ? error.message : '新建会话失败'
    sidebarError.value = errorMessageText
    message.error(errorMessageText)
  }
}

const handleSelectThread = async (threadId: string) => {
  try {
    sidebarError.value = ''
    stopStream()
    await selectThread(threadId)
  } catch (error) {
    const errorMessageText = error instanceof Error ? error.message : '加载会话失败'
    sidebarError.value = errorMessageText
    message.error(errorMessageText)
  }
}

const handleArchiveThread = async (threadId: string) => {
  try {
    sidebarError.value = ''
    await archiveThread(threadId)
  } catch (error) {
    const errorMessageText = error instanceof Error ? error.message : '归档会话失败'
    sidebarError.value = errorMessageText
    message.error(errorMessageText)
  }
}

const processAgentEvent = (event: AgentSseEvent, assistantId: string) => {
  if (event.eventType === 'final') {
    patchAssistantMessage(
      assistantId,
      extractEventPrimaryText(event) || '助手回答已完成。',
      'done',
    )
  }

  if (event.eventType === 'error') {
    patchAssistantMessage(
      assistantId,
      extractEventPrimaryText(event) || '助手请求出错。',
      'error',
    )
  }
}

const submitWithContent = async (content: string) => {
  const trimmedContent = content.trim()
  if (!trimmedContent || isStreaming.value || !props.appId) {
    return
  }

  sidebarError.value = ''

  try {
    const threadId = await ensureThread()
    const assistantId = appendOptimisticPair(trimmedContent)
    draft.value = ''

    await sendMessage({
      threadId,
      content: trimmedContent,
      onEvent: (event) => processAgentEvent(event, assistantId),
    })

    const assistantMessage = displayMessages.value.find((item) => item.id === assistantId)
    if (assistantMessage && !assistantMessage.content) {
      patchAssistantMessage(assistantId, '助手回答已完成。', 'done')
    }

    await refreshThreads(threadId)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }
    const errorMessageText = error instanceof Error ? error.message : '发送消息失败'
    sidebarError.value = errorMessageText
    const lastAssistant = [...displayMessages.value]
      .reverse()
      .find((item) => item.role === 'assistant')
    if (lastAssistant) {
      patchAssistantMessage(lastAssistant.id, errorMessageText, 'error')
    }
    message.error(errorMessageText)
  }
}

const handleSubmit = async () => {
  await submitWithContent(draft.value)
}

const handleQuickReply = async (value: string) => {
  await submitWithContent(value)
}

const handleInputEnter = (event: KeyboardEvent) => {
  if (event.shiftKey) {
    return
  }
  event.preventDefault()
  void handleSubmit()
}
</script>

<style scoped>
.agent-sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, 0.14), transparent 28%),
    linear-gradient(180deg, #ffffff, #f8fbff 52%, #ffffff);
}

.sidebar-composer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid #eef2f7;
  background: #ffffff;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.composer-hint {
  font-size: 12px;
  color: #6b7280;
}
</style>
