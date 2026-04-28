<template>
  <div id="learningAssistantPage">
    <div class="page-hero">
      <div class="hero-badge">Python Agent</div>
      <h1 class="page-title">学习助手</h1>
      <p class="page-subtitle">
        这里是独立的学习工作区，消息历史、会话列表和输入草稿都与 coding 工作区分开保存。
      </p>
    </div>

    <div class="workspace-shell">
      <AgentThreadList
        :threads="threads"
        :active-thread-id="activeSessionId"
        :loading="loadingSessions"
        :creating="creatingSession"
        :archiving-thread-id="archivingSessionId"
        :can-create="canUseLearningAssistant"
        @create="handleCreateSession"
        @select="handleSelectSession"
        @archive="handleArchiveSession"
      />

      <section class="conversation-shell">
        <div class="conversation-header">
          <div>
            <div class="conversation-title">学习对话</div>
            <div class="conversation-subtitle">
              {{ activeSession?.title || '请选择或新建一个会话以开始。' }}
            </div>
          </div>
          <a-tag color="orange">直连 Python</a-tag>
        </div>

        <AgentMessagePane
          :messages="displayMessages"
          :loading="false"
          :has-thread="Boolean(activeSessionId)"
          :is-streaming="isStreaming"
          :thread-title="activeSession?.title"
        />

        <AgentClarificationCard
          :card="clarificationCard"
          :disabled="isStreaming"
          @select="handleQuickReply"
        />

        <AgentAnswerInsights
          :final-payload="finalPayload"
          :timeline="timeline"
          :is-streaming="isStreaming"
          :trace-id="traceId"
          :turn-id="turnId"
          :session-id="sessionId"
          :workflow-version="workflowVersion"
        />

        <div class="composer-shell">
          <a-alert
            v-if="pageError"
            type="error"
            show-icon
            :message="pageError"
            class="composer-alert"
          />
          <a-textarea
            v-model:value="draft"
            :auto-size="{ minRows: 3, maxRows: 5 }"
            :disabled="!canUseLearningAssistant || isStreaming"
            placeholder="请输入你想学习的内容，例如：讲解 Vue 响应式原理"
            name="learning-assistant-input"
            autocomplete="off"
            autocorrect="off"
            autocapitalize="off"
            spellcheck="false"
            @keydown.enter="handleInputEnter"
          />
          <div class="composer-actions">
            <div class="composer-hint">Enter 发送，Shift + Enter 换行</div>
            <a-button type="primary" :loading="isStreaming" @click="handleSubmit">发送</a-button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: 'LearningAssistantPage',
})

import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { useLoginUserStore } from '@/stores/loginUser'
import { useUiPreferenceStore } from '@/stores/uiPreference'
import AgentAnswerInsights from '@/features/agent-sidebar/components/AgentAnswerInsights.vue'
import AgentClarificationCard from '@/features/agent-sidebar/components/AgentClarificationCard.vue'
import AgentMessagePane from '@/features/agent-sidebar/components/AgentMessagePane.vue'
import AgentThreadList from '@/features/agent-sidebar/components/AgentThreadList.vue'
import {
  createEmptyStreamSnapshot,
  extractEventPrimaryText,
} from '@/features/agent-sidebar/utils/agentEventReducer'
import type {
  AgentDisplayMessage,
  AgentSseEvent,
  AgentStreamSnapshot,
  AgentThread,
} from '@/features/agent-sidebar/types'
import { useLearningStream } from '@/features/learning-assistant/composables/useLearningStream'

type LearningSession = {
  id: string
  title: string
  createTime: string
  lastMessageAt?: string
  archived?: boolean
  draft: string
  messages: AgentDisplayMessage[]
  streamSnapshot: AgentStreamSnapshot
}

const router = useRouter()
const loginUserStore = useLoginUserStore()
const uiPreferenceStore = useUiPreferenceStore()

const sessions = ref<LearningSession[]>([])
const activeSessionId = ref<string>()
const loadingSessions = ref(false)
const creatingSession = ref(false)
const archivingSessionId = ref<string>()
const pageError = ref('')

const {
  isStreaming,
  timeline,
  clarificationCard,
  finalPayload,
  traceId,
  turnId,
  sessionId,
  workflowVersion,
  snapshot,
  hydrateFromSnapshot,
  resetStreamState,
  sendMessage,
  stopStream,
  errorMessage,
} = useLearningStream()

const storageKey = computed(() => {
  const userId = loginUserStore.loginUser.id ? String(loginUserStore.loginUser.id) : 'guest'
  return `ai-code-mother-learning-sessions-${userId}`
})

const canUseLearningAssistant = computed(() => Boolean(loginUserStore.loginUser.id))

const activeSession = computed(() => {
  return sessions.value.find((session) => session.id === activeSessionId.value)
})

