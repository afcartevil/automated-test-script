<script setup lang="ts">
import { ref, computed, reactive, watch, nextTick, onMounted } from 'vue'
import { NButton, NSelect, NInput, NProgress, NTag, NSpin, NModal, NTabs, NTabPane, NForm, NFormItem, NSwitch, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import ModelProviderBanner from '@/components/tahp/ModelProviderBanner.vue'
import BugAnalysisInteractionModal from '@/components/tahp/BugAnalysisInteractionModal.vue'
import type { ContinueChatPrompt } from '@/components/tahp/BugAnalysisInteractionModal.vue'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import type { TahpModule } from '@/constants/tahp-modules'
import { fetchDynamicDomains } from '@/api/tahp/skills'
import { startAdaptAgentRun, previewAdaptAgentPrompts, submitAdaptUserInput, continueAdaptAgentRun, respondAdaptApproval, completeAdaptAgentRun, cancelAdaptAgentRun } from '@/api/tahp/adapt'
import { listTaskReports, getTaskReport, type TaskReportSummary, type TaskReportDetail } from '@/api/tahp/reports'
import { waitForTahpSocketReady } from '@/api/tahp/socket'
import { fetchSkills, type SkillInfo } from '@/api/hermes/skills'
import {
  fetchAdaptLayouts,
  saveAdaptDomainConfig,
  type AdaptLayoutFieldDef,
  type AdaptLayoutSyncMeta,
} from '@/api/tahp/adapt-layout'
import {
  ADAPT_WORKSPACES,
  cloneAdaptDomains,
  defaultActiveDomainId,
  getAdaptWorkspace,
  getBuiltinDomainsForWorkspace,
  type AdaptWorkspaceId,
} from '@/constants/adapt-domains'

const message = useMessage()
const router = useRouter()
const tasksStore = useTahpTasksStore()
const { isReady: modelProviderReady } = useModelProviderReadiness()

// ─────────────────────────────────────────────────────────────────────────────
// 类型定义
// ─────────────────────────────────────────────────────────────────────────────
type DomainId = string

interface FieldDef {
  name: string
  label: string
  type: 'text' | 'select' | 'textarea'
  placeholder?: string
  required: boolean
  options?: { label: string; value: string }[]
  /** 布局编辑草稿：下拉选项文本（每行 label:value） */
  optionsText?: string
}

interface DomainDef {
  id: DomainId
  label: string
  icon: string
  color: string
  status: 'active' | 'done' | 'pending' | 'warn'
  fields: FieldDef[]
  relatedSkills: string[]
  interactionMode?: boolean
}

interface AdaptApprovalRequest {
  approval_id: string
  command: string
  description: string
  choices: string[]
  timeout_ms: number
  deadline_at: number
}

interface AdaptUserInputRequest {
  request_id: string
  title: string
  message?: string
  fields: Array<{
    name: string
    label: string
    type?: string
    required?: boolean
    placeholder?: string
    hint?: string
    default?: string
  }>
  timeout_sec: number
  deadline_at: number
  persist_key?: string
}

// ─────────────────────────────────────────────────────────────────────────────
// 工作区与子界面（AI适配调试 / 特性适配 / 运营商配置）
// ─────────────────────────────────────────────────────────────────────────────
const WORKSPACE_STORAGE_KEY = 'tahp-adapt-workspace'

function readStoredWorkspace(): AdaptWorkspaceId {
  const raw = localStorage.getItem(WORKSPACE_STORAGE_KEY)
  if (raw && ADAPT_WORKSPACES.some(w => w.id === raw)) return raw as AdaptWorkspaceId
  return 'adapt-debug'
}

const activeWorkspaceId = ref<AdaptWorkspaceId>(readStoredWorkspace())
const activeWorkspace = computed(() => getAdaptWorkspace(activeWorkspaceId.value))

function initDomainsForWorkspace(ws: AdaptWorkspaceId): DomainDef[] {
  return reactive(cloneAdaptDomains(getBuiltinDomainsForWorkspace(ws))) as DomainDef[]
}

const workspaceDomains = reactive<Record<AdaptWorkspaceId, DomainDef[]>>({
  'adapt-debug': initDomainsForWorkspace('adapt-debug'),
  'feature-adapt': initDomainsForWorkspace('feature-adapt'),
  'carrier-config': initDomainsForWorkspace('carrier-config'),
})

const DOMAINS = computed(() => workspaceDomains[activeWorkspaceId.value])

const activeDomainByWorkspace = reactive<Record<AdaptWorkspaceId, string>>({
  'adapt-debug': defaultActiveDomainId('adapt-debug'),
  'feature-adapt': defaultActiveDomainId('feature-adapt'),
  'carrier-config': defaultActiveDomainId('carrier-config'),
})

const activeDomainId = computed({
  get: () => activeDomainByWorkspace[activeWorkspaceId.value],
  set: (v: string) => { activeDomainByWorkspace[activeWorkspaceId.value] = v },
})

function formScopeKey(domainId: string): string {
  return `${activeWorkspaceId.value}:${domainId}`
}

function buildStaticDefaults(ws: AdaptWorkspaceId) {
  const domains = getBuiltinDomainsForWorkspace(ws)
  return {
    fields: Object.fromEntries(
      domains.map(d => [d.id, JSON.parse(JSON.stringify(d.fields)) as FieldDef[]]),
    ),
    skills: Object.fromEntries(domains.map(d => [d.id, [...d.relatedSkills]])),
  }
}

const staticDefaultsByWorkspace = reactive<Record<AdaptWorkspaceId, {
  fields: Record<string, FieldDef[]>
  skills: Record<string, string[]>
}>>({
  'adapt-debug': buildStaticDefaults('adapt-debug'),
  'feature-adapt': buildStaticDefaults('feature-adapt'),
  'carrier-config': buildStaticDefaults('carrier-config'),
})

function currentStaticDefaultFields(): Record<string, FieldDef[]> {
  return staticDefaultsByWorkspace[activeWorkspaceId.value].fields
}

function currentStaticDefaultSkills(): Record<string, string[]> {
  return staticDefaultsByWorkspace[activeWorkspaceId.value].skills
}

interface WorkspaceRunState {
  agentLaunching: boolean
  launchedTaskId: string | null
  taskStatus: string
  showMonitor: boolean
  monitorMode: 'agent' | null
  startTime: number
}

function defaultRunState(): WorkspaceRunState {
  return {
    agentLaunching: false,
    launchedTaskId: null,
    taskStatus: '',
    showMonitor: false,
    monitorMode: null,
    startTime: 0,
  }
}

const runStateByWorkspace = reactive<Record<AdaptWorkspaceId, WorkspaceRunState>>({
  'adapt-debug': defaultRunState(),
  'feature-adapt': defaultRunState(),
  'carrier-config': defaultRunState(),
})

/** 各工作区 × 域 当前活跃运行（用于进行中计数与域按钮闪烁） */
interface DomainActiveRun {
  taskId: string
  domainId: string
  workspaceId: AdaptWorkspaceId
}
const activeRunsByKey = reactive<Record<string, DomainActiveRun>>({})

function domainRunKey(workspaceId: AdaptWorkspaceId, domainId: string): string {
  return `${workspaceId}:${domainId}`
}

function isTaskStreamActive(taskId: string): boolean {
  const evs = tasksStore.getStream(taskId)
  if (!evs.length) {
    return launchedTaskId.value === taskId && isRunning.value
  }
  const last = evs[evs.length - 1]
  if (last.type === 'task.completed' || last.type === 'task.failed' || last.type === 'task.cancelled') return false
  return true
}

const runningTasksCount = computed(() =>
  Object.values(activeRunsByKey).filter(
    r => r.workspaceId === activeWorkspaceId.value && isTaskStreamActive(r.taskId),
  ).length,
)

function domainRunDotClass(domainId: string): string {
  const rk = domainRunKey(activeWorkspaceId.value, domainId)
  const run = activeRunsByKey[rk]
  if (run && isTaskStreamActive(run.taskId)) return 'dot-running'
  const domain = DOMAINS.value.find(d => d.id === domainId)
  if (domain?.status === 'done') return 'dot-done'
  if (domain?.status === 'warn') return 'dot-warn'
  return 'dot-pending'
}

function registerActiveRun(taskId: string, domainId: string, workspaceId: AdaptWorkspaceId = activeWorkspaceId.value) {
  activeRunsByKey[domainRunKey(workspaceId, domainId)] = { taskId, domainId, workspaceId }
}

function unregisterActiveRun(taskId: string) {
  for (const [key, run] of Object.entries(activeRunsByKey)) {
    if (run.taskId === taskId) delete activeRunsByKey[key]
  }
}

const agentLaunching = computed({
  get: () => runStateByWorkspace[activeWorkspaceId.value].agentLaunching,
  set: (v: boolean) => { runStateByWorkspace[activeWorkspaceId.value].agentLaunching = v },
})
const launchedTaskId = computed({
  get: () => runStateByWorkspace[activeWorkspaceId.value].launchedTaskId,
  set: (v: string | null) => { runStateByWorkspace[activeWorkspaceId.value].launchedTaskId = v },
})
const taskStatus = computed({
  get: () => runStateByWorkspace[activeWorkspaceId.value].taskStatus,
  set: (v: string) => { runStateByWorkspace[activeWorkspaceId.value].taskStatus = v },
})
const showMonitor = computed({
  get: () => runStateByWorkspace[activeWorkspaceId.value].showMonitor,
  set: (v: boolean) => { runStateByWorkspace[activeWorkspaceId.value].showMonitor = v },
})
const monitorMode = computed({
  get: () => runStateByWorkspace[activeWorkspaceId.value].monitorMode,
  set: (v: 'agent' | null) => { runStateByWorkspace[activeWorkspaceId.value].monitorMode = v },
})
const startTime = computed({
  get: () => runStateByWorkspace[activeWorkspaceId.value].startTime,
  set: (v: number) => { runStateByWorkspace[activeWorkspaceId.value].startTime = v },
})

const layoutSyncMetaByWorkspace = reactive<Record<AdaptWorkspaceId, AdaptLayoutSyncMeta | null>>({
  'adapt-debug': null,
  'feature-adapt': null,
  'carrier-config': null,
})
const layoutManifestPathByWorkspace = reactive<Record<AdaptWorkspaceId, string>>({
  'adapt-debug': '',
  'feature-adapt': '',
  'carrier-config': '',
})
const layoutsReadyByWorkspace = reactive<Record<AdaptWorkspaceId, boolean>>({
  'adapt-debug': false,
  'feature-adapt': false,
  'carrier-config': false,
})

const layoutSyncMeta = computed(() => layoutSyncMetaByWorkspace[activeWorkspaceId.value])
const layoutManifestPath = computed(() => layoutManifestPathByWorkspace[activeWorkspaceId.value])
const layoutsReady = computed(() => layoutsReadyByWorkspace[activeWorkspaceId.value])

// ─────────────────────────────────────────────────────────────────────────────
// 域定义（按工作区独立维护，见 constants/adapt-domains）
// ─────────────────────────────────────────────────────────────────────────────

// 动态 formData：按需初始化，支持后续加入的自定义域
const formData = reactive<Record<string, Record<string, string>>>({})

// 为已知静态域初始化 formData
function initDomainFormData(domain: DomainDef) {
  const key = formScopeKey(domain.id)
  if (!formData[key]) {
    formData[key] = {}
  }
  domain.fields.forEach(field => {
    if (formData[key][field.name] === undefined) {
      formData[key][field.name] = ''
    }
  })
}

// 初始化所有静态域的表单数据
for (const ws of ADAPT_WORKSPACES) {
  workspaceDomains[ws.id].forEach(domain => initDomainFormData(domain))
}

function syncFormDataForDomain(domain: DomainDef) {
  const key = formScopeKey(domain.id)
  if (!formData[key]) formData[key] = {}
  const validNames = new Set(domain.fields.map(f => f.name))
  for (const k of Object.keys(formData[key])) {
    if (!validNames.has(k)) delete formData[key][k]
  }
  domain.fields.forEach(field => {
    if (formData[key][field.name] === undefined) {
      formData[key][field.name] = ''
    }
  })
}

function applyFieldsToDomain(domainId: string, fields: FieldDef[]) {
  const domain = DOMAINS.value.find(d => d.id === domainId)
  if (!domain) return
  domain.fields = fields.map(f => ({ ...f }))
  syncFormDataForDomain(domain)
}

function applyRelatedSkillsToDomain(domainId: string, skills: string[]) {
  const domain = DOMAINS.value.find(d => d.id === domainId)
  if (!domain || !skills.length) return
  domain.relatedSkills = [...skills]
}

function applyDomainConfigFromRecord(
  workspaceId: AdaptWorkspaceId,
  domainId: string,
  record: { fields?: FieldDef[]; related_skills?: string[] },
) {
  const prevWs = activeWorkspaceId.value
  activeWorkspaceId.value = workspaceId
  if (record.fields?.length) applyFieldsToDomain(domainId, record.fields)
  if (record.related_skills?.length) applyRelatedSkillsToDomain(domainId, record.related_skills)
  activeWorkspaceId.value = prevWs
}

// ─────────────────────────────────────────────────────────────────────────────
// 布局持久化（按工作区独立 manifest）
// ─────────────────────────────────────────────────────────────────────────────
const layoutEditMode = ref(false)
const layoutDraftFields = ref<FieldDef[]>([])
const layoutDraftRelatedSkills = ref<string[]>([])
const layoutSaving = ref(false)
const showSkillSearchModal = ref(false)
const skillSearchQuery = ref('')
const allSkillsCatalog = ref<SkillInfo[]>([])
const skillCatalogLoading = ref(false)
const showAddFieldModal = ref(false)
const newFieldDraft = reactive({
  name: '',
  label: '',
  type: 'text' as FieldDef['type'],
  placeholder: '',
  required: false,
  optionsText: '',
})

let layoutLoadErrorShown = false

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function isRetryableLayoutLoadError(err: unknown): boolean {
  const msg = String((err as Error)?.message || err || '')
  return /502|503|504|Failed to fetch|NetworkError|ECONNREFUSED|fetch failed/i.test(msg)
}

function formatLayoutLoadError(err: unknown): string {
  const raw = String((err as Error)?.message || err || '未知错误')
  if (/502|503|504/i.test(raw)) {
    return '后端服务未就绪（请确认已执行 npm run dev 且 server:8650 已启动），稍后刷新页面'
  }
  return raw
}

/** 从服务端 manifest 恢复域配置；启动时若后端尚未就绪会自动重试 */
async function loadAdaptLayouts(options: {
  workspaceId?: AdaptWorkspaceId
  showError?: boolean
} = {}): Promise<boolean> {
  const ws = options.workspaceId ?? activeWorkspaceId.value
  const showError = options.showError !== false
  const maxAttempts = 5
  let lastErr: unknown = null

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetchAdaptLayouts(ws)
      layoutSyncMetaByWorkspace[ws] = res.sync
      layoutManifestPathByWorkspace[ws] = res.manifest_path || ''
      for (const [domainId, record] of Object.entries(res.layouts || {})) {
        if (!record) continue
        applyDomainConfigFromRecord(ws, domainId, {
          fields: record.fields as FieldDef[],
          related_skills: record.related_skills,
        })
      }
      layoutsReadyByWorkspace[ws] = true
      return true
    } catch (err) {
      lastErr = err
      if (attempt < maxAttempts && isRetryableLayoutLoadError(err)) {
        await sleep(600 * attempt)
        continue
      }
      break
    }
  }

  console.error('[adapt-layout] load failed', lastErr)
  if (showError && !layoutLoadErrorShown) {
    layoutLoadErrorShown = true
    message.warning(`域配置加载失败，使用内置默认: ${formatLayoutLoadError(lastErr)}`)
  }
  layoutsReadyByWorkspace[ws] = true
  return false
}

