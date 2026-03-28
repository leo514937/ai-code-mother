import { computed, ref, watch, type Ref } from 'vue'
import { archiveAgentThread, createAgentThread, listAgentMessages, listAgentThreads } from '../api'
import type { AgentMessageRecord, AgentThread } from '../types'

interface UseAgentThreadsOptions {
  appId: Ref<string | number | undefined>
}

export const useAgentThreads = ({ appId }: UseAgentThreadsOptions) => {
  const threads = ref<AgentThread[]>([])
  const activeThreadId = ref<string>()
  const messageRecords = ref<AgentMessageRecord[]>([])
  const loadingThreads = ref(false)
  const loadingMessages = ref(false)
  const creatingThread = ref(false)
  const archivingThreadId = ref<string>()

  const activeThread = computed(() => {
    return threads.value.find((thread) => thread.id === activeThreadId.value)
  })

  const loadMessages = async (threadId?: string) => {
    if (!threadId) {
      messageRecords.value = []
      return
    }
    loadingMessages.value = true
    try {
      messageRecords.value = await listAgentMessages(threadId)
    } finally {
      loadingMessages.value = false
    }
  }

  const selectThread = async (threadId?: string) => {
    activeThreadId.value = threadId
    await loadMessages(threadId)
  }

  const refreshThreads = async (preferredThreadId?: string) => {
    if (!appId.value) {
      threads.value = []
      activeThreadId.value = undefined
      messageRecords.value = []
      return
    }

    loadingThreads.value = true
    try {
      const nextThreads = await listAgentThreads(appId.value)
      threads.value = nextThreads

      if (!nextThreads.length) {
        activeThreadId.value = undefined
        messageRecords.value = []
        return
      }

      const nextThreadId =
        nextThreads.find((thread) => thread.id === preferredThreadId)?.id ||
        nextThreads.find((thread) => thread.id === activeThreadId.value)?.id ||
        nextThreads[0]?.id

      await selectThread(nextThreadId)
    } finally {
      loadingThreads.value = false
    }
  }

  const createThread = async (title?: string) => {
    if (!appId.value) {
      throw new Error('Missing app context')
    }
    creatingThread.value = true
    try {
      const thread = await createAgentThread({
        appId: appId.value,
        title,
      })
      threads.value = [thread, ...threads.value.filter((item) => item.id !== thread.id)]
      activeThreadId.value = thread.id
      messageRecords.value = []
      return thread
    } finally {
      creatingThread.value = false
    }
  }

  const archiveThread = async (threadId: string) => {
    archivingThreadId.value = threadId
    try {
      await archiveAgentThread(threadId)
      const nextThreads = threads.value.filter((thread) => thread.id !== threadId)
      threads.value = nextThreads
      if (activeThreadId.value === threadId) {
        await selectThread(nextThreads[0]?.id)
      }
    } finally {
      archivingThreadId.value = undefined
    }
  }

  watch(
    appId,
    async (nextAppId) => {
      if (!nextAppId) {
        threads.value = []
        activeThreadId.value = undefined
        messageRecords.value = []
        return
      }
      await refreshThreads()
    },
    { immediate: true },
  )

  return {
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
    loadMessages,
  }
}
