<script setup lang="ts">
import { ref, computed, reactive, watch, nextTick, onMounted } from 'vue'
import { NButton, NSelect, NInput, NProgress, NTag, NSpin, NModal, NTabs, NTabPane, NForm, NFormItem, NSwitch, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import type { TahpModule } from '@/api/tahp/tasks'
import { fetchDynamicDomains } from '@/api/tahp/skills'
import { startAdaptAgentRun, previewAdaptAgentPrompts } from '@/api/tahp/adapt'
import { fetchSkills, type SkillInfo } from '@/api/hermes/skills'
import {
  fetchAdaptLayouts,
  saveAdaptDomainConfig,
  type AdaptLayoutFieldDef,
  type AdaptLayoutSyncMeta,
} from '@/api/tahp/adapt-layout'

const message = useMessage()
const router = useRouter()
const tasksStore = useTahpTasksStore()

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
}

interface DomainDef {
  id: DomainId
  label: string
  icon: string
  color: string
  status: 'active' | 'done' | 'pending' | 'warn'
  fields: FieldDef[]
  relatedSkills: string[]
}

// ─────────────────────────────────────────────────────────────────────────────
// 域定义
// ─────────────────────────────────────────────────────────────────────────────
const DOMAINS = reactive<DomainDef[]>([
  {
    id: 'tp',
    label: 'TP触摸屏',
    icon: 'TP',
    color: '#388bfd',
    status: 'active',
    relatedSkills: ['tp-adapt-dws-pin', 'tp-adapt-ko-order', 'tp-adapt-power-sequence', 'fc-tp-driver', 'fc-tp-selinux'],
    fields: [
      { name: 'ic_vendor',  label: 'IC厂商',              type: 'select', required: true,  options: [{ label:'FocalTech', value:'ft' },{ label:'Goodix', value:'gt' },{ label:'Synaptics', value:'rmi' },{ label:'Ilitek', value:'ili' }] },
      { name: 'ic_model',   label: 'IC型号',               type: 'text',   required: true,  placeholder: '如 FT8006M' },
      { name: 'interface',  label: '接口类型',              type: 'select', required: true,  options: [{ label:'I2C', value:'i2c' },{ label:'SPI', value:'spi' }] },
      { name: 'i2c_addr',  label: 'I2C地址',               type: 'text',   required: true,  placeholder: '如 0x38' },
      { name: 'rst_gpio',   label: 'RST GPIO',             type: 'text',   required: true,  placeholder: '如 4' },
      { name: 'int_gpio',   label: 'INT GPIO',             type: 'text',   required: true,  placeholder: '如 10' },
      { name: 'avdd_gpio',  label: 'AVDD GPIO',            type: 'text',   required: false, placeholder: '如 20' },
      { name: 'vddi_gpio',  label: 'VDDI GPIO',            type: 'text',   required: false, placeholder: '如 21' },
      { name: 'dts_path',   label: 'DTS文件路径',           type: 'text',   required: true,  placeholder: 'arch/arm64/boot/dts/mediatek/tp/...' },
      { name: 'dws_path1',  label: 'DWS路径1 (tools/dct)', type: 'text',   required: true,  placeholder: 'vendor/mediatek/proprietary/tools/dct/dws/...' },
      { name: 'dws_path2',  label: 'DWS路径2 (preloader)', type: 'text',   required: true,  placeholder: 'bootable/bootloader/preloader/custom/...' },
      { name: 'dws_path3',  label: 'DWS路径3 (kernel/dct)',type: 'text',   required: true,  placeholder: 'custom/.../kernel/dct/...' },
      { name: 'ko_table',   label: 'ko_order_table路径',   type: 'text',   required: true,  placeholder: 'vendor/transsion/projects/.../ko_order_table.csv' },
    ],
  },
  {
    id: 'vib',
    label: '振动马达',
    icon: 'VIB',
    color: '#f78166',
    status: 'pending',
    relatedSkills: ['vib-adapt-lra-driver', 'vib-adapt-dts-regulator', 'vib-adapt-projectconfig', 'fc-vib-driver', 'fc-vib-effect'],
    fields: [
      { name: 'motor_type',  label: '马达类型',  type: 'select', required: true,  options: [{ label:'LRA (线性)', value:'lra' },{ label:'ERM (旋转)', value:'erm' }] },
      { name: 'ic_vendor',   label: 'IC厂商',    type: 'select', required: true,  options: [{ label:'Awinic (AW)', value:'aw' },{ label:'AAC', value:'aac' },{ label:'其他', value:'other' }] },
      { name: 'ic_model',    label: 'IC型号',    type: 'text',   required: true,  placeholder: '如 AW8692x / AW8693x' },
      { name: 'i2c_channel', label: 'I2C通道',   type: 'text',   required: true,  placeholder: '如 7' },
      { name: 'i2c_addr',   label: 'I2C地址',   type: 'text',   required: true,  placeholder: '如 0x5A' },
      { name: 'irq_gpio',    label: 'IRQ GPIO',  type: 'text',   required: true,  placeholder: '如 15' },
      { name: 'rst_gpio',    label: 'RST GPIO',  type: 'text',   required: true,  placeholder: '如 22' },
      { name: 'lra_fw_dir',  label: 'LRA固件目录', type: 'text', required: true,  placeholder: 'vendor/transsion/projects/.../lra_fw/' },
      { name: 'regulator',   label: '调节器类型', type: 'text',  required: false, placeholder: 'regulator_vibrator' },
    ],
  },
  {
    id: 'fp',
    label: '指纹',
    icon: 'FP',
    color: '#3fb950',
    status: 'pending',
    relatedSkills: ['drv-fp-adapt', 'drv-fp-check', 'android-fingerprint-log-analysis'],
    fields: [
      { name: 'arch_type',   label: '架构类型', type: 'select', required: true, options: [{ label:'归一化 (tran_common_v2)', value:'normalized' },{ label:'非归一化 (tran_common)', value:'non_normalized' }] },
      { name: 'ic_vendor',   label: 'IC厂商',   type: 'select', required: true, options: [{ label:'GOODIX', value:'goodix' },{ label:'ANC', value:'anc' },{ label:'Silead', value:'silead' },{ label:'其他', value:'other' }] },
      { name: 'ic_model',    label: 'IC型号',   type: 'text',   required: true, placeholder: '如 GW9598' },
      { name: 'soc_model',   label: 'SoC型号',  type: 'text',   required: true, placeholder: '如 MT6878 / MT6789' },
      { name: 'ref_project', label: '参考项目',  type: 'text',   required: true, placeholder: '参考项目代码' },
      { name: 'spi_channel', label: 'SPI通道',  type: 'text',   required: false, placeholder: '如 0' },
    ],
  },
  {
    id: 'audio',
    label: '音频',
    icon: 'AUD',
    color: '#e3b341',
    status: 'pending',
    relatedSkills: ['DRV_Audio_Adapt', 'audio-bug-solver', 'audio-self-check'],
    fields: [
      { name: 'codec_vendor', label: 'Codec厂商', type: 'select', required: true, options: [{ label:'Cirrus', value:'cs' },{ label:'Everest', value:'es' },{ label:'Realtek', value:'rt' },{ label:'其他', value:'other' }] },
      { name: 'codec_model',  label: 'Codec型号', type: 'text',   required: true, placeholder: '如 CS35L45' },
      { name: 'i2c_addr',    label: 'I2C地址',   type: 'text',   required: true, placeholder: '如 0x40' },
      { name: 'audio_topo',   label: '音频拓扑',  type: 'text',   required: false, placeholder: '音频路由配置' },
    ],
  },
  {
    id: 'charging',
    label: '充电',
    icon: 'CHG',
    color: '#f78166',
    status: 'pending',
    relatedSkills: ['mtk-adapt-template-device-charger-ic', 'transsion-charger-orchestrator'],
    fields: [
      { name: 'charger_ic', label: '充电IC型号', type: 'text',   required: true, placeholder: '如 SM5414 / BQ25970' },
      { name: 'topo_type',  label: '拓扑类型',   type: 'select', required: true, options: [{ label:'PE5 (级联)', value:'pe5' },{ label:'FC (单芯)', value:'fc' },{ label:'Basic (基础)', value:'basic' }] },
      { name: 'gauge_ic',   label: 'Gauge IC',   type: 'text',   required: false, placeholder: '如 BQ28Z610' },
      { name: 'pd_ic',      label: 'PD IC',      type: 'text',   required: false, placeholder: '如 TUSB322' },
    ],
  },
  {
    id: 'modem',
    label: '通信Modem',
    icon: 'MDM',
    color: '#388bfd',
    status: 'pending',
    relatedSkills: ['MODEM_P1_Adapt', 'com-comm-analysis-foundation', 'carrier-porting-assistant'],
    fields: [
      { name: 'path_a_pub', label: 'Path_A_Pub（原分支公共仓）', type: 'text', required: true, placeholder: 'D:\\project\\mp_release_10.0\\common\\' },
      { name: 'path_a_priv', label: 'Path_A_Priv（原分支私有仓）', type: 'text', required: true, placeholder: 'D:\\project\\mp_release_10.0\\private\\' },
      { name: 'path_b_pub', label: 'Path_B_Pub（目标分支公共仓）', type: 'text', required: true, placeholder: 'D:\\project\\main\\common\\' },
      { name: 'path_b_priv', label: 'Path_B_Priv（目标分支私有仓）', type: 'text', required: true, placeholder: 'D:\\project\\main\\private\\' },
      { name: 'bom_name', label: 'BOM_Name（项目 BOM）', type: 'text', required: true, placeholder: 'ae10_h833_a1 / cm7_h781 / x6870_h781_f1' },
      { name: 'bom_name_target', label: 'BOM_Name_Target（变更后 BOM）', type: 'text', required: true, placeholder: 'x6856_h971_a1' },
      { name: 'rf_target_location', label: 'RF_TARGET_LOCATION', type: 'select', required: true, options: [{ label: 'public（公共仓）', value: 'public' }, { label: 'private（私有仓）', value: 'private' }] },
      { name: 'modem_platform', label: 'Modem 平台（补充）', type: 'select', required: false, options: [{ label: 'MTK', value: 'mtk' }, { label: 'Qualcomm', value: 'qcom' }, { label: 'UNISOC', value: 'unisoc' }] },
      { name: 'rf_param_dir', label: 'RF 参数目录（补充）', type: 'text', required: false, placeholder: 'vendor/mediatek/proprietary/modem_1/rf_params' },
      { name: 'carrier', label: '运营商（补充）', type: 'text', required: false, placeholder: 'CMCC / Vodafone' },
      { name: 'user_notes', label: '补充说明', type: 'textarea', required: false, placeholder: '覆盖确认、特殊分支说明等' },
    ],
  },
  {
    id: 'comm-framework',
    label: '通信框架',
    icon: 'CMF',
    color: '#0ea5e9',
    status: 'pending',
    relatedSkills: ['comm-framework-agent-test', 'com-comm-analysis-foundation'],
    fields: [
      { name: 'prj_path', label: 'PRJ Path（项目路径）', type: 'text', required: true, placeholder: 'D:\\project\\your_comm_framework\\' },
      { name: 'user_notes', label: '补充说明', type: 'textarea', required: false, placeholder: '说明要测试的场景、注意事项等' },
    ],
  },
  {
    id: 'kernel',
    label: '内核CPU',
    icon: 'KRN',
    color: '#e3b341',
    status: 'pending',
    relatedSkills: ['KRN_LK_CPU_Ddapt', 'kernel-panic-tracer', 'android-ke-log-analysis'],
    fields: [
      { name: 'cpu_model',   label: 'CPU型号',                   type: 'text', required: true, placeholder: '如 MT6878' },
      { name: 'lk_version',  label: 'LK版本',                    type: 'text', required: true, placeholder: '如 5.0.2' },
      { name: 'kdm_version', label: 'kernel_device_modules版本', type: 'text', required: true, placeholder: '如 5.4-2023' },
    ],
  },
  {
    id: 'scp',
    label: 'SCP传感器',
    icon: 'SCP',
    color: '#a371f7',
    status: 'pending',
    relatedSkills: ['BSP_sensor_ps_anti_touch', 'mtk-sensor-dts-config', 'scp-sensor-check'],
    fields: [
      { name: 'sensor_ic',    label: '传感器IC型号', type: 'text',   required: true, placeholder: '如 BMA4xx / ICM' },
      { name: 'interface',    label: '接口类型',     type: 'select', required: true, options: [{ label:'I2C', value:'i2c' },{ label:'SPI', value:'spi' }] },
      { name: 'channel_addr', label: '通道/地址',    type: 'text',   required: true, placeholder: '如 0x68 (I2C)' },
    ],
  },
  {
    id: 'aikey',
    label: 'AI按键',
    icon: 'KEY',
    color: '#a371f7',
    status: 'pending',
    relatedSkills: ['aikey-adapt-dts', 'fc-aikey-dts', 'fc-aikey-event', 'bsp-adapt-lk-key'],
    fields: [
      { name: 'gpio_config', label: 'GPIO编号',  type: 'text',     required: true, placeholder: '按键使用的GPIO编号' },
      { name: 'key_mapping', label: '按键映射',  type: 'textarea', required: true, placeholder: '按键到功能的映射配置' },
      { name: 'hal_version', label: 'HAL版本',   type: 'text',     required: false, placeholder: '如 v1.0' },
    ],
  },
])