async function switchAdaptWorkspace(ws: AdaptWorkspaceId) {
  if (ws === activeWorkspaceId.value) return
  if (layoutEditMode.value) cancelLayoutEdit()
  activeWorkspaceId.value = ws
  localStorage.setItem(WORKSPACE_STORAGE_KEY, ws)
  if (!layoutsReadyByWorkspace[ws]) {
    await loadAdaptLayouts({ workspaceId: ws, showError: false })
    if (getAdaptWorkspace(ws).allowDynamicDomains) {
      await loadDynamicDomains(ws)
    }
  }
}

function enterLayoutEdit() {
  layoutDraftFields.value = activeDomain.value.fields.map(f => ({
    ...f,
    options: f.options ? f.options.map(o => ({ ...o })) : undefined,
    optionsText: f.type === 'select' ? formatOptionsText(f.options) : '',
  }))
  layoutDraftRelatedSkills.value = [...activeDomain.value.relatedSkills]
  layoutEditMode.value = true
}

function cancelLayoutEdit() {
  layoutEditMode.value = false
  layoutDraftFields.value = []
  layoutDraftRelatedSkills.value = []
}

async function ensureSkillCatalogLoaded() {
  if (allSkillsCatalog.value.length) return
  skillCatalogLoading.value = true
  try {
    const data = await fetchSkills()
    allSkillsCatalog.value = data.categories.flatMap(c => c.skills)
  } catch (err) {
    message.error(`Skill 清单加载失败: ${(err as Error).message}`)
    throw err
  } finally {
    skillCatalogLoading.value = false
  }
}

async function openSkillSearchModal() {
  skillSearchQuery.value = ''
  showSkillSearchModal.value = true
  try {
    await ensureSkillCatalogLoaded()
  } catch {
    showSkillSearchModal.value = false
  }
}

const filteredSkillCandidates = computed(() => {
  const q = skillSearchQuery.value.trim().toLowerCase()
  const selected = new Set(layoutDraftRelatedSkills.value)
  return allSkillsCatalog.value
    .filter(s => !selected.has(s.name))
    .filter(s => {
      if (!q) return true
      return s.name.toLowerCase().includes(q)
        || (s.description || '').toLowerCase().includes(q)
        || (s.group || '').toLowerCase().includes(q)
    })
    .slice(0, 80)
})

function addRelatedSkill(skillName: string) {
  if (!layoutDraftRelatedSkills.value.includes(skillName)) {
    layoutDraftRelatedSkills.value.push(skillName)
  }
  showSkillSearchModal.value = false
}

function removeRelatedSkill(index: number) {
  if (layoutDraftRelatedSkills.value.length <= 1) {
    message.warning('至少保留一个关联 Skill（第一项为主控）')
    return
  }
  layoutDraftRelatedSkills.value.splice(index, 1)
}

function openAddFieldModal() {
  Object.assign(newFieldDraft, {
    name: '',
    label: '',
    type: 'text',
    placeholder: '',
    required: false,
    optionsText: '',
  })
  showAddFieldModal.value = true
}

function parseOptionsText(text: string): { label: string; value: string }[] {
  return text
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => ({ label: line, value: line }))
}

function formatOptionsText(options?: { label: string; value: string }[]): string {
  if (!options?.length) return ''
  return options.map(o => o.value).join('\n')
}

function onLayoutFieldTypeChange(field: FieldDef, newType: FieldDef['type']) {
  field.type = newType
  if (newType === 'select') {
    if (!field.optionsText) {
      field.optionsText = formatOptionsText(field.options)
    }
  } else {
    delete field.options
    field.optionsText = ''
  }
}

function normalizeLayoutDraftFields(draft: FieldDef[]): FieldDef[] {
  return draft.map((raw) => {
    const { optionsText, ...rest } = raw
    const field: FieldDef = { ...rest }
    const placeholder = field.placeholder?.trim()
    field.placeholder = placeholder || undefined
    if (field.type === 'select') {
      const options = parseOptionsText(optionsText || '')
      if (!options.length) {
        throw new Error(`下拉字段「${field.label || field.name}」至少需要一个选项（每行一个）`)
      }
      field.options = options
    } else {
      delete field.options
    }
    delete field.optionsText
    return field
  })
}

function confirmAddField(): boolean {
  const name = newFieldDraft.name.trim()
  const label = newFieldDraft.label.trim()
  if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(name)) {
    message.warning('字段名须以字母开头，仅含字母、数字、下划线')
    return false
  }
  if (!label) {
    message.warning('请填写显示标签')
    return false
  }
  if (layoutDraftFields.value.some(f => f.name === name)) {
    message.warning('字段名已存在')
    return false
  }
  const field: FieldDef = {
    name,
    label,
    type: newFieldDraft.type,
    required: newFieldDraft.required,
    placeholder: newFieldDraft.placeholder || undefined,
  }
  if (newFieldDraft.type === 'select') {
    const options = parseOptionsText(newFieldDraft.optionsText)
    if (!options.length) {
      message.warning('下拉框至少需要一个选项（每行一个）')
      return false
    }
    field.options = options
    field.optionsText = newFieldDraft.optionsText.trim()
  }
  layoutDraftFields.value.push(field)
  showAddFieldModal.value = false
  return true
}

function removeLayoutField(index: number) {
  layoutDraftFields.value.splice(index, 1)
}

async function saveLayout() {
  if (!layoutDraftFields.value.length) {
    message.warning('至少保留一个表单字段')
    return
  }
  if (!layoutDraftRelatedSkills.value.length) {
    message.warning('至少保留一个关联 Skill')
    return
  }
  layoutSaving.value = true
  try {
    const fields = normalizeLayoutDraftFields(layoutDraftFields.value) as AdaptLayoutFieldDef[]
    const related_skills = [...layoutDraftRelatedSkills.value]
    const result = await saveAdaptDomainConfig(activeDomainId.value, { fields, related_skills }, activeWorkspaceId.value)
    applyFieldsToDomain(activeDomainId.value, fields)
    applyRelatedSkillsToDomain(activeDomainId.value, related_skills)
    layoutEditMode.value = false
    layoutDraftRelatedSkills.value = []
    if (result.cloud_pushed) {
      message.success(`布局已保存并同步云端 (rev ${result.revision})`)
    } else if (result.cloud_error) {
      message.warning(`布局已保存本地，云端同步失败: ${result.cloud_error}`)
    } else {
      message.success(`布局已保存 (rev ${result.revision})`)
    }
    await loadAdaptLayouts()
  } catch (err) {
    message.error(`保存失败: ${(err as Error).message}`)
  } finally {
    layoutSaving.value = false
  }
}

async function restoreBuiltinLayout() {
  const defaults = currentStaticDefaultFields()[activeDomainId.value]
  const defaultSkills = currentStaticDefaultSkills()[activeDomainId.value]
  if (!defaults?.length || !defaultSkills?.length) {
    message.warning('当前域无内置默认配置')
    return
  }
  layoutSaving.value = true
  try {
    const fields = JSON.parse(JSON.stringify(defaults)) as AdaptLayoutFieldDef[]
    const related_skills = [...defaultSkills]
    await saveAdaptDomainConfig(activeDomainId.value, { fields, related_skills }, activeWorkspaceId.value)
    applyFieldsToDomain(activeDomainId.value, fields)
    applyRelatedSkillsToDomain(activeDomainId.value, related_skills)
    layoutDraftFields.value = fields.map(f => ({ ...f }))
    layoutDraftRelatedSkills.value = [...related_skills]
    layoutEditMode.value = false
    message.success('已恢复内置默认配置')
    await loadAdaptLayouts()
  } catch (err) {
    message.error(`恢复失败: ${(err as Error).message}`)
  } finally {
    layoutSaving.value = false
  }
}

watch(activeDomainId, () => {
  if (layoutEditMode.value) cancelLayoutEdit()
})

const formFieldsForAgent = computed(() =>
  activeDomain.value.fields.map(f => ({
    name: f.name,
    label: f.label,
    required: f.required,
  })),
)

// ─────────────────────────────────────────────────────────────────────────────
// 计算属性（表单）
// ─────────────────────────────────────────────────────────────────────────────
const activeDomain = computed<DomainDef>(() =>
  DOMAINS.value.find(d => d.id === activeDomainId.value) ?? DOMAINS.value[0]
)

const currentFormData = computed<Record<string, string>>(() =>
  formData[formScopeKey(activeDomainId.value)] ?? {}
)

const requiredCount = computed(() => (activeDomain.value?.fields ?? []).filter(f => f.required).length)
const filledCount = computed(() => (activeDomain.value?.fields ?? []).filter(f => f.required && currentFormData.value[f.name]).length)
// 没有必填项（requiredCount === 0）时也视为完整，允许启动任务
const isComplete = computed(() => requiredCount.value === 0 || filledCount.value === requiredCount.value)
const completedDomains = computed(() => DOMAINS.value.filter(d => d.status === 'done').length)
const overallPercent = computed(() => Math.round((completedDomains.value / DOMAINS.value.length) * 100))

// ─────────────────────────────────────────────────────────────────────────────
// Getter / Setter — 避免在 computed 上使用 v-model
// ─────────────────────────────────────────────────────────────────────────────
function getFieldValue(fieldName: string): string {
  return (formData[formScopeKey(activeDomainId.value)] ?? {})[fieldName] ?? ''
}
function getSelectFieldValue(fieldName: string): string | null {
  const value = getFieldValue(fieldName)
  return value || null
}
function setFieldValue(fieldName: string, value: string) {
  const key = formScopeKey(activeDomainId.value)
  if (!formData[key]) formData[key] = {}
  formData[key][fieldName] = value
}

