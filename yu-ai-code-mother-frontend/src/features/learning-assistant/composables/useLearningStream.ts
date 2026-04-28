import { computed, ref } from 'vue'
import { streamLearningMessage } from '../api'
import type {
  AgentRawSsePacket,
  AgentSseEvent,
  AgentStreamSnapshot,
} from '@/features/agent-sidebar/types'
import {
  createEmptyStreamSnapshot,
  normalizeAgentSseEvent,
  reduceAgentEvent,
} from '@/features/agent-sidebar/utils/agentEventReducer'

export const useLearningStream = () => {
  const isStreaming = ref(false)
  const persistedSnapshot = ref<AgentStreamSnapshot>(createEmptyStreamSnapshot())
  const liveSnapshot = ref<AgentStreamSnapshot>(createEmptyStreamSnapshot())
  const activeAbortController = ref<AbortController>()

  const hydrateFromSnapshot = (snapshot?: AgentStreamSnapshot | null) => {
    persistedSnapshot.value = snapshot ? { ...snapshot } : createEmptyStreamSnapshot()
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
    sessionId: string
    userId: string
    content: string
    onEvent?: (event: AgentSseEvent) => void
  }) => {
    stopStream()
    clearLiveStreamState()

    const controller = new AbortController()
    activeAbortController.value = controller
    isStreaming.value = true

    const traceId = crypto.randomUUID()

    try {
      await streamLearningMessage(
        {
          user_id: options.userId,
          session_id: options.sessionId,
          trace_id: traceId,
          message: options.content,
        },
        {
          signal: controller.signal,
          onEvent: (rawEvent: AgentRawSsePacket) => {
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

    return traceId
  }

  const mergedSnapshot = computed(() => ({
    timeline: [...persistedSnapshot.value.timeline, ...liveSnapshot.value.timeline],
    clarificationCard:
      liveSnapshot.value.clarificationCard ?? persistedSnapshot.value.clarificationCard,
    finalMessage: liveSnapshot.value.finalMessage || persistedSnapshot.value.finalMessage,
    errorMessage: liveSnapshot.value.errorMessage || persistedSnapshot.value.errorMessage,
    finalPayload: liveSnapshot.value.finalPayload ?? persistedSnapshot.value.finalPayload,
    traceId: liveSnapshot.value.traceId || persistedSnapshot.value.traceId,
    turnId: liveSnapshot.value.turnId || persistedSnapshot.value.turnId,
    sessionId: liveSnapshot.value.sessionId || persistedSnapshot.value.sessionId,
    workflowVersion:
      liveSnapshot.value.workflowVersion || persistedSnapshot.value.workflowVersion,
  }))

  return {
    isStreaming,
    timeline: computed(() => mergedSnapshot.value.timeline),
    clarificationCard: computed(() => mergedSnapshot.value.clarificationCard),
    finalMessage: computed(() => mergedSnapshot.value.finalMessage),
    errorMessage: computed(() => mergedSnapshot.value.errorMessage),
    finalPayload: computed(() => mergedSnapshot.value.finalPayload),
    traceId: computed(() => mergedSnapshot.value.traceId),
    turnId: computed(() => mergedSnapshot.value.turnId),
    sessionId: computed(() => mergedSnapshot.value.sessionId),
    workflowVersion: computed(() => mergedSnapshot.value.workflowVersion),
    snapshot: computed(() => mergedSnapshot.value),
    hydrateFromSnapshot,
    resetStreamState,
    stopStream,
    sendMessage,
  }
}
