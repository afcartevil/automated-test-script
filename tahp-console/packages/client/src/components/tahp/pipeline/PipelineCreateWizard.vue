<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NInput, NInputNumber, NSelect, NSpin, NSteps, NStep, NTable, useMessage } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import {
  createPipelineRun,
  discardPipelineDraftRun,
  fetchCapabilities,
  fetchDomainCatalog,
  fetchHarnessSkills,
  fetchPipelinePrereqs,
  parsePipelinePathParams,
  startPipelineRun,
  type BuildContext,
  type CapabilityItem,
  type CreateRunInput,
  type DomainCatalog,
  type DomainCatalogDomain,
  type DomainCatalogField,
  type PathParamField,
  type PathParams,
  type PipelineDomainInput,
  type PrereqResolveData,
  type TestPlan,
  type TestPlanMode,
} from '@/api/tahp/adapt-pipeline'
import { fetchPrereqProjects, peekPrereqProjects, type AdaptPrereqProject } from '@/api/tahp/adapt'
import { refreshDevices, type DeviceInfo } from '@/api/tahp/device-self-check'
import {
  ADAPT_WORKSPACES,
  getBuiltinDomainsForWorkspace,
  type AdaptFieldType,
  type AdaptWorkspaceId,
  isAdaptWorkspaceId,
} from '@/constants/adapt-domains'
import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

const emit = defineEmits<{
  created: [runId: string]
}>()

const router = useRouter()
const route = useRoute()
const message = useMessage()

const step = ref(1)
const loading = ref(false)
const launching = ref(false)
const centralConfigured = ref(true)
const capabilities = ref<CapabilityItem[]>([])
const domainCatalog = ref<DomainCatalog | null>(null)

const projects = ref<AdaptPrereqProject[]>(peekPrereqProjects() ?? [])
const devices = ref<DeviceInfo[]>([])

/** 分步加载提示（互不阻塞） */
const projectsLoading = ref(false)
const projectsRefreshing = ref(false)
const projectsLoadError = ref('')
const catalogLoading = ref(false)
const prereqsLoading = ref(false)
const devicesLoading = ref(false)
const capsLoading = ref(false)

const DEVICE_POLL_MS = 2000
let devicePollTimer: ReturnType<typeof setInterval> | null = null
let devicePollInFlight = false

const projectCode = ref('')
const manualProjectCode = ref('')
const campaignId = ref<string | null>(null)
const prereqData = ref<PrereqResolveData | null>(null)

const oldVendorRoot = ref('')
const newVendorRoot = ref('')
const newSystemRoot = ref('')
const parsingPaths = ref(false)
const parsedPathFields = ref<PathParamField[]>([])
const parsedAt = ref('')
const lastParsedSignature = ref('')

/** 勾选的工作区；默认功能适配 */
const selectedWorkspaces = ref<AdaptWorkspaceId[]>(['adapt-debug'])

interface WizardFieldSchema {
  key: string
  label: string
  required?: boolean
  type: AdaptFieldType
  placeholder?: string
  options?: Array<{ label: string; value: string }>
  defaultValue?: string
}

interface WizardDomain {
  workspace_id: string
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  enabled: boolean
  schema: WizardFieldSchema[]
  form_data: Record<string, string>
  incomplete_required: string[]
  from_central: boolean
}

interface ChecklistRow {
  name: string
  code: string
}

const wizardDomains = ref<WizardDomain[]>([])

const BUILD_TARGET_OPTIONS = [
  { label: 'sys', value: 'sys' },
  { label: 'krn', value: 'krn' },
  { label: 'vext', value: 'vext' },
  { label: 'hal', value: 'hal' },
  { label: 'odm', value: 'odm' },
]

const buildContext = reactive<BuildContext>({
  mapped_root: '',
  workspace: '',
  project: '',
  variant: 'userdebug',
  build_flag: 'staging',
  system_path: '',
  vendor_path: '',
  build_targets: BUILD_TARGET_OPTIONS.map(o => o.value),
  need_pack: true,
  flash_skill_id: '',
  flash_mode: 'full_rom',
  target_branch: '',
  gerrit_issue_id: '',
})

const selectedBuildTargets = ref<string[]>(BUILD_TARGET_OPTIONS.map(o => o.value))
const needPack = ref<'yes' | 'no'>('yes')
const deviceId = ref<string | null>(null)
const testPlanMode = ref<TestPlanMode>('smoke')

const TEST_PLAN_MODE_LABELS: Record<TestPlanMode, string> = {
  smoke: '冒烟用例测试',
  pipeline_adapt: '适配流水线用例',
  recommend: '推荐策略',
  fixed: '固定用例',
}

const CATALOG_PLAN_MODES: TestPlanMode[] = ['smoke', 'pipeline_adapt']
const maxIterations = ref(3)

const TELEPHONY_DOMAINS = new Set([
  'modem',
  'comm-framework',
  'carrierconfig-tools',
  'ecc-config',
  'apn-config',
  'spn-config',
])

function mapDomainToModule(domainId: string, moduleHint?: string): string {
  if (moduleHint?.trim()) return moduleHint.trim()
  if (TELEPHONY_DOMAINS.has(domainId)) return 'telephony'
  return 'kernel-driver'
}

function domainKey(workspaceId: string, domainId: string): string {
  return `${workspaceId}::${domainId}`
}

function normalizeFieldType(raw?: string): AdaptFieldType {
  if (raw === 'select' || raw === 'textarea' || raw === 'checklist') return raw
  return 'text'
}

function schemaFromBuiltin(workspaceId: string, domainId: string): WizardFieldSchema[] {
  if (!isAdaptWorkspaceId(workspaceId)) return []
  const def = getBuiltinDomainsForWorkspace(workspaceId).find(d => d.id === domainId)
  if (!def) return []
  return def.fields.map(f => ({
    key: f.name,
    label: f.label,
    required: f.required,
    type: f.type,
    placeholder: f.placeholder,
    options: f.options?.map(o => ({ label: o.label, value: o.value })),
    defaultValue: f.defaultValue,
  }))
}

