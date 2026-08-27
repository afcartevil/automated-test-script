<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
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
const inboxPackages = ref<Array<{
  package_id: string
  project_code: string
  campaign_id?: string
  domain_id?: string
  domain_label?: string
  title: string
  kind?: string
  unread?: boolean
  unread_count?: number
  notice_type?: string
  next?: string
  version_type?: string
  variant?: string
  node_rule_id?: string
  resolved_version?: string
  track_mode?: 'pipeline' | 'manual'
}>>([])
type ApplyPrompt = {
  run: { run_id: string; project_code: string; campaign_id?: string; status?: string; dimension?: string; domain_id?: string }
  packages: Array<{
    package_id: string
    title: string
    domain_label: string
    pending_items: Array<{ line_id: string; item_id: string; title: string }>
  }>
  also_pass_default?: boolean
  domain_unspecified?: boolean
  campaign_unspecified?: boolean
}
const applyPrompt = ref<ApplyPrompt | null>(null)
const applyPkgId = ref('')
const applyChecked = ref<string[]>([])
const applyAlsoPass = ref(false)
const applyBusy = ref(false)
const taskContext = ref<{
  package_id: string
  project_code: string
  campaign_id: string
  domain_id: string
  kind: string
  set_at: string
} | null>(null)
const hideContextBanner = ref(false)
const showTaskPop = ref(false)
const taskPopWrap = ref<HTMLElement | null>(null)

const manualNav: Array<{ label: string; name?: string; url?: string }> = [
  { label: 'EasyAdapter 使用手册', name: 'tahp.manual' },
  { label: '反馈问题', url: FEEDBACK_URL },
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
      data?: {
        unread?: number
        packages?: typeof inboxPackages.value
        apply_prompt?: ApplyPrompt | null
        task_context?: typeof taskContext.value
      }
    }
    if (!json.success) return
    inboxPackages.value = json.data?.packages || []
    const nextCtx = json.data?.task_context || null
    if (nextCtx?.set_at !== taskContext.value?.set_at) hideContextBanner.value = false
    taskContext.value = nextCtx
    if (applyBusy.value) return
    const prompt = json.data?.apply_prompt || null
    if (prompt?.packages?.some(p => p.pending_items?.length)) {
      if (applyPrompt.value?.run.run_id !== prompt.run.run_id) {
        applyPrompt.value = prompt
        applyPkgId.value = prompt.packages[0]?.package_id || ''
        const first = prompt.packages[0]
        applyChecked.value = first?.pending_items.map(i => i.line_id) || []
        applyAlsoPass.value = prompt.run?.status === 'pass' && !prompt.campaign_unspecified
      }
    } else {
      applyPrompt.value = null
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

const checklistPackages = computed(() => inboxPackages.value.filter(p => !p.notice_type))
const unfinishedChecklist = computed(() =>
  checklistPackages.value.filter(p => (p.unread_count || 0) > 0),
)
const pipelinePackages = computed(() =>
  unfinishedChecklist.value.filter(p => p.kind === 'adapt-pipeline'),
)
const selfCheckPackages = computed(() =>
  unfinishedChecklist.value.filter(p => p.kind !== 'adapt-pipeline'),
)
const patchPackages = computed(() => inboxPackages.value.filter(p => p.notice_type))
const taskRemain = computed(() => unfinishedChecklist.value.length)
const taskUnread = computed(() => unfinishedChecklist.value.filter(p => p.unread).length)
const applyCanPass = computed(() =>
  applyPrompt.value?.run.status === 'pass' && !applyPrompt.value?.campaign_unspecified,
)

function kindBadge(kind?: string) {
  if (kind === 'adapt-pipeline') return '流水线'
  if (kind === 'gki-patch') return 'GKI'
  if (kind === 'modem-patch') return 'Modem'
  return '自检'
}

function nodeLabel(p: (typeof inboxPackages.value)[number]) {
  const bits = [p.version_type === 'TEST' ? '转测 TEST' : p.version_type, p.variant].filter(Boolean)
  return bits.join(' · ')
}

function packageHeadline(p: (typeof inboxPackages.value)[number]) {
  if (p.kind === 'self-check') {
    return [p.project_code, nodeLabel(p) || '节点', p.domain_label || p.domain_id].filter(Boolean).join(' · ')
  }
  return [p.project_code, p.campaign_id, p.domain_label || p.domain_id].filter(Boolean).join(' · ')
}

function packageMeta(p: (typeof inboxPackages.value)[number]) {
  const bits: string[] = []
  if (p.unread) bits.push('新通知')
  if (p.track_mode === 'manual') bits.push('人工跟踪')
  if (p.kind === 'self-check') bits.push('将拉取最新包')
  bits.push(`${p.unread_count || 0} 项未完成`)
  return bits.join(' · ')
}

function canGoExecute(p: (typeof inboxPackages.value)[number]) {
  return p.track_mode !== 'manual'
}

function toggleTaskPop(e: Event) {
  e.stopPropagation()
  showTaskPop.value = !showTaskPop.value
}

function closeTaskPop() {
  showTaskPop.value = false
}

function onDocClick(e: MouseEvent) {
  const el = taskPopWrap.value
  if (!el) return
  if (!el.contains(e.target as Node)) showTaskPop.value = false
}

function openChecklist(pkg: (typeof inboxPackages.value)[number]) {
  closeTaskPop()
  void openCentral('/tasks/mine?package=' + encodeURIComponent(pkg.package_id))
}

function openAllChecklist() {
  closeTaskPop()
  void openCentral('/tasks/mine')
}

function openHistory() {
  closeTaskPop()
  void openCentral('/tasks/mine?view=history')
}

function openPatch(pkg: (typeof inboxPackages.value)[number]) {
  closeTaskPop()
  if (pkg.notice_type === 'gki-patch') void router.push({ name: 'tahp.gki-patch.dashboard' })
  else void router.push({ name: 'tahp.modem-baseline.workbench' })
}

async function goExecute(pkg: (typeof inboxPackages.value)[number]) {
  closeTaskPop()
  const selfCheck = pkg.kind === 'self-check'
  try {
    await fetch('/api/tahp/task-context', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        package_id: pkg.package_id,
        project_code: pkg.project_code,
        campaign_id: selfCheck ? '' : (pkg.campaign_id || ''),
        domain_id: pkg.domain_id || '',
        kind: pkg.kind || 'self-check',
        node_rule_id: pkg.node_rule_id || '',
      }),
    })
  } catch {
    /* 本机 context 写失败仍打开执行页 */
  }
  const name = pkg.kind === 'adapt-pipeline' ? 'tahp.pipeline' : 'tahp.self-check'
  void router.push({
    name,
    query: selfCheck
      ? {
          project_code: pkg.project_code || '',
          domain_id: pkg.domain_id || '',
          package_id: pkg.package_id,
        }
      : {
          project_code: pkg.project_code || '',
          campaign_id: pkg.campaign_id || '',
          domain_id: pkg.domain_id || '',
          package_id: pkg.package_id,
        },
  })
  hideContextBanner.value = false
  void refreshTaskInbox()
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
  void refreshTaskInbox()
}

