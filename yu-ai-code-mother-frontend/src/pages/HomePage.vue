<script setup lang="ts">
defineOptions({
  name: 'HomePage',
})

import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useLoginUserStore } from '@/stores/loginUser'
import { useUiPreferenceStore } from '@/stores/uiPreference'
import { addApp, listGoodAppVoByPage, listMyAppVoByPage } from '@/api/appController'
import { getDeployUrl } from '@/config/env'
import AppCard from '@/components/AppCard.vue'

const router = useRouter()
const loginUserStore = useLoginUserStore()
const uiPreferenceStore = useUiPreferenceStore()

// 用户提示词
const userPrompt = ref('')
const creating = ref(false)

// 我的应用数据
const myApps = ref<API.AppVO[]>([])
const myAppsPage = reactive({
  current: 1,
  pageSize: 6,
  total: 0,
})

// 精选应用数据
const featuredApps = ref<API.AppVO[]>([])
const featuredAppsPage = reactive({
  current: 1,
  pageSize: 6,
  total: 0,
})

// 设置提示词
const setPrompt = (prompt: string) => {
  userPrompt.value = prompt
}

const isLearningMode = computed(() => uiPreferenceStore.uiMode === 'learning')

const heroTitle = computed(() =>
  isLearningMode.value ? 'Chat with Learning Assistant' : 'Chat with Coding Agent',
)

const promptPlaceholder = computed(() =>
  isLearningMode.value ? '告诉我你想学习的知识点，比如“讲解 React Hooks”' : '帮我创建个人博客网站',
)

const quickPrompts = computed(() => {
  if (isLearningMode.value) {
    return [
      {
        label: 'JavaScript 入门',
        prompt:
          '请用循序渐进的方式讲解 JavaScript 基础语法、变量、函数、数组和对象，并给出简单示例。',
      },
      {
        label: 'Vue 3 进阶',
        prompt: '系统讲解 Vue 3 的响应式原理、Composition API、组件通信和常见最佳实践。',
      },
      {
        label: '算法练习',
        prompt: '给我设计 3 道适合初学者的算法练习题，并附上思路提示和参考答案。',
      },
      {
        label: '系统设计',
        prompt: '用通俗的语言解释一个中小型 Web 应用从前端到后端的基本架构与协作方式。',
      },
    ]
  }

  return [
    {
      label: '个人博客网站',
      prompt:
        '创建一个现代化的个人博客网站，包含文章列表、详情页、分类标签、搜索功能、评论系统和个人简介页面。采用简洁的设计风格，支持响应式布局，文章支持Markdown格式，首页展示最新文章和热门推荐。',
    },
    {
      label: '企业官网',
      prompt:
        '设计一个专业的企业官网，包含公司介绍、产品服务展示、新闻资讯、联系我们等页面。采用商务风格的设计，包含轮播图、产品展示卡片、团队介绍、客户案例展示，支持多语言切换和在线客服功能。',
    },
    {
      label: '在线商城',
      prompt:
        '构建一个功能完整的在线商城，包含商品展示、购物车、用户注册登录、订单管理、支付结算等功能。设计现代化的商品卡片布局，支持商品搜索筛选、用户评价、优惠券系统和会员积分功能。',
    },
    {
      label: '作品展示网站',
      prompt:
        '制作一个精美的作品展示网站，适合设计师、摄影师、艺术家等创作者。包含作品画廊、项目详情页、个人简历、联系方式等模块。采用瀑布流或网格布局展示作品，支持图片放大预览和作品分类筛选。',
    },
  ]
})

// 创建应用
const createApp = async () => {
  if (!userPrompt.value.trim()) {
    message.warning('请输入应用描述')
    return
  }

  if (!loginUserStore.loginUser.id) {
    message.warning('请先登录')
    await router.push('/user/login')
    return
  }

  creating.value = true
  try {
    const res = await addApp({
      initPrompt: userPrompt.value.trim(),
    })

    if (res.data.code === 0 && res.data.data) {
      message.success('应用创建成功')
      const appId = String(res.data.data)
      await router.push(`/app/chat/${appId}`)
    } else {
      message.error('创建失败：' + res.data.message)
    }
  } catch (error) {
    console.error('创建应用失败：', error)
    message.error('创建失败，请重试')
  } finally {
    creating.value = false
  }
}

