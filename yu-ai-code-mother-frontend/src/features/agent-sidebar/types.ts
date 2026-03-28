export type AgentThreadStatus = 'ACTIVE' | 'ARCHIVED' | string

export type AgentMessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM' | string

export type AgentSseEventType =
  | 'ack'
  | 'retrieval_started'
  | 'retrieval_result'
  | 'tool_call'
  | 'tool_result'
  | 'clarification_card'
  | 'final'
  | 'error'
  | string

export type AgentTimelineTone = 'info' | 'success' | 'warning' | 'error'

export interface AgentThread {
  id: string
  appId?: string | number
  userId?: string | number
  title?: string
  pythonSessionId?: string
  status?: AgentThreadStatus
  lastMessageAt?: string
  createTime?: string
  updateTime?: string
}

export interface AgentThreadCreateRequest {
  appId: string | number
  title?: string
}

export interface AgentMessageStreamRequest {
  content: string
}

export interface AgentMessageQueryRequest {
  pageSize?: number
  lastCreateTime?: string
}

export interface AgentMessageRecord {
  id?: string
  threadId?: string
  turnId?: string
  role?: AgentMessageRole
  eventType?: string
  contentText?: string
  payloadJson?: unknown
  seq?: number
  createTime?: string
  updateTime?: string
}

export interface AgentDisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
  status?: 'done' | 'streaming' | 'error'
}

export interface AgentTimelineEntry {
  id: string
  eventType: AgentSseEventType
  label: string
  summary: string
  tone: AgentTimelineTone
  createdAt?: string
}

export interface AgentClarificationOption {
  id: string
  label: string
  value: string
  description?: string
}

export interface AgentClarificationCard {
  title: string
  description?: string
  options: AgentClarificationOption[]
}

export interface AgentSseEvent {
  eventType: AgentSseEventType
  threadId?: string
  turnId?: string
  traceId?: string
  timestamp?: string
  payload?: unknown
}

export interface AgentStreamSnapshot {
  timeline: AgentTimelineEntry[]
  clarificationCard: AgentClarificationCard | null
  finalMessage: string
  errorMessage: string
}

export interface AgentRawSsePacket {
  event: string
  data: unknown
  rawData: string
}
