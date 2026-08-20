<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NDropdown, useMessage } from 'naive-ui'
import { useAppStore } from '@/stores/hermes/app'
import ModelSelector from './ModelSelector.vue'
import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const appStore = useAppStore()
const showModelModal = ref(false)

const CONFIG_ROUTE_NAMES = new Set([
  CONFIG_ROUTE_NAME,
  'hermes.models',
  'tahp.skill-config',
])

const coreNav = [
  { name: 'tahp.dashboard', label: '首页' },
  { name: 'tahp.adapt-debug', label: 'AI 适配调试' },
  { name: 'tahp.pipeline', label: '适配流水线' },
  { name: 'tahp.modem-baseline.workbench', label: 'Modem升级' },
  { name: 'tahp.gki-patch.dashboard', label: 'GKI 升级' },
]

const publicNav = [
  { name: 'tahp.bug-analysis', label: '智能诊断' },
  { name: 'tahp.self-check', label: '质量验测' },
  { name: 'tahp.code-pull', label: '代码拉取' },
]

const secondaryNav = [
  { name: 'tahp.reports', label: '报告' },
  { name: 'tahp.evals', label: '质量评测' },
  { name: 'hermes.skills', label: 'Skills' },
  { name: 'hermes.chat', label: '对话搜索' },
]

const systemNav = [
  { name: CONFIG_ROUTE_NAME, label: '配置' },
]

const FEEDBACK_URL = 'https://transsioner.feishu.cn/share/base/form/shrcnDOMx8H12Nm1tcTmIOAHDId'
const taskUnread = ref(0)
const inboxPackages = ref<Array<{
  package_id: string
  project_code: string
  domain_label?: string
  title: string
  unread?: boolean
  unread_count?: number
  notice_type?: string
  next?: string
}>>([])
type ApplyPrompt = {
  run: { run_id: string; project_code: string; status?: string; dimension?: string; domain_id?: string }
  packages: Array<{
    package_id: string
    title: string
    domain_label: string
    pending_items: Array<{ line_id: string; item_id: string; title: string }>
  }>
  also_pass_default?: boolean
  domain_unspecified?: boolean
}
const applyPrompt = ref<ApplyPrompt | null>(null)
const applyPkgId = ref('')
const applyChecked = ref<string[]>([])
const applyAlsoPass = ref(true)
const applyBusy = ref(false)

const manualNav: Array<{ label: string; name?: string; url?: string }> = [
  { label: 'EasyAdapter 使用手册', name: 'tahp.manual' },
]

const selectedKey = computed(() => {
  const name = route.name?.toString() || ''
  if (CONFIG_ROUTE_NAMES.has(name)) return CONFIG_ROUTE_NAME
  return name
})

function isActive(name: string) {
  if (name === 'tahp.modem-baseline.workbench') {
    return selectedKey.value.startsWith('tahp.modem-baseline')
  }
  if (name === 'tahp.gki-patch.dashboard') {
    return selectedKey.value.startsWith('tahp.gki-patch')
  }
  return selectedKey.value === name
}

const modelDisplay = computed(() => {
  const groups = appStore.profileModelGroups.find(g => g.profile === (appStore as any).activeProfile)?.groups
    || appStore.profileModelGroups[0]?.groups
    || []
  const found = groups.find(g => g.provider === appStore.selectedProvider)
  if (found && found.models.includes(appStore.selectedModel)) {
    return appStore.displayModelName(appStore.selectedModel, appStore.selectedProvider)
  }
  return appStore.selectedModel || '—'
})

const systemOptions = systemNav.map(item => ({
  label: item.label,
  key: item.name,
}))

const publicOptions = publicNav.map(item => ({
  label: item.label,
  key: item.name,
}))

const secondaryOptions = secondaryNav.map(item => ({
  label: item.label,
  key: item.name,
}))

const manualOptions = manualNav.map((item, idx) => ({
  label: item.label,
  key: `manual:${idx}`,
}))

const isPublicActive = computed(() => publicNav.some(item => isActive(item.name)))
const isSecondaryActive = computed(() => secondaryNav.some(item => isActive(item.name)))
const isManualActive = computed(() => selectedKey.value === 'tahp.manual')
const flushLayout = computed(() => route.meta.flushLayout === true)

function goHome() {
  router.push({ name: 'tahp.dashboard' })
}

function nav(name: string) {
  router.push({ name })
}

function onSystemSelect(key: string) {
  router.push({ name: key })
}

