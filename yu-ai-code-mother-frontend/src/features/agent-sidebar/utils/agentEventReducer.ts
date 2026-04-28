import { AGENT_EVENT_META, AGENT_SIDEBAR_DEFAULT_TITLE } from '../constants'
import type {
  AgentFeedbackResponse,
  AgentCitation,
  AgentClarificationCard,
  AgentClarificationOption,
  AgentDisplayMessage,
  AgentFinalPayload,
  AgentMemoryUsedItemSummary,
  AgentMemoryUsedSummary,
  AgentMemoryActionResponse,
  AgentMemoryCandidateSummary,
  AgentMemoryRecordSummary,
  AgentMemoryTraceSummary,
  AgentMessageRecord,
  AgentRetrievalSummary,
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
  finalPayload: null,
  traceId: undefined,
  turnId: undefined,
  sessionId: undefined,
  workflowVersion: undefined,
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
    sessionId: toText(source ? readCandidate(source, ['sessionId', 'session_id']) : undefined),
    workflowVersion: toText(
      source ? readCandidate(source, ['workflowVersion', 'workflow_version']) : undefined,
    ),
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

const toStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item) => toText(item)).filter(Boolean)
}

const toCitation = (value: unknown): AgentCitation | null => {
  const source = toPayloadRecord(value)
  if (!source) {
    return null
  }
  const chunkId = toText(readCandidate(source, ['chunkId', 'chunk_id']))
  if (!chunkId) {
    return null
  }
  return {
    chunkId,
    documentId: toText(readCandidate(source, ['documentId', 'document_id'])) || undefined,
    sourceType: toText(readCandidate(source, ['sourceType', 'source_type'])) || undefined,
    version: toText(readCandidate(source, ['version'])) || undefined,
    score: toNumber(readCandidate(source, ['score'])),
    title: toText(readCandidate(source, ['title'])) || undefined,
    locator: toText(readCandidate(source, ['locator'])) || undefined,
  }
}

const toRetrievalSummary = (value: unknown): AgentRetrievalSummary | null => {
  const source = toPayloadRecord(value)
  if (!source) {
    return null
  }
  return {
    semanticQuery: toText(readCandidate(source, ['semanticQuery', 'semantic_query'])) || undefined,
    keywordQuery: toText(readCandidate(source, ['keywordQuery', 'keyword_query'])) || undefined,
    retrievalStrategy:
      toText(readCandidate(source, ['retrievalStrategy', 'retrieval_strategy'])) || undefined,
    retrievalHitCount: toNumber(
      readCandidate(source, ['retrievalHitCount', 'retrieval_hit_count']),
    ),
    evidenceUsedCount: toNumber(
      readCandidate(source, ['evidenceUsedCount', 'evidence_used_count']),
    ),
    evidenceStatus: toText(readCandidate(source, ['evidenceStatus', 'evidence_status'])) || undefined,
    evidenceStrongCount: toNumber(
      readCandidate(source, ['evidenceStrongCount', 'evidence_strong_count']),
    ),
    evidenceWeakCount: toNumber(readCandidate(source, ['evidenceWeakCount', 'evidence_weak_count'])),
    retrievalFilters:
      toPayloadRecord(readCandidate(source, ['retrievalFilters', 'retrieval_filters'])) || undefined,
  }
}

const toMemoryUsedItemSummary = (value: unknown): AgentMemoryUsedItemSummary | null => {
  const source = toPayloadRecord(value)
  if (!source) {
    return null
  }
  const memoryId = toText(readCandidate(source, ['memoryId', 'memory_id']))
  if (!memoryId) {
    return null
  }
  return {
    memoryId,
    memoryType: toText(readCandidate(source, ['memoryType', 'memory_type'])) || undefined,
    scope: toText(readCandidate(source, ['scope'])) || undefined,
    summary: toText(readCandidate(source, ['summary'])) || undefined,
    source: toText(readCandidate(source, ['source'])) || undefined,
    confidence: toNumber(readCandidate(source, ['confidence'])),
  }
}

const toMemoryUsedItems = (value: unknown): AgentMemoryUsedItemSummary[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map((item) => toMemoryUsedItemSummary(item))
    .filter((item): item is AgentMemoryUsedItemSummary => Boolean(item))
}

