<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchGkiPatchStatus, startGkiPatchServer, type GkiPatchStatus } from '@/api/tahp/gki-patch'
import {
  buildGkiFrameSrc,
  GKI_PATCH_PATH_TO_ROUTE,
  GKI_PATCH_ROUTE_TO_PATH,
  isGkiPatchNavMessage,
  isGkiPatchReadyMessage,
  resolveGkiFrameSync,
} from '@/utils/gki-patch-navigation'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const loadingHint = ref('正在检查 GKI 服务…')
const error = ref('')
const status = ref<GkiPatchStatus | null>(null)
const frameRef = ref<HTMLIFrameElement | null>(null)
const frameReady = ref(false)
const frameAppReady = ref(false)
/** 已挂载 iframe 的 src；工作台为空，离开工作台时按目标 path 写入 */
const mountedFrameSrc = ref('')
/** 最近一次同步到 iframe 的目标 URL（含 postMessage 切页；与 src 属性不是同一概念） */
const lastPostedSrc = ref('')

const workbenchItem = { name: 'tahp.gki-patch.dashboard', label: '工作台', icon: 'dashboard' }

const navItems = [
  { name: 'tahp.gki-patch.analysis', label: 'patch分析', icon: 'analysis' },
  { name: 'tahp.gki-patch.upgrade', label: 'patch入库', icon: 'upgrade' },
  { name: 'tahp.gki-patch.crash', label: '故障诊断', icon: 'crash' },
  { name: 'tahp.gki-patch.patches', label: '数据库', icon: 'database' },
  { name: 'tahp.gki-patch.settings', label: '设置', icon: 'settings' },
]

const activeName = computed(() => route.name?.toString() || 'tahp.gki-patch.dashboard')
const isNativeWorkbench = computed(() => Boolean(route.meta?.gkiNativeWorkbench))

const gkiPath = computed(() => {
  const fromMeta = route.meta?.gkiPath
  if (typeof fromMeta === 'string' && fromMeta) return fromMeta
  return GKI_PATCH_ROUTE_TO_PATH[activeName.value] || '/dashboard'
})

const SIDEBAR_COLLAPSED_KEY = 'ea_gki_patch_sidebar_collapsed'
const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1')

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed.value ? '1' : '0')
}

function routeQueryAsRecord(): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(route.query)) {
    const raw = Array.isArray(value) ? value[0] : value
    if (raw == null || raw === '') continue
    out[key] = String(raw)
  }
  return out
}

const desiredFrameSrc = computed(() => {
  if (!status.value || isNativeWorkbench.value) return ''
  return buildGkiFrameSrc(status.value, gkiPath.value, route.query as Record<string, unknown>)
})

function resetFrame() {
  mountedFrameSrc.value = ''
  lastPostedSrc.value = ''
  frameReady.value = false
  frameAppReady.value = false
}

function postNavigateToFrame() {
  const win = frameRef.value?.contentWindow
  if (!win || isNativeWorkbench.value) return
  if (!frameReady.value && !frameAppReady.value) return
  lastPostedSrc.value = desiredFrameSrc.value
  win.postMessage(
    {
      type: 'ea-gki-patch-navigate',
      path: gkiPath.value,
      query: { ...routeQueryAsRecord(), embedded: '1' },
    },
    '*',
  )
}