/** 目录/layout schema 优先；缺 type/options/default 时用内置域补齐（对齐 AI 适配调试） */
function enrichSchemaFromBuiltin(
  workspaceId: string,
  domainId: string,
  catalogSchema: DomainCatalogField[],
): WizardFieldSchema[] {
  const builtin = schemaFromBuiltin(workspaceId, domainId)
  if (!catalogSchema.length) return builtin
  const byKey = new Map(builtin.map(f => [f.key, f]))
  return catalogSchema.map((s) => {
    const b = byKey.get(s.key)
    return {
      key: s.key,
      label: s.label || b?.label || s.key,
      required: s.required ?? b?.required ?? false,
      type: normalizeFieldType(s.type || b?.type),
      placeholder: s.placeholder ?? b?.placeholder,
      options: (s.options?.length ? s.options : b?.options)?.map(o => ({
        label: o.label,
        value: o.value,
      })),
      defaultValue: s.defaultValue ?? b?.defaultValue,
    }
  })
}

function parseChecklistText(text?: string): ChecklistRow[] {
  if (!text?.trim()) return []
  return text
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map((line) => {
      const tabIdx = line.indexOf('\t')
      if (tabIdx >= 0) {
        return {
          name: line.slice(0, tabIdx).trim(),
          code: line.slice(tabIdx + 1).trim(),
        }
      }
      const match = line.match(/^(.*?)[\s\t]+(SF-[\w-]+)\s*$/i)
      if (match) {
        return { name: match[1].trim(), code: match[2].trim() }
      }
      return { name: line, code: line }
    })
    .filter(row => row.name || row.code)
}

function checklistDisplayText(field: WizardFieldSchema, formData: Record<string, string>): string {
  const fromForm = String(formData[field.key] ?? '').trim()
  if (fromForm) return fromForm
  return field.defaultValue?.trim() || ''
}

function getSelectFieldValue(domain: WizardDomain, key: string): string | null {
  const v = domain.form_data[key]
  return v == null || v === '' ? null : v
}

function setDomainFieldValue(domain: WizardDomain, key: string, value: string) {
  domain.form_data[key] = value
  onDomainFieldChange(domain)
}

function resolveModule(workspaceId: string, domainId: string, hint?: string): string {
  if (!isAdaptWorkspaceId(workspaceId)) return mapDomainToModule(domainId, hint)
  const def = getBuiltinDomainsForWorkspace(workspaceId).find(d => d.id === domainId)
  return mapDomainToModule(domainId, hint ?? def?.module)
}

const projectOptions = computed(() =>
  projects.value.map(p => ({
    label: `${p.code}${p.name ? ` · ${p.name}` : ''}`,
    value: p.code,
    campaign: p.active_campaign_id,
  })),
)

const selectedProjectLabel = computed(() => {
  const code = projectCode.value || manualProjectCode.value
  if (!code) return '—'
  const p = projects.value.find(x => x.code === code)
  const os = prereqData.value
  if (os?.from_os && os?.to_os) return `${code} · tOS${os.from_os} → tOS${os.to_os}`
  return p ? `${code}${p.name ? ` · ${p.name}` : ''}` : code
})

const enabledDomains = computed(() => wizardDomains.value.filter(d => d.enabled))

const visibleDomains = computed(() => {
  const ws = new Set(selectedWorkspaces.value)
  return wizardDomains.value.filter(d => ws.has(d.workspace_id as AdaptWorkspaceId))
})

const domainsByWorkspace = computed(() => {
  const groups: Array<{
    id: AdaptWorkspaceId
    label: string
    domains: WizardDomain[]
  }> = []
  for (const ws of ADAPT_WORKSPACES) {
    if (!selectedWorkspaces.value.includes(ws.id)) continue
    groups.push({
      id: ws.id,
      label: ws.label,
      domains: wizardDomains.value.filter(d => d.workspace_id === ws.id),
    })
  }
  return groups
})

const unavailableNodes = computed(() =>
  capabilities.value.filter(c => !c.availability.available),
)

const selectedProjectCode = computed(() =>
  projectCode.value || manualProjectCode.value.trim(),
)

const pathParseSignature = computed(() =>
  `${selectedProjectCode.value}||${oldVendorRoot.value.trim()}||${newVendorRoot.value.trim()}`,
)

const canParsePaths = computed(() =>
  Boolean(selectedProjectCode.value && oldVendorRoot.value.trim() && newVendorRoot.value.trim()),
)

const pathParseFresh = computed(() =>
  Boolean(lastParsedSignature.value) && lastParsedSignature.value === pathParseSignature.value,
)

const pathParseOkCount = computed(() => parsedPathFields.value.filter(f => f.ok).length)
const pathParseFailCount = computed(() => parsedPathFields.value.filter(f => !f.ok).length)

const canProceedStep1 = computed(() => canParsePaths.value && pathParseFresh.value)

function selectedProjectFull(): string | undefined {
  const v = parsedPathFields.value.find(f => f.key === 'PROJECT_FULL')?.value?.trim()
  return v || undefined
}

function setParsedFieldValue(key: string, value: string) {
  parsedPathFields.value = parsedPathFields.value.map((f) =>
    f.key === key ? { ...f, value } : f,
  )
}

function selectFieldOptions(field: PathParamField): Array<{ label: string; value: string }> {
  return (field.options ?? []).map(v => ({ label: v, value: v }))
}