async function confirmApply() {
  if (!applyPrompt.value || !applyPkgId.value || !applyChecked.value.length) return
  const alsoPass = applyAlsoPass.value && applyCanPass.value
  applyBusy.value = true
  try {
    const res = await fetch('/api/tahp/task-apply-run', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        package_id: applyPkgId.value,
        run_id: applyPrompt.value.run.run_id,
        line_ids: applyChecked.value,
        also_pass: alsoPass,
      }),
    })
    const json = await res.json() as { success?: boolean; error?: string }
    if (!json.success) {
      message.error(json.error || '勾选失败')
      return
    }
    message.success(alsoPass ? '已用本报告勾选通过' : '已关联报告')
    applyPrompt.value = null
    await refreshTaskInbox()
  } catch (e) {
    message.error((e as Error).message || '勾选失败')
  } finally {
    applyBusy.value = false
  }
}

const inboxTimer = window.setInterval(refreshTaskInbox, 15000)
refreshTaskInbox()
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  window.clearInterval(inboxTimer)
})
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
        <div ref="taskPopWrap" class="ck-task-wrap">
          <button type="button" class="ck-feedback-btn" title="我的任务" @click="toggleTaskPop">
            我的任务
            <span v-if="taskRemain" class="ck-task-remain" title="未完成工作包">{{ taskRemain > 9 ? '9+' : taskRemain }}</span>
            <span v-if="taskUnread" class="ck-task-dot" title="未读通知">{{ taskUnread > 9 ? '9+' : taskUnread }}</span>
          </button>
          <div v-if="showTaskPop" class="ck-task-pop">
            <div class="ck-task-pop-hd">红点=新通知　左侧数字=流水线+自检未完成包。打开清单不会把未完成清掉。Patch 单独计。</div>
            <template v-if="pipelinePackages.length">
              <div class="ck-task-sec">适配流水线</div>
              <div v-for="p in pipelinePackages" :key="p.package_id" class="ck-task-item">
                <div>
                  <div>
                    <span class="ck-task-badge pipe">{{ kindBadge(p.kind) }}</span>
                    <b>{{ packageHeadline(p) }}</b>
                  </div>
                  <div class="ck-task-meta">{{ packageMeta(p) }}</div>
                </div>
                <div class="ck-task-actions">
                  <button type="button" class="ea-btn-ghost ea-btn-sm" @click="openChecklist(p)">打开清单</button>
                  <button v-if="canGoExecute(p)" type="button" class="ck-feedback-btn ck-task-go" @click="goExecute(p)">去执行</button>
                </div>
              </div>
            </template>
            <template v-if="selfCheckPackages.length">
              <div class="ck-task-sec">AI 自检</div>
              <div v-for="p in selfCheckPackages" :key="p.package_id" class="ck-task-item">
                <div>
                  <div>
                    <span class="ck-task-badge check">{{ kindBadge(p.kind) }}</span>
                    <b>{{ packageHeadline(p) }}</b>
                  </div>
                  <div class="ck-task-meta">{{ packageMeta(p) }}</div>
                </div>
                <div class="ck-task-actions">
                  <button type="button" class="ea-btn-ghost ea-btn-sm" @click="openChecklist(p)">打开清单</button>
                  <button v-if="canGoExecute(p)" type="button" class="ck-feedback-btn ck-task-go" @click="goExecute(p)">去执行</button>
                </div>
              </div>
            </template>
            <div v-if="!unfinishedChecklist.length" class="ck-task-empty">没有未完成的检查表</div>
            <template v-if="patchPackages.length">
              <div class="ck-task-sec">PATCH 通知（不计入 Checklist 红点）</div>
              <div v-for="p in patchPackages" :key="p.package_id" class="ck-task-item">
                <div>
                  <div>
                    <span class="ck-task-badge patch">{{ kindBadge(p.notice_type) }}</span>
                    <b>{{ p.title || (p.notice_type === 'gki-patch' ? 'GKI Patch' : 'Modem Patch') }}</b>
                  </div>
                  <div class="ck-task-meta">仅订阅名单 · 点进现有 Patch 页</div>
                </div>
                <div class="ck-task-actions">
                  <button type="button" class="ea-btn-ghost ea-btn-sm" @click="openPatch(p)">打开 Patch</button>
                </div>
              </div>
            </template>
            <div class="ck-task-foot">
              <button type="button" class="ck-task-all" @click="openAllChecklist">打开我的 Checklist</button>
              <button type="button" class="ck-task-all" @click="openHistory">查看历史</button>
            </div>
          </div>
        </div>

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

    <div v-if="taskContext && !hideContextBanner" class="ck-task-ctx">
      当前任务：{{ taskContext.project_code }}
      <template v-if="taskContext.kind === 'self-check'">
        <span v-if="taskContext.domain_id"> · {{ taskContext.domain_id }}</span>
        · 将拉最新包，不预填适配版本
      </template>
      <template v-else>
        <span v-if="taskContext.campaign_id"> · {{ taskContext.campaign_id }}</span>
        <span v-if="taskContext.domain_id"> · {{ taskContext.domain_id }}</span>
        · 上报将优先带上该项目/版本
      </template>
      <button type="button" class="ck-task-ctx-x" @click="hideContextBanner = true">关闭</button>
    </div>

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
          <span v-if="applyPrompt.campaign_unspecified">（报告未标适配版本，不能勾选通过）</span>
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
          <input type="checkbox" v-model="applyAlsoPass" :disabled="!applyCanPass">
          <span>用本报告勾选通过（失败或未标版本的报告只能关联、不改状态）</span>
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
.ck-task-remain {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  margin-left: 6px;
  padding: 0 4px;
  border-radius: 8px;
  background: #fff;
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}
.ck-task-wrap { position: relative; }
.ck-task-pop {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  width: min(480px, calc(100vw - 32px));
  background: #fff;
  border: 1px solid var(--line-strong, #e5e7eb);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.16);
  z-index: 40;
  padding: 10px 0 8px;
}
.ck-task-pop-hd {
  padding: 4px 14px 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}
.ck-task-sec {
  padding: 8px 14px 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--muted);
}
.ck-task-empty {
  padding: 10px 14px 12px;
  font-size: 13px;
  color: var(--muted);
}
.ck-task-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
}
.ck-task-item b { font-size: 13px; }
.ck-task-meta { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.4; }
.ck-task-actions { display: flex; gap: 6px; flex-shrink: 0; }
.ck-task-go { padding: 5px 10px !important; font-size: 12px !important; }
.ck-task-badge {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}
.ck-task-badge.check { background: #ede9fe; color: #6d28d9; }
.ck-task-badge.pipe { background: #dbeafe; color: #1d4ed8; }
.ck-task-badge.patch { background: #ffedd5; color: #c2410c; }
.ck-task-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  border-top: 1px solid #f1f5f9;
  margin-top: 4px;
}
.ck-task-all {
  display: block;
  width: auto;
  flex: 1;
  margin: 0;
  padding: 8px 10px;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}

.ck-task-ctx {
  margin: 0 28px 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #eef4ff;
  color: var(--head);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ck-task-ctx-x {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
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