/** 内置默认字段快照（恢复默认 / 云端未覆盖时使用） */
const STATIC_DEFAULT_FIELDS: Record<string, FieldDef[]> = Object.fromEntries(
  DOMAINS.map(d => [d.id, JSON.parse(JSON.stringify(d.fields)) as FieldDef[]]),
)
const STATIC_DEFAULT_RELATED_SKILLS: Record<string, string[]> = Object.fromEntries(
  DOMAINS.map(d => [d.id, [...d.relatedSkills]]),
)

// ─────────────────────────────────────────────────────────────────────────────
// 表单状态
// ─────────────────────────────────────────────────────────────────────────────
const activeDomainId = ref<DomainId>('tp')

// 动态 formData：按需初始化，支持后续加入的自定义域
const formData = reactive<Record<string, Record<string, string>>>({})

// 为已知静态域初始化 formData
function initDomainFormData(domain: DomainDef) {
  if (!formData[domain.id]) {
    formData[domain.id] = {}
  }
  domain.fields.forEach(field => {
    if (formData[domain.id][field.name] === undefined) {
      formData[domain.id][field.name] = ''
    }
  })
}

// 初始化所有静态域的表单数据
DOMAINS.forEach(domain => initDomainFormData(domain))

function syncFormDataForDomain(domain: DomainDef) {
  if (!formData[domain.id]) formData[domain.id] = {}
  const validNames = new Set(domain.fields.map(f => f.name))
  for (const key of Object.keys(formData[domain.id])) {
    if (!validNames.has(key)) delete formData[domain.id][key]
  }
  domain.fields.forEach(field => {
    if (formData[domain.id][field.name] === undefined) {
      formData[domain.id][field.name] = ''
    }
  })
}