// 加载我的应用
const loadMyApps = async () => {
  if (!loginUserStore.loginUser.id) {
    return
  }

  try {
    const res = await listMyAppVoByPage({
      pageNum: myAppsPage.current,
      pageSize: myAppsPage.pageSize,
      sortField: 'createTime',
      sortOrder: 'desc',
    })

    if (res.data.code === 0 && res.data.data) {
      myApps.value = res.data.data.records || []
      myAppsPage.total = res.data.data.totalRow || 0
    }
  } catch (error) {
    console.error('加载我的应用失败：', error)
  }
}

// 加载精选应用
const loadFeaturedApps = async () => {
  try {
    const res = await listGoodAppVoByPage({
      pageNum: featuredAppsPage.current,
      pageSize: featuredAppsPage.pageSize,
      sortField: 'createTime',
      sortOrder: 'desc',
    })

    if (res.data.code === 0 && res.data.data) {
      featuredApps.value = res.data.data.records || []
      featuredAppsPage.total = res.data.data.totalRow || 0
    }
  } catch (error) {
    console.error('加载精选应用失败：', error)
  }
}

// 查看对话
const viewChat = (appId: string | number | undefined) => {
  if (appId) {
    router.push(`/app/chat/${appId}?view=1`)
  }
}

// 查看作品
const viewWork = (app: API.AppVO) => {
  if (app.deployKey) {
    const url = getDeployUrl(app.deployKey)
    window.open(url, '_blank')
  }
}

let mouseMoveHandler: ((e: MouseEvent) => void) | null = null

// 页面加载时获取数据
onMounted(() => {
  loadMyApps()
  loadFeaturedApps()

  mouseMoveHandler = (e: MouseEvent) => {
    const { clientX, clientY } = e
    const { innerWidth, innerHeight } = window
    const x = (clientX / innerWidth) * 100
    const y = (clientY / innerHeight) * 100

    document.documentElement.style.setProperty('--mouse-x', `${x}%`)
    document.documentElement.style.setProperty('--mouse-y', `${y}%`)
  }

  document.addEventListener('mousemove', mouseMoveHandler)
})

onUnmounted(() => {
  if (mouseMoveHandler) {
    document.removeEventListener('mousemove', mouseMoveHandler)
  }
})
</script>

<template>
  <div id="homePage">
    <div class="home-orbs" aria-hidden="true">
      <span class="home-orb home-orb-a"></span>
      <span class="home-orb home-orb-b"></span>
      <span class="home-orb home-orb-c"></span>
    </div>
    <div class="container">
      <div class="hero-section">
        <div class="hero-kicker">{{ isLearningMode ? 'Learning Assistant' : 'Coding Agent' }}</div>
        <h1 class="hero-title">{{ heroTitle }}</h1>
      </div>

      <div class="input-section">
        <a-textarea
          v-model:value="userPrompt"
          :placeholder="promptPlaceholder"
          :rows="4"
          :maxlength="1000"
          class="prompt-input"
        />
        <div class="input-actions">
          <a-button type="primary" size="large" @click="createApp" :loading="creating">
            <template #icon>
              <span>↑</span>
            </template>
          </a-button>
        </div>
      </div>

      <div class="quick-actions">
        <a-button
          v-for="preset in quickPrompts"
          :key="preset.label"
          type="default"
          @click="setPrompt(preset.prompt)"
        >
          {{ preset.label }}
        </a-button>
      </div>

      <div class="section">
        <h2 class="section-title">我的作品</h2>
        <div class="app-grid">
          <AppCard
            v-for="app in myApps"
            :key="app.id"
            :app="app"
            @view-chat="viewChat"
            @view-work="viewWork"
          />
        </div>
        <div class="pagination-wrapper">
          <a-pagination
            v-model:current="myAppsPage.current"
            v-model:page-size="myAppsPage.pageSize"
            :total="myAppsPage.total"
            :show-size-changer="false"
            :show-total="(total: number) => `共 ${total} 个应用`"
            @change="loadMyApps"
          />
        </div>
      </div>

      <div class="section">
        <h2 class="section-title">精选案例</h2>
        <div class="featured-grid">
          <AppCard
            v-for="app in featuredApps"
            :key="app.id"
            :app="app"
            :featured="true"
            @view-chat="viewChat"
            @view-work="viewWork"
          />
        </div>
        <div class="pagination-wrapper">
          <a-pagination
            v-model:current="featuredAppsPage.current"
            v-model:page-size="featuredAppsPage.pageSize"
            :total="featuredAppsPage.total"
            :show-size-changer="false"
            :show-total="(total: number) => `共 ${total} 个案例`"
            @change="loadFeaturedApps"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
