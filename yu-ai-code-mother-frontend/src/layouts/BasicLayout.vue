<template>
  <a-layout class="basic-layout">
    <!-- 顶部导航栏 -->
    <GlobalHeader @toggle-sidebar="toggleSidebar" />
    
    <a-layout style="flex: 1; overflow: hidden">
      <!-- 主要内容区域 -->
      <a-layout-content class="main-content">
        <router-view />
      </a-layout-content>

      <!-- 全局右侧智能助手侧边栏 (模仿 Cursor) -->
      <a-layout-sider 
        v-model:collapsed="collapsed" 
        :width="siderWidth" 
        :collapsedWidth="0"
        collapsible 
        theme="light"
        :trigger="null"
        class="global-agent-sider"
        :class="{ 'is-dragging': isDragging }"
      >
        <!-- 侧边栏拖拽调宽用的把手 -->
        <div class="sider-resizer" @mousedown="startDrag"></div>
        
        <AgentSidebar app-id="global-session" />
      </a-layout-sider>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import GlobalHeader from '@/components/GlobalHeader.vue'
import { AgentSidebar } from '@/features/agent-sidebar'

const collapsed = ref(true)
const siderWidth = ref(380)
const isDragging = ref(false)

const toggleSidebar = () => {
  collapsed.value = !collapsed.value
}

const startDrag = (e: MouseEvent) => {
  e.preventDefault()
  isDragging.value = true
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.cursor = 'col-resize'
  // 防止 iframe 或者子内容在拖拽时抢夺事件
  document.body.style.userSelect = 'none'
}

const onDrag = (e: MouseEvent) => {
  if (!isDragging.value) return
  // 右侧边栏的宽度约等于 窗口宽度减去鼠标距离左侧距离
  const newWidth = window.innerWidth - e.clientX
  // 限制宽度的最小和最大范围
  if (newWidth >= 300 && newWidth <= 800) {
    siderWidth.value = newWidth
  }
}

const stopDrag = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
</script>

<style scoped>
.basic-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1;
  padding: 0;
  background: none;
  margin: 0;
  overflow-y: auto;
}

.global-agent-sider {
  border-left: 1px solid #f0f0f0;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.05);
  background: white;
  z-index: 10;
  position: relative;
  transition: width 0.2s cubic-bezier(0.2, 0, 0, 1) 0s;
  height: 100%;
}

.global-agent-sider.is-dragging {
  transition: none !important;
}

.sider-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -2px;
  width: 5px;
  cursor: col-resize;
  background: transparent;
  z-index: 100;
  transition: background 0.2s;
}

.sider-resizer:hover, .sider-resizer:active {
  background: #1890ff;
}
</style>