function applyFieldsToDomain(domainId: string, fields: FieldDef[]) {
  const domain = DOMAINS.find(d => d.id === domainId)
  if (!domain) return
  domain.fields = fields.map(f => ({ ...f }))
  syncFormDataForDomain(domain)
}

function applyRelatedSkillsToDomain(domainId: string, skills: string[]) {
  const domain = DOMAINS.find(d => d.id === domainId)
  if (!domain || !skills.length) return
  domain.relatedSkills = [...skills]
}

function applyDomainConfigFromRecord(
  domainId: string,
  record: { fields?: FieldDef[]; related_skills?: string[] },
) {
  if (record.fields?.length) applyFieldsToDomain(domainId, record.fields)
  if (record.related_skills?.length) applyRelatedSkillsToDomain(domainId, record.related_skills)
}

// ─────────────────────────────────────────────────────────────────────────────
// 布局持久化（本地 manifest + 可扩展云端同步）
// ─────────────────────────────────────────────────────────────────────────────
const layoutSyncMeta = ref<AdaptLayoutSyncMeta | null>(null)
const layoutManifestPath = ref('')
const layoutsReady = ref(false)
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
async function loadAdaptLayouts(options: { showError?: boolean } = {}): Promise<boolean> {
  const showError = options.showError !== false
  const maxAttempts = 5
  let lastErr: unknown = null

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetchAdaptLayouts()
      layoutSyncMeta.value = res.sync
      layoutManifestPath.value = res.manifest_path || ''
      for (const [domainId, record] of Object.entries(res.layouts || {})) {
        if (!record) continue
        applyDomainConfigFromRecord(domainId, {
          fields: record.fields as FieldDef[],
          related_skills: record.related_skills,
        })
      }
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
  return false
}

