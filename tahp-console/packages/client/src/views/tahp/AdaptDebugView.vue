<script setup lang="ts">
import { ref, computed, reactive, watch, nextTick, onMounted } from 'vue'
import { NButton, NSelect, NInput, NProgress, NTag, NSpin, NModal, NForm, NFormItem, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import type { TahpModule } from '@/api/tahp/tasks'
import { fetchDynamicDomains } from '@/api/tahp/skills'

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
// 全局上下文 + 编辑状态
// ─────────────────────────────────────────────────────────────────────────────
const ctx = reactive({
  projectCode: 'X6876_H786',
  soc: 'MT6878',
  kernelVersion: '6.1',
  preVendor: 'vendor14',
  postVendor: 'vendor16',
})

// 上下文编辑弹窗
const showCtxEdit = ref(false)
const ctxEdit = reactive({ ...ctx })   // 编辑副本，取消时不影响 ctx

function openCtxEdit() {
  Object.assign(ctxEdit, ctx)
  showCtxEdit.value = true
}

function saveCtxEdit() {
  Object.assign(ctx, ctxEdit)
  showCtxEdit.value = false
  message.success('项目上下文已更新')
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
      { name: 'modem_platform', label: 'Modem平台', type: 'select', required: true, options: [{ label:'MTK', value:'mtk' },{ label:'Qualcomm', value:'qcom' },{ label:'UNISOC', value:'unisoc' }] },
      { name: 'rf_param_dir',   label: 'RF参数目录', type: 'text',   required: true, placeholder: 'vendor/mediatek/proprietary/modem_1/rf_params' },
      { name: 'carrier',        label: '运营商',     type: 'text',   required: false, placeholder: '如 CMCC / Vodafone' },
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
const launching   = ref(false)
const launchedTaskId = ref<string | null>(null)
const taskStatus  = ref<string>('')
const showMonitor = ref(false)
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
  stream.value.filter(ev => ev.type !== 'task.message')
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
    }
  } catch {
    // 动态域加载失败不影响静态域功能
  } finally {
    loadingDomains.value = false
  }
}

onMounted(() => { loadDynamicDomains() })

// ─────────────────────────────────────────────────────────────────────────────
// 构建内联文档内容（传给 MCP Pipeline）
// ─────────────────────────────────────────────────────────────────────────────
function buildDocContent(): string {
  const d    = activeDomain.value
  const data = currentFormData.value

  let doc = `# AI 适配调试任务 — ${d.label}\n\n`
  doc += `## 项目信息\n`
  doc += `- 项目代码: ${ctx.projectCode}\n`
  doc += `- SoC: ${ctx.soc}\n`
  doc += `- Kernel 版本: ${ctx.kernelVersion}\n`
  doc += `- 升级路径: ${ctx.preVendor} → ${ctx.postVendor}\n\n`
  doc += `## 适配域: ${d.label} (${d.id})\n\n`
  doc += `### 前置条件参数\n`
  d.fields.forEach(f => {
    const val = data[f.name]
    doc += `- ${f.label}: ${val || '(未填)'}\n`
  })
  doc += `\n### 关联 Skills\n`
  d.relatedSkills.forEach(s => { doc += `- ${s}\n` })
  doc += `\n---\n_由 TAHP Console AI 适配调试面板自动生成_\n`
  return doc
}

// ─────────────────────────────────────────────────────────────────────────────
// 启动任务（核心修复：真正调用 MCP Pipeline）
// ─────────────────────────────────────────────────────────────────────────────
async function launchTask() {
  if (!isComplete.value) {
    message.warning('请先完成所有必填前置条件')
    return
  }

  launching.value   = true
  taskStatus.value  = 'starting'
  launchedTaskId.value = null
  showMonitor.value = true
  startTime.value   = Date.now()

  try {
    tasksStore.ensureSocket()

    const info = await tasksStore.start({
      document_path:    '__inline__',
      document_content: buildDocContent(),
      module:           mapDomainToModule(activeDomainId.value),
      domain:           'code_adaptation',
      extra_context:    `AI适配调试 | 域: ${activeDomain.value.label} | 项目: ${ctx.projectCode} | SoC: ${ctx.soc} | Kernel: ${ctx.kernelVersion}`,
    })

    const tid = (info.task_id || info.taskId) as string | undefined
    if (tid) {
      launchedTaskId.value = tid
      message.success(`任务已启动: ${tid}`)
    } else {
      message.warning('任务已提交，但服务端未返回 task_id，请检查 MCP 日志')
    }
  } catch (err) {
    const errMsg = (err as Error).message
    taskStatus.value = 'FAILED'
    // 保留 showMonitor=true，让用户看到错误信息
    message.error(`启动失败: ${errMsg}`)
  } finally {
    launching.value = false
  }
}

