<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NInput, NInputNumber, NSelect, NSteps, NStep, useMessage } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import {
  createPipelineRun,
  discardPipelineDraftRun,
  fetchCapabilities,
  fetchPipelinePrereqs,
  startPipelineRun,
  type BuildContext,
  type CapabilityItem,
  type CreateRunInput,
  type PipelineDomainInput,
  type PrereqResolveData,
  type TestPlan,
} from '@/api/tahp/adapt-pipeline'
import { fetchPrereqProjects, type AdaptPrereqProject } from '@/api/tahp/adapt'
import { listDevices, type DeviceInfo } from '@/api/tahp/device-self-check'
import { getRuntimeMode } from '@/api/tahp/knowledge'
import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

const emit = defineEmits<{
  created: [runId: string]
}>()

const router = useRouter()
const message = useMessage()

const step = ref(1)
const loading = ref(false)
const launching = ref(false)
const centralConfigured = ref(true)
const capabilities = ref<CapabilityItem[]>([])

const projects = ref<AdaptPrereqProject[]>([])
const devices = ref<DeviceInfo[]>([])

const projectCode = ref('')
const manualProjectCode = ref('')
const campaignId = ref<string | null>(null)
const prereqData = ref<PrereqResolveData | null>(null)

interface WizardDomain {
  workspace_id: string
  domain_id: string
  domain_label: string
  module: string
  enabled: boolean
  schema: Array<{ key: string; label: string; required?: boolean }>
  form_data: Record<string, string>
  incomplete_required: string[]
}

const wizardDomains = ref<WizardDomain[]>([])

const buildContext = reactive<BuildContext>({
  mapped_root: '',
  workspace: '',
  components: ['krn'],
  variant: 'userdebug',
})

const componentsText = ref('krn')
const deviceId = ref<string | null>(null)
const testPlanMode = ref<'recommend' | 'fixed'>('recommend')
const maxIterations = ref(3)

const DOMAIN_LABELS: Record<string, string> = {
  tp: 'TP触摸屏',
  vib: '振动马达',
  lcm: 'LCM',
  charging: '充电',
  sensor: 'Sensor',
  memory: '内存',
  modem: 'Modem',
  'comm-framework': '通信框架',
  audio: '音频',
  'ecc-config': 'ECC配置',
}

function labelForDomain(id: string): string {
  return DOMAIN_LABELS[id] ?? id
}

function mapDomainToModule(domainId: string): string {
  if (domainId === 'modem' || domainId === 'comm-framework') return 'telephony'
  return 'kernel-driver'
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

const unavailableNodes = computed(() =>
  capabilities.value.filter(c => !c.availability.available),
)

const canProceedStep1 = computed(() =>
  Boolean((projectCode.value || manualProjectCode.value.trim()).length),
)

const canProceedStep2 = computed(() => {
  if (!centralConfigured.value) return false
  if (!wizardDomains.value.length) return false
  return enabledDomains.value.every(d => d.incomplete_required.length === 0)
})

function recomputeIncomplete(domain: WizardDomain) {
  const missing: string[] = []
  for (const field of domain.schema) {
    if (!field.required) continue
    const val = String(domain.form_data[field.key] ?? '').trim()
    if (!val) missing.push(field.key)
  }
  domain.incomplete_required = missing
}

function onDomainFieldChange(domain: WizardDomain) {
  recomputeIncomplete(domain)
}

function validateBuildPaths(): string | null {
  const root = buildContext.mapped_root.trim().replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
  if (!root) return '请填写 mapped_root'
  if (!buildContext.workspace.trim()) return '请填写 workspace'
  const ws = buildContext.workspace.trim().replace(/\\/g, '/').toLowerCase()
  if (!ws.startsWith(root) && !root.startsWith(ws.split('/')[0] ?? '')) {
    // workspace is relative path under mapped_root typically
    if (!ws.includes('/') && !/^[a-z]:/i.test(ws)) {
      // ok relative
    }
  }
  return null
}

const canProceedStep3 = computed(() => {
  if (!buildContext.mapped_root.trim() || !buildContext.workspace.trim()) return false
  if (!componentsText.value.trim()) return false
  return validateBuildPaths() === null
})

async function loadProjects() {
  try {
    projects.value = await fetchPrereqProjects()
  } catch {
    projects.value = []
  }
}

async function loadPrereqs() {
  const code = projectCode.value || manualProjectCode.value.trim()
  if (!code || !centralConfigured.value) return
  loading.value = true
  try {
    const data = await fetchPipelinePrereqs(code, campaignId.value ?? undefined)
    prereqData.value = data
    campaignId.value = data.campaign_id
    wizardDomains.value = data.domains.map(d => {
      const formData: Record<string, string> = {}
      for (const [k, v] of Object.entries(d.form_data ?? {})) {
        formData[k] = String(v ?? '')
      }
      const domain: WizardDomain = {
        workspace_id: d.workspace_id,
        domain_id: d.domain_id,
        domain_label: labelForDomain(d.domain_id),
        module: mapDomainToModule(d.domain_id),
        enabled: true,
        schema: (d.schema ?? []).map(s => ({
          key: s.key,
          label: s.label,
          required: s.required,
        })),
        form_data: formData,
        incomplete_required: [...d.incomplete_required],
      }
      recomputeIncomplete(domain)
      return domain
    })
  } catch (err) {
    message.error((err as Error).message)
    prereqData.value = null
    wizardDomains.value = []
  } finally {
    loading.value = false
  }
}

async function goNext() {
  if (step.value === 1) {
    if (!projectCode.value && manualProjectCode.value.trim()) {
      projectCode.value = ''
    }
    if (centralConfigured.value) {
      await loadPrereqs()
    }
    step.value = 2
    return
  }
  if (step.value === 2) {
    step.value = 3
    return
  }
  if (step.value === 3) {
    buildContext.components = componentsText.value.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean)
    const caps = capabilities.value.length ? capabilities.value : await fetchCapabilities()
    capabilities.value = caps
    step.value = 4
  }
}

