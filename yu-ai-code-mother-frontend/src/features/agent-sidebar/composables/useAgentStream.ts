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
  const streamSnapshot = ref(createEmptyStreamSnapshot())
  const activeAbortController = ref<AbortController>()

  const hydrateFromRecords = (records: AgentMessageRecord[]) => {
    streamSnapshot.value = deriveStreamSnapshotFromRecords(records)
  }

  const resetStreamState = () => {
    streamSnapshot.value = createEmptyStreamSnapshot()
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
    resetStreamState()

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
            streamSnapshot.value = reduceAgentEvent(streamSnapshot.value, event)
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

  return {
    isStreaming,
    timeline: computed(() => streamSnapshot.value.timeline),
    clarificationCard: computed(() => streamSnapshot.value.clarificationCard),
    finalMessage: computed(() => streamSnapshot.value.finalMessage),
    errorMessage: computed(() => streamSnapshot.value.errorMessage),
    hydrateFromRecords,
    resetStreamState,
    stopStream,
    sendMessage,
  }
}