const toMemoryUsedSummary = (value: unknown): AgentMemoryUsedSummary | null => {
  const source = toPayloadRecord(value)
  if (!source) {
    return null
  }
  return {
    used: Boolean(readCandidate(source, ['used'])),
    totalMemories: toNumber(readCandidate(source, ['totalMemories', 'total_memories'])) || 0,
    retrievalReason:
      toText(readCandidate(source, ['retrievalReason', 'retrieval_reason'])) || undefined,
    totalTokenEstimate:
      toNumber(readCandidate(source, ['totalTokenEstimate', 'total_token_estimate'])) || 0,
    promptMemories: toMemoryUsedItems(readCandidate(source, ['promptMemories', 'prompt_memories'])),
    stateMemories: toMemoryUsedItems(readCandidate(source, ['stateMemories', 'state_memories'])),
    toolMemories: toMemoryUsedItems(readCandidate(source, ['toolMemories', 'tool_memories'])),
    ragMemories: toMemoryUsedItems(readCandidate(source, ['ragMemories', 'rag_memories'])),
  }
}

const toFinalPayload = (event: AgentSseEvent): AgentFinalPayload | null => {
  const payload = toPayloadRecord(event.payload)
  if (!payload) {
    return null
  }
  const citations = Array.isArray(payload.citations)
    ? payload.citations
        .map((item) => toCitation(item))
        .filter((item): item is AgentCitation => Boolean(item))
    : []
  return {
    answerText: toText(readCandidate(payload, ['answerText', 'answer_text', 'answer', 'content'])),
    citations,
    usedTools: toStringArray(readCandidate(payload, ['usedTools', 'used_tools'])),
    resolvedTopic: toText(readCandidate(payload, ['resolvedTopic', 'resolved_topic'])) || undefined,
    retrievalStrategy:
      toText(readCandidate(payload, ['retrievalStrategy', 'retrieval_strategy'])) || undefined,
    groundingStatus:
      toText(readCandidate(payload, ['groundingStatus', 'grounding_status'])) || 'not_grounded',
    retrievalSummary: toRetrievalSummary(
      readCandidate(payload, ['retrievalSummary', 'retrieval_summary']),
    ),
    memoryUsedSummary: toMemoryUsedSummary(
      readCandidate(payload, ['memoryUsedSummary', 'memory_used_summary']),
    ),
    memoryUpdates:
      toPayloadRecord(readCandidate(payload, ['memoryUpdates', 'memory_updates'])) || undefined,
    recommendation:
      toPayloadRecord(readCandidate(payload, ['recommendation'])) || undefined,
    confidence: toNumber(readCandidate(payload, ['confidence'])),
    intent: toText(readCandidate(payload, ['intent'])) || undefined,
    requestedOutputStyle:
      toText(readCandidate(payload, ['requestedOutputStyle', 'requested_output_style'])) || undefined,
    metrics: toPayloadRecord(readCandidate(payload, ['metrics'])) || undefined,
  }
}

const summarizeTimelineEvent = (event: AgentSseEvent): string => {
  const payload = toPayloadRecord(event.payload)
  if (event.eventType === 'retrieval_result' && payload) {
    const hitCount = toNumber(readCandidate(payload, ['retrieval_hit_count', 'retrievalHitCount'])) || 0
    const evidenceCount =
      toNumber(readCandidate(payload, ['evidence_used_count', 'evidenceUsedCount'])) || 0
    return `命中 ${hitCount} 条候选，采用 ${evidenceCount} 条证据`
  }
  if (event.eventType === 'memory_retrieval_result' && payload) {
    const injected = Array.isArray(payload.injected) ? payload.injected.length : 0
    const retrieved = Array.isArray(payload.retrieved) ? payload.retrieved.length : 0
    return `读取 ${retrieved} 条历史记忆，注入 ${injected} 条上下文`
  }
  if (event.eventType === 'memory_promotion_result' && payload) {
    const promoted = Array.isArray(payload.promoted_ids) ? payload.promoted_ids.length : 0
    const rejected = Array.isArray(payload.rejected_ids) ? payload.rejected_ids.length : 0
    return `提升 ${promoted} 条记忆，拒绝 ${rejected} 条候选`
  }
  if (event.eventType === 'final') {
    const finalPayload = toFinalPayload(event)
    if (finalPayload?.groundingStatus === 'grounded') {
      return '回答已完成，证据充分'
    }
    if (finalPayload?.groundingStatus === 'weakly_grounded') {
      return '回答已完成，证据较弱'
    }
  }
  return extractEventPrimaryText(event)
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
    summary: summarizeTimelineEvent(event) || meta.label,
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
    finalPayload: snapshot.finalPayload,
    traceId: event.traceId || snapshot.traceId,
    turnId: event.turnId || snapshot.turnId,
    sessionId: event.sessionId || snapshot.sessionId,
    workflowVersion: event.workflowVersion || snapshot.workflowVersion,
  }

  if (event.eventType === 'clarification_card') {
    nextSnapshot.clarificationCard = toClarificationCard(event)
  }

  if (event.eventType === 'final') {
    const finalPayload = toFinalPayload(event)
    nextSnapshot.finalPayload = finalPayload
    nextSnapshot.finalMessage = finalPayload?.answerText || extractEventPrimaryText(event)
    nextSnapshot.errorMessage = ''
  }

  if (event.eventType === 'error') {
    nextSnapshot.finalPayload = null
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

const toStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item) => toText(item)).filter(Boolean)
}