// ─────────────────────────────────────────────────────────────────────────────
// 历史表单（复用 adapt-agent 运行报告：含 form_data，可回填 + 查看报告）
// ─────────────────────────────────────────────────────────────────────────────
const historyLoading = ref(false)
const historyItems = ref<TaskReportSummary[]>([])
const historyScope = ref<'current' | 'all'>('current')
const historySearch = ref('')
const expandedTaskId = ref<string | null>(null)
const expandedLoading = ref(false)
const detailCache = reactive<Record<string, TaskReportDetail>>({})
/** 最近回填的字段名，用于表单高亮反馈（1.5s 后清空） */
const refilledFields = ref<string[]>([])
let refillHighlightTimer: ReturnType<typeof setTimeout> | null = null

async function loadHistory() {
  historyLoading.value = true
  try {
    const all = await listTaskReports()
    historyItems.value = all.filter(
      item => !item.report_type || item.report_type === 'adapt_agent',
    )
  } catch {
    // 历史加载失败不影响主功能
  } finally {
    historyLoading.value = false
  }
}

/** 当前工作区包含的域 id 集合（「全部域」范围限定在当前工作区，避免跨 Tab 混入） */
const currentWorkspaceDomainIds = computed(() => new Set(DOMAINS.value.map(d => d.id)))

const filteredHistory = computed<TaskReportSummary[]>(() => {
  const wsIds = currentWorkspaceDomainIds.value
  const kw = historySearch.value.trim().toLowerCase()
  return historyItems.value.filter((item) => {
    const domainId = item.domain || ''
    if (!wsIds.has(domainId)) return false
    if (historyScope.value === 'current' && domainId !== activeDomainId.value) return false
    if (kw) {
      const detail = detailCache[item.task_id]
      const haystack = [
        item.domain_label,
        item.domain,
        item.task_id,
        detail ? projectNameOf(detail) : '',
      ].filter(Boolean).join(' ').toLowerCase()
      if (!haystack.includes(kw)) return false
    }
    return true
  })
})

async function ensureDetail(taskId: string): Promise<TaskReportDetail | null> {
  if (detailCache[taskId]) return detailCache[taskId]
  try {
    const d = await getTaskReport(taskId)
    detailCache[taskId] = d
    return d
  } catch {
    return null
  }
}

/** 为当前筛选结果预取详情（补齐标题项目名与状态），限量避免请求过多 */
async function prefetchHistoryDetails() {
  const pending = filteredHistory.value
    .filter(item => !detailCache[item.task_id])
    .slice(0, 50)
  await Promise.all(pending.map(item => ensureDetail(item.task_id)))
}

function domainDefById(id?: string): DomainDef | undefined {
  if (!id) return undefined
  return DOMAINS.value.find(d => d.id === id)
}

/** 取一次运行的「项目名」：该域第一个必填字段的值，回退域标签 */
function projectNameOf(detail: TaskReportDetail): string {
  const domain = domainDefById(detail.domain_id || detail.domain)
  const fd = detail.form_data || {}
  if (domain) {
    const firstRequired = domain.fields.find(f => f.required && fd[f.name])
    if (firstRequired && fd[firstRequired.name]) return fd[firstRequired.name]
    const firstAny = domain.fields.find(f => fd[f.name])
    if (firstAny && fd[firstAny.name]) return fd[firstAny.name]
  }
  return detail.domain_label || detail.domain || detail.task_id
}

/** 折叠行标题：域简写 + 项目名 */
function historyTitle(item: TaskReportSummary): string {
  const badge = historyBadge(item)
  const detail = detailCache[item.task_id]
  const project = detail ? projectNameOf(detail) : (item.domain_label || item.domain || '')
  const label = [badge.label, project].filter(Boolean).join(' · ')
  return label || item.task_id || '未命名任务'
}

/** 域徽标（图标/颜色）来自当前工作区域定义 */
function historyBadge(item: TaskReportSummary): { icon: string; color: string; label: string } {
  const domain = domainDefById(item.domain)
  return {
    icon: domain?.icon || (item.domain || '?').slice(0, 3).toUpperCase(),
    color: domain?.color || '#94a3b8',
    label: domain?.label || item.domain_label || item.domain || '',
  }
}

function historyStatus(item: TaskReportSummary): { label: string; type: 'success' | 'error' | 'warning' | 'default' } {
  const status = (detailCache[item.task_id]?.status || '').toLowerCase()
  if (/(complete|done|success|finish)/.test(status)) return { label: '成功', type: 'success' }
  if (/(fail|error)/.test(status)) return { label: '失败', type: 'error' }
  if (/(user_ended|ended|cancel)/.test(status)) return { label: '已结束', type: 'warning' }
  if (item.completed_at) return { label: '已完成', type: 'default' }
  return { label: '进行中', type: 'warning' }
}

function relativeTime(input?: string | number): string {
  if (!input) return ''
  const ts = typeof input === 'number' ? input : Date.parse(input)
  if (!ts || Number.isNaN(ts)) return ''
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  return new Date(ts).toLocaleDateString()
}

function absoluteTime(input?: string | number): string {
  if (!input) return ''
  const ts = typeof input === 'number' ? input : Date.parse(input)
  if (!ts || Number.isNaN(ts)) return ''
  return new Date(ts).toLocaleString()
}

function historyTimeValue(item: TaskReportSummary): string | number | undefined {
  return item.completed_at || item.started_at || item.mtime
}

async function toggleExpand(taskId: string) {
  if (expandedTaskId.value === taskId) {
    expandedTaskId.value = null
    return
  }
  expandedTaskId.value = taskId
  if (!detailCache[taskId]) {
    expandedLoading.value = true
    await ensureDetail(taskId)
    expandedLoading.value = false
  }
}

/** 展开面板：表单快照（字段 label → value） */
function formSnapshot(detail: TaskReportDetail): Array<{ label: string; value: string }> {
  const fd = detail.form_data || {}
  const domain = domainDefById(detail.domain_id || detail.domain)
  const rows: Array<{ label: string; value: string }> = []
  if (domain) {
    for (const f of domain.fields) {
      const v = fd[f.name]
      if (v) rows.push({ label: f.label || f.name, value: v })
    }
  } else {
    for (const [k, v] of Object.entries(fd)) {
      if (v) rows.push({ label: k, value: String(v) })
    }
  }
  return rows
}

