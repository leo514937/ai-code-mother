import type { AgentTimelineTone } from './types'

export const AGENT_SIDEBAR_DEFAULT_TITLE = 'New Thread'

export const AGENT_THREAD_PAGE_SIZE = 50

export const AGENT_EVENT_META: Record<
  string,
  {
    label: string
    tone: AgentTimelineTone
  }
> = {
  ack: {
    label: 'Accepted',
    tone: 'info',
  },
  retrieval_started: {
    label: 'Retrieval Started',
    tone: 'info',
  },
  retrieval_result: {
    label: 'Retrieval Result',
    tone: 'success',
  },
  tool_call: {
    label: 'Tool Call',
    tone: 'warning',
  },
  tool_result: {
    label: 'Tool Result',
    tone: 'success',
  },
  clarification_card: {
    label: 'Needs Clarification',
    tone: 'warning',
  },
  final: {
    label: 'Final Answer',
    tone: 'success',
  },
  error: {
    label: 'Error',
    tone: 'error',
  },
}