async function handleParsePaths() {
  if (!canParsePaths.value || parsingPaths.value) return
  parsingPaths.value = true
  try {
    const data: PathParams = await parsePipelinePathParams({
      project_code: selectedProjectCode.value,
      OLD_VENDOR_ROOT: oldVendorRoot.value.trim(),
      NEW_VENDOR_ROOT: newVendorRoot.value.trim(),
      NEW_SYSTEM_ROOT: newSystemRoot.value.trim() || undefined,
      PROJECT_FULL: selectedProjectFull(),
    })
    parsedPathFields.value = data.fields.map(f => ({ ...f }))
    parsedAt.value = data.parsed_at
    lastParsedSignature.value = pathParseSignature.value
    const failed = data.fields.filter(f => !f.ok).length
    if (failed) {
      message.warning(`解析完成，${failed} 个字段失败，可手工填写后继续`)
    } else {
      message.success('路径参数解析完成')
    }
  } catch (err) {
    message.error((err as Error).message || '路径解析失败')
  } finally {
    parsingPaths.value = false
  }
}

const canProceedStep2 = computed(() => true)

function recomputeIncomplete(domain: WizardDomain) {
  const missing: string[] = []
  for (const field of domain.schema) {
    if (!field.required) continue
    const val = field.type === 'checklist'
      ? checklistDisplayText(field, domain.form_data)
      : String(domain.form_data[field.key] ?? '').trim()
    if (!val) missing.push(field.key)
  }
  domain.incomplete_required = missing
}

function onDomainFieldChange(domain: WizardDomain) {
  recomputeIncomplete(domain)
}

const canProceedStep3 = computed(() => {
  if (!String(buildContext.gerrit_issue_id ?? '').trim()) return false
  if (!String(buildContext.variant ?? '').trim()) return false
  if (!String(buildContext.build_flag ?? '').trim()) return false
  if (!selectedBuildTargets.value.length && needPack.value !== 'yes') return false
  return true
})

function buildLocalCatalogDomains(): DomainCatalogDomain[] {
  const list: DomainCatalogDomain[] = []
  for (const ws of ADAPT_WORKSPACES) {
    for (const def of getBuiltinDomainsForWorkspace(ws.id)) {
      list.push({
        workspace_id: ws.id,
        domain_id: def.id,
        domain_label: def.label,
        module: resolveModule(ws.id, def.id, def.module),
        related_skills: [...(def.relatedSkills ?? [])],
        schema: def.fields.map(f => ({
          key: f.name,
          label: f.label,
          required: f.required,
          type: f.type,
          placeholder: f.placeholder,
          options: f.options?.map(o => ({ label: o.label, value: o.value })),
          defaultValue: f.defaultValue,
        })),
      })
    }
  }
  return list
}

function buildWizardDomains(
  catalogDomains: DomainCatalogDomain[],
  prereq: PrereqResolveData | null,
): WizardDomain[] {
  const prereqMap = new Map(
    (prereq?.domains ?? []).map(d => [domainKey(d.workspace_id, d.domain_id), d]),
  )

  return catalogDomains.map(cat => {
    const schema = enrichSchemaFromBuiltin(
      cat.workspace_id,
      cat.domain_id,
      cat.schema ?? [],
    )
    const central = prereqMap.get(domainKey(cat.workspace_id, cat.domain_id))
    const formData: Record<string, string> = {}
    for (const field of schema) {
      // checklist：与 AI 适配调试一致，默认带上 layout/内置清单内容
      formData[field.key] = field.type === 'checklist' ? (field.defaultValue ?? '') : ''
    }
    if (central?.form_data) {
      for (const [k, v] of Object.entries(central.form_data)) {
        formData[k] = String(v ?? '')
      }
    }

    const domain: WizardDomain = {
      workspace_id: cat.workspace_id,
      domain_id: cat.domain_id,
      domain_label: cat.domain_label,
      module: resolveModule(cat.workspace_id, cat.domain_id, cat.module),
      related_skills: [...(cat.related_skills ?? [])],
      // 中心有该域则默认勾选；否则需用户显式启用
      enabled: Boolean(central) && selectedWorkspaces.value.includes(cat.workspace_id as AdaptWorkspaceId),
      schema,
      form_data: formData,
      incomplete_required: [],
      from_central: Boolean(central),
    }
    recomputeIncomplete(domain)
    return domain
  })
}

function rebuildWizardFromSources() {
  const fromApi = domainCatalog.value?.workspaces.flatMap(w => w.domains) ?? []
  const catalogDomains = fromApi.length ? fromApi : buildLocalCatalogDomains()
  wizardDomains.value = buildWizardDomains(catalogDomains, prereqData.value)
}

async function loadProjects(force = false) {
  if (!force) {
    const cached = peekPrereqProjects()
    if (cached) {
      projects.value = cached
      projectsLoadError.value = ''
      projectsLoading.value = false
      return
    }
  }
  if (!projects.value.length) projectsLoading.value = true
  projectsLoadError.value = ''
  try {
    projects.value = await fetchPrereqProjects({ force })
    projectsLoadError.value = ''
  } catch (err) {
    if (!projects.value.length) {
      projectsLoadError.value = (err as Error).message || '项目列表加载失败'
    }
    if (force) throw err
  } finally {
    projectsLoading.value = false
  }
}

async function refreshProjectConfig() {
  if (projectsRefreshing.value) return
  projectsRefreshing.value = true
  try {
    await loadProjects(true)
    const code = projectCode.value || manualProjectCode.value.trim()
    if (code) {
      const data = await fetchPipelinePrereqs(code, campaignId.value ?? undefined, { force: true })
      prereqData.value = data
      campaignId.value = data.campaign_id
      rebuildWizardFromSources()
    }
    message.success('已拉取最新项目配置')
  } catch (err) {
    message.error((err as Error).message || '刷新项目配置失败')
  } finally {
    projectsRefreshing.value = false
  }
}

async function loadCatalog() {
  catalogLoading.value = true
  try {
    domainCatalog.value = await fetchDomainCatalog()
  } catch {
    domainCatalog.value = null
  } finally {
    catalogLoading.value = false
    rebuildWizardFromSources()
  }
}

