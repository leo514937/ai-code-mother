<template>
  <a-layout-header class="header">
    <a-row :wrap="false">
      <a-col flex="auto">
        <div class="header-left">
          <RouterLink to="/" class="brand-link">
            <span class="brand-text">Agent</span>
          </RouterLink>
          <div class="mode-switch">
            <a-button
              size="small"
              :type="uiPreferenceStore.uiMode === 'coding' ? 'primary' : 'default'"
              :ghost="uiPreferenceStore.uiMode !== 'coding'"
              @click="goCoding"
            >
              coding Agent
            </a-button>
            <a-button
              size="small"
              :type="uiPreferenceStore.uiMode === 'learning' ? 'primary' : 'default'"
              :ghost="uiPreferenceStore.uiMode !== 'learning'"
              @click="goLearning"
            >
              学习助手
            </a-button>
          </div>
        </div>
      </a-col>
      <a-col>
        <div class="user-login-status">
          <a-space>
            <a-tooltip :title="uiPreferenceStore.themeMode === 'dark' ? '切换到浅色模式' : '切换到深色模式'">
              <a-button type="text" @click="uiPreferenceStore.toggleThemeMode()">
                <template #icon>
                  <BulbOutlined />
                </template>
              </a-button>
            </a-tooltip>

            <div v-if="loginUserStore.loginUser.id">
              <a-dropdown>
                <a-space>
                  <a-avatar :src="loginUserStore.loginUser.userAvatar" />
                  <span class="user-name">{{ loginUserStore.loginUser.userName ?? '无名' }}</span>
              </a-space>
              <template #overlay>
                <a-menu>
                  <a-menu-item @click="doLogout">
                    <LogoutOutlined />
                    退出登录
                  </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>
            <div v-else>
              <a-button type="primary" href="/user/login">登录</a-button>
            </div>
          </a-space>
        </div>
      </a-col>
    </a-row>
  </a-layout-header>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useLoginUserStore } from '@/stores/loginUser.ts'
import { useUiPreferenceStore } from '@/stores/uiPreference'
import { userLogout } from '@/api/userController.ts'
import { BulbOutlined, LogoutOutlined } from '@ant-design/icons-vue'

const loginUserStore = useLoginUserStore()
const uiPreferenceStore = useUiPreferenceStore()
const router = useRouter()

const goCoding = async () => {
  await router.push('/')
}

const goLearning = async () => {
  await router.push('/learning')
}

// 退出登录
const doLogout = async () => {
  const res = await userLogout()
  if (res.data.code === 0) {
    loginUserStore.setLoginUser({
      userName: '未登录',
    })
    message.success('退出登录成功')
    await router.push('/user/login')
  } else {
    message.error('退出登录失败，' + res.data.message)
  }
}
</script>

<style scoped>
.header {
  background: var(--surface-bg);
  padding: 0 24px;
  border-bottom: 1px solid var(--border-color);
  backdrop-filter: blur(18px);
}

.header :deep(.ant-row) {
  align-items: center;
  min-height: 64px;
}

.brand-link {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.brand-text {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: rgb(var(--brand-primary-rgb));
  letter-spacing: 0.04em;
}

.mode-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding-left: 12px;
}

.mode-switch :deep(.ant-btn) {
  border-radius: 999px;
  border-color: var(--border-color);
}

.mode-switch :deep(.ant-btn-primary) {
  background: rgb(var(--brand-primary-rgb));
  border-color: rgb(var(--brand-primary-rgb));
}

html:not([data-theme='dark']) .mode-switch :deep(.ant-btn) {
  color: #111827;
  font-weight: 400;
}

html:not([data-theme='dark']) .mode-switch :deep(.ant-btn-primary) {
  color: #111827;
}

.user-login-status :deep(.ant-btn-text) {
  color: var(--text-primary);
}

.user-name {
  color: var(--text-primary);
  font-weight: 500;
}

html[data-theme='dark'] .user-name {
  color: #ffffff;
}

html:not([data-theme='dark']) .user-name {
  color: #111827;
}

</style>
