<template>
  <section v-if="card" class="clarification-card">
    <div class="card-title">{{ card.title }}</div>
    <div v-if="card.description" class="card-description">{{ card.description }}</div>
    <div class="card-options">
      <a-button
        v-for="option in card.options"
        :key="option.id"
        block
        :disabled="disabled"
        @click="$emit('select', option.value)"
      >
        <div class="option-label">{{ option.label }}</div>
        <div v-if="option.description" class="option-description">{{ option.description }}</div>
      </a-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { AgentClarificationCard } from '../types'

defineProps<{
  card: AgentClarificationCard | null
  disabled?: boolean
}>()

defineEmits<{
  (event: 'select', value: string): void
}>()
</script>

<style scoped>
.clarification-card {
  padding: 14px 16px;
  border-top: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  background: var(--surface-muted);
}

.card-title {
  font-size: 13px;
  font-weight: 700;
  color: rgb(var(--brand-primary-rgb));
}

.card-description {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.card-options {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.option-label {
  font-weight: 600;
}

.option-description {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