#homePage {
  width: 100%;
  margin: 0;
  padding: 0;
  min-height: 100vh;
  color: var(--text-primary);
  background:
    linear-gradient(
      180deg,
      var(--home-bg-start) 0%,
      var(--home-bg-mid) 8%,
      var(--home-bg-end) 100%
    ),
    radial-gradient(circle at 20% 80%, rgba(var(--brand-primary-rgb), 0.15) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(var(--brand-secondary-rgb), 0.12) 0%, transparent 50%),
    radial-gradient(circle at 40% 40%, rgba(var(--brand-accent-rgb), 0.08) 0%, transparent 50%);
  position: relative;
  overflow: hidden;
}

.home-orbs {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 1;
}

.home-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(2px);
  opacity: 0.65;
  mix-blend-mode: screen;
  will-change: transform, opacity;
}

.home-orb::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: inherit;
  box-shadow: 0 0 60px currentColor;
}

.home-orb-a {
  width: 320px;
  height: 320px;
  top: 10%;
  left: 6%;
  color: rgba(var(--brand-primary-rgb), 0.18);
  background: radial-gradient(circle at 35% 35%, rgba(var(--brand-primary-rgb), 0.28), transparent 68%);
  animation: orbFloatA 18s ease-in-out infinite alternate;
}

.home-orb-b {
  width: 240px;
  height: 240px;
  top: 58%;
  left: 18%;
  color: rgba(var(--brand-secondary-rgb), 0.18);
  background: radial-gradient(circle at 35% 35%, rgba(var(--brand-secondary-rgb), 0.26), transparent 70%);
  animation: orbFloatB 20s ease-in-out infinite alternate;
}

.home-orb-c {
  width: 360px;
  height: 360px;
  top: 18%;
  right: 8%;
  color: rgba(var(--brand-accent-rgb), 0.16);
  background: radial-gradient(circle at 35% 35%, rgba(var(--brand-accent-rgb), 0.24), transparent 70%);
  animation: orbFloatC 22s ease-in-out infinite alternate;
}

#homePage::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(var(--home-grid-rgb), 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(var(--home-grid-rgb), 0.05) 1px, transparent 1px),
    linear-gradient(rgba(var(--home-grid-secondary-rgb), 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(var(--home-grid-secondary-rgb), 0.04) 1px, transparent 1px);
  background-size:
    100px 100px,
    100px 100px,
    20px 20px,
    20px 20px;
  pointer-events: none;
  animation: gridFloat 20s ease-in-out infinite;
}

#homePage::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(
      600px circle at var(--mouse-x, 50%) var(--mouse-y, 50%),
      rgba(var(--home-grid-rgb), 0.08) 0%,
      rgba(var(--home-grid-secondary-rgb), 0.06) 40%,
      transparent 80%
    ),
    linear-gradient(
      45deg,
      transparent 30%,
      rgba(var(--home-grid-rgb), 0.04) 50%,
      transparent 70%
    ),
    linear-gradient(
      -45deg,
      transparent 30%,
      rgba(var(--home-grid-secondary-rgb), 0.04) 50%,
      transparent 70%
    );
  pointer-events: none;
  animation: lightPulse 8s ease-in-out infinite alternate;
}

@keyframes gridFloat {
  0%,
  100% {
    transform: translate(0, 0);
  }
  50% {
    transform: translate(5px, 5px);
  }
}

@keyframes lightPulse {
  0% {
    opacity: 0.3;
  }
  100% {
    opacity: 0.7;
  }
}

@keyframes orbFloatA {
  0% {
    transform: translate3d(-10px, 10px, 0) scale(0.96);
    opacity: 0.45;
  }
  100% {
    transform: translate3d(40px, -30px, 0) scale(1.08);
    opacity: 0.75;
  }
}

@keyframes orbFloatB {
  0% {
    transform: translate3d(20px, -10px, 0) scale(1);
    opacity: 0.5;
  }
  100% {
    transform: translate3d(-30px, 40px, 0) scale(1.12);
    opacity: 0.8;
  }
}

@keyframes orbFloatC {
  0% {
    transform: translate3d(0, 0, 0) scale(0.94);
    opacity: 0.4;
  }
  100% {
    transform: translate3d(-50px, 24px, 0) scale(1.1);
    opacity: 0.72;
  }
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  position: relative;
  z-index: 2;
  width: 100%;
  box-sizing: border-box;
}