export const normalizeMemoryRecordSummary = (value: unknown): AgentMemoryRecordSummary => {
  const source = toPayloadRecord(value) ?? {}
  return {
    memoryId: toText(readCandidate(source, ['memoryId', 'memory_id'])) || buildId('memory'),
    userId: toText(readCandidate(source, ['userId', 'user_id'])) || undefined,
    sessionId: toText(readCandidate(source, ['sessionId', 'session_id'])) || undefined,
    projectId: toText(readCandidate(source, ['projectId', 'project_id'])) || undefined,
    topic: toText(readCandidate(source, ['topic'])) || undefined,
    memoryType: toText(readCandidate(source, ['memoryType', 'memory_type'])) || undefined,
    scope: toText(readCandidate(source, ['scope'])) || undefined,
    status: toText(readCandidate(source, ['status'])) || undefined,
    source: toText(readCandidate(source, ['source'])) || undefined,
    summary: toText(readCandidate(source, ['summary'])) || undefined,
    confidence: toNumber(readCandidate(source, ['confidence'])),
    importance: toNumber(readCandidate(source, ['importance'])),
    stability: toNumber(readCandidate(source, ['stability'])),
    sensitivity: toText(readCandidate(source, ['sensitivity'])) || undefined,
    retrievalMode: toText(readCandidate(source, ['retrievalMode', 'retrieval_mode'])) || undefined,
    shouldVectorize: Boolean(readCandidate(source, ['shouldVectorize', 'should_vectorize'])),
    ttlSeconds: toNumber(readCandidate(source, ['ttlSeconds', 'ttl_seconds'])),
    validUntil: toText(readCandidate(source, ['validUntil', 'valid_until'])) || undefined,
    tags: toStringList(readCandidate(source, ['tags'])),
    entities: toStringList(readCandidate(source, ['entities'])),
    sourceTurnId: toText(readCandidate(source, ['sourceTurnId', 'source_turn_id'])) || undefined,
    sourceMessageIds: toStringList(readCandidate(source, ['sourceMessageIds', 'source_message_ids'])),
    lastAccessedAt: toText(readCandidate(source, ['lastAccessedAt', 'last_accessed_at'])) || undefined,
    accessCount: toNumber(readCandidate(source, ['accessCount', 'access_count'])),
    supersedes: toText(readCandidate(source, ['supersedes'])) || undefined,
    supersededBy: toText(readCandidate(source, ['supersededBy', 'superseded_by'])) || undefined,
    embeddingId: toText(readCandidate(source, ['embeddingId', 'embedding_id'])) || undefined,
    rawEvidence: toPayloadRecord(readCandidate(source, ['rawEvidence', 'raw_evidence'])) || undefined,
    schemaVersion: toText(readCandidate(source, ['schemaVersion', 'schema_version'])) || undefined,
    extra: toPayloadRecord(readCandidate(source, ['extra'])) || undefined,
  }
}

export const normalizeMemoryCandidateSummary = (value: unknown): AgentMemoryCandidateSummary => {
  const source = toPayloadRecord(value) ?? {}
  const record = readCandidate(source, ['record'])
  return {
    candidateId: toText(readCandidate(source, ['candidateId', 'candidate_id'])) || buildId('candidate'),
    memoryId: toText(readCandidate(source, ['memoryId', 'memory_id'])) || undefined,
    userId: toText(readCandidate(source, ['userId', 'user_id'])) || undefined,
    sessionId: toText(readCandidate(source, ['sessionId', 'session_id'])) || undefined,
    projectId: toText(readCandidate(source, ['projectId', 'project_id'])) || undefined,
    topic: toText(readCandidate(source, ['topic'])) || undefined,
    memoryType: toText(readCandidate(source, ['memoryType', 'memory_type'])) || undefined,
    scope: toText(readCandidate(source, ['scope'])) || undefined,
    status: toText(readCandidate(source, ['status'])) || undefined,
    source: toText(readCandidate(source, ['source'])) || undefined,
    summary: toText(readCandidate(source, ['summary'])) || undefined,
    confidence: toNumber(readCandidate(source, ['confidence'])),
    importance: toNumber(readCandidate(source, ['importance'])),
    stability: toNumber(readCandidate(source, ['stability'])),
    governanceAction:
      toText(readCandidate(source, ['governanceAction', 'governance_action'])) || undefined,
    requireConfirmation: Boolean(
      readCandidate(source, ['requireConfirmation', 'require_confirmation']),
    ),
    approvalNotes: toStringList(readCandidate(source, ['approvalNotes', 'approval_notes'])),
    decisionReason:
      toText(readCandidate(source, ['decisionReason', 'decision_reason'])) || undefined,
    conflictIds: toStringList(readCandidate(source, ['conflictIds', 'conflict_ids'])),
    deletionJobIds: toStringList(readCandidate(source, ['deletionJobIds', 'deletion_job_ids'])),
    skipReason: toText(readCandidate(source, ['skipReason', 'skip_reason'])) || undefined,
    record: record ? normalizeMemoryRecordSummary(record) : undefined,
    extra: toPayloadRecord(readCandidate(source, ['extra'])) || undefined,
  }
}