function onPublicSelect(key: string) {
  router.push({ name: key })
}

function onSecondarySelect(key: string) {
  router.push({ name: key })
}

function onManualSelect(key: string) {
  const idx = Number(key.split(':')[1])
  const item = manualNav[idx]
  if (!item) return
  if (item.name) router.push({ name: item.name })
  else if (item.url) window.open(item.url, '_blank', 'noopener,noreferrer')
}

async function handleUpdate() {
  const ok = await appStore.doUpdate()
  if (ok) message.success('更新成功', { duration: 5000 })
  else message.error('更新失败')
}

async function refreshTaskInbox() {
  try {
    const res = await fetch('/api/tahp/task-inbox')
    const json = await res.json() as {
      success?: boolean
      data?: { unread?: number; packages?: typeof inboxPackages.value; apply_prompt?: ApplyPrompt | null }
    }
    if (!json.success) return
    taskUnread.value = json.data?.unread || 0
    inboxPackages.value = json.data?.packages || []
    const prompt = json.data?.apply_prompt || null
    if (prompt?.packages?.some(p => p.pending_items?.length) && !applyPrompt.value) {
      applyPrompt.value = prompt
      applyPkgId.value = prompt.packages[0]?.package_id || ''
      const first = prompt.packages[0]
      applyChecked.value = first?.pending_items.map(i => i.line_id) || []
      applyAlsoPass.value = prompt.also_pass_default !== false && prompt.run?.status === 'pass'
      if (prompt.run?.status && prompt.run.status !== 'pass') applyAlsoPass.value = false
    }
  } catch {
    /* 中心不可达时保持原数字 */
  }
}

async function openCentral(next: string) {
  try {
    const res = await fetch('/api/tahp/central/sso-url?next=' + encodeURIComponent(next))
    const json = await res.json() as { success?: boolean; data?: { url?: string }; error?: string }
    if (!json.success || !json.data?.url) {
      message.error(json.error || '无法打开中心页面')
      return
    }
    window.open(json.data.url, '_blank')
  } catch (e) {
    message.error((e as Error).message || '无法打开中心页面')
  }
}

const taskOptions = computed(() => {
  const items = inboxPackages.value.map(p => ({
    label: p.notice_type
      ? (p.title || (p.notice_type === 'gki-patch' ? 'GKI Patch' : 'Modem Patch'))
      : `${p.project_code} · ${p.domain_label || ''} · ${p.title || ''}`.replace(/ · $/, ''),
    key: p.notice_type ? `patch:${p.package_id}` : `pkg:${p.package_id}`,
  }))
  return [
    ...items,
    ...(items.length ? [{ type: 'divider', key: 'div' }] : []),
    { label: '打开我的 Checklist', key: 'all' },
  ]
})

function onTaskSelect(key: string) {
  if (key === 'all') {
    void openCentral('/tasks/mine')
    return
  }
  if (key.startsWith('patch:')) {
    const id = key.slice('patch:'.length)
    const item = inboxPackages.value.find(p => p.package_id === id)
    if (item?.notice_type === 'gki-patch') {
      void router.push({ name: 'tahp.gki-patch.dashboard' })
      return
    }
    void router.push({ name: 'tahp.modem-baseline.workbench' })
    return
  }
  if (key.startsWith('pkg:')) {
    void openCentral('/tasks/mine?package=' + encodeURIComponent(key.slice(4)))
  }
}

const applyRows = computed(() =>
  applyPrompt.value?.packages.find(p => p.package_id === applyPkgId.value)?.pending_items || [],
)

function toggleApply(id: string, on: boolean) {
  if (on) applyChecked.value = [...new Set([...applyChecked.value, id])]
  else applyChecked.value = applyChecked.value.filter(x => x !== id)
}

async function dismissApply() {
  applyPrompt.value = null
  try { await fetch('/api/tahp/task-apply-dismiss', { method: 'POST' }) } catch { /* ignore */ }
}

async function confirmApply() {
  if (!applyPrompt.value || !applyPkgId.value || !applyChecked.value.length) return
  applyBusy.value = true
  try {
    const res = await fetch('/api/tahp/task-apply-run', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        package_id: applyPkgId.value,
        run_id: applyPrompt.value.run.run_id,
        line_ids: applyChecked.value,
        also_pass: applyAlsoPass.value,
      }),
    })
    const json = await res.json() as { success?: boolean; error?: string }
    if (!json.success) {
      message.error(json.error || '勾选失败')
      return
    }
    message.success(applyAlsoPass.value ? '已用本报告勾选通过' : '已关联报告')
    applyPrompt.value = null
  } catch (e) {
    message.error((e as Error).message || '勾选失败')
  } finally {
    applyBusy.value = false
  }
}

