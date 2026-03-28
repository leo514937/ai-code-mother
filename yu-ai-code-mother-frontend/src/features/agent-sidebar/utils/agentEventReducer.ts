import { AGENT_EVENT_META, AGENT_SIDEBAR_DEFAULT_TITLE } from '../constants'
import type {
  AgentClarificationCard,
  AgentClarificationOption,
  AgentDisplayMessage,
  AgentMessageRecord,
  AgentSseEvent,
  AgentStreamSnapshot,
  AgentThread,
  AgentTimelineEntry,
} from '../types'

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const toText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return ''
}

const toNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return undefined
}

const readCandidate = (source: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null) {
      return source[key]
    }
  }
  return undefined
}

export const parseMaybeJson = (value: unknown): unknown => {
  if (typeof value !== "string") {
    return value
  }
  const trimmed = value.trim()
  if (!trimmed) {
    return ''
  }
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

const toPayloadRecord = (value: unknown): Record<string, unknown> | null => {
  const parsed = parseMaybeJson(value)
  return isRecord(parsed) ? parsed : null
}

const truncate = (value: string, max = 140) => {
  if (value.length <= max) {
    return value
  }
  return `${value.slice(0, max)}...`
}

const buildId = (prefix: string, seed?: string) => {
  return `${prefix}-${seed || Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

const sortRecords = (records: AgentMessageRecord[]) => {
  return [...records].sort((left, right) => {
    if (left.seq !== undefined && right.seq !== undefined && left.seq !== right.seq) {
      return left.seq - right.seq
    }
    const leftTime = left.createTime ? new Date(left.createTime).getTime() : 0
    const rightTime = right.createTime ? new Date(right.createTime).getTime() : 0
    return leftTime - rightTime
  })
}

export const createEmptyStreamSnapshot = (): AgentStreamSnapshot => ({
  timeline: [],
  clarificationCard: null,
  finalMessage: '',
  errorMessage: '',
})

export const normalizeAgentThread = (value: unknown): AgentThread => {
  const source = toPayloadRecord(value) ?? {}
  return {
    id: toText(readCandidate(source, ['id'])) || buildId('thread'),
    appId: readCandidate(source, ['appId', 'app_id']) as string | number | undefined,
    userId: readCandidate(source, ['userId', 'user_id']) as string | number | undefined,
    title: toText(readCandidate(source, ['title'])) || AGENT_SIDEBAR_DEFAULT_TITLE,
    pythonSessionId: toText(readCandidate(source, ['pythonSessionId', 'python_session_id'])),
    status: toText(readCandidate(source, ['status'])) || 'ACTIVE',
    lastMessageAt: toText(readCandidate(source, ['lastMessageAt', 'last_message_at'])),
    createTime: toText(readCandidate(source, ['createTime', 'create_time'])),
    updateTime: toText(readCandidate(source, ['updateTime', 'update_time'])),
  }
}

export const normalizeAgentMessageRecord = (value: unknown): AgentMessageRecord => {
  const source = toPayloadRecord(value) ?? {}
  return {
    id: toText(readCandidate(source, ['id'])) || buildId('message'),
    threadId: toText(readCandidate(source, ['threadId', 'thread_id'])),
    turnId: toText(readCandidate(source, ['turnId', 'turn_id'])),
    role: toText(readCandidate(source, ['role'])) || 'SYSTEM',
    eventType: toText(readCandidate(source, ['eventType', 'event_type'])),
    contentText: toText(readCandidate(source, ['contentText', 'content_text', 'content', 'message'])),
    payloadJson: readCandidate(source, ['payloadJson', 'payload_json', 'payload']),
    seq: toNumber(readCandidate(source, ['seq'])),
    createTime: toText(readCandidate(source, ['createTime', 'create_time', 'timestamp'])),
    updateTime: toText(readCandidate(source, ['updateTime', 'update_time'])),
  }
}

export const normalizeAgentSseEvent = (eventName: string, value: unknown): AgentSseEvent => {
  const source = toPayloadRecord(value)
  const eventType =
    toText(source ? readCandidate(source, ['eventType', 'event_type', 'type']) : undefined) ||
    eventName ||
    'message'

  return {
    eventType,
    threadId: toText(source ? readCandidate(source, ['threadId', 'thread_id']) : undefined),
    turnId: toText(source ? readCandidate(source, ['turnId', 'turn_id']) : undefined),
    traceId: toText(source ? readCandidate(source, ['traceId', 'trace_id']) : undefined),
    timestamp: toText(source ? readCandidate(source, ['timestamp', 'createTime', 'createdAt']) : undefined),
    payload: source && source.payload !== undefined ? source.payload : value,
  }
}

const summarizePayload = (payload: unknown): string => {
  if (typeof payload === 'string') {
    return truncate(payload)
  }
  if (Array.isArray(payload)) {
    return `${payload.length} items`
  }
  const source = toPayloadRecord(payload)
  if (!source) {
    return ''
  }
  const candidates = [
    'answer_text',
    'answerText',
    'message',
    'text',
    'content',
    'description',
    'summary',
    'question',
    'tool_name',
    'toolName',
  ]
  for (const key of candidates) {
    const text = toText(source[key])
    if (text) {
      return truncate(text)
    }
  }
  const count = readCandidate(source, ['count', 'total', 'size'])
  if (typeof count === 'number') {
    return `${count} items`
  }
  return ''
}

export const extractEventPrimaryText = (event: AgentSseEvent) => {
  return summarizePayload(event.payload)
}

const toClarificationOptions = (value: unknown): AgentClarificationOption[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map((item, index) => {
      if (typeof item === 'string') {
        const label = item.trim()
        if (!label) {
          return null
        }
        return {
          id: `clarify-${index}`,
          label,
          value: label,
        }
      }
      const source = toPayloadRecord(item)
      if (!source) {
        return null
      }
      const label = toText(readCandidate(source, ['label', 'title', 'name', 'text']))
      const optionValue = toText(readCandidate(source, ['value', 'content', 'message'])) || label
      if (!label && !optionValue) {
        return null
      }
      return {
        id: toText(readCandidate(source, ['id'])) || `clarify-${index}`,
        label: label || optionValue,
        value: optionValue || label,
        description: toText(readCandidate(source, ['description', 'desc'])),
      }
    })
    .filter((item): item is AgentClarificationOption => Boolean(item))
}

const toClarificationCard = (event: AgentSseEvent): AgentClarificationCard | null => {
  const payload = toPayloadRecord(event.payload)
  if (!payload) {
    return null
  }
  const title = toText(readCandidate(payload, ['question', 'title'])) || 'Clarify the request'
  const description = toText(readCandidate(payload, ['description', 'detail', 'hint', 'context']))
  const options = toClarificationOptions(readCandidate(payload, ['options', 'choices', 'items']))
  if (!options.length && !description) {
    return null
  }
  return {
    title,
    description,
    options,
  }
}

const toTimelineEntry = (event: AgentSseEvent): AgentTimelineEntry => {
  const meta = AGENT_EVENT_META[event.eventType] ?? {
    label: event.eventType,
    tone: 'info' as const,
  }
  return {
    id: buildId(event.eventType, event.timestamp),
    eventType: event.eventType,
    label: meta.label,
    summary: extractEventPrimaryText(event) || meta.label,
    tone: meta.tone,
    createdAt: event.timestamp,
  }
}

export const reduceAgentEvent = (snapshot: AgentStreamSnapshot, event: AgentSseEvent): AgentStreamSnapshot => {
  const nextSnapshot: AgentStreamSnapshot = {
    timeline: [...snapshot.timeline, toTimelineEntry(event)],
    clarificationCard: snapshot.clarificationCard,
    finalMessage: snapshot.finalMessage,
    errorMessage: snapshot.errorMessage,
  }

  if (event.eventType === 'clarification_card') {
    nextSnapshot.clarificationCard = toClarificationCard(event)
  }

  if (event.eventType === 'final') {
    nextSnapshot.finalMessage = extractEventPrimaryText(event)
  }

  if (event.eventType === 'error') {
    nextSnapshot.errorMessage = extractEventPrimaryText(event) || 'Agent request failed'
  }

  return nextSnapshot
}

export const deriveStreamSnapshotFromRecords = (records: AgentMessageRecord[]): AgentStreamSnapshot => {
  let snapshot = createEmptyStreamSnapshot()
  for (const record of sortRecords(records)) {
    if ((record.role || '').toUpperCase() !== 'SYSTEM' || !record.eventType) {
      continue
    }
    const event = normalizeAgentSseEvent(record.eventType, {
      eventType: record.eventType,
      payload: record.payloadJson,
      timestamp: record.createTime,
      threadId: record.threadId,
      turnId: record.turnId,
    })
    snapshot = reduceAgentEvent(snapshot, event)
  }
  return snapshot
}

export const buildDisplayMessages = (records: AgentMessageRecord[]): AgentDisplayMessage[] => {
  return sortRecords(records)
    .filter((record) => {
      const role = (record.role || '').toUpperCase()
      return role === 'USER' || role === 'ASSISTANT'
    })
    .map((record) => ({
      id: record.id || buildId('display', record.createTime),
      role: (record.role || '').toUpperCase() === 'USER' ? 'user' : 'assistant',
      content: record.contentText || '',
      createdAt: record.createTime,
      status: 'done',
    }))
}
