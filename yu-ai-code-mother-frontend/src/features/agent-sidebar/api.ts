import request from '@/request'
import { API_BASE_URL } from '@/config/env'
import { AGENT_THREAD_PAGE_SIZE } from './constants'
import type {
  AgentMessageQueryRequest,
  AgentMessageRecord,
  AgentMessageStreamRequest,
  AgentRawSsePacket,
  AgentThread,
  AgentThreadCreateRequest,
} from './types'
import { normalizeAgentMessageRecord, normalizeAgentThread } from './utils/agentEventReducer'

type AgentBaseResponse<T> = {
  code?: number
  data?: T
  message?: string
}

type AgentListPayload<T> = {
  records?: T[]
  list?: T[]
}

const ensureSuccess = <T>(payload: AgentBaseResponse<T> | undefined) => {
  if (!payload) {
    throw new Error('Empty response')
  }
  if (payload.code !== undefined && payload.code !== 0) {
    throw new Error(payload.message || 'Request failed')
  }
  return payload.data
}

const resolveListData = <T>(value: unknown): T[] => {
  if (Array.isArray(value)) {
    return value as T[]
  }
  if (value && typeof value === 'object') {
    const listPayload = value as AgentListPayload<T>
    if (Array.isArray(listPayload.records)) {
      return listPayload.records
    }
    if (Array.isArray(listPayload.list)) {
      return listPayload.list
    }
  }
  return []
}

const getApiBaseUrl = () => {
  return request.defaults.baseURL || API_BASE_URL
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

export const listAgentThreads = async (appId: string | number): Promise<AgentThread[]> => {
  const response = await request<AgentBaseResponse<unknown>>('/agent/threads', {
    method: 'GET',
    params: { appId },
  })
  const data = ensureSuccess(response.data)
  return resolveListData<unknown>(data).map(normalizeAgentThread)
}

export const createAgentThread = async (payload: AgentThreadCreateRequest): Promise<AgentThread> => {
  const response = await request<AgentBaseResponse<unknown>>('/agent/threads', {
    method: 'POST',
    data: payload,
  })
  const data = ensureSuccess(response.data)
  return normalizeAgentThread(data)
}

export const listAgentMessages = async (
  threadId: string,
  query: AgentMessageQueryRequest = {},
): Promise<AgentMessageRecord[]> => {
  const response = await request<AgentBaseResponse<unknown>>(`/agent/threads/${threadId}/messages`, {
    method: 'GET',
    params: {
      pageSize: query.pageSize ?? AGENT_THREAD_PAGE_SIZE,
      lastCreateTime: query.lastCreateTime,
    },
  })
  const data = ensureSuccess(response.data)
  return resolveListData<unknown>(data).map(normalizeAgentMessageRecord)
}

export const archiveAgentThread = async (threadId: string) => {
  const response = await request<AgentBaseResponse<boolean>>(`/agent/threads/${threadId}/archive`, {
    method: 'POST',
  })
  ensureSuccess(response.data)
  return true
}

export const getAgentSidebarEnabled = async (): Promise<boolean> => {
  const response = await request<AgentBaseResponse<boolean>>('/agent/sidebar/enabled', {
    method: 'GET',
  })
  return Boolean(ensureSuccess(response.data))
}

export const streamAgentMessage = async (
  threadId: string,
  payload: AgentMessageStreamRequest,
  options: {
    signal?: AbortSignal
    onEvent: (event: AgentRawSsePacket) => void
  },
) => {
  const response = await fetch(`${getApiBaseUrl()}/agent/threads/${threadId}/messages/stream`, {
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