async function loadPrereqs() {
  const code = projectCode.value || manualProjectCode.value.trim()
  if (!code || !centralConfigured.value) {
    prereqData.value = null
    rebuildWizardFromSources()
    return
  }
  prereqsLoading.value = true
  try {
    const data = await fetchPipelinePrereqs(code, campaignId.value ?? undefined)
    prereqData.value = data
    campaignId.value = data.campaign_id
    rebuildWizardFromSources()
  } catch (err) {
    message.error((err as Error).message)
    prereqData.value = null
    rebuildWizardFromSources()
  } finally {
    prereqsLoading.value = false
  }
}

async function loadDevicesOnce() {
  if (devicePollInFlight) return
  devicePollInFlight = true
  // 仅首次无设备时显示「加载中」，轮询刷新不再闪烁整块
  if (!devices.value.length) devicesLoading.value = true
  try {
    const next = await refreshDevices()
    devices.value = next
    if (deviceId.value && !next.some(d => d.deviceId === deviceId.value)) {
      deviceId.value = null
    }
  } catch {
    // 保留上次列表
  } finally {
    devicesLoading.value = false
    devicePollInFlight = false
  }
}

function startDevicePolling() {
  stopDevicePolling()
  void loadDevicesOnce()
  devicePollTimer = setInterval(() => {
    void loadDevicesOnce()
  }, DEVICE_POLL_MS)
}

function stopDevicePolling() {
  if (devicePollTimer) {
    clearInterval(devicePollTimer)
    devicePollTimer = null
  }
}

function toggleWorkspace(id: AdaptWorkspaceId, checked: boolean) {
  if (checked) {
    if (!selectedWorkspaces.value.includes(id)) {
      selectedWorkspaces.value = [...selectedWorkspaces.value, id]
    }
  } else {
    if (selectedWorkspaces.value.length <= 1) {
      message.warning('至少保留一个工作区')
      return
    }
    selectedWorkspaces.value = selectedWorkspaces.value.filter(w => w !== id)
  }
  // 切换工作区时：新工作区下中心有数据的域自动启用；移出的工作区域取消启用
  for (const d of wizardDomains.value) {
    const inSelected = selectedWorkspaces.value.includes(d.workspace_id as AdaptWorkspaceId)
    if (!inSelected) {
      d.enabled = false
    } else if (d.from_central && !d.enabled) {
      d.enabled = true
      recomputeIncomplete(d)
    }
  }
}

function selectAllVisible() {
  for (const d of visibleDomains.value) {
    d.enabled = true
    recomputeIncomplete(d)
  }
}

function clearAllVisible() {
  for (const d of visibleDomains.value) {
    d.enabled = false
  }
}

async function goNext() {
  if (step.value === 1) {
    if (!projectCode.value && manualProjectCode.value.trim()) {
      projectCode.value = ''
    }
    // 先进入 Step2 展示加载提示，再拉前置（不堵在 Step1）
    step.value = 2
    // 目录未就绪时先用本地 builtin，目录返回后再 rebuild
    if (!wizardDomains.value.length) rebuildWizardFromSources()
    await loadPrereqs()
    return
  }
  if (step.value === 2) {
    step.value = 3
    return
  }
  if (step.value === 3) {
    buildContext.build_targets = [...selectedBuildTargets.value]
    buildContext.need_pack = needPack.value === 'yes'
    if (!capabilities.value.length) {
      capsLoading.value = true
      try {
        capabilities.value = await fetchCapabilities()
      } finally {
        capsLoading.value = false
      }
    }
    step.value = 4
  }
}

function goBack() {
  if (step.value > 1) step.value -= 1
}

function buildDomainsPayload(): PipelineDomainInput[] {
  return enabledDomains.value.map((d) => {
    const form_data = { ...d.form_data }
    for (const field of d.schema) {
      if (field.type !== 'checklist') continue
      const text = checklistDisplayText(field, form_data)
      if (text) form_data[field.key] = text
      else delete form_data[field.key]
    }
    return {
      workspace_id: d.workspace_id,
      domain_id: d.domain_id,
      domain_label: d.domain_label,
      module: d.module,
      related_skills: [...d.related_skills],
      form_data,
      incomplete_required: [...d.incomplete_required],
      enabled: true,
      status: 'pending' as const,
    }
  })
}

function buildCreateInput(): CreateRunInput {
  const code = projectCode.value || manualProjectCode.value.trim()
  const projectFull = selectedProjectFull() || code
  const vendorRoot = newVendorRoot.value.trim()
  const systemRoot = newSystemRoot.value.trim()
  const testPlan: TestPlan = {
    mode: testPlanMode.value,
    ...(CATALOG_PLAN_MODES.includes(testPlanMode.value) ? { test_type: testPlanMode.value } : {}),
  }
  return {
    project_code: code,
    campaign_id: prereqData.value?.campaign_id ?? campaignId.value ?? undefined,
    from_os: prereqData.value?.from_os,
    to_os: prereqData.value?.to_os,
    domains: buildDomainsPayload(),
    domain_ids: enabledDomains.value.map(d => d.domain_id),
    build_context: {
      mapped_root: '',
      workspace: '',
      project: projectFull,
      variant: buildContext.variant,
      build_flag: buildContext.build_flag || 'staging',
      system_path: systemRoot,
      vendor_path: vendorRoot,
      build_targets: selectedBuildTargets.value.length ? [...selectedBuildTargets.value] : [],
      need_pack: needPack.value === 'yes',
      flash_skill_id: (buildContext.flash_skill_id || '').trim() || undefined,
      flash_mode: 'full_rom',
      target_branch: buildContext.target_branch?.trim() || undefined,
      gerrit_issue_id: buildContext.gerrit_issue_id?.trim() || undefined,
    },
    device_id: deviceId.value ?? undefined,
    test_plan: testPlan,
    max_iterations: maxIterations.value,
    path_params: parsedPathFields.value.length
      ? {
          inputs: {
            project_code: code,
            OLD_VENDOR_ROOT: oldVendorRoot.value.trim(),
            NEW_VENDOR_ROOT: newVendorRoot.value.trim(),
            ...(newSystemRoot.value.trim() ? { NEW_SYSTEM_ROOT: newSystemRoot.value.trim() } : {}),
            ...(selectedProjectFull() ? { PROJECT_FULL: selectedProjectFull() } : {}),
          },
          fields: parsedPathFields.value.map(f => ({ ...f })),
          parsed_at: parsedAt.value || new Date().toISOString(),
        }
      : undefined,
  }
}