function syncFrame() {
  const mode = resolveGkiFrameSync({
    nativeWorkbench: isNativeWorkbench.value,
    desiredSrc: desiredFrameSrc.value,
    mountedSrc: mountedFrameSrc.value,
    frameAppReady: frameAppReady.value,
    lastPostedSrc: lastPostedSrc.value,
  })
  if (mode === 'none') {
    if (isNativeWorkbench.value && mountedFrameSrc.value) resetFrame()
    return
  }
  if (mode === 'mount' || mode === 'reload') {
    if (mode === 'reload') {
      frameReady.value = false
      frameAppReady.value = false
    }
    mountedFrameSrc.value = desiredFrameSrc.value
    lastPostedSrc.value = desiredFrameSrc.value
    return
  }
  postNavigateToFrame()
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function waitForRunningStatus(maxAttempts = 8): Promise<GkiPatchStatus> {
  let last = await fetchGkiPatchStatus()
  for (let i = 0; i < maxAttempts; i += 1) {
    if (last.running) return last
    if (!last.starting && i > 0) break
    loadingHint.value = '正在启动 GKI 服务，请稍候…'
    await sleep(800)
    last = await fetchGkiPatchStatus()
  }
  return last
}

async function ensureReady() {
  loading.value = true
  loadingHint.value = '正在检查 GKI 服务…'
  error.value = ''
  resetFrame()
  try {
    let next = await fetchGkiPatchStatus()
    if (!next.frontendBuilt) {
      error.value = 'GKI Patch 前端尚未构建，请执行 npm run setup:gki-patch 后重启 EasyAdapter'
      return
    }

    if (!next.running) {
      loadingHint.value = next.starting
        ? 'GKI 服务正在后台启动…'
        : '正在拉起 GKI 服务…'
      // 最多尝试 3 次 start；与 bootstrap 的 startingPromise 合并，不会重复 spawn
      let lastErr = ''
      for (let attempt = 1; attempt <= 3; attempt += 1) {
        try {
          loadingHint.value = `正在拉起 GKI 服务（${attempt}/3）…`
          next = await startGkiPatchServer()
          if (next.running) break
          next = await waitForRunningStatus()
          if (next.running) break
        } catch (err) {
          lastErr = err instanceof Error ? err.message : String(err)
          loadingHint.value = `启动未完成，正在重试（${attempt}/3）…`
          await sleep(1000 * attempt)
        }
      }
      if (!next.running) {
        error.value = lastErr
          || 'GKI 服务暂时未就绪。请稍等数秒后点重试；若持续失败请查看启动日志或执行 npm run setup:gki-patch'
        return
      }
    }

    status.value = next
    syncFrame()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function nav(name: string) {
  router.push({ name })
}

function handleGkiPatchMessage(event: MessageEvent) {
  if (isGkiPatchReadyMessage(event.data)) {
    frameAppReady.value = true
    postNavigateToFrame()
    return
  }
  if (!isGkiPatchNavMessage(event.data)) return
  const routeName = GKI_PATCH_PATH_TO_ROUTE[event.data.path]
  if (!routeName) return
  const query = event.data.query || {}
  router.push({ name: routeName, query })
}

function onFrameLoad() {
  frameReady.value = true
  postNavigateToFrame()
}

watch(
  () => [isNativeWorkbench.value, desiredFrameSrc.value] as const,
  () => {
    if (!status.value) return
    syncFrame()
  },
)

onMounted(() => {
  void ensureReady()
  window.addEventListener('message', handleGkiPatchMessage)
})

onUnmounted(() => {
  window.removeEventListener('message', handleGkiPatchMessage)
})
</script>

<template>
  <div class="gki-shell" :class="{ collapsed: sidebarCollapsed && !loading && !error }">
    <div v-if="loading" class="gki-state">
      <p>{{ loadingHint }}</p>
      <p class="gki-state-sub">首次启动可能需要几十秒，请稍候</p>
    </div>

    <div v-else-if="error" class="gki-state gki-state-error">
      <p>{{ error }}</p>
      <button type="button" class="ea-btn-primary" @click="ensureReady">重试</button>
    </div>

    <template v-else>
      <aside class="gki-sidebar" :class="{ collapsed: sidebarCollapsed }">
        <div class="gki-sidebar-top">
          <button
            type="button"
            class="gki-collapse-btn"
            :title="sidebarCollapsed ? '展开导航' : '折叠导航'"
            @click="toggleSidebar"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              :class="{ 'is-flipped': sidebarCollapsed }"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
        </div>

        <nav class="gki-nav">
          <button
            type="button"
            class="gki-nav-btn"
            :class="{ active: activeName === workbenchItem.name }"
            :title="workbenchItem.label"
            @click="nav(workbenchItem.name)"
          >
            <span class="gki-nav-icon" :data-icon="workbenchItem.icon" />
            <span class="gki-nav-label">{{ workbenchItem.label }}</span>
          </button>

          <div class="gki-nav-sep" />

          <button
            v-for="item in navItems"
            :key="item.name"
            type="button"
            class="gki-nav-btn"
            :class="{ active: activeName === item.name }"
            :title="item.label"
            @click="nav(item.name)"
          >
            <span class="gki-nav-icon" :data-icon="item.icon" />
            <span class="gki-nav-label">{{ item.label }}</span>
          </button>
        </nav>
      </aside>

      <section class="gki-main">
        <div class="gki-main-body">
          <div v-if="isNativeWorkbench" class="gki-workbench-host">
            <router-view />
          </div>
          <iframe
            v-if="!isNativeWorkbench && mountedFrameSrc"
            ref="frameRef"
            class="gki-frame"
            :src="mountedFrameSrc"
            title="GKI Patch Tool"
            @load="onFrameLoad"
          />
          <router-view v-if="!isNativeWorkbench" />
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped lang="scss">
.gki-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: calc(100vh - 120px);
  margin: -8px -28px -40px;
  background: var(--bg);

  &.collapsed {
    grid-template-columns: 64px minmax(0, 1fr);
  }
}

.gki-state {
  grid-column: 1 / -1;
  display: grid;
  place-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 15px;
}

.gki-state-sub {
  margin: 0;
  font-size: 12px;
  opacity: 0.85;
}

.gki-state-error { color: var(--error); }

.gki-sidebar {
  display: flex;
  flex-direction: column;
  padding: 12px 10px 16px;
  border-right: 1px solid color-mix(in srgb, var(--sky-ic) 12%, var(--line));
  background: linear-gradient(180deg, var(--sky-bg) 0%, color-mix(in srgb, var(--sky-bg) 70%, var(--surface)) 100%);
  overflow: hidden;
  min-width: 0;

  &.collapsed {
    padding-inline: 8px;
  }
}

.gki-sidebar-top {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;

  .collapsed & {
    justify-content: center;
  }
}

.gki-collapse-btn {
  width: 32px;
  height: 32px;
  border: 1px solid color-mix(in srgb, var(--sky-ic) 18%, var(--line));
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface) 82%, var(--sky-bg));
  color: var(--sky-fg);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.18s, border-color 0.18s, color 0.18s;

  &:hover {
    background: var(--surface);
    border-color: color-mix(in srgb, var(--sky-ic) 35%, var(--line));
    color: var(--accent);
  }

  svg {
    transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  svg.is-flipped {
    transform: rotate(180deg);
  }
}

.gki-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gki-nav-sep {
  height: 1px;
  margin: 6px 4px;
  background: color-mix(in srgb, var(--sky-ic) 14%, var(--line));

  .collapsed & {
    margin-inline: 2px;
  }
}

.gki-nav-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px 14px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  text-align: left;
  transition: color 0.18s, background 0.18s;

  .collapsed & {
    justify-content: center;
    padding: 11px 8px;
  }

  &:hover {
    color: var(--sky-fg);
    background: color-mix(in srgb, var(--surface) 65%, var(--sky-bg));
  }

  &.active {
    color: var(--sky-fg);
    background: color-mix(in srgb, var(--surface) 88%, var(--sky-bg));
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sky-ic) 22%, transparent);
    font-weight: 700;
  }
}

