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
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

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
</script>