/** 报告摘要首行（结论） */
function reportSummaryLine(detail: TaskReportDetail): string {
  const text = (detail.llm_response || detail.audit_report || '').trim()
  if (!text) return '无文本结论'
  const firstLine = text.split('\n').map(l => l.replace(/^#+\s*/, '').trim()).find(l => l.length > 0)
  if (!firstLine) return '无文本结论'
  return firstLine.length > 80 ? `${firstLine.slice(0, 80)}…` : firstLine
}

function auditCounts(detail: TaskReportDetail): { pass: number; fail: number } {
  const items = detail.audit_summary || []
  return {
    pass: items.filter(i => i.status === 'pass').length,
    fail: items.filter(i => i.status === 'fail').length,
  }
}

// ── 回填 ──────────────────────────────────────────────────────────────────
const refillPendingDetail = ref<TaskReportDetail | null>(null)
const refillConfirmVisible = ref(false)

function domainFormHasContent(domainId: string): boolean {
  const domain = domainDefById(domainId)
  if (!domain) return false
  const form = formData[formScopeKey(domainId)] || {}
  return domain.fields.some(f => (form[f.name] ?? '').trim() !== '')
}

function requestRefill(detail: TaskReportDetail | null) {
  if (!detail) return
  const targetId = detail.domain_id || detail.domain
  if (!targetId || !domainDefById(targetId)) {
    message.warning('该记录对应的适配域已不存在于当前工作区，无法回填')
    return
  }
  if (!detail.form_data || Object.keys(detail.form_data).length === 0) {
    message.warning('该记录未保存表单快照，无法回填')
    return
  }
  if (domainFormHasContent(targetId)) {
    refillPendingDetail.value = detail
    refillConfirmVisible.value = true
    return
  }
  applyRefill(detail)
}

function applyRefill(detail: TaskReportDetail) {
  const targetId = detail.domain_id || detail.domain
  const domain = domainDefById(targetId)
  if (!domain) return
  const fd = detail.form_data || {}

  activeDomainId.value = domain.id
  const key = formScopeKey(domain.id)
  if (!formData[key]) formData[key] = {}

  const validNames = new Set(domain.fields.map(f => f.name))
  let filled = 0
  for (const f of domain.fields) {
    if (fd[f.name] !== undefined && fd[f.name] !== '') {
      formData[key][f.name] = String(fd[f.name])
      filled++
    }
  }
  const ignored = Object.keys(fd).filter(k => k && !validNames.has(k) && fd[k]).length

  refilledFields.value = domain.fields.filter(f => fd[f.name]).map(f => f.name)
  if (refillHighlightTimer) clearTimeout(refillHighlightTimer)
  refillHighlightTimer = setTimeout(() => { refilledFields.value = [] }, 1500)

  refillConfirmVisible.value = false
  refillPendingDetail.value = null
  expandedTaskId.value = null

  message.success(
    ignored > 0
      ? `已回填 ${filled} 个字段，${ignored} 个字段因布局变更已忽略`
      : `已回填 ${filled} 个字段`,
  )
}

function viewReport(taskId: string) {
  router.push({ name: 'tahp.reports', query: { task_id: taskId } })
}

watch([filteredHistory], () => { prefetchHistoryDetails() })

// ─────────────────────────────────────────────────────────────────────────────
// 执行 / 监控状态（按工作区隔离，见 runStateByWorkspace）
// ─────────────────────────────────────────────────────────────────────────────
const eventListEl = ref<HTMLElement | null>(null)

const stream = computed(() =>
  launchedTaskId.value ? tasksStore.getStream(launchedTaskId.value) : []
)

// LLM 流式输出：将所有 task.message 事件的文本拼接为完整回复
const llmResponse = computed(() =>
  stream.value
    .filter(ev => ev.type === 'task.message')
    .map(ev => String(ev.payload?.text ?? ''))
    .join('')
)

const isRunning = computed(() =>
  taskStatus.value !== '' &&
  taskStatus.value !== 'COMPLETED' &&
  taskStatus.value !== 'FAILED' &&
  taskStatus.value !== 'completed' &&
  taskStatus.value !== 'failed'
)

type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'warning'

interface AdaptExecStep {
  step_id: string
  label: string
  status: StepStatus
  message?: string
  ts?: number
}

interface FileChangeRow {
  path: string
  tool?: string
  status?: string
  ts?: number
}

const ADAPT_PIPELINE_STEPS = [
  { step_id: 'task-start', label: '创建任务' },
  { step_id: 'prepare', label: '准备指令' },
  { step_id: 'connect-agent', label: '连接 Agent Bridge' },
  { step_id: 'read-skill', label: '读取 Skill' },
  { step_id: 'execute-adapt', label: '执行适配' },
  { step_id: 'self-audit', label: '自检审核' },
  { step_id: 'finalize', label: '生成报告' },
] as const

const ADAPT_PIPELINE_STEP_IDS = ADAPT_PIPELINE_STEPS.map(s => s.step_id)

/** 预编排执行步骤：任务启动即展示，由事件流驱动状态更新 */
const executionSteps = computed((): AdaptExecStep[] => {
  const steps: AdaptExecStep[] = ADAPT_PIPELINE_STEPS.map(d => ({
    ...d,
    status: 'pending' as StepStatus,
  }))
  const byId = Object.fromEntries(steps.map(s => [s.step_id, s])) as Record<string, AdaptExecStep>

  if (!launchedTaskId.value) return steps

  const rank: Record<StepStatus, number> = {
    pending: 0,
    running: 1,
    warning: 2,
    failed: 3,
    completed: 4,
  }
  const setStep = (id: string, status: StepStatus, message?: string, ts?: number, force = false) => {
    const s = byId[id]
    if (!s) return
    if (force || rank[status] >= rank[s.status] || (status === 'running' && s.status === 'pending')) {
      s.status = status
      if (message) s.message = message
      if (ts) s.ts = ts
    }
  }

  if (!stream.value.length) {
    if (agentLaunching.value || isRunning.value || taskStatus.value === 'starting') {
      setStep('task-start', 'running', '正在连接 TaskStream...', undefined, true)
    }
    return steps
  }

  let primarySkill = ''
  for (const ev of stream.value) {
    if (ev.type === 'task.started') {
      primarySkill = String((ev.payload?.related_skills as string[] | undefined)?.[0] || '')
      setStep('task-start', 'completed', String(ev.payload?.message || '任务已创建'), ev.ts, true)
      setStep('prepare', 'running', '准备 Agent 指令...', ev.ts, true)
    }
    if (ev.type === 'task.phase') {
      const phase = String(ev.payload?.phase || '')
      const msg = String(ev.payload?.message || '')
      if (phase === 'PREPARING') setStep('prepare', 'running', msg, ev.ts)
      if (phase === 'CONNECTING_AGENT') {
        setStep('prepare', 'completed', undefined, ev.ts, true)
        setStep('connect-agent', 'running', msg, ev.ts, true)
      }
      if (phase === 'EXECUTING') {
        setStep('connect-agent', 'completed', undefined, ev.ts, true)
        setStep('read-skill', 'running', primarySkill ? `读取 ${primarySkill}` : '读取主控 Skill', ev.ts, true)
        setStep('execute-adapt', 'running', msg, ev.ts, true)
      }
      if (phase === 'COMPLETED') setStep('finalize', 'running', msg, ev.ts)
    }
    if (ev.type === 'task.step') {
      const sid = String(ev.payload?.step_id || '')
      const st = (ev.payload?.status as StepStatus) || 'completed'
      const msg = String(ev.payload?.message || '')
      if (sid === 'connect-agent') {
        setStep('connect-agent', st === 'completed' ? 'completed' : st, msg, ev.ts, true)
      }
      if (sid === 'agent-run') {
        setStep('read-skill', 'completed', undefined, ev.ts, true)
        setStep('execute-adapt', st === 'completed' ? 'completed' : st, msg, ev.ts, true)
      }
      if (sid === 'self-audit') setStep('self-audit', st, msg, ev.ts, true)
    }
    if (ev.type === 'task.skill_use') {
      const skill = String(ev.payload?.skill_id || '')
      if (skill === 'read_file' || skill === 'skill_view' || skill === 'Read') {
        const args = String(ev.payload?.args || ev.payload?.message || '')
        if (!primarySkill || args.includes(primarySkill) || args.includes('SKILL.md')) {
          setStep('read-skill', 'running', String(ev.payload?.message || skill), ev.ts)
        }
      }
      if (byId['execute-adapt']?.status === 'pending') {
        setStep('connect-agent', 'completed', undefined, ev.ts, true)
        setStep('execute-adapt', 'running', 'Agent 正在调用工具...', ev.ts, true)
      }
    }
    if (ev.type === 'task.completed') {
      setStep('execute-adapt', 'completed', undefined, ev.ts, true)
      if (byId['self-audit']?.status === 'pending') {
        setStep('self-audit', 'warning', '未检测到审核章节', ev.ts, true)
      }
      setStep('finalize', 'completed', String(ev.payload?.message || '报告已生成'), ev.ts, true)
    }
    if (ev.type === 'task.failed') {
      const errMsg = String(ev.payload?.message || ev.payload?.error || '任务失败')
      for (const s of steps) {
        if (s.status === 'running') s.status = 'failed'
      }
      if (byId['execute-adapt']?.status !== 'completed') {
        setStep('execute-adapt', 'failed', errMsg, ev.ts, true)
      } else {
        setStep('finalize', 'failed', errMsg, ev.ts, true)
      }
    }
  }

  // 已有后续步骤推进时，前面的步骤统一显示为已完成（避免长期灰色/蓝色）
  let furthest = -1
  for (let i = 0; i < ADAPT_PIPELINE_STEP_IDS.length; i++) {
    const st = byId[ADAPT_PIPELINE_STEP_IDS[i]]?.status
    if (st && st !== 'pending') furthest = i
  }
  for (let i = 0; i < furthest; i++) {
    const s = byId[ADAPT_PIPELINE_STEP_IDS[i]]
    if (s && (s.status === 'pending' || s.status === 'running')) {
      s.status = 'completed'
    }
  }

  return steps
})

const agentRunError = computed(() => {
  const s = taskStatus.value.toUpperCase()
  if (s !== 'FAILED') return ''
  const failed = [...stream.value].reverse().find(e => e.type === 'task.failed')
  if (failed) return String(failed.payload?.message || failed.payload?.error || '')
  return ''
})

const agentSkillEvents = computed(() =>
  stream.value.filter(ev => ev.type === 'task.skill_use')
)

const agentFileEvents = computed((): FileChangeRow[] => {
  const byPath = new Map<string, FileChangeRow>()
  for (const ev of stream.value) {
    if (ev.type === 'task.file_change') {
      const p = String(ev.payload?.path || '')
      if (!p) continue
      byPath.set(p, {
        path: p,
        tool: String(ev.payload?.tool || ''),
        status: String(ev.payload?.status || ev.payload?.action || 'modify'),
        ts: ev.ts,
      })
    }
    if (ev.type === 'task.completed') {
      const files = ev.payload?.files_modified as string[] | undefined
      if (Array.isArray(files)) {
        for (const p of files) {
          if (!p) continue
          const prev = byPath.get(p)
          byPath.set(p, {
            path: p,
            tool: prev?.tool || 'report',
            status: 'completed',
            ts: ev.ts,
          })
        }
      }
    }
  }
  return Array.from(byPath.values()).sort((a, b) => (a.ts || 0) - (b.ts || 0))
})

const statusTagType = computed<'info' | 'success' | 'error' | 'warning'>(() => {
  const s = taskStatus.value.toUpperCase()
  if (s === 'COMPLETED') return 'success'
  if (s === 'FAILED')    return 'error'
  if (s === 'STARTING')  return 'warning'
  if (s === 'WAITING_USER' || s === 'WAITING_USER_INPUT') return 'warning'
  return 'info'
})

// ─────────────────────────────────────────────────────────────────────────────
// 人机协同弹窗（CarrierConfig 等交互式域）
// ─────────────────────────────────────────────────────────────────────────────
const pendingApproval = ref<AdaptApprovalRequest | null>(null)
const pendingUserInput = ref<AdaptUserInputRequest | null>(null)
const canContinueChat = ref(false)
const showContinueChatModal = ref(false)
const completeTaskLoading = ref(false)
const interactionSubmitting = ref(false)
const handledInteractionTs = ref<Record<string, number>>({})

const CONTINUE_CHAT_CONFIG: ContinueChatPrompt = {
  title: '补充信息继续分析',
  message: '请输入补充说明，Agent 将根据您的输入继续执行。',
}

const isInteractiveDomain = computed(() => !!activeDomain.value.interactionMode)

const canCompleteInteractiveTask = computed(() => {
  if (!isInteractiveDomain.value || !launchedTaskId.value) return false
  const s = taskStatus.value.toUpperCase()
  return s !== '' && s !== 'COMPLETED' && s !== 'FAILED' && s !== 'STARTING'
})

const canViewAdaptReport = computed(() => {
  if (!launchedTaskId.value) return false
  return taskStatus.value.toUpperCase() === 'COMPLETED'
})

function openAdaptReport() {
  const tid = launchedTaskId.value
  if (!tid) return
  router.push({ name: 'tahp.reports', query: { task_id: tid } })
}

function resetInteractionState() {
  pendingApproval.value = null
  pendingUserInput.value = null
  canContinueChat.value = false
  showContinueChatModal.value = false
  handledInteractionTs.value = {}
}

function openContinueChatModal() {
  if (!canContinueChat.value) return
  showContinueChatModal.value = true
}

function onContinueChatDismiss() {
  showContinueChatModal.value = false
}

watch(stream, () => {
  if (!isInteractiveDomain.value || !launchedTaskId.value) return
  for (const ev of stream.value) {
    const key = `${ev.type}:${ev.ts}`
    if (handledInteractionTs.value[key]) continue
    handledInteractionTs.value[key] = 1

    if (ev.type === 'task.approval_requested' && !pendingApproval.value) {
      const p = ev.payload
      pendingApproval.value = {
        approval_id: String(p.approval_id || ''),
        command: String(p.command || ''),
        description: String(p.description || ''),
        choices: Array.isArray(p.choices) ? p.choices as string[] : ['once', 'deny'],
        timeout_ms: Number(p.timeout_ms) || 60000,
        deadline_at: Number(p.deadline_at) || Date.now() + 60000,
      }
      showContinueChatModal.value = false
    }
    if (ev.type === 'task.approval_resolved') {
      pendingApproval.value = null
    }
    if (ev.type === 'task.user_input_requested') {
      const requestId = String(ev.payload?.request_id || '')
      const fields = Array.isArray(ev.payload?.fields) ? ev.payload.fields as AdaptUserInputRequest['fields'] : []
      if (!requestId || !fields.length) continue
      pendingUserInput.value = {
        request_id: requestId,
        title: String(ev.payload?.title || '请确认/补充信息'),
        message: typeof ev.payload?.message === 'string' ? ev.payload.message : undefined,
        fields,
        timeout_sec: Number(ev.payload?.timeout_sec) || 300,
        deadline_at: Number(ev.payload?.deadline_at) || Date.now() + 300000,
        persist_key: typeof ev.payload?.persist_key === 'string' ? ev.payload.persist_key : undefined,
      }
      showContinueChatModal.value = false
      taskStatus.value = 'WAITING_USER_INPUT'
    }
    if (ev.type === 'task.user_input_submitted') {
      pendingUserInput.value = null
      taskStatus.value = 'EXECUTING'
    }
    if (ev.type === 'task.phase') {
      const phase = String(ev.payload?.phase || '')
      if (phase === 'WAITING_USER' && !pendingUserInput.value && !pendingApproval.value) {
        canContinueChat.value = true
        showContinueChatModal.value = false
        taskStatus.value = 'WAITING_USER'
      }
      if (phase === 'EXECUTING') {
        canContinueChat.value = false
        showContinueChatModal.value = false
      }
    }
    if (ev.type === 'task.completed' || ev.type === 'task.failed') {
      resetInteractionState()
    }
  }
}, { deep: true })

async function onAdaptApproval(choice: string) {
  const tid = launchedTaskId.value
  const ap = pendingApproval.value
  if (!tid || !ap) return
  interactionSubmitting.value = true
  try {
    await respondAdaptApproval(tid, { approval_id: ap.approval_id, choice })
    pendingApproval.value = null
  } catch (err) {
    message.error((err as Error).message || '审批提交失败')
  } finally {
    interactionSubmitting.value = false
  }
}

async function onAdaptUserInput(values: Record<string, string>) {
  const tid = launchedTaskId.value
  const ui = pendingUserInput.value
  if (!tid || !ui) return
  interactionSubmitting.value = true
  try {
    await submitAdaptUserInput(tid, { request_id: ui.request_id, values })
    pendingUserInput.value = null
  } catch (err) {
    message.error((err as Error).message || '提交失败')
  } finally {
    interactionSubmitting.value = false
  }
}

async function onAdaptContinueChat(text: string) {
  const tid = launchedTaskId.value
  if (!tid || !text.trim()) return
  interactionSubmitting.value = true
  try {
    await continueAdaptAgentRun(tid, text.trim())
    showContinueChatModal.value = false
    canContinueChat.value = false
    taskStatus.value = 'EXECUTING'
  } catch (err) {
    message.error((err as Error).message || '发送失败')
  } finally {
    interactionSubmitting.value = false
  }
}

async function onCompleteAdaptTask() {
  const tid = launchedTaskId.value
  if (!tid) return
  completeTaskLoading.value = true
  try {
    await completeAdaptAgentRun(tid)
    showContinueChatModal.value = false
    canContinueChat.value = false
    taskStatus.value = 'COMPLETED'
    message.success('任务已结束，报告已生成')
  } catch (err) {
    message.error((err as Error).message || '结束任务失败')
  } finally {
    completeTaskLoading.value = false
  }
}

// 监听事件流 → 更新状态 + 自动滚动到底部 + 任务结束时刷新历史
watch(stream, async (evs) => {
  if (!evs.length) return
  const last = evs[evs.length - 1]
  if (last.type === 'task.completed') {
    taskStatus.value = 'COMPLETED'
    unregisterActiveRun(launchedTaskId.value || '')
    void loadHistory()
  } else if (last.type === 'task.failed') {
    taskStatus.value = 'FAILED'
    unregisterActiveRun(launchedTaskId.value || '')
  } else if (last.type === 'task.phase') {
    taskStatus.value = (last.payload?.phase as string) || 'running'
  } else if (taskStatus.value !== 'COMPLETED' && taskStatus.value !== 'FAILED') {
    taskStatus.value = 'running'
  }

  await nextTick()
  if (eventListEl.value) {
    eventListEl.value.scrollTop = eventListEl.value.scrollHeight
  }
}, { deep: true })

// ─────────────────────────────────────────────────────────────────────────────
// 适配域 → TAHP 模块映射（优先从动态域 module 字段读取）
// ─────────────────────────────────────────────────────────────────────────────
function mapDomainToModule(id: DomainId): TahpModule {
  const domain = DOMAINS.value.find(d => d.id === id)
  if (domain && (domain as any).module) {
    return (domain as any).module as TahpModule
  }
  // 静态域回退规则
  if (id === 'modem') return 'telephony'
  if (id === 'comm-framework') return 'telephony'
  return 'kernel-driver'
}

// ─────────────────────────────────────────────────────────────────────────────
// 加载动态域（用户通过知识库创建的自定义适配技能）
// ─────────────────────────────────────────────────────────────────────────────

/** 已下线域 / 测试域，不再从动态技能列表注入 */
const BLOCKED_DYNAMIC_DOMAIN_IDS = new Set(['Test', 'kernel', 'scp', 'aikey'])
const loadingDomains = ref(false)

async function loadDynamicDomains(workspaceId: AdaptWorkspaceId = activeWorkspaceId.value) {
  if (!getAdaptWorkspace(workspaceId).allowDynamicDomains) return
  loadingDomains.value = true
  const prevWs = activeWorkspaceId.value
  activeWorkspaceId.value = workspaceId
  try {
    const res = await fetchDynamicDomains()
    const dynamicDomains = res.domains || []
    const staticIds = new Set(getBuiltinDomainsForWorkspace(workspaceId).map(d => d.id))
    const domains = workspaceDomains[workspaceId]
    domains.splice(staticIds.size)
    const defaults = staticDefaultsByWorkspace[workspaceId]

    for (const dd of dynamicDomains) {
      if (
        staticIds.has(dd.id)
        || staticIds.has(dd.skillId)
        || BLOCKED_DYNAMIC_DOMAIN_IDS.has(dd.id)
        || BLOCKED_DYNAMIC_DOMAIN_IDS.has(dd.skillId)
      ) continue
      const domainDef: DomainDef & { module?: string } = {
        id:            dd.id,
        label:         dd.label,
        icon:          dd.icon,
        color:         dd.color,
        status:        'pending',
        relatedSkills: dd.relatedSkills || [dd.skillId],
        fields:        (dd.fields || []).map((f: any) => ({
          name:        f.name,
          label:       f.label,
          type:        f.type as 'text' | 'select' | 'textarea',
          required:    f.required ?? false,
          placeholder: f.placeholder || '',
          options:     f.options,
        })),
        module:        dd.module,
      }
      domains.push(domainDef)
      initDomainFormData(domainDef)
      defaults.fields[domainDef.id] = JSON.parse(JSON.stringify(domainDef.fields))
      defaults.skills[domainDef.id] = [...domainDef.relatedSkills]
    }
  } catch {
    // 动态域加载失败不影响静态域功能
  } finally {
    activeWorkspaceId.value = prevWs
    loadingDomains.value = false
  }
}

onMounted(async () => {
  const ws = activeWorkspaceId.value
  layoutsReadyByWorkspace[ws] = false
  await loadAdaptLayouts({ workspaceId: ws, showError: true })
  await loadDynamicDomains(ws)
  await loadAdaptLayouts({ workspaceId: ws, showError: false })
  layoutsReadyByWorkspace[ws] = true
  await loadHistory()
})

// ─────────────────────────────────────────────────────────────────────────────
// Agent 自动适配
// ─────────────────────────────────────────────────────────────────────────────
function buildAgentRunPayload() {
  const d = activeDomain.value
  return {
    workspace_id: activeWorkspaceId.value,
    domain_id: activeDomainId.value,
    domain_label: d.label,
    module: mapDomainToModule(activeDomainId.value),
    related_skills: d.relatedSkills,
    form_data: { ...currentFormData.value },
    form_fields: formFieldsForAgent.value,
    user_notes: currentFormData.value.user_notes || undefined,
    interaction_mode: d.interactionMode === true,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 提示词预览
// ─────────────────────────────────────────────────────────────────────────────
const showPromptPreview = ref(false)
const promptPreviewLoading = ref(false)
const promptPreviewTab = ref<'system' | 'user'>('system')
const previewSystemPrompt = ref('')
const previewUserPrompt = ref('')

const previewAllText = computed(() =>
  `# 系统提示词\n\n${previewSystemPrompt.value}\n\n---\n\n# 用户提示词\n\n${previewUserPrompt.value}`,
)

async function openPromptPreview() {
  if (layoutEditMode.value) {
    message.warning('请先保存或取消布局编辑')
    return
  }
  if (!isComplete.value) {
    message.warning('请先完成当前域所需的全部表单参数')
    return
  }

  promptPreviewLoading.value = true
  showPromptPreview.value = true
  previewSystemPrompt.value = ''
  previewUserPrompt.value = ''

  try {
    const data = await previewAdaptAgentPrompts(buildAgentRunPayload())
    previewSystemPrompt.value = data.system_prompt
    previewUserPrompt.value = data.user_prompt
  } catch (err) {
    showPromptPreview.value = false
    message.error(`预览失败: ${(err as Error).message}`)
  } finally {
    promptPreviewLoading.value = false
  }
}

async function copyPromptText(text: string, label: string) {
  if (!text) {
    message.warning('暂无内容可复制')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    message.success(`已复制${label}`)
  } catch {
    message.error('复制失败，请手动选择文本复制')
  }
}

async function launchAgentAdapt() {
  if (!modelProviderReady.value) {
    message.warning('请先在「模型管理」中配置模型 Provider 和 API Key')
    return
  }
  if (!isComplete.value) {
    message.warning('请先完成当前域所需的全部表单参数')
    return
  }
  if (!activeDomain.value.relatedSkills.length) {
    message.warning('请至少配置一个关联 Skill（可在「编辑布局」中设置）')
    return
  }

  const ws = activeWorkspaceId.value
  const domainId = activeDomainId.value
  const runKey = domainRunKey(ws, domainId)
  const existingRun = activeRunsByKey[runKey]
  if (existingRun && isTaskStreamActive(existingRun.taskId)) {
    try {
      await cancelAdaptAgentRun(existingRun.taskId)
      unregisterActiveRun(existingRun.taskId)
      message.info('已终止同域上一次未完成的任务')
    } catch {
      message.warning('同域仍有任务在执行，请稍候或手动终止后再试')
      return
    }
  }

  agentLaunching.value = true
  monitorMode.value = 'agent'
  taskStatus.value = 'starting'
  launchedTaskId.value = null
  resetInteractionState()
  showMonitor.value = true
  startTime.value = Date.now()

  try {
    tasksStore.ensureSocket()
    await waitForTahpSocketReady()
    const data = await startAdaptAgentRun(buildAgentRunPayload())
    const tid = data.task_id
    if (tid) {
      launchedTaskId.value = tid
      tasksStore.trackTask(tid)
      registerActiveRun(tid, domainId, ws)
      message.success(`Agent 任务已启动: ${tid}`)
    }
  } catch (err) {
    taskStatus.value = 'FAILED'
    message.error(`Agent 启动失败: ${(err as Error).message}`)
  } finally {
    agentLaunching.value = false
  }
}

/** 统一三个入口的监控视图布局（均展示三栏 Agent 监控） */
function openMonitorView() {
  monitorMode.value = 'agent'
  showMonitor.value = true
}

const cancelTaskLoading = ref(false)

async function cancelRunningTask() {
  const tid = launchedTaskId.value
  if (!tid || !isRunning.value) return
  cancelTaskLoading.value = true
  try {
    await cancelAdaptAgentRun(tid)
    taskStatus.value = 'FAILED'
    unregisterActiveRun(tid)
    message.info('任务已终止')
  } catch (err) {
    message.error(`终止失败: ${(err as Error).message}`)
  } finally {
    cancelTaskLoading.value = false
  }
}

function backToForm() {
  showMonitor.value = false
  // 保留 launchedTaskId 与 monitorMode，再次打开监控时仍为 Agent 三栏布局
  loadHistory()
}

// ─────────────────────────────────────────────────────────────────────────────
// 事件流工具函数
// ─────────────────────────────────────────────────────────────────────────────
function formatTs(ts: number): string {
  return new Date(ts).toLocaleTimeString()
}

function formatPayload(payload: Record<string, unknown>): string {
  const msg = payload?.message || payload?.content || payload?.text
  if (typeof msg === 'string') return msg
  return JSON.stringify(payload, null, 2)
}

// ─────────────────────────────────────────────────────────────────────────────
// 导航辅助
// ─────────────────────────────────────────────────────────────────────────────
function selectDomain(id: DomainId) {
  activeDomainId.value = id
}

function openSkill(skillName: string) {
  router.push({ name: 'hermes.skills', query: { search: skillName } })
}
</script>

<template>
  <div class="page page-wide" :class="{ 'adapt-page--monitor': showMonitor }">

    <EaPageHead
      title="AI 适配调试"
      :subtitle="activeWorkspace.subtitle"
    >
      <template #actions>
        <span v-if="layoutSyncMeta?.cloud_sync_enabled" class="ea-pill-info">云端同步已启用</span>
        <button
          v-if="activeWorkspace.allowDynamicDomains"
          type="button"
          class="ea-btn-ghost ea-btn-sm adapt-refresh-btn"
          :class="{ spinning: loadingDomains }"
          title="刷新域列表（创建新技能后点击）"
          @click="loadDynamicDomains()"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          刷新域
        </button>
      </template>
    </EaPageHead>

    <ModelProviderBanner class="adapt-provider-banner" />

    <div class="adapt-workspace-bar">
      <div class="adapt-workspace-toggle">
        <button
          v-for="ws in ADAPT_WORKSPACES"
          :key="ws.id"
          type="button"
          class="adapt-workspace-btn"
          :class="activeWorkspaceId === ws.id ? 'ea-btn-soft' : 'mode-idle'"
          @click="switchAdaptWorkspace(ws.id)"
        >
          {{ ws.label }}
        </button>
      </div>
      <span class="adapt-workspace-hint">各子界面表单与 Skill 配置独立存放，互不影响</span>
    </div>

    <!-- 顶部域选择条 -->
    <div class="ea-domain-bar">
      <button
        v-for="domain in DOMAINS"
        :key="domain.id"
        type="button"
        class="ea-domain-chip"
        :class="{ active: activeDomainId === domain.id }"
        @click="selectDomain(domain.id)"
      >
        <span class="ea-domain-badge" :style="{ background: domain.color }">{{ domain.icon }}</span>
        {{ domain.label }}
        <span class="adapt-domain-dot" :class="domainRunDotClass(domain.id)" />
      </button>
    </div>

    <!-- ───────── 表单阶段 ───────── -->
    <template v-if="!showMonitor">
      <div class="ea-split-3">
        <!-- 左栏：表单主区 -->
        <div class="ea-stack">
          <EaCard>
            <div class="ea-domain-head">
              <span class="dh-badge" :style="{ background: activeDomain.color }">{{ activeDomain.icon }}</span>
              <div class="ea-grow">
                <h2>{{ activeDomain.label }}</h2>
                <div class="dh-sub">
                  <template v-if="requiredCount === 0">参考填写，无强制必填项</template>
                  <template v-else>必填项 {{ filledCount }} / {{ requiredCount }} 已完成</template>
                </div>
              </div>
              <EaPill v-if="isComplete" variant="ok">前置条件完整</EaPill>
              <EaPill v-else variant="warn">请完成必填项</EaPill>
              <div class="ea-head-actions adapt-domain-actions">
                <NButton
                  v-if="!layoutEditMode"
                  size="small"
                  secondary
                  @click="enterLayoutEdit"
                >
                  编辑布局
                </NButton>
                <span v-if="layoutManifestPath" class="layout-manifest-hint" :title="layoutManifestPath">本地配置已加载</span>
              </div>
            </div>

            <NSpin v-if="!layoutsReady" size="small" style="margin: 24px 0;">正在加载域配置…</NSpin>

            <template v-else>
              <div v-if="activeDomainId === 'modem' || activeDomainId === 'comm-framework' || activeDomainId === 'apn-config'" class="modem-skill-hint">
                <template v-if="activeDomainId === 'modem'">
                  以下字段来自 <code>MODEM_P1_Adapt</code> SKILL.md 的必填输入；填完后可用「Agent 自动适配」由桥接 Agent 按 Skill SOP 执行。
                </template>
                <template v-else-if="activeDomainId === 'apn-config'">
                  填写代码仓库路径与补充信息后，由 <code>apn-edit</code> Skill 按 SOP 定位并修改 APN 配置。
                </template>
                <template v-else>
                  以下字段来自 <code>comm-framework-agent-test</code> 测试 Skill 输入；点击「Agent 自动适配」后将按 Skill 分步骤在 PRJ Path 下创建并写入测试文件。
                </template>
              </div>

              <!-- 布局编辑模式 -->
              <div v-if="layoutEditMode" class="layout-editor">
                <div class="layout-editor-head">
                  <span class="layout-editor-title">域配置编辑</span>
                  <span class="layout-editor-hint">可增删表单字段与关联 Skill；第一项为主控 Skill。保存后写入本地 manifest，重启自动恢复（云端同步接口已预留）。</span>
                </div>
                <div class="layout-skills-editor">
                  <span class="layout-skills-label">关联 Skills</span>
                  <div class="layout-skills-tags">
                    <NTag
                      v-for="(skill, sIdx) in layoutDraftRelatedSkills"
                      :key="'draft-skill-' + skill"
                      size="small"
                      closable
                      class="skill-tag"
                      @close="removeRelatedSkill(sIdx)"
                      @click="openSkill(skill)"
                    >
                      {{ sIdx === 0 ? '主控 · ' : '' }}{{ skill }}
                    </NTag>
                  </div>
                  <NButton size="small" @click="openSkillSearchModal">+ 添加 Skill</NButton>
                </div>
                <div v-if="!layoutDraftFields.length" class="layout-editor-empty">暂无字段，请添加</div>
                <div
                  v-for="(field, idx) in layoutDraftFields"
                  :key="'draft-' + field.name"
                  class="layout-field-row"
                >
                  <div class="lfr-body">
                    <div class="lfr-main">
                      <NInput v-model:value="field.label" size="small" placeholder="显示标签" />
                      <code class="lfr-name">{{ field.name }}</code>
                      <NSelect
                        :value="field.type"
                        size="small"
                        :options="[
                          { label: '文本', value: 'text' },
                          { label: '多行文本', value: 'textarea' },
                          { label: '下拉选择', value: 'select' },
                        ]"
                        style="width: 120px;"
                        @update:value="v => onLayoutFieldTypeChange(field, v as FieldDef['type'])"
                      />
                      <label class="lfr-req">
                        <NSwitch v-model:value="field.required" size="small" />
                        <span>必填</span>
                      </label>
                    </div>
                    <div class="lfr-extra">
                      <NInput
                        v-model:value="field.placeholder"
                        size="small"
                        :placeholder="field.type === 'select' ? '占位提示（未选择时显示在下拉框内）' : '占位提示（可选）'"
                      />
                      <NInput
                        v-if="field.type === 'select'"
                        v-model:value="field.optionsText"
                        type="textarea"
                        size="small"
                        placeholder="下拉选项，每行一个&#10;如：&#10;GOODIX&#10;SAMSUNG"
                        :autosize="{ minRows: 2, maxRows: 6 }"
                      />
                    </div>
                  </div>
                  <NButton size="tiny" type="error" quaternary @click="removeLayoutField(idx)">删除</NButton>
                </div>
                <div class="layout-editor-actions">
                  <NButton size="small" @click="openAddFieldModal">+ 添加字段</NButton>
                  <NButton size="small" type="primary" :loading="layoutSaving" @click="saveLayout">保存布局</NButton>
                  <NButton size="small" @click="cancelLayoutEdit">取消</NButton>
                  <NButton size="small" tertiary :loading="layoutSaving" @click="restoreBuiltinLayout">恢复内置默认</NButton>
                </div>
              </div>

              <!-- 填写模式 -->
              <div v-else>
                <div class="ea-form-grid2">
                  <div
                    v-for="field in activeDomain.fields"
                    :key="activeDomainId + '-' + field.name"
                    class="ea-field"
                    :class="{ 'ea-field-full': field.type === 'textarea', 'ea-field-refilled': refilledFields.includes(field.name) }"
                  >
                    <label>
                      {{ field.label }}
                      <span v-if="field.required" class="req">*</span>
                    </label>
                    <NSelect
                      v-if="field.type === 'select'"
                      :value="getSelectFieldValue(field.name)"
                      :options="field.options"
                      :placeholder="field.placeholder || '请选择'"
                      clearable
                      @update:value="v => setFieldValue(field.name, v == null ? '' : String(v))"
                    />
                    <NInput
                      v-else-if="field.type === 'textarea'"
                      :value="getFieldValue(field.name)"
                      type="textarea"
                      :placeholder="field.placeholder"
                      :autosize="{ minRows: 3, maxRows: 6 }"
                      @update:value="v => setFieldValue(field.name, v)"
                    />
                    <NInput
                      v-else
                      :value="getFieldValue(field.name)"
                      :placeholder="field.placeholder"
                      @update:value="v => setFieldValue(field.name, v)"
                    />
                  </div>
                </div>

                <div v-if="!layoutEditMode" class="skill-row">
                  <span class="ea-muted" style="font-size:12.5px;font-weight:700">关联 Skills</span>
                  <span
                    v-for="(skill, sIdx) in activeDomain.relatedSkills"
                    :key="skill"
                    class="ea-skill-tag"
                    :class="{ lead: sIdx === 0 }"
                    @click="openSkill(skill)"
                  >
                    {{ sIdx === 0 ? '主控 · ' : '' }}{{ skill }}
                  </span>
                </div>

                <div class="action-row ea-mt16">
                  <NButton
                    size="large"
                    type="primary"
                    :disabled="!modelProviderReady || layoutEditMode || !isComplete || !activeDomain.relatedSkills.length"
                    :loading="agentLaunching"
                    @click="launchAgentAdapt"
                  >
                    {{ agentLaunching ? 'Agent 启动中...' : 'Agent 自动适配' }}
                  </NButton>
                  <NButton
                    size="large"
                    secondary
                    :disabled="layoutEditMode || !isComplete"
                    :loading="promptPreviewLoading"
                    @click="openPromptPreview"
                  >
                    预览提示词
                  </NButton>
                  <NButton
                    v-if="launchedTaskId"
                    size="large"
                    secondary
                    @click="openMonitorView"
                  >
                    <template #icon>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    </template>
                    查看执行进度
                    <NTag size="tiny" :type="statusTagType" style="margin-left:6px;">{{ taskStatus }}</NTag>
                  </NButton>
                </div>
              </div>
            </template>
          </EaCard>
        </div>

        <!-- 右栏：进度与域列表 -->
        <div class="ea-stack">
          <EaCard>
            <div class="ea-section-title ea-mb0">适配进度</div>
            <div class="ea-meta-grid adapt-progress-grid">
              <div class="mg">
                <div class="mg-k">总域数</div>
                <div class="mg-v">{{ DOMAINS.length }}</div>
              </div>
              <div class="mg">
                <div class="mg-k">已完成</div>
                <div class="mg-v adapt-stat-done">{{ completedDomains }}</div>
              </div>
              <div class="mg">
                <div class="mg-k">进行中</div>
                <div class="mg-v adapt-stat-active">{{ runningTasksCount }}</div>
              </div>
              <div class="mg">
                <div class="mg-k">总进度</div>
                <div class="mg-v">{{ overallPercent }}%</div>
              </div>
            </div>
            <NProgress
              :percentage="overallPercent"
              :show-indicator="false"
              :height="4"
              style="margin-top: 12px;"
            />
            <div class="adapt-progress-detail">{{ completedDomains }} / {{ DOMAINS.length }} 域完成</div>
          </EaCard>

          <EaCard v-if="launchedTaskId" class="adapt-task-snap">
            <div class="ea-section-title ea-mb0">当前任务</div>
            <div class="snap-row">
              <span class="snap-k">状态</span>
              <NTag size="tiny" :type="statusTagType">{{ taskStatus || '-' }}</NTag>
            </div>
            <div class="snap-row">
              <span class="snap-k">事件数</span>
              <span class="snap-v">{{ stream.length }}</span>
            </div>
            <div class="snap-row-id">
              <span class="snap-k">Task ID</span>
              <code class="snap-tid">{{ launchedTaskId }}</code>
            </div>
            <NButton
              size="tiny"
              type="primary"
              style="margin-top:8px;width:100%;"
              @click="openMonitorView"
            >查看执行详情</NButton>
          </EaCard>

          <EaCard>
            <div class="ea-row ea-between adapt-history-head">
              <div class="ea-section-title ea-mb0">历史表单</div>
              <div class="ea-row" style="gap:6px">
                <NSelect
                  v-model:value="historyScope"
                  size="tiny"
                  style="width:104px"
                  :options="[
                    { label: '仅当前域', value: 'current' },
                    { label: '全部域', value: 'all' },
                  ]"
                />
                <NButton size="tiny" quaternary :loading="historyLoading" title="刷新历史" @click="loadHistory">
                  刷新
                </NButton>
              </div>
            </div>

            <NInput
              v-model:value="historySearch"
              size="small"
              clearable
              placeholder="搜索项目名 / 域 / 任务号"
              style="margin:8px 0"
            />

            <div v-if="historyLoading && !historyItems.length" class="adapt-history-empty">
              <NSpin size="small" />
            </div>
            <div v-else-if="!filteredHistory.length" class="adapt-history-empty">
              暂无历史运行记录，完成一次 Agent 自动适配后这里会出现记录。
            </div>

            <div v-else class="adapt-history-list">
              <div
                v-for="item in filteredHistory"
                :key="item.task_id"
                class="adapt-history-item"
                :class="{ expanded: expandedTaskId === item.task_id }"
              >
                <button type="button" class="ahi-row" @click="toggleExpand(item.task_id)">
                  <span class="ahi-badge" :style="{ background: historyBadge(item).color }">
                    {{ historyBadge(item).icon }}
                  </span>
                  <span class="ahi-main">
                    <span class="ahi-title" :title="historyTitle(item)">
                      {{ historyTitle(item) }}
                    </span>
                    <span class="ahi-time" :title="absoluteTime(historyTimeValue(item))">
                      {{ relativeTime(historyTimeValue(item)) }}
                    </span>
                  </span>
                  <NTag size="tiny" :type="historyStatus(item).type">{{ historyStatus(item).label }}</NTag>
                  <span class="ahi-caret" :class="{ open: expandedTaskId === item.task_id }">▸</span>
                </button>

                <div v-if="expandedTaskId === item.task_id" class="ahi-detail">
                  <div v-if="expandedLoading && !detailCache[item.task_id]" class="ahi-detail-loading">
                    <NSpin size="small" />
                  </div>
                  <template v-else-if="detailCache[item.task_id]">
                    <div class="ahi-snap">
                      <div class="ahi-sub">表单快照</div>
                      <div v-if="formSnapshot(detailCache[item.task_id]).length" class="ahi-snap-grid">
                        <template v-for="row in formSnapshot(detailCache[item.task_id])" :key="row.label">
                          <span class="ahi-k">{{ row.label }}</span>
                          <span class="ahi-v" :title="row.value">{{ row.value }}</span>
                        </template>
                      </div>
                      <div v-else class="ahi-muted">该记录未保存表单快照</div>
                    </div>

                    <div class="ahi-report">
                      <div class="ahi-sub">运行报告</div>
                      <div class="ahi-report-line">{{ reportSummaryLine(detailCache[item.task_id]) }}</div>
                      <div class="ahi-report-meta">
                        <span>改动文件 {{ item.files_modified ?? 0 }}</span>
                        <span v-if="auditCounts(detailCache[item.task_id]).pass || auditCounts(detailCache[item.task_id]).fail">
                          审计 ✓{{ auditCounts(detailCache[item.task_id]).pass }} ✗{{ auditCounts(detailCache[item.task_id]).fail }}
                        </span>
                      </div>
                    </div>

                    <div class="ahi-actions">
                      <NButton
                        size="tiny"
                        type="primary"
                        :disabled="!detailCache[item.task_id].form_data || !Object.keys(detailCache[item.task_id].form_data || {}).length"
                        @click="requestRefill(detailCache[item.task_id])"
                      >回填此表单</NButton>
                      <NButton size="tiny" @click="viewReport(item.task_id)">查看完整报告</NButton>
                    </div>
                  </template>
                  <div v-else class="ahi-muted">报告加载失败</div>
                </div>
              </div>
            </div>
          </EaCard>
        </div>
      </div>
    </template>

    <!-- ───────── 监控阶段 ───────── -->
    <template v-else>
      <EaCard class="adapt-monitor-card">
        <div class="ea-row ea-between ea-wrap adapt-monitor-head">
          <div class="ea-row" style="gap:12px">
            <button type="button" class="ea-btn-ghost ea-btn-sm" @click="backToForm">
              ← 返回表单
            </button>
            <span class="dh-badge adapt-monitor-badge" :style="{ background: activeDomain.color }">{{ activeDomain.icon }}</span>
            <strong class="adapt-monitor-title">{{ activeDomain.label }} — Agent 自动适配</strong>
          </div>
          <div class="ea-row" style="gap:10px">
            <code v-if="launchedTaskId" class="adapt-taskid">{{ launchedTaskId }}</code>
            <NButton
              v-if="isRunning && launchedTaskId"
              size="small"
              type="error"
              secondary
              :loading="cancelTaskLoading"
              @click="cancelRunningTask"
            >
              终止任务
            </NButton>
            <EaPill :variant="statusTagType === 'success' ? 'ok' : statusTagType === 'error' ? 'err' : statusTagType === 'warning' ? 'warn' : 'info'">
              <span v-if="isRunning" class="ea-dot-live" />
              {{ taskStatus || 'starting' }}
            </EaPill>
          </div>
        </div>

        <!-- 启动中 -->
        <div v-if="agentLaunching && !launchedTaskId" class="monitor-state">
          <NSpin size="large" />
          <p class="ms-hint">正在启动 Agent 自动适配，请稍候...</p>
          <p class="ms-sub">Agent Bridge 连接中</p>
        </div>

        <!-- 启动失败且无事件 -->
        <div
          v-else-if="taskStatus === 'FAILED' && !stream.length"
          class="monitor-state monitor-error"
        >
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p class="ms-hint">Agent 任务启动失败</p>
          <p class="ms-sub">请检查 Agent Bridge 配置与关联 Skill 是否可用</p>
          <div class="ea-row" style="gap:8px;margin-top:4px;">
            <NButton type="primary" @click="backToForm">返回重新配置</NButton>
            <NButton :disabled="!modelProviderReady" @click="launchAgentAdapt" :loading="agentLaunching">重试</NButton>
          </div>
        </div>

        <!-- 等待任务 ID（仅启动 API 阶段） -->
        <div
          v-else-if="!launchedTaskId"
          class="monitor-state"
        >
          <NSpin size="medium" />
          <p class="ms-hint">任务已提交，等待服务端创建任务...</p>
        </div>

        <!-- 主监控视图：有 taskId 即展示步骤时间线 -->
        <div v-else class="ea-monitor adapt-monitor-body" :class="{ 'adapt-monitor-agent': monitorMode === 'agent' || !!launchedTaskId }">
          <div v-if="agentRunError" class="adapt-error-banner">
            <strong>任务失败</strong>
            <pre class="adapt-error-text">{{ agentRunError }}</pre>
            <div class="ea-row" style="gap:8px;margin-top:8px;">
              <NButton size="small" type="warning" @click="router.push({ name: 'hermes.models' })">模型管理</NButton>
              <NButton size="small" :disabled="!modelProviderReady" :loading="agentLaunching" @click="launchAgentAdapt">重试</NButton>
            </div>
          </div>
          <!-- 执行步骤（左侧） -->
          <div class="ea-mon-panel adapt-steps-panel">
            <h4>执行步骤</h4>
            <div ref="eventListEl" class="adapt-steps-list">
              <div
                v-for="step in executionSteps"
                :key="step.step_id"
                class="adapt-pipeline-step"
                :class="`step-${step.status}`"
              >
                <span class="adapt-step-dot" />
                <div class="adapt-step-body">
                  <div class="adapt-step-head">
                    <span class="adapt-step-label">{{ step.label }}</span>
                    <span v-if="step.ts" class="adapt-step-ts">{{ formatTs(step.ts) }}</span>
                  </div>
                  <div v-if="step.message" class="adapt-step-msg">{{ step.message }}</div>
                </div>
              </div>
              <div style="height:8px;" />
            </div>
          </div>

          <!-- 流式输出（中间） -->
          <div class="adapt-output-col">
            <div class="ea-row ea-between adapt-output-head">
              <span class="ea-section-title ea-mb0">Agent 执行输出</span>
              <EaPill v-if="isRunning" variant="info">
                <span class="ea-dot-live" />
                流式输出中
              </EaPill>
              <EaPill v-else-if="taskStatus === 'COMPLETED'" variant="ok">已完成</EaPill>
            </div>
            <pre v-if="llmResponse" class="ea-mon-output">{{ llmResponse }}</pre>
            <div v-else-if="agentRunError" class="adapt-run-error">
              <pre>{{ agentRunError }}</pre>
            </div>
            <div v-else-if="isRunning" class="lrp-waiting">
              <NSpin size="small" />
              <span>大模型思考中...</span>
            </div>
            <div
              v-if="isInteractiveDomain && (canContinueChat || canCompleteInteractiveTask || canViewAdaptReport)"
              class="adapt-output-actions"
            >
              <NButton
                v-if="canContinueChat"
                type="primary"
                secondary
                @click="openContinueChatModal"
              >
                补充信息继续分析
              </NButton>
              <NButton
                v-if="canCompleteInteractiveTask"
                type="warning"
                secondary
                :loading="completeTaskLoading"
                @click="onCompleteAdaptTask"
              >
                结束任务（生成报告）
              </NButton>
              <NButton
                v-if="canViewAdaptReport"
                type="primary"
                @click="openAdaptReport"
              >
                查看报告
              </NButton>
            </div>
          </div>

          <!-- Skill / 文件（右侧） -->
          <div v-if="monitorMode === 'agent' || launchedTaskId" class="adapt-sidebar-col">
            <div class="ea-mon-panel adapt-mon-scroll-panel">
              <h4>Skill / 工具调用</h4>
              <div class="adapt-mon-scroll-body">
                <div v-if="!agentSkillEvents.length" class="mon-empty">尚未调用工具</div>
                <div v-for="(ev, i) in agentSkillEvents" :key="'sk-' + i" class="mon-skill-row">
                  <NTag size="tiny" type="info">{{ ev.payload?.skill_id || 'tool' }}</NTag>
                  <span class="mon-skill-msg">{{ ev.payload?.message || formatPayload(ev.payload) }}</span>
                </div>
              </div>
            </div>
            <div class="ea-mon-panel adapt-mon-scroll-panel">
              <h4>文件修改</h4>
              <div class="adapt-mon-scroll-body">
                <div v-if="!agentFileEvents.length" class="mon-empty">暂无检测到的写文件操作</div>
                <div v-for="(fc, i) in agentFileEvents" :key="'fc-' + i" class="mon-file-row">
                  <code>{{ fc.path }}</code>
                  <span class="mon-file-meta">{{ fc.tool }} · {{ fc.status || 'modify' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 完成 / 失败横幅 -->
        <div v-if="taskStatus === 'COMPLETED'" class="result-banner result-ok">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          适配任务已完成
          <NButton size="small" type="primary" style="margin-left:12px;" @click="openAdaptReport">查看报告</NButton>
          <NButton size="small" style="margin-left:6px;" @click="backToForm">返回表单</NButton>
        </div>
        <div v-else-if="taskStatus === 'FAILED'" class="result-banner result-err">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          {{ agentRunError || '任务执行失败' }}
          <NButton size="small" type="warning" style="margin-left:12px;" @click="router.push({ name: 'hermes.models' })">模型管理</NButton>
          <NButton size="small" style="margin-left:6px;" @click="backToForm">重新配置</NButton>
          <NButton size="small" style="margin-left:6px;" :disabled="!modelProviderReady" :loading="agentLaunching" @click="launchAgentAdapt">重试</NButton>
        </div>
      </EaCard>
    </template>

    <!-- ====== 添加表单字段 ====== -->
    <NModal
      v-model:show="showAddFieldModal"
      preset="dialog"
      title="添加表单字段"
      positive-text="添加"
      negative-text="取消"
      style="width: 520px;"
      @positive-click="confirmAddField"
    >
      <NForm label-placement="left" label-width="88" size="small">
        <NFormItem label="字段名" required>
          <NInput v-model:value="newFieldDraft.name" placeholder="如 ic_model（字母开头）" />
        </NFormItem>
        <NFormItem label="显示标签" required>
          <NInput v-model:value="newFieldDraft.label" placeholder="如 IC型号" />
        </NFormItem>
        <NFormItem label="组件类型">
          <NSelect
            v-model:value="newFieldDraft.type"
            :options="[
              { label: '单行文本', value: 'text' },
              { label: '多行文本', value: 'textarea' },
              { label: '下拉选择', value: 'select' },
            ]"
          />
        </NFormItem>
        <NFormItem label="占位提示">
          <NInput
            v-model:value="newFieldDraft.placeholder"
            :placeholder="newFieldDraft.type === 'select' ? '未选择时显示在下拉框内' : '可选'"
          />
        </NFormItem>
        <NFormItem label="必填">
          <NSwitch v-model:value="newFieldDraft.required" />
        </NFormItem>
        <NFormItem v-if="newFieldDraft.type === 'select'" label="下拉选项">
          <NInput
            v-model:value="newFieldDraft.optionsText"
            type="textarea"
            placeholder="每行一个选项值，例如：&#10;GOODIX&#10;SAMSUNG"
            :autosize="{ minRows: 4, maxRows: 8 }"
          />
        </NFormItem>
      </NForm>
    </NModal>

    <!-- ====== 搜索添加 Skill ====== -->
    <NModal
      v-model:show="showSkillSearchModal"
      preset="card"
      title="添加关联 Skill"
      style="width: min(640px, 92vw);"
    >
      <NInput
        v-model:value="skillSearchQuery"
        placeholder="搜索 Skill 名称、描述或模块…"
        clearable
        style="margin-bottom: 12px;"
      />
      <NSpin v-if="skillCatalogLoading" size="small" style="padding: 16px 0;" />
      <div v-else class="skill-search-list">
        <div v-if="!filteredSkillCandidates.length" class="skill-search-empty">
          {{ skillSearchQuery ? '无匹配 Skill' : '输入关键词搜索' }}
        </div>
        <button
          v-for="skill in filteredSkillCandidates"
          :key="skill.name"
          type="button"
          class="skill-search-item"
          @click="addRelatedSkill(skill.name)"
        >
          <span class="ssi-name">{{ skill.name }}</span>
          <span v-if="skill.group" class="ssi-group">{{ skill.group }}</span>
          <span v-if="skill.description" class="ssi-desc">{{ skill.description }}</span>
        </button>
      </div>
    </NModal>

    <!-- ====== Agent 提示词预览 ====== -->
    <NModal
      v-model:show="showPromptPreview"
      preset="card"
      title="Agent 提示词预览"
      style="width: min(920px, 92vw);"
      :mask-closable="!promptPreviewLoading"
    >
      <div class="prompt-preview-body">
        <p class="prompt-preview-hint">
          以下为即将发往 Agent Bridge 的最终提示词（与「Agent 自动适配」启动时一致，Skill 正文不在此预注入）。
        </p>
        <div v-if="promptPreviewLoading" class="prompt-preview-loading">
          <NSpin size="medium" />
          <span>正在生成提示词...</span>
        </div>
        <template v-else>
          <div class="prompt-preview-actions">
            <NButton size="small" type="primary" @click="copyPromptText(previewAllText, '全部内容')">
              复制全部
            </NButton>
            <NButton size="small" @click="copyPromptText(previewSystemPrompt, '系统提示词')">
              复制系统提示词
            </NButton>
            <NButton size="small" @click="copyPromptText(previewUserPrompt, '用户提示词')">
              复制用户提示词
            </NButton>
            <span class="prompt-preview-meta">
              系统 {{ previewSystemPrompt.length.toLocaleString() }} 字 ·
              用户 {{ previewUserPrompt.length.toLocaleString() }} 字
            </span>
          </div>
          <NTabs v-model:value="promptPreviewTab" type="line" animated>
            <NTabPane name="system" tab="系统提示词">
              <pre class="prompt-preview-content">{{ previewSystemPrompt }}</pre>
            </NTabPane>
            <NTabPane name="user" tab="用户提示词">
              <pre class="prompt-preview-content">{{ previewUserPrompt }}</pre>
            </NTabPane>
          </NTabs>
        </template>
      </div>
    </NModal>

    <NModal
      v-model:show="refillConfirmVisible"
      preset="card"
      title="覆盖当前表单？"
      style="width: min(420px, 92vw);"
    >
      <p class="adapt-refill-confirm-text">
        目标域「{{ domainDefById(refillPendingDetail?.domain_id || refillPendingDetail?.domain)?.label || '' }}」当前表单已有内容，回填将覆盖这些字段。是否继续？
      </p>
      <template #footer>
        <div class="ea-row ea-between">
          <NButton size="small" @click="refillConfirmVisible = false; refillPendingDetail = null">取消</NButton>
          <NButton size="small" type="primary" @click="refillPendingDetail && applyRefill(refillPendingDetail)">覆盖回填</NButton>
        </div>
      </template>
    </NModal>

    <BugAnalysisInteractionModal
      v-if="isInteractiveDomain"
      :approval="pendingApproval"
      :user-input="pendingUserInput"
      :continue-chat="canContinueChat ? CONTINUE_CHAT_CONFIG : null"
      :show-continue-chat="showContinueChatModal"
      :submitting="interactionSubmitting"
      @approval="onAdaptApproval"
      @user-input="onAdaptUserInput"
      @continue-chat="onAdaptContinueChat"
      @continue-chat-dismiss="onContinueChatDismiss"
    />

  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.adapt-provider-banner {
  margin-bottom: 4px;
}

.adapt-workspace-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.adapt-workspace-toggle {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  background: var(--surface-2, rgba(255, 255, 255, 0.04));
  border: 1px solid var(--line, rgba(255, 255, 255, 0.08));
}

.adapt-workspace-btn {
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  border: none;
}

.adapt-workspace-btn.mode-idle {
  background: none;
  color: var(--muted);
}

.adapt-workspace-hint {
  font-size: 12px;
  color: var(--muted);
}

.adapt-refresh-btn.spinning svg {
  animation: adapt-spin 0.6s linear infinite;
}

@keyframes adapt-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.adapt-domain-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;

  &.dot-done { background: var(--success); }
  &.dot-running { background: var(--info); animation: ea-blink 1.5s infinite; }
  &.dot-active { background: var(--info); }
  &.dot-warn { background: var(--warn); }
  &.dot-pending { background: var(--line-strong); }
}

.adapt-domain-actions {
  margin-left: auto;
}

.ea-field-full {
  grid-column: 1 / -1;
}

.skill-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.action-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.modem-skill-hint {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 14px;
  line-height: 1.5;

  code {
    font-size: 11px;
    color: var(--accent);
  }
}

.layout-manifest-hint {
  font-size: 10px;
  color: var(--muted);
}

// ── 布局编辑 ────────────────────────────────────────────────────────────────
.layout-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.layout-editor-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 4px;
}

.layout-editor-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}