async function handleLaunch() {
  if (launching.value) return
  if (!props.store.bridgeRunning) {
    message.warning('Agent Bridge 未就绪，无法启动适配流水线')
    return
  }
  launching.value = true
  loading.value = true
  let createdRunId: string | null = null
  try {
    const created = await createPipelineRun(buildCreateInput())
    createdRunId = created.run_id
    await startPipelineRun(created.run_id)
    message.success('流水线已启动')
    await props.store.loadRuns()
    await props.store.selectRun(created.run_id)
    await props.store.loadTimeline(created.run_id)
    emit('created', created.run_id)
  } catch (err) {
    if (createdRunId) {
      try {
        await discardPipelineDraftRun(createdRunId)
      } catch {
        // ignore cleanup errors
      }
      await props.store.loadRuns()
    }
    message.error((err as Error).message)
  } finally {
    loading.value = false
    launching.value = false
  }
}

function goConfig() {
  router.push({ name: CONFIG_ROUTE_NAME })
}

onMounted(() => {
  const qCode = String(route.query.project_code || '').trim()
  const qCamp = String(route.query.campaign_id || '').trim()
  if (!projectCode.value && qCode) {
    projectCode.value = qCode
    if (qCamp) campaignId.value = qCamp
  }
  rebuildWizardFromSources()
  // 项目列表不依赖就绪检查：有会话缓存则首屏直接出下拉
  void loadProjects()
  void (async () => {
    catalogLoading.value = true
    capsLoading.value = true
    devicesLoading.value = true
    await props.store.checkRuntimeReadiness()
    centralConfigured.value = props.store.centralConfigured
    await Promise.all([
      loadCatalog(),
      fetchCapabilities()
        .then((caps) => { capabilities.value = caps })
        .catch(() => { capabilities.value = [] })
        .finally(() => { capsLoading.value = false }),
      loadDevicesOnce(),
      fetchHarnessSkills('flash')
        .then(({ items }) => {
          const ids = items.map(s => s.id)
          const preferred = ids.find(id => id === 'asf-device')
            || ids.find(id => id === 'harness-device')
            || ids[0]
          if (preferred) buildContext.flash_skill_id = preferred
        })
        .catch(() => { /* 服务端 defaultFlashSkillId 兜底 */ }),
    ])
    startDevicePolling()
  })()
})

onUnmounted(() => {
  stopDevicePolling()
})
</script>

