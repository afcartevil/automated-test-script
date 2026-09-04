<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NDropdown, useMessage } from 'naive-ui'
import { useAppStore } from '@/stores/hermes/app'
import ModelSelector from './ModelSelector.vue'
import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'
import {
  defaultCollapsedTypes,
  groupApplyItems,
  initialApplySelection,
  matchInboxQuery,
  type ApplyItemType,
  type InboxTab,
} from '@/utils/task-inbox-checklist'

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
  { name: 'tahp.rf-calib-meta', label: '校准数据' },
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
const applyCheckedByPkg = ref<Record<string, string[]>>({})
const applyRecommendedIds = ref<string[]>([])
const applyAlsoPass = ref(false)
const applyBusy = ref(false)
const applyQuery = ref('')
const applyRecOnly = ref(false)
const applyCollapsed = ref<ApplyItemType[]>([])
const inboxTab = ref<InboxTab>('all')
const inboxQuery = ref('')
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
        const sel = initialApplySelection(prompt)
        applyPkgId.value = sel.packageId
        applyCheckedByPkg.value = sel.packageId ? { [sel.packageId]: sel.checked } : {}
        applyRecommendedIds.value = sel.checked
        applyQuery.value = ''
        applyRecOnly.value = false
        applyCollapsed.value = defaultCollapsedTypes(prompt.run?.dimension)
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
const patchPackages = computed(() =>
  inboxPackages.value.filter(p => p.notice_type && p.notice_type !== 'verify-task'),
)
const verifyPackages = computed(() =>
  inboxPackages.value.filter(p => p.notice_type === 'verify-task'),
)
const taskRemain = computed(() => unfinishedChecklist.value.length)
// 红点：检查表新通知 + 验测任务指派通知（patch 通知不计）
const taskUnread = computed(() =>
  unfinishedChecklist.value.filter(p => p.unread).length + verifyPackages.value.length,
)
const applyCanPass = computed(() =>
  applyPrompt.value?.run.status === 'pass' && !applyPrompt.value?.campaign_unspecified,
)

const INBOX_TABS: Array<{ id: InboxTab; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'pipe', label: '流水线' },
  { id: 'check', label: '自检' },
  { id: 'verify', label: '验测' },
  { id: 'patch', label: 'Patch' },
]

function inboxCount(tab: InboxTab) {
  if (tab === 'all') {
    return unfinishedChecklist.value.length + verifyPackages.value.length + patchPackages.value.length
  }
  if (tab === 'pipe') return pipelinePackages.value.length
  if (tab === 'check') return selfCheckPackages.value.length
  if (tab === 'verify') return verifyPackages.value.length
  return patchPackages.value.length
}

function inboxHaystack(pkg: (typeof inboxPackages.value)[number]) {
  if (pkg.notice_type) return `${pkg.title || ''} ${pkg.notice_type}`
  return `${packageHeadline(pkg)} ${packageMeta(pkg)}`
}

function visibleInbox(list: typeof inboxPackages.value) {
  return list.filter(pkg => matchInboxQuery(inboxHaystack(pkg), inboxQuery.value))
}

const showInboxPipe = computed(() => inboxTab.value === 'all' || inboxTab.value === 'pipe')
const showInboxCheck = computed(() => inboxTab.value === 'all' || inboxTab.value === 'check')
const showInboxVerify = computed(() => inboxTab.value === 'all' || inboxTab.value === 'verify')
const showInboxPatch = computed(() => inboxTab.value === 'all' || inboxTab.value === 'patch')
const visiblePipelinePackages = computed(() => visibleInbox(pipelinePackages.value))
const visibleSelfCheckPackages = computed(() => visibleInbox(selfCheckPackages.value))
const visibleVerifyPackages = computed(() => visibleInbox(verifyPackages.value))
const visiblePatchPackages = computed(() => visibleInbox(patchPackages.value))
const inboxListEmpty = computed(() => {
  if (showInboxPipe.value && visiblePipelinePackages.value.length) return false
  if (showInboxCheck.value && visibleSelfCheckPackages.value.length) return false
  if (showInboxVerify.value && visibleVerifyPackages.value.length) return false
  if (showInboxPatch.value && visiblePatchPackages.value.length) return false
  return true
})

