import { createRouter, createWebHashHistory } from 'vue-router'
import { hasApiKey, setApiKey } from '@/api/client'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    // ===== TAHP Console 路由 =====
    {
      path: '/tahp/dashboard',
      name: 'tahp.dashboard',
      component: () => import('@/views/tahp/DashboardView.vue'),
    },
    {
      path: '/tahp/executor',
      name: 'tahp.executor',
      component: () => import('@/views/tahp/TaskExecutorView.vue'),
    },
    {
      path: '/tahp/tasks',
      name: 'tahp.tasks',
      component: () => import('@/views/tahp/TaskListView.vue'),
    },
    {
      path: '/tahp/modules',
      name: 'tahp.modules',
      component: () => import('@/views/tahp/ModuleMatrixView.vue'),
    },
    {
      path: '/tahp/constraints/:module/:file',
      name: 'tahp.constraint-editor',
      component: () => import('@/views/tahp/ConstraintEditorView.vue'),
      props: true,
    },
    {
      path: '/tahp/gate',
      name: 'tahp.gate',
      component: () => import('@/views/tahp/GateCheckView.vue'),
    },
    {
      path: '/tahp/knowledge',
      name: 'tahp.knowledge',
      component: () => import('@/views/tahp/KnowledgeBaseView.vue'),
    },
    {
      path: '/tahp/playbooks',
      name: 'tahp.playbooks',
      component: () => import('@/views/tahp/PlaybookView.vue'),
    },
    {
      path: '/tahp/tools',
      name: 'tahp.tools',
      component: () => import('@/views/tahp/ToolsView.vue'),
    },
    {
      path: '/tahp/reports',
      name: 'tahp.reports',
      component: () => import('@/views/tahp/ReportsView.vue'),
    },
    // ===== Hermes 原生视图 (通用 LLM Chat / 周边能力) =====
    {
      path: '/hermes/chat',
      name: 'hermes.chat',
      component: () => import('@/views/hermes/ChatView.vue'),
    },
    {
      path: '/hermes/history',
      name: 'hermes.history',
      component: () => import('@/views/hermes/HistoryView.vue'),
    },
    {
      path: '/hermes/models',
      name: 'hermes.models',
      component: () => import('@/views/hermes/ModelsView.vue'),
    },
    {
      path: '/hermes/skills',
      name: 'hermes.skills',
      component: () => import('@/views/hermes/SkillsView.vue'),
    },
    {
      path: '/hermes/logs',
      name: 'hermes.logs',
      component: () => import('@/views/hermes/LogsView.vue'),
    },
    {
      path: '/hermes/settings',
      name: 'hermes.settings',
      component: () => import('@/views/hermes/SettingsView.vue'),
    },
    {
      path: '/hermes/channels',
      name: 'hermes.channels',
      component: () => import('@/views/hermes/ChannelsView.vue'),
    },
    {
      path: '/hermes/terminal',
      name: 'hermes.terminal',
      component: () => import('@/views/hermes/TerminalView.vue'),
    },
    {
      path: '/hermes/files',
      name: 'hermes.files',
      component: () => import('@/views/hermes/FilesView.vue'),
    },
  ],
})

// TAHP 默认入口
const DEFAULT_LANDING = '/tahp/dashboard'

router.beforeEach((to, _from, next) => {
  // 内网团队工具默认关闭鉴权 — 可通过 VITE_AUTH_DISABLED=0 重启用
  const authDisabled = (import.meta as any).env?.VITE_AUTH_DISABLED !== '0'

  if (to.meta.public) {
    if (to.name === 'login' && (hasApiKey() || authDisabled)) {
      next({ path: DEFAULT_LANDING })
      return
    }
    next()
    return
  }

  if (authDisabled) {
    // 预置虚拟 key，让 hasApiKey() 返回 true，避免 models store 等拒绝加载
    if (!hasApiKey()) setApiKey('auth-disabled')
    next()
    return
  }

  if (!hasApiKey()) {
    next({ name: 'login' })
    return
  }

  next()
})

export default router