<template>
  <EaCard class="wizard card">
    <NAlert v-if="!centralConfigured" type="warning" :bordered="false" class="banner">
      未配置 TAHP 中心连接，无法拉取项目前置。
      <button type="button" class="link-btn" @click="goConfig">前往配置</button>
    </NAlert>

    <NSteps :current="step" class="steps">
      <NStep title="选项目" />
      <NStep title="确认前置" />
      <NStep title="配置执行" />
      <NStep title="确认启动" />
    </NSteps>

    <!-- Step 1 -->
    <div v-if="step === 1" class="step-body">
      <h2>选择项目</h2>
      <div v-if="centralConfigured" class="field">
        <div class="field-head">
          <label>项目</label>
          <NButton
            size="small"
            secondary
            :loading="projectsRefreshing"
            :disabled="projectsRefreshing"
            @click="refreshProjectConfig"
          >
            刷新
          </NButton>
        </div>
        <div v-if="projectsLoading && !projectOptions.length" class="load-hint">
          <NSpin :size="16" />
          <span>项目列表加载中…</span>
        </div>
        <template v-else>
          <NSelect
            v-if="projectOptions.length"
            v-model:value="projectCode"
            :options="projectOptions"
            placeholder="从中心选择项目"
            filterable
            @update:value="(v) => { campaignId = projectOptions.find(p => p.value === v)?.campaign ?? null }"
          />
          <p v-else-if="projectsLoadError" class="field-error">项目列表加载失败：{{ projectsLoadError }}</p>
          <p v-else class="muted">中心暂无项目列表，请使用下方手工输入。</p>
        </template>
      </div>
      <div class="field">
        <div class="field-head">
          <label>{{ centralConfigured ? '或手工输入项目码' : '项目码' }}</label>
          <NButton
            v-if="!centralConfigured"
            size="small"
            secondary
            :loading="projectsRefreshing"
            :disabled="projectsRefreshing"
            @click="refreshProjectConfig"
          >
            刷新
          </NButton>
        </div>
        <NInput v-model:value="manualProjectCode" placeholder="例如 KM9" :disabled="Boolean(projectCode)" />
      </div>

      <h3 class="sub-title">代码根目录</h3>
      <div class="field">
        <label>OLD_VENDOR_ROOT <span class="req">*</span></label>
        <NInput v-model:value="oldVendorRoot" placeholder="例如 Z:\code-pull\cpull-xxx\vendor" />
      </div>
      <div class="field">
        <label>NEW_VENDOR_ROOT <span class="req">*</span></label>
        <NInput v-model:value="newVendorRoot" placeholder="例如 Z:\project\CM8\vendor" />
      </div>
      <div class="field">
        <label>NEW_SYSTEM_ROOT</label>
        <NInput v-model:value="newSystemRoot" placeholder="可选，仅保存不参与本轮解析" />
      </div>
      <div class="parse-bar">
        <NButton
          type="primary"
          :disabled="!canParsePaths || parsingPaths"
          :loading="parsingPaths"
          @click="handleParsePaths"
        >
          解析
        </NButton>
        <p v-if="parsedPathFields.length && !pathParseFresh" class="field-error">
          项目或 vendor 根已变化，请重新解析后再下一步。
        </p>
        <p v-else-if="!canParsePaths" class="muted">填写项目与两个必填 vendor 根后可解析。</p>
      </div>

      <div v-if="parsedPathFields.length" class="parsed-fields">
        <div
          v-for="field in parsedPathFields"
          :key="field.key"
          class="field"
          :class="{ inline: true }"
        >
          <label>
            {{ field.label }}
            <span v-if="field.ok" class="pill ok">解析成功</span>
            <span v-else class="pill fail">解析失败</span>
          </label>
          <NSelect
            v-if="field.kind === 'select'"
            :value="field.value || null"
            :options="selectFieldOptions(field)"
            filterable
            clearable
            placeholder="请选择项目目录"
            @update:value="(v: string | null) => setParsedFieldValue(field.key, v == null ? '' : String(v))"
          />
          <NInput
            v-else
            :value="field.value"
            :placeholder="field.error || field.label"
            @update:value="(v: string) => setParsedFieldValue(field.key, v)"
          />
          <p v-if="!field.ok && field.error" class="field-error">{{ field.error }}</p>
        </div>
      </div>
    </div>

    <!-- Step 2 -->
    <div v-else-if="step === 2" class="step-body">
      <h2>选择工作区与适配模块</h2>

      <div class="workspace-bar">
        <span class="bar-label">工作区</span>
        <label
          v-for="ws in ADAPT_WORKSPACES"
          :key="ws.id"
          class="ws-chip"
          :class="{ active: selectedWorkspaces.includes(ws.id) }"
        >
          <input
            type="checkbox"
            :checked="selectedWorkspaces.includes(ws.id)"
            @change="toggleWorkspace(ws.id, ($event.target as HTMLInputElement).checked)"
          >
          {{ ws.label }}
        </label>
        <div class="bar-actions">
          <button type="button" class="link-btn" @click="selectAllVisible">全选当前</button>
          <button type="button" class="link-btn" @click="clearAllVisible">清空当前</button>
        </div>
      </div>

      <div v-if="!visibleDomains.length" class="muted">请至少选择一个工作区。</div>
      <div v-else class="workspace-groups">
        <div v-for="group in domainsByWorkspace" :key="group.id" class="ws-group">
          <h3 class="ws-title">{{ group.label }}</h3>
          <div class="domain-list">
            <div
              v-for="domain in group.domains"
              :key="`${domain.workspace_id}::${domain.domain_id}`"
              class="domain-card"
              :class="{ disabled: !domain.enabled }"
            >
              <label class="domain-head">
                <input v-model="domain.enabled" type="checkbox" @change="onDomainFieldChange(domain)">
                <strong>{{ domain.domain_label }}</strong>
                <span class="domain-id">{{ domain.domain_id }}</span>
                <span v-if="domain.from_central" class="pill ok">中心有数据</span>
                <span v-else class="pill muted-pill">需手工填写</span>
              </label>
              <div v-if="domain.enabled" class="fields">
                <div
                  v-for="field in domain.schema"
                  :key="field.key"
                  class="field"
                  :class="{
                    inline: field.type === 'text' || field.type === 'select',
                    'field-full': field.type === 'textarea' || field.type === 'checklist',
                  }"
                >
                  <label>
                    {{ field.label }}
                    <span v-if="field.required" class="req">*</span>
                  </label>
                  <NSelect
                    v-if="field.type === 'select'"
                    :value="getSelectFieldValue(domain, field.key)"
                    :options="field.options ?? []"
                    :placeholder="field.placeholder || '请选择'"
                    clearable
                    @update:value="(v: string | null) => setDomainFieldValue(domain, field.key, v == null ? '' : String(v))"
                  />
                  <div
                    v-else-if="field.type === 'checklist'"
                    class="checklist-table-wrap"
                  >
                    <NTable
                      v-if="parseChecklistText(checklistDisplayText(field, domain.form_data)).length"
                      :bordered="true"
                      :single-line="false"
                      size="small"
                      class="checklist-table"
                    >
                      <thead>
                        <tr>
                          <th>特性编码</th>
                          <th>特性名称</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(row, rowIdx) in parseChecklistText(checklistDisplayText(field, domain.form_data))"
                          :key="field.key + '-' + rowIdx"
                        >
                          <td><code>{{ row.code }}</code></td>
                          <td>{{ row.name }}</td>
                        </tr>
                      </tbody>
                    </NTable>
                    <p v-else class="checklist-empty">暂无特性清单（与 AI 适配调试一致，请在适配调试「编辑布局」中配置）</p>
                  </div>
                  <NInput
                    v-else-if="field.type === 'textarea'"
                    type="textarea"
                    :value="domain.form_data[field.key]"
                    :placeholder="field.placeholder || field.label"
                    :autosize="{ minRows: 3, maxRows: 6 }"
                    @update:value="(v: string) => setDomainFieldValue(domain, field.key, v)"
                  />
                  <NInput
                    v-else
                    :value="domain.form_data[field.key]"
                    :placeholder="field.placeholder || field.label"
                    @update:value="(v: string) => setDomainFieldValue(domain, field.key, v)"
                  />
                </div>
                <p v-if="!domain.schema.length" class="muted">该域暂无表单字段，可直接启用。</p>
                <p v-if="domain.incomplete_required.length" class="field-error">
                  缺少必填项：{{ domain.incomplete_required.join(', ') }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
      <p v-if="!enabledDomains.length && !prereqsLoading" class="muted">当前未启用适配模块，仍可进入下一步。</p>
    </div>

    <!-- Step 3 -->
    <div v-else-if="step === 3" class="step-body">
      <h2>配置执行环境</h2>
      <p class="step-hint">
        编译经 remote-runner 在 Linux <code>~/code/ea-build</code> 执行 <code>ez-build.sh</code>。
        Windows 盘符路径会换算为 <code>/work/code/$USER/...</code>。请先保持齐治 Bridge READY。
      </p>

      <h3 class="sub-title">编译（ez-build）</h3>
      <div class="field-row">
        <div class="field">
          <label>variant <span class="req">*</span></label>
          <NSelect
            v-model:value="buildContext.variant"
            :options="[
              { label: 'userdebug', value: 'userdebug' },
              { label: 'user', value: 'user' },
              { label: 'user_root', value: 'user_root' },
            ]"
          />
        </div>
        <div class="field">
          <label>build_flag <span class="req">*</span></label>
          <NSelect
            v-model:value="buildContext.build_flag"
            :options="[
              { label: 'bleeding_edge', value: 'bleeding_edge' },
              { label: 'staging', value: 'staging' },
              { label: 'fooding', value: 'fooding' },
              { label: 'stable', value: 'stable' },
            ]"
          />
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <label>是否打包</label>
          <NSelect
            v-model:value="needPack"
            :options="[
              { label: '否', value: 'no' },
              { label: '是（追加 pack）', value: 'yes' },
            ]"
          />
          <p class="field-hint">选「是」时会在 targets 末尾追加 <code>pack</code>。project / system / vendor 分别取自 PROJECT_FULL、NEW_SYSTEM_ROOT、NEW_VENDOR_ROOT。</p>
        </div>
      </div>
      <div class="field">
        <label>编译 target <span class="req">*</span></label>
        <NSelect
          v-model:value="selectedBuildTargets"
          multiple
          :options="BUILD_TARGET_OPTIONS"
          max-tag-count="responsive"
          placeholder="sys / krn / vext / hal / odm"
        />
        <p class="field-hint">可多选：sys / krn / vext / hal / odm。</p>
      </div>

      <h3 class="sub-title">烧录 / 自检 / 入库</h3>
      <p class="field-hint section-hint">
        本轮编译不强制产出刷机包路径；烧录仍依赖后续产物或人工。整包烧录使用本机已装的 asf-device / harness-device。
      </p>
      <div class="field-row">
        <div class="field">
          <label>
            目标设备
            <span v-if="devicesLoading" class="inline-hint">扫描中…</span>
            <span v-else class="inline-hint muted">每 2 秒刷新</span>
          </label>
          <NSelect
            v-model:value="deviceId"
            :options="devices.map(d => ({ label: `${d.deviceId} (${d.deviceName})`, value: d.deviceId }))"
            clearable
            :loading="devicesLoading"
            :placeholder="devicesLoading ? '正在扫描 ADB 设备…' : (devices.length ? '选择烧录/自检设备' : '未检测到设备')"
          />
          <p class="field-hint">烧录与 AI 自检共用。不选则烧录阶段会失败并转人工。</p>
        </div>
        <div class="field">
          <label>自检用例策略</label>
          <NSelect
            v-model:value="testPlanMode"
            :options="[
              { label: '冒烟用例测试（仅执行冒烟用例）', value: 'smoke' },
              { label: '适配流水线用例（按勾选域：TP/马达/音频/LCM/指纹）', value: 'pipeline_adapt' },
              { label: '推荐策略（按适配域推断）', value: 'recommend' },
              { label: '固定用例（后续在自检节点确认）', value: 'fixed' },
            ]"
          />
          <p class="field-hint">默认仅跑冒烟用例；适配流水线用例只跑勾选调试项对应的模块（TP/马达/音频/LCM/指纹），无对应模块则转人工。</p>
        </div>
      </div>
      <div class="field-row">
        <div class="field narrow">
          <label>最大迭代轮次</label>
          <NInputNumber v-model:value="maxIterations" :min="1" :max="99" />
          <p class="field-hint">失败后改代码再编译的循环上限（自检通过后直接提交 Gerrit）。</p>
        </div>
        <div class="field">
          <label>Gerrit 目标分支（可选）</label>
          <NInput v-model:value="buildContext.target_branch" placeholder="留空=按仓库远程默认分支" />
          <p class="field-hint">仅入库阶段使用，与编译无关。需要强制推到指定分支时填写。</p>
        </div>
      </div>
      <div class="field">
        <label>Gerrit 提交 ID <span class="req">*</span></label>
        <NInput v-model:value="buildContext.gerrit_issue_id" placeholder="如 TOS1501-63219 或 AR-202506-002681" />
        <p class="field-hint">
          写入各仓 commit 模板的 <code>ID:</code> 字段（AR/BUG，禁止 task ID）。多仓共用同一 ID；
          各仓 <code>DESCRIPTION</code> 仍按该仓实际 diff 由 gerrit-submit Skill 填写。
        </p>
      </div>
    </div>

    <!-- Step 4 -->
    <div v-else class="step-body">
      <h2>确认启动计划</h2>
      <div v-if="capsLoading" class="load-hint">
        <NSpin :size="16" />
        <span>能力探测加载中…</span>
      </div>
      <div class="summary">
        <div class="summary-row"><span class="k">项目</span><span>{{ selectedProjectLabel }}</span></div>
        <div class="summary-row">
          <span class="k">工作区</span>
          <span>{{ selectedWorkspaces.map(id => ADAPT_WORKSPACES.find(w => w.id === id)?.label ?? id).join(' · ') }}</span>
        </div>
        <div class="summary-row">
          <span class="k">启用域</span>
          <span>{{ enabledDomains.map(d => `${d.domain_label}(${d.workspace_id})`).join(' · ') || '—' }}</span>
        </div>
        <div class="summary-row">
          <span class="k">编译</span>
          <span>
            ez-build · {{ selectedProjectFull() || '—' }}
            · {{ buildContext.variant }} / {{ buildContext.build_flag }}
            · targets={{ selectedBuildTargets.join(',') || '—' }}{{ needPack === 'yes' ? ',pack' : '' }}
            · sys={{ newSystemRoot.trim() || '—' }}
            · vnd={{ newVendorRoot.trim() || '—' }}
          </span>
        </div>
        <div class="summary-row">
          <span class="k">路径参数</span>
          <span>
            成功 {{ pathParseOkCount }} / 失败 {{ pathParseFailCount }}
            · OLD={{ oldVendorRoot.trim() || '—' }}
            · NEW={{ newVendorRoot.trim() || '—' }}
            <template v-if="newSystemRoot.trim()"> · SYS={{ newSystemRoot.trim() }}</template>
          </span>
        </div>
        <div class="summary-row">
          <span class="k">烧录</span>
          <span>自动使用编译产物 · 设备 {{ deviceId ?? '未指定' }}</span>
        </div>
        <div class="summary-row">
          <span class="k">自检</span>
          <span>{{ TEST_PLAN_MODE_LABELS[testPlanMode] }} · 最多 {{ maxIterations }} 轮</span>
        </div>
        <div class="summary-row">
          <span class="k">Gerrit 分支</span>
          <span>{{ buildContext.target_branch?.trim() || '按仓库默认' }}</span>
        </div>
        <div class="summary-row">
          <span class="k">Gerrit 提交 ID</span>
          <span>{{ buildContext.gerrit_issue_id?.trim() || '—' }}</span>
        </div>
      </div>
      <div v-if="unavailableNodes.length" class="warn-box">
        <strong>启动前须知</strong>
        <ul>
          <li v-for="node in unavailableNodes" :key="node.key">
            {{ node.label }}：{{ node.availability.reason ?? '能力未接入' }}，将在该节点转人工处理
          </li>
        </ul>
      </div>
    </div>

    <div class="footer">
      <NButton v-if="step > 1" :disabled="loading" @click="goBack">上一步</NButton>
      <div class="spacer" />
      <NButton
        v-if="step < 4"
        type="primary"
        :disabled="loading || (step === 1 && !canProceedStep1) || (step === 2 && !canProceedStep2) || (step === 3 && !canProceedStep3)"
        @click="goNext"
      >
        下一步
      </NButton>
      <NButton
        v-else
        type="primary"
        :loading="loading"
        :disabled="!store.bridgeRunning || launching"
        @click="handleLaunch"
      >
        启动流水线
      </NButton>
    </div>
  </EaCard>
