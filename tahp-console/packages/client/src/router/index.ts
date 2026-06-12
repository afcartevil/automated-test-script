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
      path: '/tahp/knowledge',
      name: 'tahp.knowledge',
      component: () => import('@/views/tahp/KnowledgeBaseView.vue'),
    },
    {
      path: '/tahp/reports',
      name: 'tahp.reports',
      component: () => import('@/views/tahp/ReportsView.vue'),
    },
    {
      path: '/tahp/adapt-debug',
      name: 'tahp.adapt-debug',
      component: () => import('@/views/tahp/AdaptDebugView.vue'),
    },
    {
      path: '/tahp/bug-analysis',
      name: 'tahp.bug-analysis',
      component: () => import('@/views/tahp/BugAnalysisView.vue'),
    },
    // ===== Hermes 原生视图 =====
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

const DEFAULT_LANDING = '/tahp/dashboard'

router.beforeEach((to, _from, next) => {
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