.layout-editor-hint {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.45;
}

.layout-editor-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 12px 0;
}

.layout-field-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
}

.lfr-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lfr-extra {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lfr-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  flex-wrap: wrap;
}

.lfr-name {
  font-size: 10px;
  color: var(--muted);
  font-family: $font-code;
  padding: 2px 6px;
  background: var(--surface-2);
  border-radius: 4px;
}

.lfr-req {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--muted);
}

.layout-editor-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.layout-skills-editor {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--bg);
  border: 1px dashed var(--line-strong);
}

.layout-skills-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  min-width: 72px;
}

.layout-skills-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
}

.skill-tag {
  cursor: pointer;
}

// ── 右栏进度 / 任务 ─────────────────────────────────────────────────────────
.adapt-progress-grid {
  grid-template-columns: 1fr 1fr;
  margin-top: 12px;
}

.adapt-stat-done { color: var(--success); }
.adapt-stat-active { color: var(--info); }

.adapt-progress-detail {
  font-size: 11px;
  color: var(--muted);
  margin-top: 8px;
}

.adapt-task-snap {
  border-color: color-mix(in srgb, var(--accent) 30%, transparent);
}

.snap-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}

.snap-k { color: var(--muted); }
.snap-v { font-weight: 700; color: var(--text); }

