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
      path: '/tahp/evals',
      name: 'tahp.evals',
      component: () => import('@/views/tahp/EvalsView.vue'),
    },
    {
      path: '/tahp/pipeline',
      name: 'tahp.pipeline',
      component: () => import('@/views/tahp/AdaptPipelineView.vue'),
    },
    {
      path: '/tahp/bug-analysis',
      name: 'tahp.bug-analysis',
      component: () => import('@/views/tahp/BugAnalysisView.vue'),
    },
    {
      path: '/tahp/modem-baseline',
      name: 'tahp.modem-baseline',
      component: () => import('@/views/tahp/ModemBaselineView.vue'),
      redirect: { name: 'tahp.modem-baseline.workbench' },
      children: [
        {
          path: 'workbench',
          name: 'tahp.modem-baseline.workbench',
          component: () => import('@/views/tahp/ModemBaselineWorkbenchView.vue'),
        },
        {
          path: 'history/:runId?',
          name: 'tahp.modem-baseline.history',
          component: () => import('@/views/tahp/ModemBaselineHistoryView.vue'),
        },
        {
          path: 'settings',
          name: 'tahp.modem-baseline.settings',
          component: () => import('@/views/tahp/ModemBaselineSettingsView.vue'),
        },
      ],
    },
    {
      path: '/tahp/gki-patch',
      name: 'tahp.gki-patch',
      component: () => import('@/views/tahp/GkiPatchView.vue'),
      redirect: { name: 'tahp.gki-patch.dashboard' },
      children: [
        {
          path: 'dashboard',
          name: 'tahp.gki-patch.dashboard',
          component: () => import('@/views/tahp/GkiPatchWorkbenchView.vue'),
          meta: { gkiPath: '/dashboard', gkiNativeWorkbench: true },
        },
        {
          path: 'analysis',
          name: 'tahp.gki-patch.analysis',
          component: () => import('@/views/tahp/GkiPatchRouteStub.vue'),
          meta: { gkiPath: '/analysis' },
        },
        {
          path: 'crash',
          name: 'tahp.gki-patch.crash',
          component: () => import('@/views/tahp/GkiPatchRouteStub.vue'),
          meta: { gkiPath: '/crash' },
        },
        {
          path: 'upgrade',
          name: 'tahp.gki-patch.upgrade',
          component: () => import('@/views/tahp/GkiPatchRouteStub.vue'),
          meta: { gkiPath: '/upgrade' },
        },
        {
          path: 'patches',
          name: 'tahp.gki-patch.patches',
          component: () => import('@/views/tahp/GkiPatchRouteStub.vue'),
          meta: { gkiPath: '/patches' },
        },
        {
          path: 'settings',
          name: 'tahp.gki-patch.settings',
          component: () => import('@/views/tahp/GkiPatchRouteStub.vue'),
          meta: { gkiPath: '/settings' },
        },
      ],
    },
    {
      path: '/tahp/self-check',
      name: 'tahp.self-check',
      component: () => import('@/views/tahp/DeviceSelfCheckView.vue'),
    },
    {
      path: '/tahp/code-pull',
      name: 'tahp.code-pull',
      component: () => import('@/views/tahp/CodePullView.vue'),
    },
    {
      path: '/tahp/config',
      name: 'tahp.config',
      component: () => import('@/views/tahp/ConfigView.vue'),
    },
    {
      path: '/tahp/manual',
      name: 'tahp.manual',
      component: () => import('@/views/tahp/ManualView.vue'),
    },
    {
      path: '/tahp/skill-config',
      name: 'tahp.skill-config',
      redirect: (to) => ({
        name: 'tahp.config',
        query: { tab: to.query.openForm === '1' ? 'form' : 'skills' },
      }),
    },
    // ===== Hermes 原生视图 =====
    {
      path: '/hermes/chat',
      name: 'hermes.chat',
      component: () => import('@/views/hermes/ChatView.vue'),
      meta: { flushLayout: true },
    },
    {
      path: '/hermes/history',
      name: 'hermes.history',
      component: () => import('@/views/hermes/HistoryView.vue'),
    },
    {
      path: '/hermes/models',
      name: 'hermes.models',
      redirect: { name: 'tahp.config', query: { tab: 'models' } },
    },
    {
      path: '/hermes/skills',
      name: 'hermes.skills',
      component: () => import('@/views/hermes/SkillsView.vue'),
    },
    {
      path: '/hermes/settings',
      name: 'hermes.settings',
      component: () => import('@/views/hermes/SettingsView.vue'),
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
