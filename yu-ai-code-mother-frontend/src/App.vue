<script setup lang="ts">
import { onBeforeMount } from 'vue'
import BasicLayout from '@/layouts/BasicLayout.vue'
import { useUiPreferenceStore } from '@/stores/uiPreference'

const uiPreferenceStore = useUiPreferenceStore()

onBeforeMount(() => {
  uiPreferenceStore.initPreferences()
})
</script>

<template>
  <BasicLayout />
</template>

<style>
/* 全局样式优化 */
* {
  box-sizing: border-box;
}

html {
  background: var(--app-bg);
}

body {
  margin: 0;
  padding: 0;
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell',
    'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow-x: hidden;
  background: var(--app-bg);
  color: var(--text-primary);
  line-height: 1.6;
}

html,
body {
  overflow-x: hidden;
}

:root {
  --app-bg: #eef2f7;
  --surface-bg: rgba(255, 255, 255, 0.96);
  --surface-elevated: rgba(255, 255, 255, 0.99);
  --surface-muted: rgba(241, 245, 249, 0.98);
  --text-primary: #0f172a;
  --text-secondary: #334155;
  --text-tertiary: #64748b;
  --text-inverse: #ffffff;
  --border-color: rgba(15, 23, 42, 0.12);
  --shadow-color: rgba(15, 23, 42, 0.1);
  --brand-primary-rgb: 37, 99, 235;
  --brand-secondary-rgb: 124, 58, 237;
  --brand-accent-rgb: 14, 165, 233;
  --home-bg-start: #f8fafc;
  --home-bg-mid: #eef2ff;
  --home-bg-end: #dbeafe;
  --home-grid-rgb: 37, 99, 235;
  --home-grid-secondary-rgb: 124, 58, 237;
  --home-grid-accent-rgb: 14, 165, 233;
}

html[data-ui-mode='learning'] {
  --brand-primary-rgb: 249, 115, 22;
  --brand-secondary-rgb: 245, 158, 11;
  --brand-accent-rgb: 14, 165, 233;
  --home-grid-rgb: 249, 115, 22;
  --home-grid-secondary-rgb: 245, 158, 11;
  --home-grid-accent-rgb: 14, 165, 233;
}

html[data-theme='dark'] {
  --app-bg: #08101f;
  --surface-bg: rgba(15, 23, 42, 0.94);
  --surface-elevated: rgba(17, 24, 39, 0.98);
  --surface-muted: rgba(30, 41, 59, 0.96);
  --text-primary: #f8fafc;
  --text-secondary: #d1d5db;
  --text-tertiary: #94a3b8;
  --text-inverse: #ffffff;
  --border-color: rgba(148, 163, 184, 0.28);
  --shadow-color: rgba(0, 0, 0, 0.5);
  --home-bg-start: #0f172a;
  --home-bg-mid: #111827;
  --home-bg-end: #020617;
}

html[data-theme='dark'] :where(.ant-modal-content, .ant-modal-header, .ant-card, .ant-drawer-content, .ant-popover-inner, .ant-alert) {
  background-color: var(--surface-elevated);
  color: var(--text-primary);
}

html[data-theme='dark'] :where(.ant-input, .ant-input-affix-wrapper, .ant-select-selector, .ant-picker, .ant-input-number, .ant-table, .ant-pagination-item, .ant-pagination-prev .ant-pagination-item-link, .ant-pagination-next .ant-pagination-item-link) {
  background-color: var(--surface-muted);
  color: var(--text-primary);
  border-color: var(--border-color);
}
</style>