</template>

<style scoped lang="scss">
.wizard {
  padding: 24px;
}
.banner {
  margin-bottom: 14px;
}
.link-btn {
  margin-left: 8px;
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-weight: 700;
  text-decoration: underline;
}
.steps {
  margin-bottom: 24px;
}
.step-body h2 {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 800;
}
.sub-title {
  margin: 18px 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--muted);
  letter-spacing: 0.02em;
}
.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--muted);
  code {
    font-size: 11px;
    padding: 0 4px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--line) 55%, transparent);
  }
}
.section-hint { margin: 0 0 12px; }
.step-hint {
  margin: -8px 0 14px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
}
.req { color: var(--err); font-weight: 700; }
.workspace-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface) 94%, var(--bg));
}
.bar-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  margin-right: 4px;
}
.ws-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  font-size: 13px;
  cursor: pointer;
  &.active {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }
}
.bar-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}
.workspace-groups {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.ws-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 700;
  color: var(--muted);
}
.field {
  margin-bottom: 14px;
  label {
    display: block;
    margin-bottom: 6px;
    font-size: 13px;
    color: var(--muted);
    font-weight: 600;
  }
}
.field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  label { margin-bottom: 0; }
}
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  @media (max-width: 720px) { grid-template-columns: 1fr; }
}
.parse-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 4px 0 16px;
}
.parsed-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  @media (max-width: 720px) { grid-template-columns: 1fr; }
}
.parsed-fields .field label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.field.narrow { max-width: 160px; }
.muted { color: var(--muted); }
.domain-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.domain-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  background: color-mix(in srgb, var(--surface) 94%, var(--bg));
  &.disabled {
    opacity: 0.72;
  }
}
.domain-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  cursor: pointer;
  .domain-id {
    font-size: 12px;
    color: var(--faint);
    font-family: var(--mono, monospace);
  }
}
.pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  &.ok {
    background: color-mix(in srgb, var(--ok, #3fb950) 18%, transparent);
    color: var(--ok, #2da44e);
  }
  &.fail {
    background: color-mix(in srgb, var(--err, #b03351) 16%, transparent);
    color: var(--err, #b03351);
  }
  &.muted-pill {
    background: color-mix(in srgb, var(--muted) 16%, transparent);
    color: var(--muted);
  }
}
.fields {
  margin-top: 10px;
  display: grid;
  gap: 8px;
}
.field-full {
  grid-column: 1 / -1;
}
.checklist-table-wrap {
  width: 100%;
  overflow: auto;
}
.checklist-table {
  width: 100%;
  font-size: 12.5px;
  th, td {
    padding: 6px 8px;
    text-align: left;
  }
  code {
    font-size: 12px;
  }
}
.checklist-empty {
  margin: 0;
  font-size: 12.5px;
  color: var(--muted);
}
.field-error {
  color: var(--err, #b03351);
  font-size: 12px;
  margin: 4px 0 0;
}
.req { color: var(--err, #b03351); }
.summary {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 14px;
}
.summary-row {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  .k { color: var(--muted); font-weight: 600; }
}
.warn-box {
  background: var(--warn-soft);
  border: 1px solid color-mix(in srgb, var(--warn) 25%, transparent);
  border-radius: 12px;
  padding: 12px;
  font-size: 13px;
  ul { margin: 8px 0 0; padding-left: 18px; }
}
.footer {
  display: flex;
  align-items: center;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  .spacer { flex: 1; }
}
.load-hint {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
  min-height: 34px;
}
.muted-line {
  margin-top: 8px;
}
.load-banner {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 14px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--accent) 25%, var(--line));
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  strong { display: block; margin-bottom: 4px; }
  p { margin: 0; font-size: 12px; }
}
.inline-hint {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--accent);
  &.muted { color: var(--muted); font-weight: 400; }
}
</style>
