<script setup lang="ts">
import { ref, computed, reactive, watch, nextTick, onMounted } from 'vue'
import { NButton, NSelect, NInput, NProgress, NTag, NSpin, NModal, NTabs, NTabPane, NForm, NFormItem, NSwitch, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import ModelProviderBanner from '@/components/tahp/ModelProviderBanner.vue'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import type { TahpModule } from '@/constants/tahp-modules'
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
    relatedSkills: ['tp-adapt-bringup'],
    fields: [
      { name: 'debug_project', label: '调试项目名', type: 'text', required: true, placeholder: '如 X6876_H786' },
      { name: 'project_platform', label: '项目平台', type: 'text', required: true, placeholder: '如 MT6878' },
      { name: 'ic_vendor', label: 'IC厂商', type: 'text', required: true, placeholder: '如 FocalTech / Goodix' },
      { name: 'ic_model', label: 'IC型号', type: 'text', required: true, placeholder: '如 FT8006M' },
      { name: 'spi_gpio', label: 'SPI口及GPIO号', type: 'text', required: true, placeholder: 'SPI 口与对应 GPIO 配置' },
      { name: 'tp_int_rst_gpio', label: 'TP int、rst gpio脚', type: 'text', required: true, placeholder: 'INT / RST GPIO 编号' },
      { name: 'vddi_avdd_power', label: 'vddi、avdd的LDO或GPIO', type: 'text', required: true, placeholder: '供电 LDO 或 GPIO 配置' },
      { name: 'old_tp_firmware', label: '升级前TP固件文件', type: 'text', required: true, placeholder: '升级前 TP 固件绝对路径' },
      { name: 'old_dts', label: '升级前dts文件', type: 'text', required: true, placeholder: '升级前 DTS 文件路径' },
      { name: 'ref_project_branch', label: '同分支参考项目', type: 'text', required: true, placeholder: '同分支参考项目名或路径' },
    ],
  },
  {
    id: 'vib',
    label: '振动马达',
    icon: 'VIB',
    color: '#f78166',
    status: 'pending',
    relatedSkills: ['vib-adapt-lra-driver', 'vib-adapt-rotor-driver'],
    fields: [
      { name: 'motor_type', label: '马达类型', type: 'text', required: true, placeholder: 'LRA / ERM' },
      { name: 'ic_vendor', label: '控制IC厂商', type: 'text', required: true, placeholder: '如 Awinic / AAC' },
      { name: 'ic_model', label: '控制IC型号', type: 'text', required: true, placeholder: '如 AW8692x' },
      { name: 'motor_model', label: '马达型号', type: 'text', required: true, placeholder: '马达型号' },
      { name: 'i2c_bus', label: 'i2c号', type: 'text', required: true, placeholder: '如 7' },
      { name: 'i2c_addr', label: 'i2c通讯地址', type: 'text', required: true, placeholder: '如 0x5A' },
      { name: 'irq_gpio', label: '马达中断gpio', type: 'text', required: true, placeholder: 'IRQ GPIO' },
      { name: 'rst_gpio', label: '复位gpio', type: 'text', required: true, placeholder: 'RST GPIO' },
      { name: 'old_motor_firmware', label: '升级前的马达固件', type: 'text', required: true, placeholder: '升级前马达固件路径' },
      { name: 'old_dts_config', label: '升级前的dts参数配置', type: 'text', required: true, placeholder: '升级前 DTS 参数文件或路径' },
    ],
  },
  {
    id: 'lcm',
    label: 'LCM',
    icon: 'LCM',
    color: '#58a6ff',
    status: 'pending',
    relatedSkills: ['display_analyser'],
    fields: [
      { name: 'PROJECT_NAME', label: 'PROJECT_NAME（项目名称）', type: 'text', required: true, placeholder: '项目名称' },
      { name: 'PLATFORM_NAME', label: 'PLATFORM_NAME（平台名称）', type: 'text', required: true, placeholder: '平台名称' },
      { name: 'BOARD_NAME', label: 'BOARD_NAME（主板名称）', type: 'text', required: true, placeholder: '主板名称' },
      { name: 'PANEL_TYPE', label: 'PANEL_TYPE（屏幕类型）', type: 'text', required: true, placeholder: '屏幕类型' },
      { name: 'KERNEL_VERSION_OLD', label: 'KERNEL_VERSION_OLD（旧项目内核版本）', type: 'text', required: true, placeholder: '如 kernel-5.15' },
      { name: 'KERNEL_VERSION_NEW', label: 'KERNEL_VERSION_NEW（新项目内核版本）', type: 'text', required: true, placeholder: '如 kernel-6.1' },
      { name: 'PROJ_FILE_OLD', label: 'PROJ_FILE_OLD（旧项目代码目录）', type: 'text', required: true, placeholder: '旧项目代码绝对路径' },
      { name: 'PROJ_FILE_NEW', label: 'PROJ_FILE_NEW（新项目代码目录）', type: 'text', required: true, placeholder: '新项目代码绝对路径' },
      { name: 'AUTHOR_NAME', label: 'AUTHOR_NAME（作者姓名）', type: 'text', required: true, placeholder: '作者姓名' },
      { name: 'DATE', label: 'DATE（日期）', type: 'text', required: true, placeholder: '如 2026-06-08' },
    ],
  },
  {
    id: 'fp',
    label: '指纹',
    icon: 'FP',
    color: '#3fb950',
    status: 'pending',
    relatedSkills: ['drv-fp-adapt'],
    fields: [
      { name: 'debug_project', label: '调试项目名', type: 'text', required: true, placeholder: '如 LJ8k' },
      { name: 'project_platform', label: '项目平台', type: 'text', required: true, placeholder: '如 MT6878' },
      { name: 'kernel_version', label: 'kernel版本', type: 'text', required: true, placeholder: '如 kernel-6.1' },
      { name: 'fp_vendor', label: '指纹厂商', type: 'text', required: true, placeholder: '如 goodix' },
      { name: 'fp_ic_model', label: '指纹IC型号', type: 'text', required: true, placeholder: '如 GW9598' },
      { name: 'code_path_old', label: '升级前代码仓路径', type: 'text', required: true, placeholder: '升级前代码仓绝对路径' },
      { name: 'code_path_new', label: '升级后代码仓路径', type: 'text', required: true, placeholder: '升级后代码仓绝对路径' },
    ],
  },
  {
    id: 'audio',
    label: '音频',
    icon: 'AUD',
    color: '#e3b341',
    status: 'pending',
    relatedSkills: ['DRV_Audio_Adapt'],
    fields: [
      { name: 'vnd_path_old', label: '升级前vnd绝对路径', type: 'text', required: true, placeholder: '升级前 vendor 目录绝对路径' },
      { name: 'vnd_path_new', label: '升级后vnd绝对路径', type: 'text', required: true, placeholder: '升级后 vendor 目录绝对路径' },
      { name: 'upgrade_scenario', label: '升级场景', type: 'text', required: true, placeholder: '12解耦前→16解耦后 / 14解耦前→14解耦后' },
      { name: 'old_build_option', label: '升级前编译选项', type: 'text', required: true, placeholder: '从 spug 查找，如 x6885_h8923_m1' },
      { name: 'sw_config_screenshot', label: '软件配置表截图', type: 'textarea', required: true, placeholder: '声学配置表说明或截图路径（PA型号/SPK个数/SPK PATH/MIC个数/PHONE_MIC_MODE/HEADSET_MIC_MODE/是否TypeC等）' },
    ],
  },
  {
    id: 'charging',
    label: '充电',
    icon: 'CHG',
    color: '#f78166',
    status: 'pending',
    relatedSkills: ['pillar3-customization-input'],
    fields: [
      { name: 'charger_ic_model', label: '【Charger IC】型号', type: 'text', required: true, placeholder: 'Charger IC 型号' },
      { name: 'charger_i2c_bus', label: '【Charger IC】I2C总线号', type: 'text', required: true, placeholder: '如 6' },
      { name: 'charger_i2c_addr', label: '【Charger IC】I2C地址', type: 'text', required: true, placeholder: '如 0x6B' },
      { name: 'charger_irq', label: '【Charger IC】IRQ中断引脚号', type: 'text', required: true, placeholder: 'IRQ GPIO' },
      { name: 'pump_ic_model', label: '【Charge Pump】型号', type: 'text', required: true, placeholder: 'Charge Pump 型号' },
      { name: 'pump_i2c_bus', label: '【Charge Pump】I2C总线号', type: 'text', required: true, placeholder: '如 7' },
      { name: 'pump_i2c_addr', label: '【Charge Pump】I2C地址', type: 'text', required: true, placeholder: '如 0x75' },
      { name: 'pump_irq', label: '【Charge Pump】IRQ中断引脚号', type: 'text', required: true, placeholder: 'IRQ GPIO' },
      { name: 'pump_extra', label: '【Charge Pump】多颗器件补充', type: 'textarea', required: false, placeholder: '如有多颗 Charge Pump，在此补全型号/I2C/IRQ' },
      { name: 'pd_ic_model', label: '【PD IC】型号', type: 'text', required: true, placeholder: 'PD IC 型号' },
      { name: 'pd_i2c_bus', label: '【PD IC】I2C总线号', type: 'text', required: true, placeholder: '如 5' },
      { name: 'pd_i2c_addr', label: '【PD IC】I2C地址', type: 'text', required: true, placeholder: '如 0x24' },
      { name: 'pd_irq', label: '【PD IC】IRQ中断引脚号', type: 'text', required: true, placeholder: 'IRQ GPIO' },
      { name: 'gauge_type', label: '【Gauge】类型', type: 'text', required: true, placeholder: 'Gauge 类型/型号' },
      { name: 'gauge_i2c_bus', label: '【Gauge】I2C总线号', type: 'text', required: true, placeholder: '如 4' },
      { name: 'gauge_i2c_addr', label: '【Gauge】I2C地址', type: 'text', required: true, placeholder: '如 0x55' },
    ],
  },
  {
    id: 'sensor',
    label: 'Sensor',
    icon: 'SNS',
    color: '#a371f7',
    status: 'pending',
    relatedSkills: ['DRV_Sensor_Adapt'],
    fields: [
      { name: 'old_project_path', label: '旧项目完整路径', type: 'text', required: true, placeholder: '旧项目完整绝对路径' },
      { name: 'new_baseline_path', label: '新基线完整路径', type: 'text', required: true, placeholder: '新基线完整绝对路径' },
      { name: 'project_name', label: '项目名', type: 'text', required: true, placeholder: '项目名' },
      { name: 'new_features', label: '具体新增特性', type: 'textarea', required: true, placeholder: '描述本次 Sensor 适配的具体新增特性' },
    ],
  },
  {
    id: 'security',
    label: '安全',
    icon: 'SEC',
    color: '#da3633',
    status: 'pending',
    relatedSkills: ['android-platform-security-upgrade-ai-debug'],
    fields: [
      { name: 'branch_path_old', label: '升级前分支路径', type: 'text', required: true, placeholder: '升级前分支路径（须为非榫卯）' },
      { name: 'branch_path_new', label: '升级后分支路径', type: 'text', required: true, placeholder: '升级后分支路径（须为榫卯）' },
      { name: 'project_name', label: '项目名', type: 'text', required: true, placeholder: '项目名' },
      { name: 'platform_name', label: '平台名', type: 'text', required: true, placeholder: '平台名' },
    ],
  },
  {
    id: 'mini-system',
    label: '小系统',
    icon: 'LK',
    color: '#e3b341',
    status: 'pending',
    relatedSkills: ['KRN_LK_CPU_Ddapt'],
    fields: [
      { name: 'lk2_path_old', label: '升级前lk2路径', type: 'text', required: true, placeholder: '升级前 lk2 绝对路径' },
      { name: 'lk2_path_new', label: '升级后lk2路径', type: 'text', required: true, placeholder: '升级后 lk2 绝对路径' },
      { name: 'project_name', label: '项目名', type: 'text', required: true, placeholder: '项目名' },
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
/** 已下线域 / 测试域，不再从动态技能列表注入 */
const BLOCKED_DYNAMIC_DOMAIN_IDS = new Set(['Test', 'kernel', 'scp', 'aikey'])
const loadingDomains = ref(false)

async function loadDynamicDomains() {
  loadingDomains.value = true
  try {
    const res = await fetchDynamicDomains()
    const dynamicDomains = res.domains || []

    // 先移除上一批动态域（保留静态域），静态域始终在数组前段
    DOMAINS.splice(STATIC_DOMAIN_IDS.size)

    for (const dd of dynamicDomains) {
      // 跳过与静态域 ID 冲突的、或已下线的域
      if (
        STATIC_DOMAIN_IDS.has(dd.id)
        || STATIC_DOMAIN_IDS.has(dd.skillId)
        || BLOCKED_DYNAMIC_DOMAIN_IDS.has(dd.id)
        || BLOCKED_DYNAMIC_DOMAIN_IDS.has(dd.skillId)
      ) continue
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
      tasksStore.trackTask(tid)
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
      subtitle="选择适配域 → 补齐前置参数 → 由 Agent 按 Skill SOP 自动产出补丁与自检报告"
    >
      <template #actions>
        <span v-if="layoutSyncMeta?.cloud_sync_enabled" class="ea-pill-info">云端同步已启用</span>
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm adapt-refresh-btn"
          :class="{ spinning: loadingDomains }"
          title="刷新域列表（创建新技能后点击）"
          @click="loadDynamicDomains"
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
        <span class="adapt-domain-dot" :class="`dot-${domain.status}`" />
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
              <div v-if="activeDomainId === 'modem' || activeDomainId === 'comm-framework'" class="modem-skill-hint">
                <template v-if="activeDomainId === 'modem'">
                  以下字段来自 <code>MODEM_P1_Adapt</code> SKILL.md 的必填输入；填完后可用「Agent 自动适配」由桥接 Agent 按 Skill SOP 执行。
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
              <div v-else>
                <div class="ea-form-grid2">
                  <div
                    v-for="field in activeDomain.fields"
                    :key="activeDomainId + '-' + field.name"
                    class="ea-field"
                    :class="{ 'ea-field-full': field.type === 'textarea' }"
                  >
                    <label>
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
                    @click="showMonitor = true"
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
                <div class="mg-v adapt-stat-active">{{ DOMAINS.filter(d => d.status === 'active').length }}</div>
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
              @click="showMonitor = true"
            >查看执行详情</NButton>
          </EaCard>

          <EaCard>
            <div class="ea-section-title">域列表</div>
            <div class="ea-tasklist">
              <button
                v-for="d in DOMAINS"
                :key="d.id"
                type="button"
                class="ea-task-item"
                :class="{ active: d.id === activeDomainId }"
                @click="selectDomain(d.id)"
              >
                <div class="ti-top">
                  <span class="ea-row" style="gap:8px">
                    <span class="ea-domain-badge" :style="{ background: d.color }">{{ d.icon }}</span>
                    {{ d.label }}
                  </span>
                  <span class="adapt-domain-dot" :class="`dot-${d.status}`" />
                </div>
              </button>
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
            <EaPill :variant="statusTagType === 'success' ? 'ok' : statusTagType === 'error' ? 'err' : statusTagType === 'warning' ? 'warn' : 'info'">
              <span v-if="isRunning" class="ea-dot-live" />
              {{ taskStatus || 'starting' }}
            </EaPill>
            <NButton size="small" @click="router.push({ name: 'tahp.reports' })">报告</NButton>
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
        <div v-else class="ea-monitor adapt-monitor-body" :class="{ 'adapt-monitor-agent': monitorMode === 'agent' }">
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
          </div>

          <!-- Skill / 文件（右侧） -->
          <div v-if="monitorMode === 'agent'" class="adapt-sidebar-col">
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
          <NButton size="small" type="primary" style="margin-left:12px;" @click="router.push({ name: 'tahp.reports', query: launchedTaskId ? { task_id: launchedTaskId } : {} })">查看报告</NButton>
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
@use '@/styles/variables' as *;

.adapt-provider-banner {
  margin-bottom: 4px;
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
  &.dot-active { background: var(--info); animation: ea-blink 1.5s infinite; }
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
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
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
    height: $adapt-output-h;
    min-height: $adapt-output-h;
    max-height: $adapt-output-h;
    overflow-y: auto;
    margin: 0;
  }

  .lrp-waiting {
    height: $adapt-output-h;
    min-height: $adapt-output-h;
    max-height: $adapt-output-h;
    flex: none;
  }
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
</style>