.snap-row-id {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 4px;
  font-size: 11px;
}

.snap-tid {
  font-family: $font-code;
  font-size: 10px;
  word-break: break-all;
  color: var(--muted);
  background: var(--surface-2);
  padding: 2px 5px;
  border-radius: 4px;
}

.ti-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

// ── 监控 ────────────────────────────────────────────────────────────────────
.adapt-page--monitor {
  .adapt-monitor-card {
    margin-bottom: 16px;
  }
}

.adapt-monitor-head {
  margin-bottom: 16px;
}

.adapt-monitor-badge {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  font-size: 10px;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 800;
}

.adapt-monitor-title {
  font-size: 15px;
  color: var(--head);
}

.adapt-taskid {
  font-size: 11px;
  font-family: $font-code;
  color: var(--faint);
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.adapt-monitor-body {
  min-height: 360px;

  &:not(.adapt-monitor-agent) {
    grid-template-columns: 1fr 260px;
  }
}

$adapt-output-h: 720px;
$adapt-sidebar-gap: 10px;

.adapt-sidebar-col {
  display: flex;
  flex-direction: column;
  gap: $adapt-sidebar-gap;
  height: $adapt-output-h;
  max-height: $adapt-output-h;
  min-height: 0;
}

.adapt-mon-scroll-panel {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-bottom: 10px;

  h4 {
    flex-shrink: 0;
    margin-bottom: 8px;
  }
}

.adapt-mon-scroll-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.adapt-output-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;

  .ea-mon-output {
    flex: 1 1 auto;
    min-height: 280px;
    max-height: $adapt-output-h;
    height: auto;
    overflow-y: auto;
    margin: 0;
  }

  .lrp-waiting {
    flex: 1 1 auto;
    min-height: 280px;
    max-height: $adapt-output-h;
  }
}

