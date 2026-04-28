import { LEARNING_API_BASE_URL } from '@/config/env'
import type { AgentRawSsePacket } from '@/features/agent-sidebar/types'

export interface LearningMessageStreamRequest {
  user_id: string
  session_id: string
  trace_id: string
  message: string
  turn_id?: string
  response_mode?: string
  topic_hint?: string
  history_summary?: string
  client_context?: Record<string, unknown>
}

const getLearningApiBaseUrl = () => LEARNING_API_BASE_URL.replace(/\/$/, '')

const buildLearningApiUrl = (path: string) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${getLearningApiBaseUrl()}${normalizedPath}`
}

const parseSsePacket = (block: string): AgentRawSsePacket | null => {
  const trimmed = block.trim()
  if (!trimmed) {
    return null
  }

  let eventName = 'message'
  const dataLines: string[] = []

  for (const line of trimmed.split('\n')) {
    if (line.startsWith(':')) {
      continue
    }
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim() || 'message'
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  const rawData = dataLines.join('\n')
  let data: unknown = rawData
  if (rawData) {
    try {
      data = JSON.parse(rawData)
    } catch {
      data = rawData
    }
  }

  return {
    event: eventName,
    data,
    rawData,
  }
}

const consumeSseResponse = async (
  response: Response,
  onEvent: (event: AgentRawSsePacket) => void,
) => {
  if (!response.body) {
    throw new Error('Missing SSE body')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const packet = parseSsePacket(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (packet) {
          onEvent(packet)
        }
        boundary = buffer.indexOf('\n\n')
      }
    }

    const tail = parseSsePacket(buffer)
    if (tail) {
      onEvent(tail)
    }
  } finally {
    reader.releaseLock()
  }
}

export const streamLearningMessage = async (
  payload: LearningMessageStreamRequest,
  options: {
    signal?: AbortSignal
    onEvent: (event: AgentRawSsePacket) => void
  },
) => {
  const response = await fetch(buildLearningApiUrl('/internal/v1/chat/stream'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
    signal: options.signal,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed (${response.status})`)
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('text/event-stream')) {
    throw new Error('Server did not return an SSE stream')
  }

  await consumeSseResponse(response, options.onEvent)
}
