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
    label: '请求已接收',
    tone: 'info',
  },
  retrieval_started: {
    label: '开始检索知识',
    tone: 'info',
  },
  retrieval_result: {
    label: '检索结果已整理',
    tone: 'success',
  },
  memory_retrieval_started: {
    label: '开始读取记忆',
    tone: 'info',
  },
  memory_retrieval_result: {
    label: '历史记忆已参考',
    tone: 'success',
  },
  memory_promotion_result: {
    label: '记忆治理已完成',
    tone: 'success',
  },
  tool_call: {
    label: '调用工具',
    tone: 'warning',
  },
  tool_result: {
    label: '工具返回结果',
    tone: 'success',
  },
  clarification_card: {
    label: '需要澄清',
    tone: 'warning',
  },
  plan_execution_started: {
    label: '执行计划已启动',
    tone: 'info',
  },
  plan_step_result: {
    label: '计划步骤结果',
    tone: 'info',
  },
  approval_required: {
    label: '需要人工确认',
    tone: 'warning',
  },
  plan_replanned: {
    label: '计划已重排',
    tone: 'warning',
  },
  plan_execution_summary: {
    label: '计划执行摘要',
    tone: 'warning',
  },
  final: {
    label: '最终回答',
    tone: 'success',
  },
  error: {
    label: '执行失败',
    tone: 'error',
  },
}