.adapt-output-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding-top: 4px;
}

.adapt-output-head {
  flex-shrink: 0;
}

.adapt-steps-panel {
  height: $adapt-output-h;
  max-height: $adapt-output-h;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;

  h4 {
    flex-shrink: 0;
    margin-bottom: 8px;
  }
}

.adapt-steps-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.adapt-error-banner {
  grid-column: 1 / -1;
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--error) 12%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--error) 35%, transparent);
  color: var(--error);
}

.adapt-error-text {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
  font-family: $font-code;
}

.adapt-run-error {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--error) 8%, var(--surface-2));

  pre {
    margin: 0;
    font-size: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text);
    font-family: $font-code;
  }
}

.adapt-pipeline-step {
  display: flex;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 1px solid var(--border-subtle);

  &:last-child { border-bottom: none; }
}

.adapt-step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
  background: var(--muted);
}

.step-pending .adapt-step-dot { background: var(--muted); opacity: 0.5; }
.step-running .adapt-step-dot { background: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent); }
.step-completed .adapt-step-dot { background: var(--success); }
.step-completed .adapt-step-label { color: var(--success); font-weight: 600; }
.step-warning .adapt-step-dot { background: var(--warning); }
.step-failed .adapt-step-dot { background: var(--error); }

.adapt-step-body {
  flex: 1;
  min-width: 0;
}