export const normalizeMemoryTraceSummary = (value: unknown): AgentMemoryTraceSummary => {
  const source = toPayloadRecord(value) ?? {}
  return {
    traceId: toText(readCandidate(source, ['traceId', 'trace_id'])) || buildId('trace'),
    userId: toText(readCandidate(source, ['userId', 'user_id'])) || undefined,
    sessionId: toText(readCandidate(source, ['sessionId', 'session_id'])) || undefined,
    turnId: toText(readCandidate(source, ['turnId', 'turn_id'])) || undefined,
    retrieved: toStringList(readCandidate(source, ['retrieved'])),
    injected: toStringList(readCandidate(source, ['injected'])),
    skipped: toStringList(readCandidate(source, ['skipped'])),
    candidates: toStringList(readCandidate(source, ['candidates'])),
    promoted: toStringList(readCandidate(source, ['promoted'])),
    rejected: toStringList(readCandidate(source, ['rejected'])),
    decisionReasons:
      toPayloadRecord(readCandidate(source, ['decisionReasons', 'decision_reasons'])) || undefined,
    conflictIds: toStringList(readCandidate(source, ['conflictIds', 'conflict_ids'])),
    deletionJobIds: toStringList(readCandidate(source, ['deletionJobIds', 'deletion_job_ids'])),
    skipReasons:
      toPayloadRecord(readCandidate(source, ['skipReasons', 'skip_reasons'])) || undefined,
    conflictResolutions: Array.isArray(readCandidate(source, ['conflictResolutions', 'conflict_resolutions']))
      ? (readCandidate(source, ['conflictResolutions', 'conflict_resolutions']) as Record<string, unknown>[])
      : undefined,
    totalMemoryTokens: toNumber(
      readCandidate(source, ['totalMemoryTokens', 'total_memory_tokens']),
    ),
    qdrantDegraded: Boolean(readCandidate(source, ['qdrantDegraded', 'qdrant_degraded'])),
    createdAt: toText(readCandidate(source, ['createdAt', 'created_at'])) || undefined,
    extra: toPayloadRecord(readCandidate(source, ['extra'])) || undefined,
  }
}

export const normalizeAgentFeedbackResponse = (value: unknown): AgentFeedbackResponse => {
  const source = toPayloadRecord(value) ?? {}
  return {
    feedbackId: toText(readCandidate(source, ['feedbackId', 'feedback_id'])) || buildId('feedback'),
    status: toText(readCandidate(source, ['status'])) || 'pending',
    recordedAt: toText(readCandidate(source, ['recordedAt', 'recorded_at'])) || undefined,
    dedupeKey: toText(readCandidate(source, ['dedupeKey', 'dedupe_key'])) || undefined,
    payload: toPayloadRecord(readCandidate(source, ['payload'])) || undefined,
  }
}

export const normalizeMemoryActionResponse = (value: unknown): AgentMemoryActionResponse => {
  const source = toPayloadRecord(value) ?? {}
  return {
    status: toText(readCandidate(source, ['status'])) || 'success',
    action: toText(readCandidate(source, ['action'])) || '',
    message: toText(readCandidate(source, ['message'])) || undefined,
    record: readCandidate(source, ['record']) ? normalizeMemoryRecordSummary(readCandidate(source, ['record'])) : null,
    candidate: readCandidate(source, ['candidate'])
      ? normalizeMemoryCandidateSummary(readCandidate(source, ['candidate']))
      : null,
    trace: readCandidate(source, ['trace'])
      ? normalizeMemoryTraceSummary(readCandidate(source, ['trace']))
      : null,
  }
}