const inboxTimer = window.setInterval(refreshTaskInbox, 15000)
refreshTaskInbox()
onUnmounted(() => window.clearInterval(inboxTimer))
</script>

<template>
  <div class="ck-shell">
    <header class="ck-topbar">
      <div class="ck-brand" @click="goHome">
        <span class="ck-brand-mark">EA</span>
        EasyAdapter
      </div>

      <nav class="ck-tabs">
        <button
          v-for="item in coreNav"
          :key="item.name"
          type="button"
          class="ck-tab"
          :class="{ active: isActive(item.name) }"
          @click="nav(item.name)"
        >
          {{ item.label }}
        </button>

        <span class="ck-tab-sep" />

        <NDropdown trigger="click" :options="publicOptions" @select="onPublicSelect">
          <button
            type="button"
            class="ck-tab ck-tab-sub"
            :class="{ active: isPublicActive }"
          >
            公共能力
            <svg
              class="ck-caret"
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.4"
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        </NDropdown>

        <NDropdown trigger="click" :options="secondaryOptions" @select="onSecondarySelect">
          <button
            type="button"
            class="ck-tab ck-tab-sub"
            :class="{ active: isSecondaryActive }"
          >
            运营监控
            <svg
              class="ck-caret"
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.4"
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        </NDropdown>

        <NDropdown trigger="click" :options="manualOptions" @select="onManualSelect">
          <button
            type="button"
            class="ck-tab ck-tab-sub"
            :class="{ active: isManualActive }"
          >
            使用手册
            <svg
              class="ck-caret"
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.4"
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        </NDropdown>
      </nav>

      <div class="ck-spacer">
        <NDropdown trigger="click" :options="taskOptions" @select="onTaskSelect">
          <button type="button" class="ck-feedback-btn" title="打开中心我的 Checklist">
            我的任务
            <span v-if="taskUnread" class="ck-task-dot">{{ taskUnread > 9 ? '9+' : taskUnread }}</span>
          </button>
        </NDropdown>
        <a
          :href="FEEDBACK_URL"
          class="ck-feedback-btn"
          target="_blank"
          rel="noopener noreferrer"
          title="在飞书多维表格中反馈问题"
        >
          反馈问题
        </a>

        <button type="button" class="ck-mini-model" @click="showModelModal = true">
          <span class="ck-mini-dot" :class="{ offline: !appStore.connected }" />
          <b>{{ modelDisplay }}</b>
        </button>

        <NDropdown trigger="click" :options="systemOptions" @select="onSystemSelect">
          <button type="button" class="ck-sys-btn" title="系统">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
            </svg>
          </button>
        </NDropdown>

        <button v-if="appStore.updateAvailable" type="button" class="ck-sys-btn update" @click="handleUpdate" title="更新">
          ↑
        </button>
      </div>
    </header>

    <main class="ck-content" :class="{ 'ck-content--flush': flushLayout }">
      <slot />
    </main>

    <div v-show="showModelModal" class="model-overlay" @click.self="showModelModal = false">
      <div class="model-panel">
        <ModelSelector />
        <button type="button" class="ea-btn-ghost ea-btn-sm model-close" @click="showModelModal = false">关闭</button>
      </div>
    </div>

    <div v-if="applyPrompt" class="model-overlay" @click.self="dismissApply">
      <div class="model-panel ck-apply-panel">
        <h3>用本报告勾选 Checklist</h3>
        <p class="ck-apply-meta">
          {{ applyPrompt.run.project_code }} · {{ applyPrompt.run.run_id }}
          <span v-if="applyPrompt.domain_unspecified">（报告未标域，请确认不要跨域误挂）</span>
        </p>
        <label v-if="applyPrompt.packages.length > 1" class="ck-apply-pkg">
          工作包
          <select v-model="applyPkgId" @change="applyChecked = applyRows.map(i => i.line_id)">
            <option v-for="p in applyPrompt.packages" :key="p.package_id" :value="p.package_id">
              {{ p.title || p.domain_label }}
            </option>
          </select>
        </label>
        <label v-for="row in applyRows" :key="row.line_id" class="ck-apply-row">
          <input type="checkbox" :checked="applyChecked.includes(row.line_id)" @change="toggleApply(row.line_id, ($event.target as HTMLInputElement).checked)">
          <span>{{ row.item_id }} {{ row.title }}</span>
        </label>
        <p v-if="!applyRows.length" class="ck-apply-meta">没有待处理行</p>
        <label class="ck-apply-row">
          <input type="checkbox" v-model="applyAlsoPass" :disabled="applyPrompt.run.status !== 'pass'">
          <span>用本报告勾选通过（失败报告只能关联、不改状态）</span>
        </label>
        <div class="ck-apply-actions">
          <button type="button" class="ea-btn-ghost ea-btn-sm" :disabled="applyBusy" @click="dismissApply">跳过</button>
          <button type="button" class="ck-feedback-btn" :disabled="applyBusy || !applyChecked.length" @click="confirmApply">
            {{ applyBusy ? '提交中…' : (applyAlsoPass ? '勾选通过' : '只关联报告') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.ck-shell {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--bg);
}

.ck-topbar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 16px 28px;
  background: transparent;
  flex-shrink: 0;
}

