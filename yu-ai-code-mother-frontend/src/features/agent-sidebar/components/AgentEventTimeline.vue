<template>
  <section class="event-timeline">
    <div class="timeline-header">
      <span>运行日志</span>
      <a-tag :color="busy ? 'processing' : 'default'">{{ busy ? '运行中' : '空闲' }}</a-tag>
    </div>
    <div class="timeline-body">
      <div v-if="!items.length" class="timeline-empty">流式事件会在此处显示。</div>
      <div v-for="item in items" :key="item.id" class="timeline-item">
        <div class="item-top">
          <a-tag :color="toneColorMap[item.tone]">{{ item.label }}</a-tag>
          <span v-if="item.createdAt" class="item-time">{{ item.createdAt }}</span>
        </div>
        <div class="item-summary">{{ item.summary }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { AgentTimelineEntry, AgentTimelineTone } from '../types'

defineProps<{
  items: AgentTimelineEntry[]
  busy?: boolean
}>()

const toneColorMap: Record<AgentTimelineTone, string> = {
  info: 'blue',
  success: 'green',
  warning: 'orange',
  error: 'red',
}
</script>

<style scoped>
.event-timeline {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-top: 1px solid #eef2f7;
  background: #f8fafc;
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  font-size: 12px;
  font-weight: 700;
  color: #1f2937;
}

.timeline-body {
  display: grid;
  gap: 10px;
  padding: 0 16px 16px;
  overflow-y: auto;
}

.timeline-empty {
  padding: 12px 0;
  color: #6b7280;
  font-size: 12px;
}

.timeline-item {
  padding: 10px 12px;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
}

.item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.item-time {
  color: #94a3b8;
  font-size: 11px;
}

.item-summary {
  margin-top: 8px;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}
</style>
