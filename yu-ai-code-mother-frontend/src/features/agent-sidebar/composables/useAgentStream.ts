import { computed, ref } from 'vue'
import { streamAgentMessage } from '../api'
import type { AgentMessageRecord, AgentSseEvent } from '../types'
import {
  createEmptyStreamSnapshot,
  deriveStreamSnapshotFromRecords,
  normalizeAgentSseEvent,
  reduceAgentEvent,
} from '../utils/agentEventReducer'

export const useAgentStream = () => {
  const isStreaming = ref(false)
  const persistedSnapshot = ref(createEmptyStreamSnapshot())
  const liveSnapshot = ref(createEmptyStreamSnapshot())
  const activeAbortController = ref<AbortController>()

  const hydrateFromRecords = (records: AgentMessageRecord[]) => {
    persistedSnapshot.value = deriveStreamSnapshotFromRecords(records)
    liveSnapshot.value = createEmptyStreamSnapshot()
  }

  const clearLiveStreamState = () => {
    liveSnapshot.value = createEmptyStreamSnapshot()
  }

  const resetStreamState = () => {
    persistedSnapshot.value = createEmptyStreamSnapshot()
    clearLiveStreamState()
  }

  const stopStream = () => {
    activeAbortController.value?.abort()
  }

  const sendMessage = async (options: {
    threadId: string
    content: string
    onEvent?: (event: AgentSseEvent) => void
  }) => {
    stopStream()
    clearLiveStreamState()

    const controller = new AbortController()
    activeAbortController.value = controller
    isStreaming.value = true

    try {
      await streamAgentMessage(
        options.threadId,
        { content: options.content },
        {
          signal: controller.signal,
          onEvent: (rawEvent) => {
            const event = normalizeAgentSseEvent(rawEvent.event, rawEvent.data)
            liveSnapshot.value = reduceAgentEvent(liveSnapshot.value, event)
            options.onEvent?.(event)
          },
        },
      )
    } finally {
      if (activeAbortController.value === controller) {
        activeAbortController.value = undefined
      }
      isStreaming.value = false
    }
  }

  const mergedSnapshot = computed(() => ({
    timeline: [...persistedSnapshot.value.timeline, ...liveSnapshot.value.timeline],
    clarificationCard:
      liveSnapshot.value.clarificationCard ?? persistedSnapshot.value.clarificationCard,
    finalMessage: liveSnapshot.value.finalMessage || persistedSnapshot.value.finalMessage,
    errorMessage: liveSnapshot.value.errorMessage || persistedSnapshot.value.errorMessage,
  }))

  return {
    isStreaming,
    timeline: computed(() => mergedSnapshot.value.timeline),
    clarificationCard: computed(() => mergedSnapshot.value.clarificationCard),
    finalMessage: computed(() => mergedSnapshot.value.finalMessage),
    errorMessage: computed(() => mergedSnapshot.value.errorMessage),
    hydrateFromRecords,
    resetStreamState,
    stopStream,
    sendMessage,
  }
}