const draft = computed({
  get: () => activeSession.value?.draft || '',
  set: (value: string) => {
    if (activeSession.value) {
      activeSession.value.draft = value
    }
  },
})

const displayMessages = computed(() => activeSession.value?.messages || [])

const threads = computed<AgentThread[]>(() => {
  return sessions.value
    .filter((session) => !session.archived)
    .map((session) => ({
      id: session.id,
      title: session.title,
      createTime: formatTime(session.createTime),
      lastMessageAt: formatTime(session.lastMessageAt),
      status: 'ACTIVE',
    }))
})

const formatTime = (value?: string) => {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    hour12: false,
  })
}

const persistSessions = () => {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(storageKey.value, JSON.stringify(sessions.value))
}

const loadSessions = () => {
  loadingSessions.value = true
  try {
    if (typeof window === 'undefined') {
      return
    }
    const raw = window.localStorage.getItem(storageKey.value)
    if (!raw) {
      sessions.value = []
      activeSessionId.value = undefined
      return
    }
    const parsed = JSON.parse(raw) as LearningSession[]
    sessions.value = Array.isArray(parsed)
      ? parsed.map((item) => ({
          id: item.id,
          title: item.title || '新会话',
          createTime: item.createTime || new Date().toISOString(),
          lastMessageAt: item.lastMessageAt,
          archived: Boolean(item.archived),
          draft: item.draft || '',
          messages: Array.isArray(item.messages) ? item.messages : [],
          streamSnapshot: item.streamSnapshot || createEmptyStreamSnapshot(),
        }))
      : []
    activeSessionId.value = sessions.value.find((session) => !session.archived)?.id
    if (activeSessionId.value) {
      const currentSession = sessions.value.find((session) => session.id === activeSessionId.value)
      hydrateFromSnapshot(currentSession?.streamSnapshot ?? createEmptyStreamSnapshot())
    } else {
      resetStreamState()
    }
  } catch (error) {
    console.error('加载学习会话失败：', error)
    sessions.value = []
    activeSessionId.value = undefined
    resetStreamState()
  } finally {
    loadingSessions.value = false
  }
}

const ensureActiveSession = async (): Promise<LearningSession> => {
  if (activeSession.value) {
    return activeSession.value
  }
  return createSession()
}

const createSession = async () => {
  if (!canUseLearningAssistant.value) {
    throw new Error('请先登录')
  }

  creatingSession.value = true
  try {
    const now = new Date().toISOString()
    const session: LearningSession = {
      id: crypto.randomUUID(),
      title: '新会话',
      createTime: now,
      lastMessageAt: now,
      draft: '',
      messages: [],
      streamSnapshot: createEmptyStreamSnapshot(),
    }
    sessions.value = [session, ...sessions.value]
    activeSessionId.value = session.id
    hydrateFromSnapshot(session.streamSnapshot)
    persistSessions()
    return session
  } finally {
    creatingSession.value = false
  }
}

const handleCreateSession = async () => {
  try {
    pageError.value = ''
    stopStream()
    await createSession()
  } catch (error) {
    const errorText = error instanceof Error ? error.message : '新建会话失败'
    pageError.value = errorText
    message.error(errorText)
  }
}

const handleSelectSession = async (sessionId: string) => {
  try {
    pageError.value = ''
    stopStream()
    activeSessionId.value = sessionId
    const session = sessions.value.find((item) => item.id === sessionId)
    hydrateFromSnapshot(session?.streamSnapshot ?? createEmptyStreamSnapshot())
  } catch (error) {
    const errorText = error instanceof Error ? error.message : '切换会话失败'
    pageError.value = errorText
    message.error(errorText)
  }
}

const handleArchiveSession = async (sessionId: string) => {
  try {
    pageError.value = ''
    archivingSessionId.value = sessionId
    const session = sessions.value.find((item) => item.id === sessionId)
    if (session) {
      session.archived = true
    }
    const nextActive = sessions.value.find((item) => !item.archived && item.id !== sessionId)
    activeSessionId.value = nextActive?.id
    if (nextActive) {
      hydrateFromSnapshot(nextActive.streamSnapshot)
    } else {
      resetStreamState()
      activeSessionId.value = undefined
    }
    persistSessions()
  } finally {
    archivingSessionId.value = undefined
  }
}

const appendOptimisticPair = (content: string, sessionId: string): string => {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    throw new Error('学习会话不存在')
  }
  const assistantId = `assistant-${Date.now()}`
  session.messages = [
    ...session.messages,
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
  session.lastMessageAt = new Date().toISOString()
  if (session.title === '新会话') {
    const title = content.trim().slice(0, 16)
    session.title = title ? (content.trim().length > 16 ? `${title}…` : title) : '新会话'
  }
  return assistantId
}