.adapt-step-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
}

.adapt-step-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.adapt-step-ts {
  font-size: 10px;
  color: var(--muted);
  font-family: $font-code;
  flex-shrink: 0;
}

.adapt-step-msg {
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--muted);
  word-break: break-word;
}

.step-running .adapt-step-label { color: var(--accent); }
.step-failed .adapt-step-label { color: var(--error); }

.monitor-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text);
  text-align: center;

  &.monitor-error { color: var(--error); }
}

.ms-hint {
  font-size: 14px;
  margin: 0;
  font-weight: 500;
}

.ms-sub {
  font-size: 12px;
  color: var(--muted);
  margin: 0;
}

.ms-taskid {
  font-size: 11px;
  font-family: $font-code;
  background: var(--surface-2);
  padding: 3px 8px;
  border-radius: 4px;
  color: var(--muted);
}

.mon-empty {
  font-size: 11px;
  color: var(--muted);
}

.mon-pre {
  margin: 0 0 6px;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
  font-family: $font-code;
}

.mon-skill-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px dashed var(--line);

  &:last-child {
    border-bottom: none;
    margin-bottom: 0;
  }
}

.mon-skill-msg {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
}

.mon-file-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;

  code {
    font-size: 11px;
    word-break: break-all;
    color: var(--accent);
  }
}

.mon-file-meta {
  font-size: 10px;
  color: var(--muted);
}

.lrp-waiting {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--muted);
  font-size: 13px;
  min-height: 200px;
}

.adapt-evt {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--line);
  font-size: 12px;

  &:last-child { border: none; }

  &.ev-success { border-left: 2px solid var(--success); padding-left: 8px; }
  &.ev-error { border-left: 2px solid var(--error); padding-left: 8px; }
  &.ev-warning { border-left: 2px solid var(--warn); padding-left: 8px; }
  &.ev-info { border-left: 2px solid var(--info); padding-left: 8px; }

  pre {
    margin: 4px 0 0;
    font-size: 11px;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: $font-code;
    color: var(--text);
  }
}

.adapt-evt-ts {
  color: var(--faint);
  font-family: $font-code;
  font-size: 11px;
  white-space: nowrap;
}

.result-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 14px;
  flex-wrap: wrap;

  &.result-ok {
    background: var(--success-soft);
    border: 1px solid color-mix(in srgb, var(--success) 30%, transparent);
    color: var(--success);
  }

  &.result-err {
    background: var(--error-soft);
    border: 1px solid color-mix(in srgb, var(--error) 25%, transparent);
    color: var(--error);
  }
}

// ── Skill 搜索弹窗 ────────────────────────────────────────────────────────────
.skill-search-list {
  max-height: 360px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.skill-search-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 16px 4px;
  text-align: center;
}

.skill-search-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid transparent;
  background: var(--bg);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  color: var(--text);

  &:hover {
    border-color: color-mix(in srgb, var(--accent) 35%, transparent);
    background: var(--accent-soft);
  }
}

.ssi-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.ssi-group {
  font-size: 10px;
  color: var(--accent);
}

.ssi-desc {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

// ── 提示词预览弹窗 ────────────────────────────────────────────────────────────
.prompt-preview-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 360px;
}

.prompt-preview-hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

.prompt-preview-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--muted);
  font-size: 13px;
  min-height: 280px;
}

.prompt-preview-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.prompt-preview-meta {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted);
  font-family: $font-code;
}

.prompt-preview-content {
  margin: 0;
  max-height: 52vh;
  overflow: auto;
  padding: 12px 14px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 12px;
  font-size: 12px;
  font-family: $font-code;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── 历史表单 ─────────────────────────────────────────────── */
.adapt-history-head {
  align-items: center;
}
.adapt-history-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px 8px;
  font-size: 12.5px;
  color: var(--text-3, #94a3b8);
  text-align: center;
  line-height: 1.6;
}
.adapt-history-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 420px;
  overflow-y: auto;
  min-height: 48px;
}
.adapt-history-item {
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg, #fff);
  transition: border-color .15s;
  min-height: 44px;
  flex-shrink: 0;
}
.adapt-history-item.expanded {
  border-color: var(--primary, #6366f1);
}
.ahi-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  min-height: 44px;
  box-sizing: border-box;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
}
.ahi-row:hover {
  background: var(--hover, rgba(99, 102, 241, .06));
}
.ahi-badge {
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ahi-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.ahi-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-1, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ahi-domain {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-3, #94a3b8);
  margin-right: 2px;
}
.ahi-time {
  font-size: 11px;
  color: var(--text-3, #94a3b8);
}
.ahi-caret {
  flex: 0 0 auto;
  color: var(--text-3, #94a3b8);
  transition: transform .15s;
  font-size: 11px;
}
.ahi-caret.open {
  transform: rotate(90deg);
}
.ahi-detail {
  padding: 8px 10px 10px;
  border-top: 1px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ahi-detail-loading {
  display: flex;
  justify-content: center;
  padding: 8px;
}
.ahi-sub {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-3, #94a3b8);
  margin-bottom: 4px;
}
.ahi-snap-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px 10px;
  font-size: 12px;
}
.ahi-k {
  color: var(--text-3, #94a3b8);
  white-space: nowrap;
}
.ahi-v {
  color: var(--text-1, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-all;
}
.ahi-muted {
  font-size: 12px;
  color: var(--text-3, #94a3b8);
}
.ahi-report-line {
  font-size: 12px;
  color: var(--text-2, #475569);
  line-height: 1.5;
}
.ahi-report-meta {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-3, #94a3b8);
}
.ahi-actions {
  display: flex;
  gap: 8px;
}
.adapt-refill-confirm-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-2, #475569);
}
.ea-field-refilled {
  animation: adapt-refill-flash 1.5s ease-out;
}
@keyframes adapt-refill-flash {
  0% { background: rgba(99, 102, 241, .18); }
  100% { background: transparent; }
}
</style>
