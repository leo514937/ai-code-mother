export type AgentThreadStatus = 'ACTIVE' | 'ARCHIVED' | string

export type AgentMessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM' | string

export type AgentGroundingStatus = 'grounded' | 'weakly_grounded' | 'not_grounded' | string

export type AgentSseEventType =
  | 'ack'
  | 'retrieval_started'
  | 'retrieval_result'
  | 'memory_retrieval_started'
  | 'memory_retrieval_result'
  | 'memory_promotion_result'
  | 'tool_call'
  | 'tool_result'
  | 'clarification_card'
  | 'plan_execution_started'
  | 'plan_step_result'
  | 'approval_required'
  | 'plan_replanned'
  | 'plan_execution_summary'
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

export interface AgentCitation {
  chunkId: string
  documentId?: string
  sourceType?: string
  version?: string
  score?: number
  title?: string
  locator?: string
}

export interface AgentRetrievalSummary {
  semanticQuery?: string
  keywordQuery?: string
  retrievalStrategy?: string
  retrievalHitCount?: number
  evidenceUsedCount?: number
  evidenceStatus?: string
  evidenceStrongCount?: number
  evidenceWeakCount?: number
  retrievalFilters?: Record<string, unknown>
}

export interface AgentMemoryUsedItemSummary {
  memoryId: string
  memoryType?: string
  scope?: string
  summary?: string
  source?: string
  confidence?: number
}

export interface AgentMemoryUsedSummary {
  used: boolean
  totalMemories: number
  retrievalReason?: string
  totalTokenEstimate?: number
  promptMemories: AgentMemoryUsedItemSummary[]
  stateMemories: AgentMemoryUsedItemSummary[]
  toolMemories: AgentMemoryUsedItemSummary[]
  ragMemories: AgentMemoryUsedItemSummary[]
}

export interface AgentFinalPayload {
  answerText: string
  citations: AgentCitation[]
  usedTools: string[]
  resolvedTopic?: string
  retrievalStrategy?: string
  groundingStatus: AgentGroundingStatus
  retrievalSummary: AgentRetrievalSummary | null
  memoryUsedSummary: AgentMemoryUsedSummary | null
  memoryUpdates?: Record<string, unknown>
  recommendation?: Record<string, unknown> | null
  confidence?: number
  intent?: string
  requestedOutputStyle?: string
  metrics?: Record<string, unknown>
}

export type AgentFeedbackIssueType =
  | 'helpful'
  | 'unhelpful'
  | 'citation_incorrect'
  | 'missed_recall'
  | 'other'

export interface AgentFeedbackRequest {
  turnId?: string
  traceId?: string
  issueType: AgentFeedbackIssueType
  isHelpful?: boolean
  comment?: string
  finalPayload?: Record<string, unknown>
  timeline?: Record<string, unknown>[]
  retrievalSummary?: Record<string, unknown>
  memoryUsedSummary?: Record<string, unknown>
  context?: Record<string, unknown>
}

export interface AgentFeedbackResponse {
  feedbackId: string
  status: string
  recordedAt?: string
  dedupeKey?: string
  payload?: Record<string, unknown>
}

export interface AgentMemoryRecordSummary {
  memoryId: string
  userId?: string
  sessionId?: string
  projectId?: string
  topic?: string
  memoryType?: string
  scope?: string
  status?: string
  source?: string
  summary?: string
  confidence?: number
  importance?: number
  stability?: number
  sensitivity?: string
  retrievalMode?: string
  shouldVectorize?: boolean
  ttlSeconds?: number
  validUntil?: string
  tags?: string[]
  entities?: string[]
  sourceTurnId?: string
  sourceMessageIds?: string[]
  lastAccessedAt?: string
  accessCount?: number
  supersedes?: string
  supersededBy?: string
  embeddingId?: string
  rawEvidence?: Record<string, unknown>
  schemaVersion?: string
  extra?: Record<string, unknown>
}

export interface AgentMemoryCandidateSummary {
  candidateId: string
  memoryId?: string
  userId?: string
  sessionId?: string
  projectId?: string
  topic?: string
  memoryType?: string
  scope?: string
  status?: string
  source?: string
  summary?: string
  confidence?: number
  importance?: number
  stability?: number
  governanceAction?: string
  requireConfirmation?: boolean
  approvalNotes?: string[]
  decisionReason?: string
  conflictIds?: string[]
  deletionJobIds?: string[]
  skipReason?: string
  record?: AgentMemoryRecordSummary
  extra?: Record<string, unknown>
}

export interface AgentMemoryTraceSummary {
  traceId: string
  userId?: string
  sessionId?: string
  turnId?: string
  retrieved?: string[]
  injected?: string[]
  skipped?: string[]
  candidates?: string[]
  promoted?: string[]
  rejected?: string[]
  decisionReasons?: Record<string, unknown>
  conflictIds?: string[]
  deletionJobIds?: string[]
  skipReasons?: Record<string, unknown>
  conflictResolutions?: Record<string, unknown>[]
  totalMemoryTokens?: number
  qdrantDegraded?: boolean
  createdAt?: string
  extra?: Record<string, unknown>
}

export interface AgentSseEvent {
  eventType: AgentSseEventType
  threadId?: string
  turnId?: string
  traceId?: string
  sessionId?: string
  workflowVersion?: string
  timestamp?: string
  payload?: unknown
}

export interface AgentStreamSnapshot {
  timeline: AgentTimelineEntry[]
  clarificationCard: AgentClarificationCard | null
  finalMessage: string
  errorMessage: string
  finalPayload: AgentFinalPayload | null
  traceId?: string
  turnId?: string
  sessionId?: string
  workflowVersion?: string
}

export interface AgentRawSsePacket {
  event: string
  data: unknown
  rawData: string
}

export interface AgentMemoryActionRequest {
  reason?: string
  supersededBy?: string
  targetMemoryId?: string
}

export interface AgentMemoryActionResponse {
  status: string
  action: string
  message?: string
  record?: AgentMemoryRecordSummary | null
  candidate?: AgentMemoryCandidateSummary | null
  trace?: AgentMemoryTraceSummary | null
}