.gki-nav-label {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  opacity: 1;
  transform: translateX(0);
  transition:
    opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  .collapsed & {
    flex: 0;
    width: 0;
    opacity: 0;
    transform: translateX(-4px);
    pointer-events: none;
  }
}

.gki-nav-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.85;
}

.gki-nav-icon[data-icon='dashboard'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Crect x='3' y='3' width='7' height='7' rx='1'/%3E%3Crect x='14' y='3' width='7' height='7' rx='1'/%3E%3Crect x='3' y='14' width='7' height='7' rx='1'/%3E%3Crect x='14' y='14' width='7' height='7' rx='1'/%3E%3C/svg%3E") center/contain no-repeat;
}

.gki-nav-icon[data-icon='analysis'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Cpath d='M3 3v18h18'/%3E%3Cpath d='M7 16l4-6 4 3 5-7'/%3E%3C/svg%3E") center/contain no-repeat;
}

.gki-nav-icon[data-icon='crash'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Cpath d='M12 9v4'/%3E%3Cpath d='M12 17h.01'/%3E%3Cpath d='M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z'/%3E%3C/svg%3E") center/contain no-repeat;
}

.gki-nav-icon[data-icon='upgrade'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Cpath d='M12 19V5'/%3E%3Cpath d='M5 12l7-7 7 7'/%3E%3C/svg%3E") center/contain no-repeat;
}

.gki-nav-icon[data-icon='database'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Cellipse cx='12' cy='5' rx='9' ry='3'/%3E%3Cpath d='M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5'/%3E%3Cpath d='M3 12c0 1.66 4 3 9 3s9-1.34 9-3'/%3E%3C/svg%3E") center/contain no-repeat;
}

.gki-nav-icon[data-icon='settings'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cpath d='M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z'/%3E%3C/svg%3E") center/contain no-repeat;
}

.gki-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 16px 16px;
}

.gki-main-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.gki-workbench-host {
  flex: 1;
  min-height: 0;
}

.gki-frame {
  width: 100%;
  height: calc(100vh - 150px);
  min-height: 560px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #fff;
  flex: 1;
}

@media (max-width: 900px) {
  .gki-shell {
    display: flex;
    flex-direction: column;

    &.collapsed {
      grid-template-columns: unset;
    }
  }

  .gki-main {
    padding: 12px 16px 16px;
  }

  .gki-sidebar {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    border-right: none;
    border-bottom: 1px solid color-mix(in srgb, var(--sky-ic) 12%, var(--line));
    padding: 12px 14px;

    &.collapsed {
      padding-inline: 14px;
    }
  }

  .gki-sidebar-top {
    margin-bottom: 0;
    margin-right: 8px;
  }

  .gki-nav {
    flex-direction: row;
    flex-wrap: wrap;
    flex: 1;
  }

  .gki-nav-sep {
    display: none;
  }

  .gki-nav-btn {
    width: auto;

    .collapsed & {
      justify-content: flex-start;
      padding: 11px 14px;
    }
  }

  .gki-nav-label {
    .collapsed & {
      width: auto;
      opacity: 1;
      pointer-events: auto;
    }
  }
}
</style>