function goBack() {
  if (step.value > 1) step.value -= 1
}

function buildDomainsPayload(): PipelineDomainInput[] {
  return enabledDomains.value.map(d => ({
    workspace_id: d.workspace_id,
    domain_id: d.domain_id,
    domain_label: d.domain_label,
    module: d.module,
    related_skills: [],
    form_data: { ...d.form_data },
    incomplete_required: [...d.incomplete_required],
    enabled: true,
    status: 'pending' as const,
  }))
}

function buildCreateInput(): CreateRunInput {
  const code = projectCode.value || manualProjectCode.value.trim()
  const testPlan: TestPlan = { mode: testPlanMode.value }
  return {
    project_code: code,
    campaign_id: prereqData.value?.campaign_id ?? campaignId.value ?? undefined,
    from_os: prereqData.value?.from_os,
    to_os: prereqData.value?.to_os,
    domains: buildDomainsPayload(),
    domain_ids: enabledDomains.value.map(d => d.domain_id),
    build_context: {
      ...buildContext,
      components: buildContext.components.length ? buildContext.components : ['krn'],
    },
    device_id: deviceId.value ?? undefined,
    test_plan: testPlan,
    max_iterations: maxIterations.value,
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

onMounted(async () => {
  loading.value = true
  try {
    await props.store.checkRuntimeReadiness()
    const [mode, caps, devs] = await Promise.all([
      getRuntimeMode().catch(() => ({ role: 'local' as const, central_configured: false, central_url: null })),
      fetchCapabilities().catch(() => []),
      listDevices().catch(() => []),
    ])
    centralConfigured.value = mode.central_configured
    capabilities.value = caps
    devices.value = devs
    if (centralConfigured.value) {
      await loadProjects()
    }
  } finally {
    loading.value = false
  }
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
      <div v-if="centralConfigured && projectOptions.length" class="field">
        <label>项目</label>
        <NSelect
          v-model:value="projectCode"
          :options="projectOptions"
          placeholder="从中心选择项目"
          filterable
          @update:value="(v) => { campaignId = projectOptions.find(p => p.value === v)?.campaign ?? null }"
        />
      </div>
      <div class="field">
        <label>{{ centralConfigured ? '或手工输入项目码' : '项目码' }}</label>
        <NInput v-model:value="manualProjectCode" placeholder="例如 KM9" :disabled="Boolean(projectCode)" />
      </div>
    </div>

    <!-- Step 2 -->
    <div v-else-if="step === 2" class="step-body">
      <h2>确认前置信息</h2>
      <p v-if="!centralConfigured" class="muted">请先配置中心连接后再确认前置。</p>
      <p v-else-if="loading" class="muted">加载前置信息…</p>
      <div v-else-if="!wizardDomains.length" class="muted">该项目暂无域配置，请返回重选或检查中心数据。</div>
      <div v-else class="domain-list">
        <div v-for="domain in wizardDomains" :key="domain.domain_id" class="domain-card">
          <label class="domain-head">
            <input v-model="domain.enabled" type="checkbox">
            <strong>{{ domain.domain_label }}</strong>
            <span class="domain-id">{{ domain.domain_id }}</span>
          </label>
          <div v-if="domain.enabled" class="fields">
            <div v-for="field in domain.schema" :key="field.key" class="field inline">
              <label>
                {{ field.label }}
                <span v-if="field.required" class="req">*</span>
              </label>
              <NInput
                v-model:value="domain.form_data[field.key]"
                :placeholder="field.label"
                @update:value="onDomainFieldChange(domain)"
              />
            </div>
            <p v-if="domain.incomplete_required.length" class="field-error">
              缺少必填项：{{ domain.incomplete_required.join(', ') }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3 -->
    <div v-else-if="step === 3" class="step-body">
      <h2>配置执行环境</h2>
      <div class="field">
        <label>mapped_root</label>
        <NInput v-model:value="buildContext.mapped_root" placeholder="Z:\workspace" />
      </div>
      <div class="field">
        <label>workspace（相对路径）</label>
        <NInput v-model:value="buildContext.workspace" placeholder="project/KM9_NEW" />
      </div>
      <div class="field-row">
        <div class="field">
          <label>编译组件（逗号分隔）</label>
          <NInput v-model:value="componentsText" placeholder="krn, vext" />
        </div>
        <div class="field">
          <label>variant</label>
          <NSelect
            v-model:value="buildContext.variant"
            :options="[
              { label: 'userdebug', value: 'userdebug' },
              { label: 'user', value: 'user' },
              { label: 'eng', value: 'eng' },
            ]"
          />
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <label>目标设备</label>
          <NSelect
            v-model:value="deviceId"
            :options="devices.map(d => ({ label: `${d.deviceId} (${d.deviceName})`, value: d.deviceId }))"
            clearable
            placeholder="选择自检设备"
          />
        </div>
        <div class="field">
          <label>用例策略</label>
          <NSelect
            v-model:value="testPlanMode"
            :options="[
              { label: '推荐策略', value: 'recommend' },
              { label: '固定用例', value: 'fixed' },
            ]"
          />
        </div>
      </div>
      <div class="field narrow">
        <label>最大迭代轮次</label>
        <NInputNumber v-model:value="maxIterations" :min="1" :max="99" />
      </div>
    </div>

    <!-- Step 4 -->
    <div v-else class="step-body">
      <h2>确认启动计划</h2>
      <div class="summary">
        <div class="summary-row"><span class="k">项目</span><span>{{ selectedProjectLabel }}</span></div>
        <div class="summary-row">
          <span class="k">启用域</span>
          <span>{{ enabledDomains.map(d => d.domain_label).join(' · ') || '—' }}</span>
        </div>
        <div class="summary-row">
          <span class="k">编译</span>
          <span>{{ buildContext.mapped_root }} · {{ buildContext.workspace }} · {{ buildContext.variant }} · {{ componentsText }}</span>
        </div>
        <div class="summary-row">
          <span class="k">设备 / 用例</span>
          <span>{{ deviceId ?? '未指定' }} · {{ testPlanMode === 'recommend' ? '推荐策略' : '固定用例' }}</span>
        </div>
        <div class="summary-row"><span class="k">迭代上限</span><span>{{ maxIterations }} 轮</span></div>
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
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  @media (max-width: 720px) { grid-template-columns: 1fr; }
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
}
.domain-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  .domain-id {
    font-size: 12px;
    color: var(--faint);
    font-family: var(--mono, monospace);
  }
}
.fields {
  margin-top: 10px;
  display: grid;
  gap: 8px;
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
  color: var(--warn);
  ul { margin: 8px 0 0; padding-left: 18px; }
}
.footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.spacer { flex: 1; }
</style>