.hero-section {
  text-align: center;
  padding: 100px 0 72px;
  margin-bottom: 20px;
  color: var(--text-primary);
  position: relative;
  overflow: hidden;
}

.hero-kicker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 18px;
  padding: 8px 16px;
  border-radius: 999px;
  background: rgba(var(--brand-primary-rgb), 0.12);
  color: rgb(var(--brand-primary-rgb));
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  position: relative;
  z-index: 2;
}

.hero-section::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 800px 400px at center, rgba(var(--brand-primary-rgb), 0.12) 0%, transparent 70%),
    linear-gradient(45deg, transparent 30%, rgba(var(--brand-secondary-rgb), 0.05) 50%, transparent 70%),
    linear-gradient(-45deg, transparent 30%, rgba(var(--brand-accent-rgb), 0.04) 50%, transparent 70%);
  animation: heroGlow 10s ease-in-out infinite alternate;
}

@keyframes heroGlow {
  0% {
    opacity: 0.6;
    transform: scale(1);
  }
  100% {
    opacity: 1;
    transform: scale(1.02);
  }
}

.hero-title {
  font-size: 48px;
  font-weight: 700;
  margin: 0;
  line-height: 1.2;
  background: linear-gradient(
    135deg,
    rgb(var(--brand-primary-rgb)) 0%,
    rgb(var(--brand-secondary-rgb)) 50%,
    rgb(var(--brand-accent-rgb)) 100%
  );
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -1px;
  position: relative;
  z-index: 2;
  animation: titleShimmer 3s ease-in-out infinite;
}

@keyframes titleShimmer {
  0%,
  100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
}

.input-section {
  position: relative;
  margin: 0 auto 24px;
  max-width: 800px;
}

.prompt-input {
  border-radius: 16px;
  border: none;
  font-size: 16px;
  padding: 20px 60px 20px 20px;
  background: var(--surface-elevated);
  backdrop-filter: blur(20px);
  box-shadow: 0 10px 40px var(--shadow-color);
  color: var(--text-primary);
}

.prompt-input :deep(textarea) {
  background: transparent;
  color: var(--text-primary);
}

.prompt-input :deep(textarea::placeholder) {
  color: var(--text-tertiary);
}

.prompt-input:focus {
  background: var(--surface-elevated);
  box-shadow: 0 15px 50px var(--shadow-color);
  transform: translateY(-2px);
}

.input-actions {
  position: absolute;
  bottom: 12px;
  right: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.quick-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-bottom: 60px;
  flex-wrap: wrap;
}

.quick-actions .ant-btn {
  border-radius: 25px;
  padding: 8px 20px;
  height: auto;
  background: var(--surface-bg);
  border: 1px solid rgba(var(--brand-primary-rgb), 0.2);
  color: var(--text-primary);
  backdrop-filter: blur(15px);
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
}

.quick-actions .ant-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(var(--brand-primary-rgb), 0.1), transparent);
  transition: left 0.5s;
}

.quick-actions .ant-btn:hover::before {
  left: 100%;
}

.quick-actions .ant-btn:hover {
  background: var(--surface-elevated);
  border-color: rgba(var(--brand-primary-rgb), 0.4);
  color: rgb(var(--brand-primary-rgb));
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(var(--brand-primary-rgb), 0.2);
}

.section {
  margin-bottom: 60px;
}

.section-title {
  font-size: 32px;
  font-weight: 600;
  margin-bottom: 32px;
  color: var(--text-primary);
}

.pagination-wrapper :deep(.ant-pagination),
.pagination-wrapper :deep(.ant-pagination-total-text) {
  color: var(--text-secondary);
}

.pagination-wrapper :deep(.ant-pagination-item),
.pagination-wrapper :deep(.ant-pagination-prev .ant-pagination-item-link),
.pagination-wrapper :deep(.ant-pagination-next .ant-pagination-item-link) {
  background: var(--surface-elevated);
  border-color: var(--border-color);
}

.pagination-wrapper :deep(.ant-pagination-item a),
.pagination-wrapper :deep(.ant-pagination-prev .ant-pagination-item-link),
.pagination-wrapper :deep(.ant-pagination-next .ant-pagination-item-link) {
  color: var(--text-primary);
}

.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
  margin-bottom: 32px;
}

.featured-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
  margin-bottom: 32px;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 32px;
}

@media (max-width: 768px) {
  .hero-title {
    font-size: 30px;
  }

  .app-grid,
  .featured-grid {
    grid-template-columns: 1fr;
  }

  .quick-actions {
    justify-content: center;
  }
}
</style>