function kindBadge(kind?: string) {
  if (kind === 'adapt-pipeline') return '流水线'
  if (kind === 'gki-patch') return 'GKI'
  if (kind === 'modem-patch') return 'Modem'
  if (kind === 'verify-task') return '验测'
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
  const next = !showTaskPop.value
  showTaskPop.value = next
  if (next) {
    inboxTab.value = 'all'
    inboxQuery.value = ''
  }
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

/** 验测任务通知：清掉本机未读红点，直达「质量验测 → 测试执行」 */
async function openVerifyTask(pkg: (typeof inboxPackages.value)[number]) {
  closeTaskPop()
  inboxPackages.value = inboxPackages.value.filter(p => p.package_id !== pkg.package_id)
  try {
    await fetch('/api/tahp/task-inbox/ack', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ package_id: pkg.package_id }),
    })
  } catch {
    /* 清未读失败不阻断跳转 */
  }
  void router.push({ name: 'tahp.self-check', query: { tab: 'devices' } })
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

const applyChecked = computed(() => applyCheckedByPkg.value[applyPkgId.value] || [])

const applyMatchedPkg = computed(() => {
  if (!applyPrompt.value || applyPrompt.value.domain_unspecified) return null
  return applyPrompt.value.packages[0] || null
})

const applyVisibleRows = computed(() => {
  const q = applyQuery.value.trim().toLowerCase()
  return applyRows.value.filter(row => {
    if (applyRecOnly.value && !applyRecommendedIds.value.includes(row.line_id)) return false
    if (!q) return true
    return `${row.item_id} ${row.title}`.toLowerCase().includes(q)
  })
})

const applyTypeGroups = computed(() => groupApplyItems(applyVisibleRows.value).map(group => ({
  ...group,
  checkedCount: group.items.filter(item => applyChecked.value.includes(item.line_id)).length,
  allChecked: group.items.length > 0 && group.items.every(item => applyChecked.value.includes(item.line_id)),
})))

function setApplyChecked(ids: string[]) {
  applyCheckedByPkg.value = { ...applyCheckedByPkg.value, [applyPkgId.value]: ids }
}

function selectApplyPkg(pkgId: string) {
  applyPkgId.value = pkgId
  if (Object.prototype.hasOwnProperty.call(applyCheckedByPkg.value, pkgId)) return
  const matched = applyMatchedPkg.value?.package_id === pkgId
  const rows = applyPrompt.value?.packages.find(p => p.package_id === pkgId)?.pending_items || []
  setApplyChecked(matched ? rows.map(r => r.line_id) : [])
}

function toggleApply(id: string, on: boolean) {
  if (on) setApplyChecked([...new Set([...applyChecked.value, id])])
  else setApplyChecked(applyChecked.value.filter(x => x !== id))
}

function toggleApplyGroup(type: ApplyItemType) {
  applyCollapsed.value = applyCollapsed.value.includes(type)
    ? applyCollapsed.value.filter(t => t !== type)
    : [...applyCollapsed.value, type]
}

function toggleApplyGroupAll(type: ApplyItemType, on: boolean) {
  const ids = applyTypeGroups.value.find(g => g.type === type)?.items.map(i => i.line_id) || []
  if (on) setApplyChecked([...new Set([...applyChecked.value, ...ids])])
  else setApplyChecked(applyChecked.value.filter(id => !ids.includes(id)))
}

function selectAllApplyDomain() {
  setApplyChecked(applyRows.value.map(r => r.line_id))
}

function clearApplyDomain() {
  setApplyChecked([])
}

function restoreApplyRecommended() {
  const prompt = applyPrompt.value
  if (!prompt) return
  const sel = initialApplySelection(prompt)
  applyPkgId.value = sel.packageId
  applyCheckedByPkg.value = sel.packageId ? { [sel.packageId]: sel.checked } : {}
  applyRecommendedIds.value = sel.checked
  applyQuery.value = ''
  applyRecOnly.value = false
  applyCollapsed.value = defaultCollapsedTypes(prompt.run?.dimension)
}

function runKindLabel(dimension?: string) {
  if (dimension === 'self-check') return '自检'
  if (dimension === 'adapt-pipeline') return '流水线'
  return ''
}

function runStatusLabel(status?: string) {
  if (status === 'pass') return '通过'
  if (status === 'fail') return '失败'
  return status || ''
}

async function dismissApply() {
  applyPrompt.value = null
  try { await fetch('/api/tahp/task-apply-dismiss', { method: 'POST' }) } catch { /* ignore */ }
  void refreshTaskInbox()
}