function backToForm() {
  showMonitor.value = false
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

function openAIChat() {
  // 将当前域的表单数据和项目上下文序列化为自然语言草稿，
  // 通过 sessionStorage 传递给 ChatInput，让 AI 对话有具体的上下文可供参考。
  const d    = activeDomain.value
  const data = currentFormData.value

  const lines: string[] = [
    `我正在做 ${d.label} BSP 适配调试，请根据以下上下文帮我排查问题：`,
    '',
    `**项目信息**`,
    `- 项目代码: ${ctx.projectCode}`,
    `- SoC: ${ctx.soc}`,
    `- Kernel 版本: ${ctx.kernelVersion}`,
    `- 升级路径: ${ctx.preVendor} → ${ctx.postVendor}`,
    '',
    `**${d.label} 前置条件**`,
  ]

  d.fields.forEach(f => {
    const val = data[f.name]
    if (val) lines.push(`- ${f.label}: ${val}`)
  })

  if (d.relatedSkills.length) {
    lines.push('')
    lines.push(`**关联 Skills**: ${d.relatedSkills.join(', ')}`)
  }

  lines.push('')
  lines.push('**问题描述**（请在此补充你遇到的具体问题）：')

  // 主草稿：预填输入框
  sessionStorage.setItem('tahp_chat_draft', lines.join('\n'))

  // 元数据：供 ChatInput 渲染 TAHP 模式横幅 + 知识库沉淀对话框
  sessionStorage.setItem('tahp_chat_context', JSON.stringify({
    domain:        activeDomainId.value,
    domainLabel:   d.label,
    module:        mapDomainToModule(activeDomainId.value),
    relatedSkills: d.relatedSkills,
    project:       { ...ctx },
    taskId:        launchedTaskId.value,
  }))

  router.push({ name: 'hermes.chat' })
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

        <!-- 上下文信息栏 -->
        <div class="ctx-bar">
          <div class="ctx-chips">
            <span class="ctx-chip"><span class="ck">项目</span><span class="cv">{{ ctx.projectCode }}</span></span>
            <span class="ctx-chip"><span class="ck">SoC</span><span class="cv">{{ ctx.soc }}</span></span>
            <span class="ctx-chip"><span class="ck">Kernel</span><span class="cv">{{ ctx.kernelVersion }}</span></span>
            <span class="ctx-chip"><span class="ck">升级路径</span><span class="cv">{{ ctx.preVendor }} → {{ ctx.postVendor }}</span></span>
          </div>
          <NButton text type="primary" size="small" @click="openCtxEdit">编辑</NButton>
        </div>

        <!-- 域标题行 -->
        <div class="domain-head">
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
        </div>

        <!-- 前置条件表单 -->
        <div class="form-card">
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

        <!-- 关联 Skills -->
        <div class="skills-row">
          <span class="skills-title">关联 Skills</span>
          <NTag
            v-for="skill in activeDomain.relatedSkills"
            :key="skill"
            class="skill-tag"
            size="small"
            @click="openSkill(skill)"
          >
            {{ skill }}
          </NTag>
        </div>

        <!-- 操作按钮 -->
        <div class="action-row">
          <NButton
            type="primary"
            size="large"
            :disabled="!isComplete"
            :loading="launching"
            @click="launchTask"
          >
            {{ launching ? '正在启动...' : '启动 AI 适配调试' }}
          </NButton>
          <NButton size="large" @click="openAIChat">
            AI 对话调试
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
            <span class="mb-title">{{ activeDomain.label }} — AI 适配执行</span>
          </div>
          <div class="mb-right">
            <code v-if="launchedTaskId" class="mb-taskid">{{ launchedTaskId }}</code>
            <NTag size="small" :type="statusTagType" class="mb-status">
              <template v-if="isRunning">
                <span class="pulse-dot" />
              </template>
              {{ taskStatus || 'starting' }}
            </NTag>
            <NButton size="small" type="primary" @click="openAIChat">AI 对话调试</NButton>
            <NButton size="small" @click="router.push({ name: 'tahp.tasks' })">任务列表</NButton>
          </div>
        </div>

        <!-- ① 启动中（还未拿到 task_id） -->
        <div v-if="launching && !launchedTaskId" class="monitor-state">
          <NSpin size="large" />
          <p class="ms-hint">正在启动 AI 适配任务，请稍候...</p>
          <p class="ms-sub">大模型分析中，无需 MCP Server</p>
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
          <p class="ms-hint">任务启动失败</p>
          <p class="ms-sub">请在"模型管理"中配置 API Key，或设置 TAHP_LLM_UPSTREAM 环境变量</p>
          <div style="display:flex;gap:8px;margin-top:4px;">
            <NButton type="primary" @click="backToForm">返回重新配置</NButton>
            <NButton @click="launchTask" :loading="launching">重试</NButton>
          </div>
        </div>

        <!-- ③ 已提交但等待第一条事件 -->
        <div
          v-else-if="!stream.length && !launching"
          class="monitor-state"
        >
          <NSpin size="medium" />
          <p class="ms-hint">任务已提交，等待 AI 分析开始...</p>
          <code v-if="launchedTaskId" class="ms-taskid">{{ launchedTaskId }}</code>
        </div>

        <!-- ④ 主视图：LLM 回复 + 步骤侧边 -->
        <div v-else ref="eventListEl" class="llm-monitor-layout">

          <!-- 左：AI 分析内容（流式渲染）-->
          <div class="llm-response-panel">
            <div class="lrp-header">
              <span class="lrp-title">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                AI 适配分析
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
          <NButton size="small" style="margin-left:6px;" :loading="launching" @click="launchTask">重试</NButton>
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

    <!-- ====== 上下文编辑弹窗 ====== -->
    <NModal
      v-model:show="showCtxEdit"
      preset="dialog"
      title="编辑项目上下文"
      positive-text="保存"
      negative-text="取消"
      style="width: 480px;"
      @positive-click="saveCtxEdit"
      @negative-click="showCtxEdit = false"
    >
      <div class="ctx-edit-body">
        <NForm label-placement="left" label-width="96" size="small">
          <NFormItem label="项目代码">
            <NInput
              v-model:value="ctxEdit.projectCode"
              placeholder="如 X6876_H786"
              clearable
            />
          </NFormItem>
          <NFormItem label="SoC">
            <NInput
              v-model:value="ctxEdit.soc"
              placeholder="如 MT6878"
              clearable
            />
          </NFormItem>
          <NFormItem label="Kernel 版本">
            <NInput
              v-model:value="ctxEdit.kernelVersion"
              placeholder="如 6.1"
              clearable
            />
          </NFormItem>
          <NFormItem label="前版本 Vendor">
            <NInput
              v-model:value="ctxEdit.preVendor"
              placeholder="如 vendor14"
              clearable
            />
          </NFormItem>
          <NFormItem label="目标 Vendor">
            <NInput
              v-model:value="ctxEdit.postVendor"
              placeholder="如 vendor16"
              clearable
            />
          </NFormItem>
        </NForm>
        <p class="ctx-edit-hint">上下文信息会用于构建 AI 适配任务的前置约束条件。</p>
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

// ── 表单区 (原有样式保留) ─────────────────────────────────────────────────
.ctx-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid $border-color;
  margin: 16px 0 0;
  flex-shrink: 0;
}
.ctx-chips { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ctx-chip {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 20px; font-size: 11px;
  background: $bg-card; border: 1px solid $border-color;
}
.ck { color: $text-muted; font-weight: 600; }
.cv { color: $text-primary; font-family: $font-code; }

.domain-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0 14px;
  flex-shrink: 0;
}
.dh-left   { display: flex; align-items: center; gap: 12px; }
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

// ── 上下文编辑弹窗 ────────────────────────────────────────────────────────────
.ctx-edit-body {
  padding: 4px 0;
}
.ctx-edit-hint {
  font-size: 11px;
  color: $text-muted;
  margin: 12px 0 0;
  line-height: 1.5;
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
