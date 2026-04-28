<template>
  <section v-if="hasContent" class="answer-insights">
    <div class="insights-shell">
      <div class="insights-header">
        <div>
          <div class="insights-title">回答详情</div>
          <div class="insights-subtitle">{{ subtitle }}</div>
        </div>
        <a-button type="link" size="small" @click="expanded = !expanded">
          {{ expanded ? '收起详情' : '展开详情' }}
        </a-button>
      </div>

      <div class="insights-summary">
        <span class="summary-chip" :class="groundingTone">{{ groundingText }}</span>
        <span class="summary-chip neutral">引用 {{ citationCount }}</span>
        <span class="summary-chip neutral">记忆 {{ memoryCount }}</span>
        <span class="summary-chip neutral">事件 {{ timeline.length }}</span>
      </div>

      <div class="feedback-bar">
        <span class="feedback-label">反馈这次回答</span>
        <a-space wrap>
          <a-button
            size="small"
            :loading="feedbackLoading"
            :disabled="!canSendFeedback"
            @click="sendFeedback('helpful')"
          >
            有用
          </a-button>
          <a-button
            size="small"
            :loading="feedbackLoading"
            :disabled="!canSendFeedback"
            @click="sendFeedback('unhelpful')"
          >
            无用
          </a-button>
          <a-button
            size="small"
            :loading="feedbackLoading"
            :disabled="!canSendFeedback"
            @click="sendFeedback('citation_incorrect')"
          >
            引用不准
          </a-button>
          <a-button
            size="small"
            :loading="feedbackLoading"
            :disabled="!canSendFeedback"
            @click="sendFeedback('missed_recall')"
          >
            漏召回
          </a-button>
        </a-space>
      </div>

      <div v-if="expanded" class="insights-body">
        <div v-if="hasTraceMeta" class="detail-card">
          <div class="detail-title">追踪信息</div>
          <div class="trace-grid">
            <div v-if="traceId" class="trace-item">
              <span class="trace-label">Trace</span>
              <code>{{ traceId }}</code>
            </div>
            <div v-if="turnId" class="trace-item">
              <span class="trace-label">Turn</span>
              <code>{{ turnId }}</code>
            </div>
            <div v-if="sessionId" class="trace-item">
              <span class="trace-label">Session</span>
              <code>{{ sessionId }}</code>
            </div>
            <div v-if="workflowVersion" class="trace-item">
              <span class="trace-label">Workflow</span>
              <code>{{ workflowVersion }}</code>
            </div>
          </div>
        </div>

        <div v-if="finalPayload?.retrievalSummary" class="detail-card">
          <div class="detail-title">检索摘要</div>
          <div class="metric-grid">
            <div class="metric-item">
              <span class="metric-label">策略</span>
              <span class="metric-value">
                {{ finalPayload.retrievalSummary.retrievalStrategy || '未记录' }}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-label">命中候选</span>
              <span class="metric-value">
                {{ finalPayload.retrievalSummary.retrievalHitCount ?? 0 }}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-label">采用证据</span>
              <span class="metric-value">
                {{ finalPayload.retrievalSummary.evidenceUsedCount ?? 0 }}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-label">证据状态</span>
              <span class="metric-value">
                {{ finalPayload.retrievalSummary.evidenceStatus || 'EMPTY' }}
              </span>
            </div>
          </div>
          <div
            v-if="finalPayload.retrievalSummary.semanticQuery || finalPayload.retrievalSummary.keywordQuery"
            class="query-stack"
          >
            <div v-if="finalPayload.retrievalSummary.semanticQuery" class="query-item">
              <span class="query-label">语义查询</span>
              <code>{{ finalPayload.retrievalSummary.semanticQuery }}</code>
            </div>
            <div v-if="finalPayload.retrievalSummary.keywordQuery" class="query-item">
              <span class="query-label">关键词查询</span>
              <code>{{ finalPayload.retrievalSummary.keywordQuery }}</code>
            </div>
          </div>
        </div>

        <div v-if="citationCount" class="detail-card">
          <div class="detail-title">引用依据</div>
          <div class="list-stack">
            <div
              v-for="citation in finalPayload?.citations || []"
              :key="citation.chunkId"
              class="list-row"
            >
              <div class="list-title">{{ citation.title || citation.chunkId }}</div>
              <div class="list-meta">
                <span v-if="citation.documentId">文档 {{ citation.documentId }}</span>
                <span v-if="citation.score !== undefined">分数 {{ citation.score.toFixed(2) }}</span>
                <span v-if="citation.locator">{{ citation.locator }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="memoryCount" class="detail-card">
          <div class="detail-title">已参考的历史记忆</div>
          <div v-if="finalPayload?.memoryUsedSummary?.retrievalReason" class="memory-reason">
            {{ finalPayload.memoryUsedSummary.retrievalReason }}
          </div>
          <div class="list-stack">
            <div v-for="memory in allMemoryItems" :key="memory.memoryId" class="list-row">
              <div class="list-title">{{ memory.summary || memory.memoryId }}</div>
              <div class="list-meta">
                <span v-if="memory.memoryType">{{ memory.memoryType }}</span>
                <span v-if="memory.scope">{{ memory.scope }}</span>
                <span v-if="memory.confidence !== undefined">
                  置信度 {{ Number(memory.confidence || 0).toFixed(2) }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="threadId" class="detail-card">
          <div class="detail-title">记忆治理</div>
          <div class="detail-subtitle">查看当前线程的记忆记录和候选记忆，并支持确认/拒绝/删除</div>
          <div v-if="governanceLoading" class="governance-empty">正在加载记忆治理信息...</div>
          <template v-else>
            <div v-if="memoryRecords.length" class="detail-section">
              <div class="section-title">记忆记录</div>
              <div class="list-stack">
                <div v-for="item in memoryRecords" :key="item.memoryId" class="list-row">
                  <div class="list-title">{{ item.summary || item.topic || item.memoryId }}</div>
                  <div class="list-meta">
                    <span v-if="item.memoryType">{{ item.memoryType }}</span>
                    <span v-if="item.scope">{{ item.scope }}</span>
                    <span v-if="item.status">{{ item.status }}</span>
                    <span v-if="item.confidence !== undefined">
                      置信度 {{ Number(item.confidence || 0).toFixed(2) }}
                    </span>
                  </div>
                  <div class="row-actions">
                    <a-button size="small" @click="deleteMemory(item.memoryId)">删除</a-button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="memoryCandidates.length" class="detail-section">
              <div class="section-title">候选记忆</div>
              <div class="list-stack">
                <div v-for="item in memoryCandidates" :key="item.candidateId" class="list-row">
                  <div class="list-title">{{ item.summary || item.topic || item.candidateId }}</div>
                  <div class="list-meta">
                    <span v-if="item.memoryType">{{ item.memoryType }}</span>
                    <span v-if="item.scope">{{ item.scope }}</span>
                    <span v-if="item.governanceAction">{{ item.governanceAction }}</span>
                    <span v-if="item.confidence !== undefined">
                      置信度 {{ Number(item.confidence || 0).toFixed(2) }}
                    </span>
                  </div>
                  <div class="row-actions">
                    <a-button size="small" type="primary" @click="confirmCandidate(item.candidateId)">
                      确认
                    </a-button>
                    <a-button size="small" @click="rejectCandidate(item.candidateId)">拒绝</a-button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="!memoryRecords.length && !memoryCandidates.length" class="governance-empty">
              暂无可展示的治理信息
            </div>
          </template>
        </div>

        <AgentEventTimeline :items="timeline" :busy="isStreaming" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'
import {
  confirmAgentThreadMemoryCandidate,
  deleteAgentThreadMemoryRecord,
  listAgentThreadMemoryCandidates,
  listAgentThreadMemoryRecords,
  reportAgentThreadFeedback,
  rejectAgentThreadMemoryCandidate,
} from '../api'
import AgentEventTimeline from './AgentEventTimeline.vue'
import type {
  AgentFeedbackIssueType,
  AgentFinalPayload,
  AgentMemoryCandidateSummary,
  AgentMemoryRecordSummary,
  AgentMemoryUsedItemSummary,
  AgentTimelineEntry,
} from '../types'

const props = defineProps<{
  finalPayload: AgentFinalPayload | null
  timeline: AgentTimelineEntry[]
  isStreaming?: boolean
  threadId?: string
  traceId?: string
  turnId?: string
  sessionId?: string
  workflowVersion?: string
}>()

const expanded = ref(false)
const feedbackLoading = ref(false)
const governanceLoading = ref(false)
const memoryRecords = ref<AgentMemoryRecordSummary[]>([])
const memoryCandidates = ref<AgentMemoryCandidateSummary[]>([])
const governanceLoaded = ref(false)

const citationCount = computed(() => props.finalPayload?.citations.length ?? 0)

const allMemoryItems = computed<AgentMemoryUsedItemSummary[]>(() => {
  const summary = props.finalPayload?.memoryUsedSummary
  if (!summary) {
    return []
  }
  return [
    ...summary.promptMemories,
    ...summary.stateMemories,
    ...summary.toolMemories,
    ...summary.ragMemories,
  ]
})

const memoryCount = computed(() => allMemoryItems.value.length)

const groundingText = computed(() => {
  const status = props.finalPayload?.groundingStatus || 'not_grounded'
  if (status === 'grounded') {
    return '证据充分'
  }
  if (status === 'weakly_grounded') {
    return '证据较弱'
  }
  return '证据不足'
})

const groundingTone = computed(() => {
  const status = props.finalPayload?.groundingStatus || 'not_grounded'
  if (status === 'grounded') {
    return 'success'
  }
  if (status === 'weakly_grounded') {
    return 'warning'
  }
  return 'danger'
})

const subtitle = computed(() => {
  if (props.finalPayload?.resolvedTopic) {
    return `围绕「${props.finalPayload.resolvedTopic}」生成回答`
  }
  if (props.isStreaming) {
    return `正在生成中，已记录 ${props.timeline.length} 个执行事件`
  }
  return '展开后可查看引用、检索摘要、记忆摘要和执行轨迹'
})

const hasTraceMeta = computed(() => {
  return Boolean(props.traceId || props.turnId || props.sessionId || props.workflowVersion)
})

const hasContent = computed(() => {
  return Boolean(props.finalPayload || props.timeline.length || hasTraceMeta.value)
})

const canSendFeedback = computed(() => Boolean(props.threadId && props.finalPayload))

const loadGovernanceData = async () => {
  if (!props.threadId || !expanded.value) {
    return
  }
  governanceLoading.value = true
  try {
    const [records, candidates] = await Promise.all([
      listAgentThreadMemoryRecords(props.threadId, { limit: 8 }),
      listAgentThreadMemoryCandidates(props.threadId, 8),
    ])
    memoryRecords.value = records
    memoryCandidates.value = candidates
    governanceLoaded.value = true
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '加载记忆治理信息失败'
    message.error(errorMessage)
  } finally {
    governanceLoading.value = false
  }
}

const refreshGovernanceData = async () => {
  governanceLoaded.value = false
  await loadGovernanceData()
}

const sendFeedback = async (issueType: AgentFeedbackIssueType) => {
  if (!props.threadId || !props.finalPayload) {
    return
  }
  feedbackLoading.value = true
  try {
    await reportAgentThreadFeedback(props.threadId, {
      turnId: props.turnId,
      traceId: props.traceId,
      issueType,
      isHelpful: issueType === 'helpful' ? true : issueType === 'unhelpful' ? false : undefined,
      finalPayload: { ...props.finalPayload },
      timeline: props.timeline.map((item) => ({ ...item })),
      retrievalSummary: props.finalPayload.retrievalSummary
        ? { ...props.finalPayload.retrievalSummary }
        : undefined,
      memoryUsedSummary: props.finalPayload.memoryUsedSummary
        ? { ...props.finalPayload.memoryUsedSummary }
        : undefined,
      context: {
        sessionId: props.sessionId,
        workflowVersion: props.workflowVersion,
        traceId: props.traceId,
        turnId: props.turnId,
      },
    })
    message.success('已记录反馈')
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '反馈提交失败'
    message.error(errorMessage)
  } finally {
    feedbackLoading.value = false
  }
}

const confirmCandidate = async (candidateId: string) => {
  if (!props.threadId) {
    return
  }
  governanceLoading.value = true
  try {
    await confirmAgentThreadMemoryCandidate(props.threadId, candidateId, {
      reason: 'side-panel confirmation',
    })
    message.success('已确认候选记忆')
    await refreshGovernanceData()
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '确认候选记忆失败'
    message.error(errorMessage)
  } finally {
    governanceLoading.value = false
  }
}

const rejectCandidate = async (candidateId: string) => {
  if (!props.threadId) {
    return
  }
  governanceLoading.value = true
  try {
    await rejectAgentThreadMemoryCandidate(props.threadId, candidateId, {
      reason: 'side-panel rejection',
    })
    message.success('已拒绝候选记忆')
    await refreshGovernanceData()
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '拒绝候选记忆失败'
    message.error(errorMessage)
  } finally {
    governanceLoading.value = false
  }
}

const deleteMemory = async (memoryId: string) => {
  if (!props.threadId) {
    return
  }
  governanceLoading.value = true
  try {
    await deleteAgentThreadMemoryRecord(props.threadId, memoryId, {
      reason: 'side-panel delete',
    })
    message.success('已删除记忆')
    await refreshGovernanceData()
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '删除记忆失败'
    message.error(errorMessage)
  } finally {
    governanceLoading.value = false
  }
}

watch(
  () => [props.threadId, expanded.value] as const,
  ([threadId, isExpanded]) => {
    if (!threadId || !isExpanded || governanceLoaded.value) {
      return
    }
    void loadGovernanceData()
  },
  { immediate: true },
)

watch(
  () => props.threadId,
  () => {
    governanceLoaded.value = false
    memoryRecords.value = []
    memoryCandidates.value = []
  },
)
</script>

<style scoped>
.answer-insights {
  padding: 0 16px 16px;
}

.insights-shell {
  border: 1px solid var(--border-color);
  border-radius: 18px;
  background:
    linear-gradient(180deg, var(--surface-elevated), var(--surface-bg)),
    radial-gradient(circle at top left, rgba(var(--brand-primary-rgb), 0.08), transparent 40%);
  overflow: hidden;
}

.insights-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 16px 10px;
}

.insights-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.insights-subtitle {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.insights-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 12px;
}

.feedback-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 16px 16px;
}

.feedback-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.summary-chip.success {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
}

.summary-chip.warning {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
}

.summary-chip.danger {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.summary-chip.neutral {
  background: rgba(var(--brand-primary-rgb), 0.12);
  color: rgb(var(--brand-primary-rgb));
}

.insights-body {
  display: grid;
  gap: 12px;
  padding: 0 16px 16px;
}

.detail-card {
  border-radius: 14px;
  border: 1px solid var(--border-color);
  background: var(--surface-elevated);
  padding: 14px;
}

.detail-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

.detail-subtitle {
  margin-top: 4px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.trace-grid,
.metric-grid {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.trace-grid {
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.metric-grid {
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
}

.trace-item,
.metric-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trace-label,
.metric-label,
.query-label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.trace-item code,
.query-item code {
  display: block;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--surface-muted);
  color: var(--text-primary);
  word-break: break-all;
}

.metric-value {
  color: var(--text-primary);
  font-weight: 600;
}

.query-stack,
.list-stack {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.query-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.list-row {
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--surface-muted);
}

.list-title {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}

.list-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.memory-reason {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.detail-section + .detail-section {
  margin-top: 14px;
}

.section-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.governance-empty {
  padding: 8px 0;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