.ck-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 17px;
  font-weight: 800;
  letter-spacing: -0.02em;
  cursor: pointer;
  flex-shrink: 0;
  color: var(--head);
}

.ck-brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 800;
}

.ck-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  overflow-x: auto;
  scrollbar-width: none;
  flex: 1;
  min-width: 0;

  &::-webkit-scrollbar { display: none; }
}

.ck-tab {
  padding: 8px 14px;
  border: none;
  background: none;
  color: var(--muted);
  cursor: pointer;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 600;
  border-radius: 9px;
  white-space: nowrap;
  transition: color 0.18s, background 0.18s;

  &:hover { color: var(--text); background: var(--surface); }
  &.active { color: var(--accent); background: var(--accent-soft); font-weight: 700; }
}

.ck-tab-sub {
  font-size: 13px;
  font-weight: 500;
  color: #8b909f;
  display: inline-flex;
  align-items: center;
}

.ck-caret {
  margin-left: 2px;
  opacity: 0.6;
}

.ck-tab-sep {
  width: 1px;
  height: 20px;
  background: var(--line-strong);
  margin: 0 8px;
  flex-shrink: 0;
}

.ck-spacer {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.ck-task-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  margin-left: 6px;
  padding: 0 4px;
  border-radius: 8px;
  background: #e11d48;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.ck-apply-panel {
  max-width: 520px;
  padding: 20px 22px;
  h3 { margin: 0 0 8px; font-size: 16px; }
}
.ck-apply-meta { font-size: 12px; color: var(--muted); margin: 0 0 12px; }
.ck-apply-pkg { display: flex; flex-direction: column; gap: 4px; font-size: 13px; margin-bottom: 10px; }
.ck-apply-row { display: flex; align-items: flex-start; gap: 8px; font-size: 13px; margin: 6px 0; }
.ck-apply-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

.ck-feedback-btn {
  display: inline-flex;
  align-items: center;
  padding: 7px 14px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.18s, background 0.18s, border-color 0.18s;

  &:hover {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent-soft) 70%, var(--accent) 12%);
    border-color: color-mix(in srgb, var(--accent) 42%, transparent);
  }
}

.ck-mini-model {
  font-size: 12px;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: var(--shadow);
  white-space: nowrap;
  border: none;
  cursor: pointer;
  font-family: inherit;
  max-width: 200px;

  b {
    color: var(--accent);
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.ck-mini-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
  flex-shrink: 0;

  &.offline { background: var(--error); }
}

.ck-sys-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  color: var(--muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all 0.18s;

  &:hover { border-color: var(--accent); color: var(--accent); }
  &.update { color: var(--warn); font-weight: 800; }
}

.ck-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 28px 40px;
  min-height: 0;

  &--flush {
    padding: 0;
    overflow: hidden;
    display: flex;
  }
}

.model-overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 24, 40, 0.35);
  z-index: 2000;
  display: grid;
  place-items: center;
}

.model-panel {
  background: var(--surface);
  border-radius: 18px;
  padding: 20px;
  width: min(480px, calc(100vw - 32px));
  box-shadow: var(--shadow-lg);
}

.model-close {
  margin-top: 12px;
  width: 100%;
}

@media (max-width: 768px) {
  .ck-topbar {
    flex-wrap: wrap;
    padding: 12px 16px;
    gap: 10px;
  }

  .ck-tabs {
    order: 3;
    width: 100%;
  }
}
</style>