function enterLayoutEdit() {
  layoutDraftFields.value = activeDomain.value.fields.map(f => ({
    ...f,
    options: f.options ? f.options.map(o => ({ ...o })) : undefined,
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
    .map(line => {
      const [label, value] = line.split(':').map(s => s.trim())
      if (value) return { label, value }
      return { label: line, value: line }
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
      message.warning('下拉框至少需要一个选项（每行 label:value）')
      return false
    }
    field.options = options
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
    const fields = layoutDraftFields.value as AdaptLayoutFieldDef[]
    const related_skills = [...layoutDraftRelatedSkills.value]
    const result = await saveAdaptDomainConfig(activeDomainId.value, { fields, related_skills })
    applyFieldsToDomain(activeDomainId.value, layoutDraftFields.value)
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
  const defaults = STATIC_DEFAULT_FIELDS[activeDomainId.value]
  const defaultSkills = STATIC_DEFAULT_RELATED_SKILLS[activeDomainId.value]
  if (!defaults?.length || !defaultSkills?.length) {
    message.warning('当前域无内置默认配置')
    return
  }
  layoutSaving.value = true
  try {
    const fields = JSON.parse(JSON.stringify(defaults)) as AdaptLayoutFieldDef[]
    const related_skills = [...defaultSkills]
    await saveAdaptDomainConfig(activeDomainId.value, { fields, related_skills })
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
  DOMAINS.find(d => d.id === activeDomainId.value) ?? DOMAINS[0]
)

const currentFormData = computed<Record<string, string>>(() =>
  formData[activeDomainId.value] ?? {}
)

const requiredCount = computed(() => (activeDomain.value?.fields ?? []).filter(f => f.required).length)
const filledCount = computed(() => (activeDomain.value?.fields ?? []).filter(f => f.required && currentFormData.value[f.name]).length)
// 没有必填项（requiredCount === 0）时也视为完整，允许启动任务
const isComplete = computed(() => requiredCount.value === 0 || filledCount.value === requiredCount.value)
const completedDomains = computed(() => DOMAINS.filter(d => d.status === 'done').length)
const overallPercent = computed(() => Math.round((completedDomains.value / DOMAINS.length) * 100))

// ─────────────────────────────────────────────────────────────────────────────
// Getter / Setter — 避免在 computed 上使用 v-model
// ─────────────────────────────────────────────────────────────────────────────
function getFieldValue(fieldName: string): string {
  return (formData[activeDomainId.value] ?? {})[fieldName] ?? ''
}
function setFieldValue(fieldName: string, value: string) {
  if (!formData[activeDomainId.value]) formData[activeDomainId.value] = {}
  formData[activeDomainId.value][fieldName] = value
}

// ─────────────────────────────────────────────────────────────────────────────
// 执行 / 监控状态
// ─────────────────────────────────────────────────────────────────────────────
const agentLaunching = ref(false)
const launchedTaskId = ref<string | null>(null)
const taskStatus  = ref<string>('')
const showMonitor = ref(false)
const monitorMode = ref<'agent' | null>(null)
const eventListEl = ref<HTMLElement | null>(null)

// 任务创建时间，用于显示耗时
const startTime = ref<number>(0)

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

// 结构化事件（phase、step、completed、failed）用于侧边栏状态
const structuredEvents = computed(() =>
  stream.value.filter(ev =>
    ev.type !== 'task.message' &&
    ev.type !== 'task.skill_use' &&
    ev.type !== 'task.file_change' &&
    ev.type !== 'task.plan' &&
    ev.type !== 'task.tool_completed',
  )
)

const agentSkillEvents = computed(() =>
  stream.value.filter(ev => ev.type === 'task.skill_use')
)

const agentFileEvents = computed(() =>
  stream.value.filter(ev => ev.type === 'task.file_change')
)

const agentPlanEvents = computed(() =>
  stream.value.filter(ev => ev.type === 'task.plan' || (ev.type === 'task.message' && ev.payload?.level === 'reasoning'))
)

const isRunning = computed(() =>
  taskStatus.value !== '' &&
  taskStatus.value !== 'COMPLETED' &&
  taskStatus.value !== 'FAILED' &&
  taskStatus.value !== 'completed' &&
  taskStatus.value !== 'failed'
)

const statusTagType = computed<'info' | 'success' | 'error' | 'warning'>(() => {
  const s = taskStatus.value.toUpperCase()
  if (s === 'COMPLETED') return 'success'
  if (s === 'FAILED')    return 'error'
  if (s === 'STARTING')  return 'warning'
  return 'info'
})

// 监听事件流 → 更新状态 + 自动滚动到底部
watch(stream, async (evs) => {
  if (!evs.length) return
  const last = evs[evs.length - 1]
  if (last.type === 'task.completed')
    taskStatus.value = 'COMPLETED'
  else if (last.type === 'task.failed')
    taskStatus.value = 'FAILED'
  else if (last.type === 'task.phase')
    taskStatus.value = (last.payload?.phase as string) || 'running'
  else if (taskStatus.value !== 'COMPLETED' && taskStatus.value !== 'FAILED')
    taskStatus.value = 'running'

  await nextTick()
  if (eventListEl.value) {
    eventListEl.value.scrollTop = eventListEl.value.scrollHeight
  }
}, { deep: true })

// ─────────────────────────────────────────────────────────────────────────────
// 适配域 → TAHP 模块映射（优先从动态域 module 字段读取）
// ─────────────────────────────────────────────────────────────────────────────
function mapDomainToModule(id: DomainId): TahpModule {
  const domain = DOMAINS.find(d => d.id === id)
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

// 记录静态域 ID，用于刷新时区分动态域
const STATIC_DOMAIN_IDS = new Set(DOMAINS.map(d => d.id))
const loadingDomains = ref(false)

async function loadDynamicDomains() {
  loadingDomains.value = true
  try {
    const res = await fetchDynamicDomains()
    const dynamicDomains = res.domains || []

    // 先移除上一批动态域（保留静态域），静态域始终在数组前段
    DOMAINS.splice(STATIC_DOMAIN_IDS.size)

    for (const dd of dynamicDomains) {
      // 跳过与静态域 ID 冲突的
      if (STATIC_DOMAIN_IDS.has(dd.id) || STATIC_DOMAIN_IDS.has(dd.skillId)) continue
      const domainDef: DomainDef & { module?: string } = {
        id:            dd.id,
        label:         dd.label,
        icon:          dd.icon,
        color:         dd.color,
        status:        'active',
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
      DOMAINS.push(domainDef)
      initDomainFormData(domainDef)
      STATIC_DEFAULT_FIELDS[domainDef.id] = JSON.parse(JSON.stringify(domainDef.fields))
      STATIC_DEFAULT_RELATED_SKILLS[domainDef.id] = [...domainDef.relatedSkills]
    }
  } catch {
    // 动态域加载失败不影响静态域功能
  } finally {
    loadingDomains.value = false
  }
}

onMounted(async () => {
  layoutsReady.value = false
  await loadAdaptLayouts({ showError: true })
  await loadDynamicDomains()
  // 动态域加载后再合并一次 manifest（成功则静默刷新，避免重复弹错）
  await loadAdaptLayouts({ showError: false })
  layoutsReady.value = true
})

// ─────────────────────────────────────────────────────────────────────────────
// Agent 自动适配
// ─────────────────────────────────────────────────────────────────────────────
function buildAgentRunPayload() {
  const d = activeDomain.value
  return {
    domain_id: activeDomainId.value,
    domain_label: d.label,
    module: mapDomainToModule(activeDomainId.value),
    related_skills: d.relatedSkills,
    form_data: { ...currentFormData.value },
    form_fields: formFieldsForAgent.value,
    user_notes: currentFormData.value.user_notes || undefined,
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
  if (!isComplete.value) {
    message.warning('请先完成当前域所需的全部表单参数')
    return
  }
  if (!activeDomain.value.relatedSkills.length) {
    message.warning('请至少配置一个关联 Skill（可在「编辑布局」中设置）')
    return
  }

  agentLaunching.value = true
  monitorMode.value = 'agent'
  taskStatus.value = 'starting'
  launchedTaskId.value = null
  showMonitor.value = true
  startTime.value = Date.now()

  try {
    tasksStore.ensureSocket()
    const data = await startAdaptAgentRun(buildAgentRunPayload())
    const tid = data.task_id
    if (tid) {
      launchedTaskId.value = tid
      message.success(`Agent 任务已启动: ${tid}`)
    }
  } catch (err) {
    taskStatus.value = 'FAILED'
    message.error(`Agent 启动失败: ${(err as Error).message}`)
  } finally {
    agentLaunching.value = false
  }
}

function backToForm() {
  showMonitor.value = false
  monitorMode.value = null
  // 保留 launchedTaskId，以便用户再次点击"查看进度"
}

// ─────────────────────────────────────────────────────────────────────────────
// 事件流工具函数
// ─────────────────────────────────────────────────────────────────────────────
function eventColor(type: string): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (type.endsWith('.failed'))     return 'error'
  if (type.endsWith('.completed'))  return 'success'
  if (type.endsWith('.correction')) return 'warning'
  return 'info'
}

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
  <div class="adapt-root">

    <!-- ====== 左侧导航 ====== -->
    <aside class="adapt-nav">
      <div class="nav-header">
        <div class="nav-title-row">
          <div class="nav-title">AI 适配调试</div>
          <button
            class="nav-refresh-btn"
            :class="{ spinning: loadingDomains }"
            title="刷新域列表（创建新技能后点击）"
            @click="loadDynamicDomains"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
          </button>
        </div>
        <div class="nav-sub">选择适配域开始</div>
      </div>

      <div class="nav-list">
        <button
          v-for="domain in DOMAINS"
          :key="domain.id"
          class="nav-btn"
          :class="{ active: activeDomainId === domain.id }"
          @click="selectDomain(domain.id)"
        >
          <span class="nav-icon-badge" :style="{ background: domain.color }">{{ domain.icon }}</span>
          <span class="nav-label">{{ domain.label }}</span>
          <span class="nav-dot" :class="`dot-${domain.status}`" />
        </button>
      </div>

      <div class="nav-footer">
        <div class="nf-label">总进度</div>
        <div class="nf-pct">{{ overallPercent }}%</div>
        <NProgress
          :percentage="overallPercent"
          :show-indicator="false"
          :height="4"
          color="#388bfd"
        />
        <div class="nf-detail">{{ completedDomains }} / {{ DOMAINS.length }} 域完成</div>
      </div>
    </aside>

    <!-- ====== 主内容区 ====== -->
    <div class="adapt-body" :class="{ 'is-monitor': showMonitor }">

      <!-- ───────── 表单阶段 ───────── -->
      <template v-if="!showMonitor">

        <!-- 域标题行 -->
        <div class="domain-head domain-head-first">
          <div class="dh-left">
            <div class="dh-badge" :style="{ background: activeDomain.color }">{{ activeDomain.icon }}</div>
            <div>
              <div class="dh-name">{{ activeDomain.label }}</div>
              <div class="dh-sub">
                <template v-if="requiredCount === 0">参考填写，无强制必填项</template>
                <template v-else>必填项 {{ filledCount }} / {{ requiredCount }} 已完成</template>
              </div>
            </div>
          </div>
          <span v-if="isComplete" class="status-badge ok">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            前置条件完整
          </span>
          <span v-else class="status-badge warn">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            请完成必填项
          </span>
          <div class="dh-actions">
            <NButton
              v-if="!layoutEditMode"
              size="small"
              secondary
              @click="enterLayoutEdit"
            >
              编辑布局
            </NButton>
            <NTag v-if="layoutSyncMeta?.cloud_sync_enabled" size="tiny" type="info">云端同步已启用</NTag>
            <span v-if="layoutManifestPath" class="layout-manifest-hint" :title="layoutManifestPath">本地配置已加载</span>
          </div>
        </div>

        <NSpin v-if="!layoutsReady" size="small" style="margin: 24px 0;">正在加载域配置…</NSpin>

        <template v-else>
        <!-- 前置条件表单 -->
        <div v-if="activeDomainId === 'modem' || activeDomainId === 'comm-framework'" class="modem-skill-hint">
          <template v-if="activeDomainId === 'modem'">
            以下字段来自 <code>MODEM_P1_Adapt</code> SKILL.md 的必填输入；填完后可用「Agent 自动适配」由桥接 Agent 按 Skill SOP 执行。
          </template>
          <template v-else>
            以下字段来自 <code>comm-framework-agent-test</code> 测试 Skill 输入；点击「Agent 自动适配」后将按 Skill 分步骤在 PRJ Path 下创建并写入测试文件。
          </template>
        </div>
        <!-- 布局编辑模式 -->
        <div v-if="layoutEditMode" class="form-card layout-editor-card">
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
            <div class="lfr-main">
              <NInput v-model:value="field.label" size="small" placeholder="显示标签" />
              <code class="lfr-name">{{ field.name }}</code>
              <NSelect
                v-model:value="field.type"
                size="small"
                :options="[
                  { label: '文本', value: 'text' },
                  { label: '多行文本', value: 'textarea' },
                  { label: '下拉选择', value: 'select' },
                ]"
                style="width: 120px;"
              />
              <label class="lfr-req">
                <NSwitch v-model:value="field.required" size="small" />
                <span>必填</span>
              </label>
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
        <div v-else class="form-card">
          <div class="form-grid">
            <div
              v-for="field in activeDomain.fields"
              :key="activeDomainId + '-' + field.name"
              class="field-item"
            >
              <label class="field-label">
                {{ field.label }}
                <span v-if="field.required" class="req">*</span>
              </label>

              <NSelect
                v-if="field.type === 'select'"
                :value="getFieldValue(field.name)"
                :options="field.options"
                :placeholder="field.placeholder || '请选择'"
                clearable
                @update:value="v => setFieldValue(field.name, v ?? '')"
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
        </div>

        <!-- 关联 Skills（查看模式） -->
        <div v-if="!layoutEditMode" class="skills-row">
          <span class="skills-title">关联 Skills</span>
          <NTag
            v-for="(skill, sIdx) in activeDomain.relatedSkills"
            :key="skill"
            class="skill-tag"
            size="small"
            :type="sIdx === 0 ? 'primary' : 'default'"
            @click="openSkill(skill)"
          >
            {{ sIdx === 0 ? '主控 · ' : '' }}{{ skill }}
          </NTag>
        </div>

        <!-- 操作按钮 -->
        <div class="action-row">
          <NButton
            size="large"
            type="primary"
            :disabled="layoutEditMode || !isComplete || !activeDomain.relatedSkills.length"
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
          <!-- 如果已有进行中/完成的任务，显示"查看进度"快捷按钮 -->
          <NButton
            v-if="launchedTaskId"
            size="large"
            secondary
            @click="showMonitor = true"
          >
            <template #icon>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </template>
            查看执行进度
            <NTag size="tiny" :type="statusTagType" style="margin-left:6px;">{{ taskStatus }}</NTag>
          </NButton>
        </div>
        </template>

      </template>

      <!-- ───────── 监控阶段 ───────── -->
      <template v-else>

        <!-- 监控顶栏 -->
        <div class="monitor-bar">
          <div class="mb-left">
            <button class="mb-back" @click="backToForm">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
              返回表单
            </button>
            <span class="mb-sep" />
            <span class="mb-domain-badge" :style="{ background: activeDomain.color }">{{ activeDomain.icon }}</span>
            <span class="mb-title">
              {{ activeDomain.label }} — Agent 自动适配
            </span>
          </div>
          <div class="mb-right">
            <code v-if="launchedTaskId" class="mb-taskid">{{ launchedTaskId }}</code>
            <NTag size="small" :type="statusTagType" class="mb-status">
              <template v-if="isRunning">
                <span class="pulse-dot" />
              </template>
              {{ taskStatus || 'starting' }}
            </NTag>
            <NButton size="small" @click="router.push({ name: 'tahp.tasks' })">任务列表</NButton>
          </div>
        </div>

        <!-- ① 启动中（还未拿到 task_id） -->
        <div v-if="agentLaunching && !launchedTaskId" class="monitor-state">
          <NSpin size="large" />
          <p class="ms-hint">正在启动 Agent 自动适配，请稍候...</p>
          <p class="ms-sub">Agent Bridge 连接中</p>
        </div>

        <!-- ② 启动失败且无事件 -->
        <div
          v-else-if="taskStatus === 'FAILED' && !stream.length"
          class="monitor-state monitor-error"
        >
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#d03050" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p class="ms-hint">Agent 任务启动失败</p>
          <p class="ms-sub">请检查 Agent Bridge 配置与关联 Skill 是否可用</p>
          <div style="display:flex;gap:8px;margin-top:4px;">
            <NButton type="primary" @click="backToForm">返回重新配置</NButton>
            <NButton @click="launchAgentAdapt" :loading="agentLaunching">重试</NButton>
          </div>
        </div>

        <!-- ③ 已提交但等待第一条事件 -->
        <div
          v-else-if="!stream.length && !agentLaunching"
          class="monitor-state"
        >
          <NSpin size="medium" />
          <p class="ms-hint">任务已提交，等待 Agent 开始执行...</p>
          <code v-if="launchedTaskId" class="ms-taskid">{{ launchedTaskId }}</code>
        </div>

        <!-- ④ 主视图 -->
        <div v-else ref="eventListEl" class="llm-monitor-layout" :class="{ 'agent-monitor-layout': monitorMode === 'agent' }">

          <!-- Agent 模式：Skill / 规划 / 文件变更 面板 -->
          <div v-if="monitorMode === 'agent'" class="agent-side-panels">
            <div class="asp-card">
              <div class="asp-title">任务规划 / 推理</div>
              <div v-if="!agentPlanEvents.length" class="asp-empty">等待 Agent 输出规划...</div>
              <pre v-for="(ev, i) in agentPlanEvents.slice(-8)" :key="'plan-' + i" class="asp-item">{{ formatPayload(ev.payload) }}</pre>
            </div>
            <div class="asp-card">
              <div class="asp-title">Skill / 工具调用</div>
              <div v-if="!agentSkillEvents.length" class="asp-empty">尚未调用工具</div>
              <div v-for="(ev, i) in agentSkillEvents" :key="'sk-' + i" class="asp-skill-row">
                <NTag size="tiny" type="info">{{ ev.payload?.skill_id || 'tool' }}</NTag>
                <span class="asp-skill-msg">{{ ev.payload?.message || formatPayload(ev.payload) }}</span>
              </div>
            </div>
            <div class="asp-card">
              <div class="asp-title">文件修改</div>
              <div v-if="!agentFileEvents.length" class="asp-empty">暂无检测到的写文件操作</div>
              <div v-for="(ev, i) in agentFileEvents" :key="'fc-' + i" class="asp-file-row">
                <code>{{ ev.payload?.path }}</code>
                <span class="asp-file-meta">{{ ev.payload?.tool }} · {{ ev.payload?.status || 'modify' }}</span>
              </div>
            </div>
          </div>

          <!-- 左：AI 分析内容（流式渲染）-->
          <div class="llm-response-panel">
            <div class="lrp-header">
              <span class="lrp-title">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Agent 执行输出
              </span>
              <NTag v-if="isRunning" size="tiny" type="info">
                <span class="pulse-dot" />
                流式输出中
              </NTag>
              <NTag v-else-if="taskStatus === 'COMPLETED'" size="tiny" type="success">已完成</NTag>
            </div>
            <pre v-if="llmResponse" class="lrp-content">{{ llmResponse }}</pre>
            <div v-else-if="isRunning" class="lrp-waiting">
              <NSpin size="small" />
              <span style="margin-left:8px;color:#888;">大模型思考中...</span>
            </div>
          </div>

          <!-- 右：执行步骤 -->
          <div class="llm-steps-panel">
            <div class="lsp-title">执行步骤</div>
            <div
              v-for="(ev, idx) in structuredEvents"
              :key="idx"
              class="ev-row"
              :class="`ev-${eventColor(ev.type)}`"
            >
              <div class="ev-head">
                <NTag size="tiny" :type="eventColor(ev.type)" class="ev-type">{{ ev.type }}</NTag>
                <span class="ev-ts">{{ formatTs(ev.ts) }}</span>
              </div>
              <pre class="ev-body">{{ formatPayload(ev.payload) }}</pre>
            </div>
            <div style="height:8px;" />
          </div>
        </div>

        <!-- 完成 / 失败 横幅（叠加在流底部） -->
        <div v-if="taskStatus === 'COMPLETED'" class="result-banner result-ok">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          适配任务已完成 · 共 {{ stream.length }} 个执行步骤
          <NButton size="small" type="primary" style="margin-left:12px;" @click="router.push({ name: 'tahp.reports', query: launchedTaskId ? { task_id: launchedTaskId } : {} })">查看报告</NButton>
          <NButton size="small" style="margin-left:6px;" @click="backToForm">返回表单</NButton>
        </div>
        <div v-else-if="taskStatus === 'FAILED' && stream.length" class="result-banner result-err">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          任务执行失败 · 请查看上方错误事件
          <NButton size="small" type="warning" style="margin-left:12px;" @click="backToForm">重新配置</NButton>
          <NButton size="small" style="margin-left:6px;" :loading="agentLaunching" @click="launchAgentAdapt">重试</NButton>
        </div>

      </template>

    </div>

    <!-- ====== 右侧统计栏 ====== -->
    <aside class="adapt-stats">
      <div class="stat-card">
        <div class="sc-title">适配进度</div>
        <div class="sc-row"><span class="sc-k">总域数</span><span class="sc-v">{{ DOMAINS.length }}</span></div>
        <div class="sc-row"><span class="sc-k">已完成</span><span class="sc-v done">{{ completedDomains }}</span></div>
        <div class="sc-row"><span class="sc-k">进行中</span><span class="sc-v active">{{ DOMAINS.filter(d => d.status === "active").length }}</span></div>
      </div>

      <!-- 当有任务运行时，显示任务快照 -->
      <div v-if="launchedTaskId" class="stat-card task-snap">
        <div class="sc-title">当前任务</div>
        <div class="sc-row">
          <span class="sc-k">状态</span>
          <NTag size="tiny" :type="statusTagType">{{ taskStatus || '-' }}</NTag>
        </div>
        <div class="sc-row">
          <span class="sc-k">事件数</span>
          <span class="sc-v">{{ stream.length }}</span>
        </div>
        <div class="sc-row-id">
          <span class="sc-k">Task ID</span>
          <code class="sc-tid">{{ launchedTaskId }}</code>
        </div>
        <NButton
          v-if="!showMonitor"
          size="tiny"
          type="primary"
          style="margin-top:8px;width:100%;"
          @click="showMonitor = true"
        >查看执行详情</NButton>
      </div>

      <div class="stat-card">
        <div class="sc-title">域列表</div>
        <div
          v-for="d in DOMAINS"
          :key="d.id"
          class="domain-item"
          :class="{ 'domain-item-active': d.id === activeDomainId }"
          @click="selectDomain(d.id)"
        >
          <span class="di-badge" :style="{ background: d.color }">{{ d.icon }}</span>
          <span class="di-label">{{ d.label }}</span>
          <span class="di-dot" :class="`dot-${d.status}`" />
        </div>
      </div>
    </aside>

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
          <NInput v-model:value="newFieldDraft.placeholder" placeholder="可选" />
        </NFormItem>
        <NFormItem label="必填">
          <NSwitch v-model:value="newFieldDraft.required" />
        </NFormItem>
        <NFormItem v-if="newFieldDraft.type === 'select'" label="下拉选项">
          <NInput
            v-model:value="newFieldDraft.optionsText"
            type="textarea"
            placeholder="每行一个，格式 label:value&#10;如 GOODIX:goodix"
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

  </div>
</template>

<style scoped lang="scss">
@use "@/styles/variables" as *;

.adapt-root {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: $bg-primary;
  overflow: hidden;
}

// ── 左侧导航 ────────────────────────────────────────────────────────────────
.adapt-nav {
  width: 210px;
  flex-shrink: 0;
  border-right: 1px solid $border-color;
  background: $bg-secondary;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.nav-header {
  padding: 16px 14px 12px;
  border-bottom: 1px solid $border-color;
  flex-shrink: 0;
}
.nav-title-row { display: flex; align-items: center; justify-content: space-between; }
.nav-title { font-size: 13px; font-weight: 700; color: $text-primary; }
.nav-sub   { font-size: 11px; color: $text-muted; margin-top: 2px; }
.nav-refresh-btn {
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 4px; border: none; cursor: pointer;
  background: transparent; color: $text-muted; padding: 0;
  transition: background .15s, color .15s;
}
.nav-refresh-btn:hover { background: $border-color; color: $text-primary; }
@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
.nav-refresh-btn.spinning svg { animation: spin .6s linear infinite; }

.nav-list {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  overflow-y: auto;
}

.nav-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: $radius-md;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: all $transition-fast;
  color: $text-secondary;

  &:hover {
    background: rgba(56,139,253,0.08);
    color: $text-primary;
  }
  &.active {
    background: rgba(56,139,253,0.12);
    border-color: rgba(56,139,253,0.3);
    color: var(--accent-info);
  }
}
.nav-icon-badge {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  font-size: 9px;
  font-weight: 700;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  letter-spacing: -0.5px;
}
.nav-label {
  flex: 1;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nav-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  &.dot-done    { background: #10b981; }
  &.dot-active  { background: #388bfd; animation: blink 1.5s infinite; }
  &.dot-warn    { background: #f59e0b; }
  &.dot-pending { background: $border-color; }
}
@keyframes blink { 0%,100% { opacity:1 } 50% { opacity:0.4 } }

.nav-footer {
  padding: 12px;
  border-top: 1px solid $border-color;
  background: rgba(56,139,253,0.05);
  flex-shrink: 0;
}
.nf-label  { font-size: 10px; font-weight: 600; color: $text-muted; text-transform: uppercase; }
.nf-pct    { font-size: 22px; font-weight: 700; color: var(--accent-info); margin: 4px 0 6px; }
.nf-detail { font-size: 10px; color: $text-muted; margin-top: 6px; }

// ── 主内容 ──────────────────────────────────────────────────────────────────
.adapt-body {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 0 24px 32px;
  display: flex;
  flex-direction: column;

  // 监控模式：禁止主容器滚动，让事件流自己滚
  &.is-monitor {
    overflow: hidden;
    padding-bottom: 0;
  }
}

// ── 表单区 ─────────────────────────────────────────────────────────────────
.domain-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0 14px;
  flex-shrink: 0;

  &.domain-head-first {
    margin-top: 16px;
  }
}
.dh-left    { display: flex; align-items: center; gap: 12px; }
.dh-actions { display: flex; align-items: center; gap: 8px; margin-left: 12px; }
.dh-badge  {
  width: 42px; height: 42px; border-radius: 10px;
  font-size: 11px; font-weight: 800; color: #fff;
  display: flex; align-items: center; justify-content: center;
  letter-spacing: -0.5px;
}
.dh-name   { font-size: 18px; font-weight: 700; color: $text-primary; }
.dh-sub    { font-size: 11px; color: $text-muted; margin-top: 3px; }

.status-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; border: 1px solid;
  &.ok   { background: rgba(16,185,129,.1);  color: #10b981; border-color: rgba(16,185,129,.3); }
  &.warn { background: rgba(245,158,11,.1);  color: #f59e0b; border-color: rgba(245,158,11,.3); }
}

.modem-skill-hint {
  font-size: 12px;
  color: $text-muted;
  margin-bottom: 10px;
  line-height: 1.5;
  code {
    font-size: 11px;
    color: var(--accent-info, #388bfd);
  }
}

.form-card {
  background: $bg-card;
  border: 1px solid $border-color;
  border-radius: $radius-lg;
  padding: 20px;
  margin-bottom: 20px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.field-item  { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 600; color: $text-primary; display: flex; align-items: center; gap: 3px; }
.req         { color: #ef4444; }

.skills-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-bottom: 20px;
}
.skills-title { font-size: 12px; font-weight: 700; color: $text-primary; flex-shrink: 0; }
.skill-tag {
  cursor: pointer; font-size: 11px;
  background: rgba(56,139,253,.08) !important;
  border-color: rgba(56,139,253,.25) !important;
  color: var(--accent-info) !important;
  &:hover { background: rgba(56,139,253,.15) !important; }
}

.action-row { display: flex; gap: 12px; flex-wrap: wrap; }

.layout-editor-card { display: flex; flex-direction: column; gap: 10px; }
.layout-editor-head { display: flex; flex-direction: column; gap: 4px; margin-bottom: 4px; }
.layout-editor-title { font-size: 13px; font-weight: 700; color: $text-primary; }
.layout-editor-hint { font-size: 11px; color: $text-muted; line-height: 1.45; }
.layout-editor-empty { font-size: 12px; color: $text-muted; padding: 12px 0; }
.layout-field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  background: rgba(0, 0, 0, 0.02);
}
.lfr-main { display: flex; align-items: center; gap: 8px; flex: 1; flex-wrap: wrap; }
.lfr-name {
  font-size: 10px;
  color: $text-muted;
  font-family: $font-code;
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}
.lfr-req { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: $text-muted; }
.layout-editor-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.layout-skills-editor {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 10px 12px; border-radius: 8px; background: rgba(255,255,255,0.03);
  border: 1px dashed rgba(255,255,255,0.08);
}
.layout-skills-label { font-size: 12px; font-weight: 600; color: $text-secondary; min-width: 72px; }
.layout-skills-tags { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.layout-manifest-hint { font-size: 10px; color: $text-muted; margin-left: 4px; }
.skill-search-list {
  max-height: 360px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px;
}
.skill-search-empty { font-size: 12px; color: $text-muted; padding: 16px 4px; text-align: center; }
.skill-search-item {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  width: 100%; text-align: left; padding: 10px 12px; border-radius: 8px;
  border: 1px solid transparent; background: rgba(255,255,255,0.02); cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  &:hover { border-color: rgba(56,139,253,0.35); background: rgba(56,139,253,0.06); }
}
.ssi-name { font-size: 13px; font-weight: 600; color: $text-primary; }
.ssi-group { font-size: 10px; color: #388bfd; }
.ssi-desc {
  font-size: 11px; color: $text-muted; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

// ── 监控顶栏 ────────────────────────────────────────────────────────────────
.monitor-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0 10px;
  border-bottom: 1px solid $border-color;
  margin-top: 16px;
  flex-shrink: 0;
  gap: 12px;
}

.mb-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.mb-back {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: $radius-md;
  border: 1px solid $border-color;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: $text-secondary;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all $transition-fast;

  &:hover {
    background: rgba(56,139,253,.08);
    color: var(--accent-info);
    border-color: rgba(56,139,253,.3);
  }
}

.mb-sep {
  width: 1px; height: 18px;
  background: $border-color;
  flex-shrink: 0;
}

.mb-domain-badge {
  width: 24px; height: 24px; border-radius: 6px;
  font-size: 9px; font-weight: 700; color: #fff;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; letter-spacing: -0.5px;
}

.mb-title {
  font-size: 14px;
  font-weight: 700;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mb-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.mb-taskid {
  font-size: 10px;
  font-family: $font-code;
  background: rgba(0,0,0,.08);
  padding: 3px 7px;
  border-radius: 4px;
  color: $text-muted;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mb-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.pulse-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor;
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.7); }
}

// ── 监控状态占位 ─────────────────────────────────────────────────────────────
.monitor-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: $text-secondary;
  text-align: center;

  &.monitor-error { color: #d03050; }
}
.ms-hint    { font-size: 14px; margin: 0; font-weight: 500; }
.ms-sub     { font-size: 12px; color: $text-muted; margin: 0; }
.ms-taskid  {
  font-size: 11px; font-family: $font-code;
  background: rgba(0,0,0,.06); padding: 3px 8px; border-radius: 4px;
  color: $text-muted;
}

// ── 事件流 ───────────────────────────────────────────────────────────────────
.event-stream {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 0 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;

  // 细滚动条
  &::-webkit-scrollbar { width: 5px; }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb { background: $border-color; border-radius: 3px; }
}

.ev-row {
  padding: 8px 12px;
  border-radius: 6px;
  background: $bg-card;
  border: 1px solid $border-color;
  border-left: 3px solid transparent;
  flex-shrink: 0;
  transition: background $transition-fast;

  &.ev-success { border-left-color: #10b981; }
  &.ev-error   { border-left-color: #d03050; background: rgba(208,48,80,.04); border-color: rgba(208,48,80,.15); }
  &.ev-warning { border-left-color: #f59e0b; background: rgba(245,158,11,.04); }
  &.ev-info    { border-left-color: var(--accent-info, #388bfd); }
}

.ev-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}

.ev-type { font-family: $font-code; }

.ev-ts {
  color: $text-muted;
  font-size: 11px;
  font-family: $font-code;
}

.ev-idx {
  margin-left: auto;
  font-size: 10px;
  color: $text-muted;
  font-family: $font-code;
}

.ev-body {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: $text-primary;
  line-height: 1.55;
  font-family: $font-code;
}

// ── 完成/失败横幅 ────────────────────────────────────────────────────────────
.result-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: $radius-md;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 8px;
  margin-bottom: 8px;

  &.result-ok {
    background: rgba(16,185,129,.08);
    border: 1px solid rgba(16,185,129,.25);
    color: #10b981;
  }
  &.result-err {
    background: rgba(208,48,80,.06);
    border: 1px solid rgba(208,48,80,.2);
    color: #d03050;
  }
}

// ── 右侧统计 ─────────────────────────────────────────────────────────────────
.adapt-stats {
  width: 220px;
  flex-shrink: 0;
  border-left: 1px solid $border-color;
  background: $bg-secondary;
  overflow-y: auto;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.stat-card {
  background: $bg-card; border: 1px solid $border-color;
  border-radius: $radius-md; padding: 13px;

  &.task-snap { border-color: rgba(56,139,253,.3); background: rgba(56,139,253,.04); }
}
.sc-title { font-size: 11px; font-weight: 700; color: $text-primary; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
.sc-row   { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 12px; }
.sc-k     { color: $text-muted; }
.sc-v     { font-weight: 700; color: $text-primary; }
.sc-v.done   { color: #10b981; }
.sc-v.active { color: var(--accent-info); }

.sc-row-id {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 4px;
  font-size: 11px;
}
.sc-tid {
  font-family: $font-code;
  font-size: 10px;
  word-break: break-all;
  color: $text-muted;
  background: rgba(0,0,0,.06);
  padding: 2px 5px;
  border-radius: 3px;
}

.domain-item {
  display: flex; align-items: center; gap: 7px;
  padding: 6px; border-radius: $radius-sm; cursor: pointer;
  transition: background $transition-fast;
  &:hover { background: rgba(56,139,253,.06); }
  &.domain-item-active { background: rgba(56,139,253,.1); }
}
.di-badge {
  width: 20px; height: 20px; border-radius: 4px;
  font-size: 8px; font-weight: 700; color: #fff;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; letter-spacing: -0.5px;
}
.di-label {
  flex: 1; font-size: 11px; font-weight: 600; color: $text-secondary;
  .domain-item-active & { color: var(--accent-info); }
}
.di-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  &.dot-done    { background: #10b981; }
  &.dot-active  { background: #388bfd; }
  &.dot-warn    { background: #f59e0b; }
  &.dot-pending { background: $border-color; }
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
  color: $text-muted;
  line-height: 1.5;
}
.prompt-preview-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: $text-muted;
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
  color: $text-muted;
  font-family: $font-code;
}
.prompt-preview-content {
  margin: 0;
  max-height: 52vh;
  overflow: auto;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid $border-color;
  border-radius: $radius-md;
  font-size: 12px;
  font-family: $font-code;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

// ── LLM 双栏监控布局 ─────────────────────────────────────────────────────────
.llm-monitor-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 0;
  overflow: hidden;
}

.agent-monitor-layout {
  grid-template-columns: 220px 1fr 260px;
}

.agent-side-panels {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 8px;
  border-right: 1px solid $border-color;
}

.asp-card {
  background: $bg-card;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  padding: 8px 10px;
  flex-shrink: 0;
}

.asp-title {
  font-size: 11px;
  font-weight: 700;
  color: $text-primary;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.asp-empty {
  font-size: 11px;
  color: $text-muted;
}

.asp-item {
  margin: 0 0 6px;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: $text-primary;
  font-family: $font-code;
}

.asp-skill-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px dashed $border-color;
  &:last-child { border-bottom: none; margin-bottom: 0; }
}

.asp-skill-msg {
  font-size: 11px;
  color: $text-muted;
  line-height: 1.4;
}

.asp-file-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
  code {
    font-size: 11px;
    word-break: break-all;
    color: var(--accent-info, #388bfd);
  }
}

.asp-file-meta {
  font-size: 10px;
  color: $text-muted;
}

.llm-response-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid $border-color;
  padding: 12px 16px 12px 0;
}

.lrp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.lrp-title {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  color: $text-primary;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.lrp-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin: 0;
  padding: 12px 14px;
  background: rgba(0,0,0,.025);
  border: 1px solid $border-color;
  border-radius: $radius-md;
  font-size: 13px;
  font-family: $font-code;
  line-height: 1.65;
  color: $text-primary;
  white-space: pre-wrap;
  word-break: break-word;

  &::-webkit-scrollbar { width: 5px; }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb { background: $border-color; border-radius: 3px; }
}

.lrp-waiting {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: $text-muted;
  font-size: 13px;
}

.llm-steps-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 12px 0 12px 16px;
  overflow-y: auto;

  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb { background: $border-color; border-radius: 3px; }
}

.lsp-title {
  font-size: 11px;
  font-weight: 700;
  color: $text-muted;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  flex-shrink: 0;
}
</style>