async function confirmApply() {
  if (!applyPrompt.value || !applyPkgId.value) return
  const lineIds = applyChecked.value.filter(id => applyRows.value.some(r => r.line_id === id))
  if (!lineIds.length) return
  const alsoPass = applyAlsoPass.value && applyCanPass.value
  applyBusy.value = true
  try {
    const res = await fetch('/api/tahp/task-apply-run', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        package_id: applyPkgId.value,
        run_id: applyPrompt.value.run.run_id,
        line_ids: lineIds,
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
            <div class="ck-task-pop-hd">
              <div class="ck-task-pop-title">
                <b>我的任务</b>
                <span>未完成 {{ taskRemain }} · 新通知 {{ taskUnread }}</span>
              </div>
              <div>红点=新通知（含验测指派）　左侧数字=流水线+自检未完成包。Patch 单独计。</div>
            </div>
            <div class="ck-task-tabs">
              <button
                v-for="tab in INBOX_TABS"
                :key="tab.id"
                type="button"
                class="ck-task-chip"
                :class="{ on: inboxTab === tab.id }"
                @click="inboxTab = tab.id"
              >
                {{ tab.label }}
                <span v-if="inboxCount(tab.id)">{{ inboxCount(tab.id) }}</span>
              </button>
            </div>
            <input
              v-model="inboxQuery"
              class="ck-task-search"
              type="search"
              placeholder="搜索项目 / 域 / 标题"
            />
            <div class="ck-task-list">
              <template v-if="showInboxPipe && visiblePipelinePackages.length">
                <div class="ck-task-sec">适配流水线</div>
                <div v-for="p in visiblePipelinePackages" :key="p.package_id" class="ck-task-item">
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
              <template v-if="showInboxCheck && visibleSelfCheckPackages.length">
                <div class="ck-task-sec">AI 自检</div>
                <div v-for="p in visibleSelfCheckPackages" :key="p.package_id" class="ck-task-item">
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
              <div v-if="inboxTab !== 'verify' && inboxTab !== 'patch' && !unfinishedChecklist.length" class="ck-task-empty">没有未完成的检查表</div>
              <template v-if="showInboxVerify && visibleVerifyPackages.length">
                <div class="ck-task-sec">验测任务</div>
                <div v-for="p in visibleVerifyPackages" :key="p.package_id" class="ck-task-item">
                  <div>
                    <div>
                      <span class="ck-task-badge check">{{ kindBadge(p.notice_type) }}</span>
                      <b>{{ p.title || '验测任务指派' }}</b>
                    </div>
                    <div class="ck-task-meta">指派验测 · 去「测试执行」跑对应测试项</div>
                  </div>
                  <div class="ck-task-actions">
                    <button type="button" class="ea-btn-ghost ea-btn-sm" @click="openVerifyTask(p)">打开验测</button>
                  </div>
                </div>
              </template>
              <template v-if="showInboxPatch && visiblePatchPackages.length">
                <div class="ck-task-sec">PATCH 通知（不计入 Checklist 红点）</div>
                <div v-for="p in visiblePatchPackages" :key="p.package_id" class="ck-task-item">
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
              <div v-if="inboxListEmpty && unfinishedChecklist.length" class="ck-task-empty">没有匹配的任务</div>
            </div>
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

    <div v-if="applyPrompt" class="model-overlay ck-apply-overlay" @click.self="dismissApply">
      <div class="model-panel ck-apply-panel" @click.stop>
        <div class="ck-apply-head">
          <h3>用本报告勾选 Checklist</h3>
          <p class="ck-apply-meta">
            {{ applyPrompt.run.project_code }}
            <template v-if="runKindLabel(applyPrompt.run.dimension)"> · {{ runKindLabel(applyPrompt.run.dimension) }}</template>
            <template v-if="runStatusLabel(applyPrompt.run.status)"> · {{ runStatusLabel(applyPrompt.run.status) }}</template>
            · {{ applyPrompt.run.run_id }}
            <span v-if="applyPrompt.campaign_unspecified">（报告未标适配版本，不能勾选通过）</span>
          </p>
          <div v-if="applyPrompt.domain_unspecified" class="ck-apply-banner warn">
            报告未标域，请先选左侧域再勾选，避免跨域误挂。
          </div>
          <div v-else-if="applyMatchedPkg" class="ck-apply-banner">
            <span>已按报告自动关联「{{ applyMatchedPkg.domain_label || applyMatchedPkg.title }}」域待处理项（{{ applyRecommendedIds.length }} 项）。其它域未预选。</span>
            <button type="button" class="ck-apply-mini" @click="restoreApplyRecommended">恢复推荐</button>
          </div>
        </div>
        <div class="ck-apply-body" :class="{ 'no-rail': applyPrompt.packages.length < 2 }">
          <aside v-if="applyPrompt.packages.length > 1" class="ck-apply-rail">
            <div class="ck-apply-rail-h">业务域</div>
            <button
              v-for="pkg in applyPrompt.packages"
              :key="pkg.package_id"
              type="button"
              class="ck-apply-dom"
              :class="{ on: pkg.package_id === applyPkgId }"
              @click="selectApplyPkg(pkg.package_id)"
            >
              <span>
                {{ pkg.domain_label || pkg.title }}
                <i v-if="applyMatchedPkg?.package_id === pkg.package_id">匹配</i>
              </span>
              <em>{{ pkg.pending_items.length }}</em>
            </button>
          </aside>
          <section class="ck-apply-main">
            <div class="ck-apply-tools">
              <input v-model="applyQuery" class="ck-apply-search" type="search" placeholder="搜索编号或检查项" />
              <button type="button" class="ck-apply-mini" :class="{ on: applyRecOnly }" @click="applyRecOnly = !applyRecOnly">仅看推荐</button>
              <button type="button" class="ck-apply-mini" @click="selectAllApplyDomain">全选本域</button>
              <button type="button" class="ck-apply-mini" @click="clearApplyDomain">清空本域</button>
            </div>
            <div class="ck-apply-list">
              <div v-for="group in applyTypeGroups" :key="group.type" class="ck-apply-group">
                <div class="ck-apply-ghd">
                  <input
                    type="checkbox"
                    :checked="group.allChecked"
                    @change="toggleApplyGroupAll(group.type, ($event.target as HTMLInputElement).checked)"
                  />
                  <button type="button" @click="toggleApplyGroup(group.type)">
                    <b>{{ group.label }}</b>
                    <span>{{ group.checkedCount }}/{{ group.items.length }}</span>
                    <span>{{ applyCollapsed.includes(group.type) ? '展开' : '收起' }}</span>
                  </button>
                </div>
                <div v-show="!applyCollapsed.includes(group.type)" class="ck-apply-gbody">
                  <label v-for="row in group.items" :key="row.line_id" class="ck-apply-row">
                    <input
                      type="checkbox"
                      :checked="applyChecked.includes(row.line_id)"
                      @change="toggleApply(row.line_id, ($event.target as HTMLInputElement).checked)"
                    />
                    <span>
                      <span class="ck-apply-id">{{ row.item_id }}</span>
                      <span class="ck-apply-title">{{ row.title }}</span>
                    </span>
                    <em v-if="applyRecommendedIds.includes(row.line_id)">推荐</em>
                  </label>
                </div>
              </div>
              <p v-if="!applyTypeGroups.length" class="ck-apply-meta">{{ applyRows.length ? '当前筛选没有匹配项' : '没有待处理行' }}</p>
            </div>
          </section>
        </div>
        <div class="ck-apply-actions">
          <label class="ck-apply-pass">
            <input type="checkbox" v-model="applyAlsoPass" :disabled="!applyCanPass">
            <span>用本报告勾选通过（失败或未标版本的报告只能关联、不改状态）</span>
          </label>
          <span class="ck-apply-count">已选 {{ applyChecked.length }} / {{ applyRows.length }}</span>
          <div class="ck-apply-btns">
            <button type="button" class="ea-btn-ghost ea-btn-sm" :disabled="applyBusy" @click="dismissApply">跳过</button>
            <button type="button" class="ck-feedback-btn" :disabled="applyBusy || !applyChecked.length" @click="confirmApply">
              {{ applyBusy ? '提交中…' : (applyAlsoPass && applyCanPass ? '勾选通过' : '只关联报告') }}
            </button>
          </div>
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
  max-height: min(560px, 70vh);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: #fff;
  border: 1px solid var(--line-strong, #e5e7eb);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.16);
  z-index: 40;
  padding: 10px 0 0;
}
.ck-task-pop-hd {
  padding: 4px 14px 8px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
  flex-shrink: 0;
}
.ck-task-pop-title {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
  color: var(--head);
  font-size: 13px;
}
.ck-task-pop-title span { font-weight: 400; color: var(--muted); font-size: 12px; }
.ck-task-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 14px 8px;
  flex-shrink: 0;
}
.ck-task-chip {
  border: 1px solid var(--line, #e5e7eb);
  background: #fff;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--muted);
}
.ck-task-chip span {
  margin-left: 4px;
  font-weight: 700;
}
.ck-task-chip.on {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.ck-task-search {
  margin: 0 14px 8px;
  height: 32px;
  border: 1px solid var(--line, #e5e7eb);
  border-radius: 8px;
  padding: 0 10px;
  font-size: 13px;
  flex-shrink: 0;
}
.ck-task-list {
  overflow: auto;
  flex: 1;
  min-height: 0;
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
  flex-shrink: 0;
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
  width: min(860px, calc(100vw - 32px));
  max-width: 860px;
  height: min(640px, calc(100vh - 48px));
  max-height: calc(100vh - 48px);
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  h3 { margin: 0 0 4px; font-size: 16px; }
}
.ck-apply-head, .ck-apply-actions { flex-shrink: 0; padding: 16px 18px; }
.ck-apply-head { border-bottom: 1px solid var(--line, #e5e7eb); }
.ck-apply-meta { font-size: 12px; color: var(--muted); margin: 0; line-height: 1.45; }
.ck-apply-banner {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #ecfdf5;
  color: #166534;
  font-size: 12px;
  line-height: 1.45;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  &.warn { background: #fffbeb; color: #92400e; }
}
.ck-apply-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 196px 1fr;
  &.no-rail { grid-template-columns: 1fr; }
}
.ck-apply-rail {
  border-right: 1px solid var(--line, #e5e7eb);
  padding: 10px;
  overflow: auto;
  background: #fafbfe;
}
.ck-apply-rail-h {
  margin: 4px 8px 8px;
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.04em;
}
.ck-apply-dom {
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  padding: 9px 10px;
  border-radius: 9px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: var(--text, #1f2937);
  i { font-style: normal; font-size: 10px; color: #16a34a; font-weight: 700; margin-left: 4px; }
  em {
    font-style: normal;
    font-size: 11px;
    color: var(--muted);
    background: #eef0f4;
    padding: 1px 6px;
    border-radius: 999px;
  }
  &.on {
    background: #fff;
    box-shadow: 0 0 0 1px var(--accent);
    font-weight: 650;
    em { background: var(--accent-soft); color: var(--accent); }
  }
}
.ck-apply-main { min-width: 0; display: flex; flex-direction: column; min-height: 0; }
.ck-apply-tools {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line, #e5e7eb);
  flex-shrink: 0;
  flex-wrap: wrap;
}
.ck-apply-search {
  flex: 1;
  min-width: 140px;
  height: 32px;
  border: 1px solid var(--line, #e5e7eb);
  border-radius: 8px;
  padding: 0 10px;
  font-size: 13px;
}
.ck-apply-mini {
  border: 1px solid var(--line, #e5e7eb);
  background: #fff;
  border-radius: 8px;
  padding: 0 10px;
  height: 32px;
  font-size: 12px;
  white-space: nowrap;
  &.on { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
}
.ck-apply-list { flex: 1; overflow: auto; padding: 8px 12px 14px; min-height: 0; }
.ck-apply-group {
  border: 1px solid var(--line, #e5e7eb);
  border-radius: 10px;
  margin-bottom: 8px;
  overflow: hidden;
}
.ck-apply-ghd {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f8fafc;
  button {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    border: 0;
    background: transparent;
    text-align: left;
    font-size: 13px;
    b { flex: 1; }
    span { color: var(--muted); font-size: 12px; }
  }
}
.ck-apply-gbody { padding: 4px 8px 8px; }
.ck-apply-row {
  display: grid;
  grid-template-columns: 18px 1fr auto;
  gap: 8px;
  align-items: flex-start;
  font-size: 13px;
  margin: 0;
  padding: 7px 6px;
  border-radius: 8px;
  em { font-style: normal; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 999px; background: #ecfdf5; color: #15803d; }
}
.ck-apply-id { display: block; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
.ck-apply-title { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }
.ck-apply-actions {
  border-top: 1px solid var(--line, #e5e7eb);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ck-apply-pass {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
  max-width: 360px;
}
.ck-apply-count { font-size: 13px; color: var(--muted); }
.ck-apply-btns { margin-left: auto; display: flex; gap: 8px; }
.ck-apply-overlay { padding: 24px; }

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

  .ck-apply-body:not(.no-rail) { grid-template-columns: 1fr; }
  .ck-apply-rail { display: flex; gap: 6px; overflow: auto; border-right: 0; border-bottom: 1px solid var(--line, #e5e7eb); }
  .ck-apply-dom { width: auto; white-space: nowrap; }
}
</style>
