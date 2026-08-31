<template>
  <div class="app-shell" :class="{ 'app-shell-embedded': embedded }">
    <header v-if="!embedded" class="app-header">
      <RouterLink to="/" class="brand">
        <div class="brand-mark">G</div>
        <div>
          <h1 class="brand-title">GKI Patch Tool</h1>
          <div class="brand-subtitle">Patch analysis workspace</div>
        </div>
      </RouterLink>

      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          active-class=""
          exact-active-class=""
          :class="{ 'router-link-active': isNavActive(item.to) }"
        >
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="header-actions">
        <RouterLink
          to="/settings"
          class="settings-entry"
          active-class=""
          exact-active-class=""
          :class="{ 'router-link-active': isNavActive('/settings') }"
          title="环境设置"
        >
          <span class="settings-icon">⚙</span>
          <span>设置</span>
        </RouterLink>
      </div>
    </header>

    <main class="content" :class="{ 'content-embedded': embedded }">
      <RouterView v-slot="{ Component }">
        <KeepAlive :include="['UpgradeView']">
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const navItems = [
  { to: '/', label: '首页' },
  { to: '/dashboard', label: '看板' },
  { to: '/analysis', label: 'patch分析' },
  { to: '/crash', label: '故障诊断' },
  { to: '/upgrade', label: 'patch入库' },
  { to: '/patches', label: '数据库' },
]

/** EasyAdapter 集成模式：URL 带 embedded=1 时隐藏原顶部导航，仅渲染页面内容 */
const embedded = computed(() => {
  const fromQuery = new URLSearchParams(window.location.search).get('embedded')
  return fromQuery === '1' || fromQuery === 'true'
})

function isNavActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(`${path}/`)
}

function isParentNavigateMessage(data: unknown): data is {
  type: 'ea-gki-patch-navigate'
  path: string
  query?: Record<string, string>
} {
  if (!data || typeof data !== 'object') return false
  const msg = data as { type?: string; path?: string }
  return msg.type === 'ea-gki-patch-navigate' && typeof msg.path === 'string'
}

function isParentApplyNoticeMessage(data: unknown): data is {
  type: 'ea-gki-patch-apply-notice'
  fromTag: string
  toTag: string
  text?: string
  noticeId?: string
} {
  if (!data || typeof data !== 'object') return false
  const msg = data as { type?: string; fromTag?: string; toTag?: string }
  return (
    msg.type === 'ea-gki-patch-apply-notice'
    && typeof msg.fromTag === 'string'
    && typeof msg.toTag === 'string'
  )
}

function handleParentNavigate(event: MessageEvent) {
  if (!embedded.value) return
  if (isParentNavigateMessage(event.data)) {
    const path = event.data.path.startsWith('/') ? event.data.path : `/${event.data.path}`
    const query = { ...(event.data.query || {}), embedded: '1' }
    const samePath = route.path === path || route.path === `${path}/`
    const sameQuery =
      Object.keys(query).every((k) => String(route.query[k] ?? '') === String(query[k] ?? ''))
      && Object.keys(route.query).every((k) => k === 'embedded' || query[k] != null)
    if (samePath && sameQuery) return
    void router.push({ path, query })
    return
  }
  if (isParentApplyNoticeMessage(event.data)) {
    const path = '/upgrade'
    const query = {
      embedded: '1',
      from_tag: event.data.fromTag,
      to_tag: event.data.toTag,
      ...(event.data.text ? { notice_text: event.data.text } : {}),
      ...(event.data.noticeId ? { notice_id: event.data.noticeId } : {}),
    }
    void router.push({ path, query })
  }
}

onMounted(() => {
  window.addEventListener('message', handleParentNavigate)
})

onUnmounted(() => {
  window.removeEventListener('message', handleParentNavigate)
})
</script>