const patchAssistantMessage = (
  sessionId: string,
  assistantId: string,
  content: string,
  status: AgentDisplayMessage['status'],
) => {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    return
  }
  session.messages = session.messages.map((item) => {
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

const processAgentEvent = (event: AgentSseEvent, sessionId: string, assistantId: string) => {
  if (event.eventType === 'final') {
    patchAssistantMessage(
      sessionId,
      assistantId,
      extractEventPrimaryText(event) || '学习回答已完成。',
      'done',
    )
  }

  if (event.eventType === 'error') {
    patchAssistantMessage(
      sessionId,
      assistantId,
      extractEventPrimaryText(event) || '学习请求出错。',
      'error',
    )
  }
}

const saveSessionSnapshot = (sessionId: string) => {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    return
  }
  session.streamSnapshot = snapshot.value
  persistSessions()
}

const submitWithContent = async (content: string) => {
  const trimmedContent = content.trim()
  if (!trimmedContent || isStreaming.value) {
    return
  }
  if (!canUseLearningAssistant.value) {
    message.warning('请先登录')
    await router.push('/user/login')
    return
  }

  pageError.value = ''

  try {
    const session = await ensureActiveSession()
    const sessionId = String(session.id)
    const assistantId = appendOptimisticPair(trimmedContent, sessionId)
    session.draft = ''
    persistSessions()

    await sendMessage({
      sessionId,
      userId: String(loginUserStore.loginUser.id),
      content: trimmedContent,
      onEvent: (event) => processAgentEvent(event, sessionId, assistantId),
    })

    const assistantMessage = session.messages.find((item) => item.id === assistantId)
    if (assistantMessage && !assistantMessage.content) {
      patchAssistantMessage(sessionId, assistantId, '学习回答已完成。', 'done')
    }
    session.lastMessageAt = new Date().toISOString()
    saveSessionSnapshot(sessionId)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }
    const errorText = error instanceof Error ? error.message : '发送消息失败'
    pageError.value = errorText
    const currentSessionId = activeSessionId.value
    const currentSession = currentSessionId
      ? sessions.value.find((item) => item.id === currentSessionId)
      : undefined
    const lastAssistant = currentSession?.messages
      ? [...currentSession.messages].reverse().find((item) => item.role === 'assistant')
      : undefined
    if (lastAssistant) {
      patchAssistantMessage(currentSessionId || '', lastAssistant.id, errorText, 'error')
    }
    if (currentSessionId) {
      saveSessionSnapshot(currentSessionId)
    }
    message.error(errorText)
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

watch(errorMessage, (nextErrorMessage) => {
  if (nextErrorMessage) {
    pageError.value = nextErrorMessage
  }
})

watch(
  storageKey,
  () => {
    loadSessions()
  },
  { immediate: true },
)

watch(
  activeSessionId,
  (nextActiveSessionId) => {
    const session = sessions.value.find((item) => item.id === nextActiveSessionId)
    hydrateFromSnapshot(session?.streamSnapshot ?? createEmptyStreamSnapshot())
  },
  { immediate: true },
)

watch(
  sessions,
  () => {
    persistSessions()
  },
  { deep: true },
)

onMounted(() => {
  uiPreferenceStore.setUiMode('learning')
})
</script>

<style scoped>
#learningAssistantPage {
  min-height: calc(100vh - 64px);
  padding: 24px;
  background:
    linear-gradient(180deg, rgba(var(--brand-primary-rgb), 0.08), transparent 42%),
    radial-gradient(circle at top right, rgba(var(--brand-secondary-rgb), 0.12), transparent 30%),
    var(--app-bg);
  color: var(--text-primary);
}

.page-hero {
  max-width: 1200px;
  margin: 0 auto 18px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(var(--brand-primary-rgb), 0.12);
  color: rgb(var(--brand-primary-rgb));
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.page-title {
  margin: 0;
  font-size: 30px;
  color: var(--text-primary);
}

.page-subtitle {
  margin: 10px 0 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.workspace-shell {
  max-width: 1200px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
}

.workspace-shell :deep(.thread-list) {
  height: 100%;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid var(--border-color);
  background: var(--surface-elevated);
}

.conversation-shell {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 180px);
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid var(--border-color);
  background: var(--surface-elevated);
  box-shadow: 0 18px 50px var(--shadow-color);
}

.conversation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color);
}

.conversation-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.conversation-subtitle {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}

.composer-shell {
  padding: 16px 18px 18px;
  border-top: 1px solid var(--border-color);
  background: var(--surface-elevated);
}

.composer-alert {
  margin-bottom: 12px;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.composer-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

@media (max-width: 1024px) {
  .workspace-shell {
    grid-template-columns: 1fr;
  }

  .conversation-shell {
    min-height: auto;
  }
}

@media (max-width: 768px) {
  #learningAssistantPage {
    padding: 16px;
  }

  .page-title {
    font-size: 24px;
  }
}
</style>
