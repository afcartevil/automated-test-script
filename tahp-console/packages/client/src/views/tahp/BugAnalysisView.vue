<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NInput, NButton, NSpin, NEmpty, NAlert,
  NModal, NScrollbar, NProgress, NPopover, useMessage, NTooltip,
  NSpace, NForm, NFormItem,
} from 'naive-ui'
import MarkdownRenderer from '@/components/hermes/chat/MarkdownRenderer.vue'
import ModelProviderBanner from '@/components/tahp/ModelProviderBanner.vue'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import EaInnerTabs from '@/components/layout/EaInnerTabs.vue'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'
import { useBugAnalysisStore } from '@/stores/tahp/bug-analysis'
import {
  startSingle, startBatch, continueAnalysis, distillToKnowledge,
  previewJira, previewJql, getBugReport, getBugLog, cancelBugTask,
  type JiraIssueDetail, type JqlPreview, type BugReport, type JiraUserConfig,
} from '@/api/tahp/bug-analysis'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const store = useBugAnalysisStore()
const { isReady: modelProviderReady } = useModelProviderReadiness()

function ensureModelProviderOrWarn(): boolean {
  if (modelProviderReady.value) return true
  message.warning('请先在「模型管理」中配置模型 Provider 和 API Key')
  return false
}

// ─────────────────────────────────────────────────────────────────────────────
// 表单状态：mode = 'single' | 'batch'
//
// 注：已删除"模块选择"。Bug 域识别完全交给 Agent —— 它会在 Step 1 用 jira skill
// 拉到 Issue 详情后自主判断，BFF 不再做任何 keyword-based 启发式。
// ─────────────────────────────────────────────────────────────────────────────
const mode = ref<'single' | 'batch'>('single')

const singleForm = ref({
  input: '',
  user_description: '',
  extra_context: '',
})

const batchForm = ref({
  jql: '',
  extra_context: '',
})

// JIRA 预览（单条）
const jiraPreview = ref<JiraIssueDetail | null>(null)
const previewingJira = ref(false)
const previewError = ref<string | null>(null)

// JQL 预览
const jqlPreview = ref<JqlPreview | null>(null)
const previewingJql = ref(false)
const jqlPreviewError = ref<string | null>(null)

// 提交状态
const submitting = ref(false)

const showJiraConfigDialog = ref(false)
const jiraConfigForm = ref<JiraUserConfig>({ username: '', password: '' })
const jiraConfigReady = ref(false)

function loadJiraConfig() {
  const raw = localStorage.getItem('tahp_bug_jira_config')
  if (!raw) return
  try {
    const parsed = JSON.parse(raw) as Partial<JiraUserConfig>
    const username = String(parsed.username || '').trim()
    const password = String(parsed.password || '').trim()
    if (!username || !password) return
    jiraConfigForm.value = { username, password }
    jiraConfigReady.value = true
  } catch {
    // ignore invalid local data
  }
}

function saveJiraConfig() {
  const username = jiraConfigForm.value.username.trim()
  const password = jiraConfigForm.value.password.trim()
  if (!username || !password) {
    message.warning('请填写 JIRA 用户名和密码')
    return false
  }
  jiraConfigForm.value = { username, password }
  localStorage.setItem('tahp_bug_jira_config', JSON.stringify(jiraConfigForm.value))
  jiraConfigReady.value = true
  showJiraConfigDialog.value = false
  message.success('JIRA 凭证已保存')
  return true
}

function getJiraConfigOrWarn(): JiraUserConfig | null {
  if (!jiraConfigReady.value) {
    message.warning('请先配置 JIRA 账号密码')
    showJiraConfigDialog.value = true
    return null
  }
  return jiraConfigForm.value
}

// ─────────────────────────────────────────────────────────────────────────────
// 已启动任务/批次的展示
// ─────────────────────────────────────────────────────────────────────────────
const currentTaskId = computed(() => store.selectedTaskId)
const currentTask = computed(() =>
  currentTaskId.value ? store.tasks[currentTaskId.value] : null,
)
const currentLlm = computed(() => currentTaskId.value ? store.llmText(currentTaskId.value) : '')
const currentEvents = computed(() => currentTaskId.value ? store.structuredEvents(currentTaskId.value) : [])

const currentJobId = computed(() => store.selectedJobId)
const currentJob = computed(() => currentJobId.value ? store.jobs[currentJobId.value] : null)

const isRunning = computed(() => currentTask.value?.status === 'running')
const isPending = computed(() => currentTask.value?.status === 'pending')

// 详情 Tab：选择已完成报告时载入
const activeReportTab = ref<'live' | 'report' | 'jira' | 'log'>('live')
const reportDetail = ref<BugReport | null>(null)
const reportLoading = ref(false)
const taskLog = ref<string>('')
const logLoading = ref(false)

// 补充信息弹窗
const showContinueDialog = ref(false)
const continueText = ref('')

// 知识沉淀弹窗
const showDistillDialog = ref(false)
const distillNote = ref('')

// ─────────────────────────────────────────────────────────────────────────────
// 阶段名映射 — 用于侧栏显示更友好的标签
// ─────────────────────────────────────────────────────────────────────────────
const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  FETCHING_JIRA:    { label: '拉取 JIRA',      color: 'var(--info)' },
  SKILL_SELECTION:  { label: '匹配 Skill',     color: 'var(--violet-ic)' },
  LOADING_CONTEXT:  { label: '加载上下文',     color: 'var(--success)' },
  ANALYZING:        { label: '大模型分析',     color: 'var(--warn)' },
  GENERATING_REPORT:{ label: '生成报告',       color: 'var(--info)' },
  COMPLETED:        { label: '已完成',         color: 'var(--success)' },
  FAILED:           { label: '失败',           color: 'var(--error)' },
  CANCELLED:        { label: '已取消',         color: 'var(--violet-ic)' },
  QUEUED:           { label: '等待中',         color: 'var(--warn)' },
  BATCH_RUNNING:    { label: '批量执行中',     color: 'var(--info)' },
}

const BUG_STAGE_ORDER = ['FETCHING_JIRA', 'SKILL_SELECTION', 'LOADING_CONTEXT', 'ANALYZING', 'GENERATING_REPORT'] as const

const detailTabs = computed(() => [
  { key: 'live', label: '实时进展' },
  {
    key: 'report',
    label: '分析报告',
    disabled: currentTask.value?.status === 'running' && !currentTask.value?.completed_at,
  },
  { key: 'jira', label: 'JIRA 详情' },
  { key: 'log', label: '任务日志' },
])

const bugStages = computed(() => {
  const phase = currentTask.value?.phase
  const status = currentTask.value?.status
  const idx = phase ? BUG_STAGE_ORDER.indexOf(phase as typeof BUG_STAGE_ORDER[number]) : -1
  const allDone = status === 'completed' || phase === 'COMPLETED'
  return BUG_STAGE_ORDER.map((key, i) => ({
    key,
    label: PHASE_LABELS[key]?.label || key,
    done: allDone || (idx >= 0 && i < idx),
    active: !allDone && phase === key,
  }))
})

function phaseLabel(phase?: string): string {
  if (!phase) return '准备中'
  return PHASE_LABELS[phase]?.label || phase
}

function phaseColor(phase?: string): string {
  if (!phase) return 'var(--faint)'
  return PHASE_LABELS[phase]?.color || 'var(--faint)'
}

function statusPillVariant(status?: string): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  if (status === 'completed') return 'ok'
  if (status === 'failed') return 'err'
  if (status === 'cancelled') return 'warn'
  if (status === 'running') return 'info'
  if (status === 'pending') return 'warn'
  return 'muted'
}

function formatTs(ts: number): string {
  return new Date(ts).toLocaleTimeString()
}

function formatEventPayload(payload: Record<string, unknown>): string {
  const msg = payload?.message || payload?.text
  if (typeof msg === 'string') return msg
  return JSON.stringify(payload, null, 2)
}

function fmtDuration(ms?: number): string {
  if (!ms && ms !== 0) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

// 自动滚动事件流到底部
const eventsScroller = ref<HTMLElement | null>(null)
watch(() => currentEvents.value.length, async () => {
  await nextTick()
  if (eventsScroller.value) {
    eventsScroller.value.scrollTop = eventsScroller.value.scrollHeight
  }
})

// 自动滚动 LLM 流到底部
const llmScroller = ref<HTMLElement | null>(null)
watch(currentLlm, async () => {
  await nextTick()
  if (llmScroller.value) {
    llmScroller.value.scrollTop = llmScroller.value.scrollHeight
  }
})

// ─────────────────────────────────────────────────────────────────────────────
// 操作：预览 JIRA / JQL
// ─────────────────────────────────────────────────────────────────────────────
async function doPreviewJira() {
  const jiraConfig = getJiraConfigOrWarn()
  if (!jiraConfig) return
  const v = singleForm.value.input.trim()
  if (!v) { message.warning('请先填入 Bug ID 或 URL'); return }
  previewingJira.value = true
  previewError.value = null
  jiraPreview.value = null
  try {
    jiraPreview.value = await previewJira(v, jiraConfig)
  } catch (err) {
    previewError.value = (err as Error).message
  } finally {
    previewingJira.value = false
  }
}

async function doPreviewJql() {
  const jiraConfig = getJiraConfigOrWarn()
  if (!jiraConfig) return
  const v = batchForm.value.jql.trim()
  if (!v) { message.warning('请填入 JQL 查询语句'); return }
  previewingJql.value = true
  jqlPreviewError.value = null
  jqlPreview.value = null
  try {
    jqlPreview.value = await previewJql(v, jiraConfig)
  } catch (err) {
    jqlPreviewError.value = (err as Error).message
  } finally {
    previewingJql.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 操作：启动分析
// ─────────────────────────────────────────────────────────────────────────────
async function startSingleAnalysis() {
  if (!ensureModelProviderOrWarn()) return
  const jiraConfig = getJiraConfigOrWarn()
  if (!jiraConfig) return
  if (!singleForm.value.input.trim()) {
    message.warning('请填入 Bug ID 或 URL')
    return
  }
  submitting.value = true
  try {
    store.ensureSocket()
    const resp = await startSingle({
      input: singleForm.value.input.trim(),
      user_description: singleForm.value.user_description || undefined,
      extra_context: singleForm.value.extra_context || undefined,
    }, jiraConfig)
    store.registerTask({
      task_id: resp.task_id,
      jira_key: resp.jira_key || singleForm.value.input,
      jira_url: jiraPreview.value?.url || '',
      status: 'running',
      phase: 'STARTING',
      progress: 0,
      started_at: new Date().toISOString(),
      title: jiraPreview.value?.summary,
    })
    store.selectTask(resp.task_id)
    store.selectJob(null)
    activeReportTab.value = 'live'
    message.success(`分析任务已启动: ${resp.jira_key || ''}`)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

async function startBatchAnalysis() {
  if (!ensureModelProviderOrWarn()) return
  const jiraConfig = getJiraConfigOrWarn()
  if (!jiraConfig) return
  if (!batchForm.value.jql.trim()) {
    message.warning('请填入 JQL')
    return
  }
  submitting.value = true
  try {
    store.ensureSocket()
    const resp = await startBatch({
      jql: batchForm.value.jql.trim(),
      extra_context: batchForm.value.extra_context || undefined,
    }, jiraConfig)
    // 注册 Job + 子任务
    store.registerJob({
      job_id: resp.job_id,
      type: 'batch',
      jql: batchForm.value.jql,
      task_ids: resp.tasks.map(t => t.task_id),
      started_at: new Date().toISOString(),
      status: 'running',
      total: resp.total,
      completed: 0,
      failed: 0,
    })
    for (const t of resp.tasks) {
      store.registerTask({
        task_id: t.task_id,
        jira_key: t.jira_key,
        jira_url: '',
        status: 'pending',
        phase: 'QUEUED',
        progress: 0,
        started_at: new Date().toISOString(),
        parent_job_id: resp.job_id,
      })
    }
    store.selectJob(resp.job_id)
    store.selectTask(resp.tasks[0]?.task_id || null)
    activeReportTab.value = 'live'
    message.success(`批量分析已启动: 共 ${resp.total} 单`)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 操作：切换任务 / 加载报告
// ─────────────────────────────────────────────────────────────────────────────
function selectTask(taskId: string) {
  store.selectTask(taskId)
  reportDetail.value = null
  taskLog.value = ''
  activeReportTab.value = 'live'
}

async function loadReport() {
  if (!currentTaskId.value) return
  reportLoading.value = true
  reportDetail.value = null
  try {
    reportDetail.value = await getBugReport(currentTaskId.value)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    reportLoading.value = false
  }
}

async function loadLog() {
  if (!currentTaskId.value) return
  logLoading.value = true
  taskLog.value = ''
  try {
    const r = await getBugLog(currentTaskId.value)
    taskLog.value = r.content || '(日志为空)'
  } catch (err) {
    taskLog.value = `加载日志失败: ${(err as Error).message}`
  } finally {
    logLoading.value = false
  }
}

watch(activeReportTab, (tab) => {
  if (tab === 'report' && currentTaskId.value && !reportDetail.value) loadReport()
  if (tab === 'log' && currentTaskId.value && !taskLog.value) loadLog()
})

// ─────────────────────────────────────────────────────────────────────────────
// 保存报告到本地
// ─────────────────────────────────────────────────────────────────────────────
function saveReportLocally(format: 'json' | 'md') {
  if (!currentTaskId.value) return
  const tid = currentTaskId.value
  const task = currentTask.value
  const llm = currentLlm.value
  if (!task) { message.warning('当前任务无数据'); return }

  let blob: Blob
  let filename: string
  if (format === 'md') {
    const md = [
      `# Bug 分析报告 — ${task.jira_key}`,
      ``,
      `- Task: ${tid}`,
      `- JIRA: ${task.jira_url || task.jira_key}`,
      ...(task.module ? [`- 模块（Agent 识别）: ${task.module}`] : []),
      `- 状态: ${task.status}`,
      `- 启动时间: ${task.started_at}`,
      `- 完成时间: ${task.completed_at || '-'}`,
      `- 使用 Skill: ${(task.skills_used || []).join(', ') || '-'}`,
      ``,
      `## AI 分析内容`,
      ``,
      (reportDetail.value?.llm_response || llm || '(无内容)'),
    ].join('\n')
    blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    filename = `${tid}.md`
  } else {
    const data = reportDetail.value || {
      ...task,
      task_id: tid,
      llm_response: llm,
    }
    blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' })
    filename = `${tid}.json`
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  message.success(`已保存 ${filename}`)
}

function downloadLog() {
  if (!currentTaskId.value || !taskLog.value) {
    message.warning('请先在"任务日志"页加载日志')
    return
  }
  const blob = new Blob([taskLog.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${currentTaskId.value}.log`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ─────────────────────────────────────────────────────────────────────────────
// 补充信息继续分析
// ─────────────────────────────────────────────────────────────────────────────
function openContinue() {
  continueText.value = ''
  showContinueDialog.value = true
}

async function submitContinue() {
  if (!ensureModelProviderOrWarn()) return false
  if (!currentTaskId.value) return false
  const txt = continueText.value.trim()
  if (!txt) { message.warning('请填写补充信息'); return false }
  try {
    const resp = await continueAnalysis(currentTaskId.value, {
      additional_info: txt,
    })
    store.registerTask({
      task_id: resp.task_id,
      jira_key: currentTask.value?.jira_key || '',
      jira_url: currentTask.value?.jira_url || '',
      module: currentTask.value?.module,
      status: 'running',
      phase: 'STARTING',
      progress: 0,
      started_at: new Date().toISOString(),
      title: currentTask.value?.title,
    })
    store.selectTask(resp.task_id)
    activeReportTab.value = 'live'
    showContinueDialog.value = false
    message.success(`补充分析任务已启动: ${resp.task_id}`)
  } catch (err) {
    message.error((err as Error).message)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 知识沉淀（占位 — 仅记录请求）
// ─────────────────────────────────────────────────────────────────────────────
function openDistill() {
  distillNote.value = ''
  showDistillDialog.value = true
}

async function submitDistill() {
  if (!currentTaskId.value) return
  try {
    const r = await distillToKnowledge(currentTaskId.value, distillNote.value || undefined)
    message.success(r.message || '请求已记录')
    showDistillDialog.value = false
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function stopOrCancelCurrentTask() {
  if (!currentTaskId.value || !currentTask.value) return
  try {
    const r = await cancelBugTask(currentTaskId.value)
    if (r.action === 'interrupted_running') {
      message.success('已请求中断当前运行任务，通常几秒内会切到已取消并继续后续任务')
    } else if (r.action === 'cancelled_pending') {
      message.success('已取消等待中的任务')
    } else {
      message.success('任务取消请求已提交')
    }
  } catch (err) {
    message.error((err as Error).message)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 路由参数：?task_id=xxx 直接打开某条任务
// ─────────────────────────────────────────────────────────────────────────────
onMounted(async () => {
  loadJiraConfig()
  if (!jiraConfigReady.value) showJiraConfigDialog.value = true
  store.ensureSocket()
  await store.refresh()
  const queryTid = route.query.task_id as string | undefined
  if (queryTid && store.tasks[queryTid]) {
    store.selectTask(queryTid)
  }
  const queryInput = route.query.input as string | undefined
  if (queryInput) {
    singleForm.value.input = queryInput
  }
})

// JIRA URL 友好展示
const jiraInputHint = computed(() => {
  const v = singleForm.value.input.trim()
  if (!v) return ''
  const match = v.match(/([A-Z][A-Z0-9_]+-\d+)/i)
  return match ? match[1].toUpperCase() : ''
})

// 当前 Skill 列表（实时）
const currentSkills = computed<string[]>(() => currentTask.value?.skills_used || [])

// 当前 Skill 调用详情（带状态、参数、来源；Agent 模式下真实工具调用）
const currentSkillCalls = computed(() =>
  currentTaskId.value ? store.skillCallList(currentTaskId.value) : []
)

// ─────────────────────────────────────────────────────────────────────────────
// 「交给 Agent」—— 把 Bug 上下文（JIRA Key/URL/用户描述/已生成的分析）
// 通过 sessionStorage 投递到 hermes.chat，由 Claude Code Agent 完整调用 Skill
// （直连 LLM 模式只能"标记" skill；真正的 skill 执行只发生在 Agent 子进程里）
// ─────────────────────────────────────────────────────────────────────────────
function handoffToAgent(scope: 'single' | 'batch') {
  if (!ensureModelProviderOrWarn()) return
  const lines: string[] = []
  if (scope === 'single' && currentTask.value) {
    const t = currentTask.value
    lines.push(`# 任务：完整 Bug 分析（请调用 Skill）`)
    lines.push('')
    lines.push(`## Bug 单`)
    lines.push(`- Key: ${t.jira_key}`)
    if (t.jira_url) lines.push(`- URL: ${t.jira_url}`)
    if (t.title) lines.push(`- 标题: ${t.title}`)
    if (t.module) lines.push(`- 模块（Agent 已识别）: ${t.module}`)
    lines.push('')
    if (singleForm.value.user_description || t.user_description) {
      lines.push(`## 用户补充描述`)
      lines.push(t.user_description || singleForm.value.user_description || '')
      lines.push('')
    }
    if (t.extra_context) {
      lines.push(`## 附加上下文`)
      lines.push(t.extra_context)
      lines.push('')
    }
    if (currentLlm.value || reportDetail.value?.llm_response) {
      lines.push(`## 上一轮 Agent 已生成的分析报告（在此基础上继续讨论/补充）`)
      lines.push('')
      lines.push((reportDetail.value?.llm_response || currentLlm.value).slice(0, 4000))
      lines.push('')
    }
  } else if (scope === 'batch' && currentJob.value) {
    lines.push(`# 任务：批量 Bug 分析（请逐条调用 Skill）`)
    lines.push('')
    lines.push(`## JQL`)
    lines.push(currentJob.value.jql || '(无)')
    lines.push('')
    lines.push(`## Bug 列表`)
    for (const tid of currentJob.value.task_ids) {
      const t = store.tasks[tid]
      if (!t) continue
      lines.push(`- ${t.jira_key} : ${t.title || '(待获取标题)'}`)
    }
    lines.push('')
  } else {
    // 没有上下文也允许跳转
    if (singleForm.value.input.trim()) {
      lines.push(`# 任务：完整 Bug 分析`)
      lines.push('')
      lines.push(`输入: ${singleForm.value.input.trim()}`)
      if (singleForm.value.user_description) {
        lines.push('')
        lines.push(`补充: ${singleForm.value.user_description}`)
      }
    } else {
      message.warning('暂无可移交的上下文')
      return
    }
  }

  lines.push('---')
  lines.push('## 接下来希望做什么')
  lines.push('请基于以上上下文与用户对话，可以包括：')
  lines.push('- 针对某节继续追问 / 让用户补充信息')
  lines.push('- 重新拉取更详细的日志（用 transsion-harness / jira-mcp）')
  lines.push('- 写一个修复 patch / 验证脚本')
  lines.push('- 沉淀为 Skill / 知识库条目')

  sessionStorage.setItem('tahp_chat_draft', lines.join('\n'))
  sessionStorage.setItem('tahp_chat_context', JSON.stringify({
    domain: 'bug_analysis',
    domainLabel: 'Bug 分析（完整 Agent）',
    module: currentTask.value?.module,
    relatedSkills: currentSkills.value.length ? currentSkills.value : ['transsion-harness'],
    project: {
      projectCode: '-',
      soc: '-',
      kernelVersion: '-',
      preVendor: '-',
      postVendor: '-',
    },
    taskId: currentTask.value?.task_id || null,
  }))

  router.push({ name: 'hermes.chat' })
}
</script>

<template>
  <div class="page page-wide bug-analysis-root">
    <ModelProviderBanner />

    <EaPageHead
      title="智能诊断"
      subtitle="基于 JIRA · 自动调用日志/分析 Skill · 实时可观察的根因定位"
    >
      <template #actions>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="showJiraConfigDialog = true">
          JIRA 配置
        </button>
        <EaPill :variant="jiraConfigReady ? 'ok' : 'warn'">
          {{ jiraConfigReady ? 'JIRA 已配置' : '需配置 JIRA' }}
        </EaPill>
        <EaPill variant="info">
          <span class="ea-dot-live" />
          实时事件流
        </EaPill>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="store.refresh">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          刷新
        </button>
      </template>
    </EaPageHead>

    <div class="ea-split bug-split">
      <!-- Left: form + task list -->
      <div class="ea-stack bug-left">
        <EaCard>
          <div class="ea-row ea-between ea-mb0" style="margin-bottom: 14px">
            <strong style="font-size: 14px">提交分析任务</strong>
            <div class="mode-toggle">
              <button
                type="button"
                class="ea-btn-sm"
                :class="mode === 'single' ? 'ea-btn-soft' : 'mode-idle'"
                @click="mode = 'single'"
              >单条 Bug</button>
              <button
                type="button"
                class="ea-btn-sm"
                :class="mode === 'batch' ? 'ea-btn-soft' : 'mode-idle'"
                @click="mode = 'batch'"
              >JQL 批量</button>
            </div>
          </div>
          <NPopover trigger="click" placement="bottom-start" style="max-width: 420px">
            <template #trigger>
              <div class="exec-mode-banner agent-mode">
                <span class="emb-dot" />
                <span class="emb-text">
                  <strong>Agent 模式</strong> · Claude Code + 完整 Skill / MCP 工具链
                </span>
                <span class="emb-link">查看说明</span>
              </div>
            </template>
            <div class="popover-body">
              <div class="popover-title">所有 Bug 分析任务统一走 Agent</div>
              <div class="popover-section">
                <strong>· BFF 零启发式</strong><br>
                <span class="popover-muted">
                  BFF 不再做模块推断 / Skill 候选 / 约束加载 / Prompt 拼装。<br>
                  它只负责：解析 JIRA Key、记录任务、把"分析这个 Bug"这一句话原样投递给 Agent，再把 Agent 的事件流转发到前端。
                </span>
              </div>
              <div class="popover-section">
                <strong>· Agent 自主完成全链路</strong><br>
                <span class="popover-muted">
                  Agent 收到任务后，按以下顺序真实调用工具（每次调用都会出现在右侧"Skill 调用"面板）：<br>
                  1. <code>jira-mcp</code> / <code>user-jira-mcp</code> 拉取 Issue 详情 + 附件 + 评论<br>
                  2. 根据 Issue 内容<strong>自主判断</strong> Bug 域，挑对应 Skill（<code>com-voice-*</code> / <code>near-bt-*</code> / <code>power-*</code> / …）<br>
                  3. <code>transsion-harness</code> 拉日志 / 版本 / 部署<br>
                  4. 综合证据输出 8 节根因报告
                </span>
              </div>
              <div class="popover-section">
                <strong>· 失败即停止</strong><br>
                <span class="popover-muted">若 Agent Bridge 未运行 / Agent 调用出错 / Skill 失败，任务会立即标记为 failed 并把错误显示在事件流，<strong>不会降级到直连 LLM</strong>。批量分析下，任一子任务失败会终止后续。</span>
              </div>
              <div class="popover-section">
                <strong>· 依赖项</strong><br>
                <span class="popover-muted">需要 hermes CLI 已安装、agent-bridge 已启动（服务端日志查关键字 <code>[agent-bridge] starting</code>），并已在"模型管理"中配置 Claude / OpenAI 凭证供 Agent 使用。</span>
              </div>
              <div class="popover-foot">
                "预览 JIRA" 按钮仍走 BFF 直连（可选 <code>TAHP_JIRA_TOKEN</code> 等环境变量）；正式分析时 Agent 会用自己的 jira-mcp 凭证重新拉取，与 BFF 凭证无关。
              </div>
            </div>
          </NPopover>

          <!-- 单条模式 -->
          <template v-if="mode === 'single'">
            <div class="ea-field">
              <label>
                Bug ID 或 URL <span class="req">*</span>
                <NTooltip placement="top" trigger="hover">
                  <template #trigger>
                    <svg class="info-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
                    </svg>
                  </template>
                  支持纯 Key（X6873OS162-1079）或完整链接 http://jira.transsion.com/browse/...
                </NTooltip>
              </label>
              <NInput
                v-model:value="singleForm.input"
                placeholder="如 X6873OS162-1079 或 http://jira.transsion.com/browse/X6873OS162-1079"
                clearable
              />
              <div v-if="jiraInputHint" class="field-hint">解析到 Key: <code>{{ jiraInputHint }}</code></div>
            </div>

            <div class="ea-field">
              <label>用户补充描述（可选）</label>
              <NInput
                v-model:value="singleForm.user_description"
                type="textarea"
                placeholder="补充 Bug 出现条件、复现路径、相关功能、已尝试方案等..."
                :autosize="{ minRows: 3, maxRows: 8 }"
              />
            </div>

            <div class="ea-field">
              <label>附加上下文（可选）</label>
              <NInput
                v-model:value="singleForm.extra_context"
                placeholder="项目代码 / SoC / 版本 / Carrier 等"
                clearable
              />
            </div>

            <div class="ea-row ea-wrap action-row">
              <NButton type="primary" :loading="submitting" :disabled="!modelProviderReady || !singleForm.input.trim()" @click="startSingleAnalysis">
                开始分析
              </NButton>
              <NButton :loading="previewingJira" :disabled="!singleForm.input.trim()" @click="doPreviewJira">
                预览 JIRA
              </NButton>
              <NTooltip placement="top">
                <template #trigger>
                  <NButton tertiary :disabled="!modelProviderReady || !singleForm.input.trim()" @click="handoffToAgent('single')">
                    <template #icon>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    </template>
                    在 AI 对话中继续
                  </NButton>
                </template>
                跳转到 AI 对话页，在自由对话上下文里继续追问/调整（同样使用 Agent + 完整 Skill）
              </NTooltip>
            </div>

            <NAlert v-if="previewError" type="warning" :show-icon="false" style="margin-top: 12px">
              <template v-if="previewError.includes('401') || previewError.toLowerCase().includes('login')">
                <strong>BFF 端 JIRA 预览鉴权失败（401）</strong>。
                <div class="alert-sub">
                  这只影响"预览 JIRA"按钮（用于让你在提交前快速核对 Issue 标题/描述）。
                  正式"开始分析"时会把任务交给 Agent，由 Agent 用自己的 jira-mcp Skill 拉取，不依赖 BFF 凭证，请放心点击"开始分析"。
                </div>
                <details style="margin-top: 6px;">
                  <summary class="alert-link">想让 BFF 也能预览（可选）</summary>
                  <div class="alert-sub" style="margin-top: 4px;">
                    给 BFF 配置任一环境变量后重启服务：<code>TAHP_JIRA_TOKEN</code> / <code>TAHP_JIRA_USERNAME+PASSWORD</code> / <code>TAHP_JIRA_COOKIE</code>。
                  </div>
                </details>
              </template>
              <template v-else>
                {{ previewError }}
                <div class="alert-sub">
                  不影响"开始分析"——Agent 会用 jira-mcp Skill 重新拉取。
                </div>
              </template>
            </NAlert>

            <div v-if="jiraPreview" class="ea-info-soft ea-mt16">
              <div class="ea-row ea-between" style="margin-bottom: 6px">
                <EaPill variant="info">{{ jiraPreview.key }}</EaPill>
                <EaPill v-if="jiraPreview.priority" variant="warn">{{ jiraPreview.priority }}</EaPill>
              </div>
              <div class="preview-summary">{{ jiraPreview.summary }}</div>
              <div class="ea-row ea-wrap preview-meta">
                <span v-if="jiraPreview.status">状态 {{ jiraPreview.status }}</span>
                <span v-if="jiraPreview.assignee">经办 {{ jiraPreview.assignee }}</span>
                <span v-if="jiraPreview.attachments?.length">附件 {{ jiraPreview.attachments.length }} 个</span>
              </div>
              <div v-if="jiraPreview.url" style="margin-top: 8px">
                <a :href="jiraPreview.url" target="_blank" class="pv-link">{{ jiraPreview.url }}</a>
              </div>
            </div>
          </template>

          <!-- 批量模式 -->
          <template v-else>
            <div class="ea-field">
              <label>JQL <span class="req">*</span></label>
              <NInput
                v-model:value="batchForm.jql"
                type="textarea"
                placeholder='如 project = X6873OS162 AND status = "待处理" AND createdDate >= -7d'
                :autosize="{ minRows: 3, maxRows: 8 }"
              />
            </div>

            <div class="ea-field">
              <label>附加上下文（可选）</label>
              <NInput
                v-model:value="batchForm.extra_context"
                placeholder="项目代码 / SoC / 版本 / Carrier 等"
                clearable
              />
            </div>

            <div class="ea-row ea-wrap action-row">
              <NButton type="primary" :loading="submitting" :disabled="!modelProviderReady || !batchForm.jql.trim()" @click="startBatchAnalysis">
                批量分析
              </NButton>
              <NButton :loading="previewingJql" :disabled="!batchForm.jql.trim()" @click="doPreviewJql">
                预览 JQL
              </NButton>
            </div>

            <NAlert v-if="jqlPreviewError" type="warning" :show-icon="false" style="margin-top: 12px">
              {{ jqlPreviewError }}
            </NAlert>

            <div v-if="jqlPreview" class="ea-info-soft ea-mt16">
              <div class="jql-summary">
                匹配 <strong>{{ jqlPreview.issues.length }}</strong> 单（共 {{ jqlPreview.total }}）
                <EaPill v-if="jqlPreview.truncated" variant="warn">已截断</EaPill>
              </div>
              <NScrollbar style="max-height: 220px">
                <div v-for="iss in jqlPreview.issues" :key="iss.key" class="jql-item">
                  <a :href="iss.url" target="_blank" class="pv-link">{{ iss.key }}</a>
                  <span class="jql-title">{{ iss.summary }}</span>
                  <EaPill v-if="iss.priority" variant="warn">{{ iss.priority }}</EaPill>
                </div>
              </NScrollbar>
            </div>
          </template>
        </EaCard>

        <EaCard class="bug-tasks-card">
          <div class="ea-row ea-between" style="margin-bottom: 12px">
            <strong style="font-size: 14px">最近任务</strong>
            <EaPill variant="muted">{{ store.recentTasks.length }} 条</EaPill>
          </div>

          <NEmpty v-if="!store.recentTasks.length" size="small" description="还没有任务" />
          <NScrollbar v-else class="task-scroll">
            <div class="ea-tasklist">
              <button
                v-for="t in store.recentTasks"
                :key="t.task_id"
                type="button"
                class="ea-task-item"
                :class="{ active: currentTaskId === t.task_id, [`status-${t.status}`]: true }"
                @click="selectTask(t.task_id)"
              >
                <div class="ti-top">
                  <span class="ti-key">{{ t.jira_key }}</span>
                  <EaPill :variant="statusPillVariant(t.status)">{{ t.status }}</EaPill>
                </div>
                <div class="ti-title">{{ t.title || '(等待获取标题)' }}</div>
                <div class="ti-meta">
                  <span
                    class="ea-dot"
                    :class="{ 'ea-dot-live': t.status === 'running' }"
                    :style="t.status !== 'running' ? { background: phaseColor(t.phase) } : undefined"
                  />
                  <span>{{ phaseLabel(t.phase) }}</span>
                  <span v-if="t.skills_used?.length" class="ti-badge">{{ t.skills_used.length }} skill</span>
                  <span v-if="t.parent_job_id" class="ti-badge ti-batch">批量</span>
                </div>
              </button>
            </div>
          </NScrollbar>
        </EaCard>
      </div>

      <!-- Right: main panel -->
      <div class="bug-main-wrap">
        <EaCard v-if="!currentTask && !currentJob" class="bug-main bug-empty">
          <div class="empty-illus">
            <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M9 9h.01"/>
              <path d="M15 9h.01"/>
              <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
            </svg>
          </div>
          <h2>开始你的第一条 Bug 分析</h2>
          <p>输入 JIRA Key 或 URL，或粘贴 JQL 批量执行；分析过程将在此实时展示。</p>
          <div class="empty-tips">
            <div class="tip">
              <span class="tip-num">1</span>
              <span>左侧填写 Bug ID / URL（如 X6873OS162-1079）</span>
            </div>
            <div class="tip">
              <span class="tip-num">2</span>
              <span>可在 "用户补充描述" 中说明 Bug 出现条件、已尝试方案</span>
            </div>
            <div class="tip">
              <span class="tip-num">3</span>
              <span>点击 "开始分析"，AI 将自动调用日志下载/分析 Skill 完成根因定位</span>
            </div>
          </div>
        </EaCard>

        <EaCard v-else-if="currentJob && !currentTask" class="bug-main">
          <div class="ea-row ea-between" style="margin-bottom: 14px">
            <div class="ea-row" style="gap: 10px">
              <EaPill :variant="statusPillVariant(currentJob.status)">{{ currentJob.status }}</EaPill>
              <code class="mono job-id">{{ currentJob.job_id }}</code>
              <EaPill variant="info">批量 {{ currentJob.total }} 单</EaPill>
            </div>
          </div>
          <p class="job-jql"><strong>JQL:</strong> {{ currentJob.jql }}</p>
          <div class="job-progress">
            <span class="ea-muted" style="font-size: 12px">进度</span>
            <NProgress :percentage="Math.round(((currentJob.completed + currentJob.failed) / currentJob.total) * 100)" :show-indicator="true" />
            <div class="jp-stats">
              完成 <strong class="stat-ok">{{ currentJob.completed }}</strong> /
              失败 <strong class="stat-err">{{ currentJob.failed }}</strong> /
              总 {{ currentJob.total }}
            </div>
          </div>
          <p class="ea-muted" style="font-size: 12px; margin: 12px 0 6px">点击下方任一子任务查看详情：</p>
          <div class="job-tasks">
            <button
              v-for="tid in currentJob.task_ids"
              :key="tid"
              type="button"
              class="ea-task-item compact"
              :class="`status-${store.tasks[tid]?.status || 'unknown'}`"
              @click="selectTask(tid)"
            >
              <div class="ti-top">
                <span class="ti-key">{{ store.tasks[tid]?.jira_key || tid }}</span>
                <EaPill :variant="statusPillVariant(store.tasks[tid]?.status)">{{ store.tasks[tid]?.status || '-' }}</EaPill>
              </div>
              <div class="ti-meta">
                <span class="ea-dot" :style="{ background: phaseColor(store.tasks[tid]?.phase) }" />
                <span>{{ phaseLabel(store.tasks[tid]?.phase) }}</span>
              </div>
            </button>
          </div>
        </EaCard>

        <EaCard v-else-if="currentTask" class="bug-main bug-detail">
          <div class="ea-row ea-between task-head">
            <div class="ea-row task-head-left">
              <EaPill :variant="statusPillVariant(currentTask.status)">
                <span v-if="isRunning" class="ea-dot-live" />
                {{ phaseLabel(currentTask.phase) }}
              </EaPill>
              <a v-if="currentTask.jira_url" :href="currentTask.jira_url" target="_blank" class="ti-key">{{ currentTask.jira_key }}</a>
              <span v-else class="ti-key">{{ currentTask.jira_key }}</span>
              <span class="ea-muted task-title">{{ currentTask.title || '...' }}</span>
            </div>
            <div class="ea-row">
              <EaPill v-if="currentTask.module" variant="muted">{{ currentTask.module }}</EaPill>
              <code class="mono task-id">{{ currentTask.task_id }}</code>
            </div>
          </div>

          <div v-if="typeof currentTask.progress === 'number'" class="task-progress">
            <NProgress :percentage="currentTask.progress" :show-indicator="false" :height="6" :color="phaseColor(currentTask.phase)" />
            <span class="ea-muted tp-text">{{ currentTask.progress }}%</span>
          </div>

          <div class="ea-stage-track" style="margin-bottom: 16px">
            <template v-for="(s, i) in bugStages" :key="s.key">
              <div class="ea-stage" :class="{ done: s.done, active: s.active }">
                <span class="ea-stage-node">
                  <svg v-if="s.done" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  <template v-else>{{ i + 1 }}</template>
                </span>
                <span class="ea-stage-meta"><strong>{{ s.label }}</strong></span>
              </div>
              <span v-if="i < bugStages.length - 1" class="ea-stage-link" />
            </template>
          </div>

          <EaInnerTabs v-model="activeReportTab" :tabs="detailTabs" />

          <div class="tab-body">
            <div v-show="activeReportTab === 'live'" class="tab-pane">
              <div class="ea-split-3 live-grid">
                <div class="live-llm-panel">
                  <div class="ea-row ea-between live-llm-header">
                    <strong style="font-size: 13px">AI 分析（流式）</strong>
                    <EaPill v-if="isRunning" variant="info"><span class="ea-dot-live" />分析中</EaPill>
                    <EaPill v-else-if="currentTask.status === 'completed'" variant="ok">已完成</EaPill>
                    <EaPill v-else-if="currentTask.status === 'failed'" variant="err">失败</EaPill>
                  </div>
                  <div ref="llmScroller" class="live-llm-body">
                    <MarkdownRenderer v-if="currentLlm" :content="currentLlm" />
                    <div v-else-if="isRunning" class="llm-waiting">
                      <NSpin size="small" />
                      <span class="ea-muted" style="margin-left: 8px">等待大模型首条响应...</span>
                    </div>
                    <NEmpty v-else size="small" description="暂无输出" />
                  </div>
                </div>

                <div class="ea-stack live-side">
                  <div class="ea-mon-panel">
                    <h4>当前阶段</h4>
                    <div class="ss-current-phase" :style="{ borderLeftColor: phaseColor(currentTask.phase) }">
                      <span class="ea-dot" :style="{ background: phaseColor(currentTask.phase) }" />
                      <span>{{ phaseLabel(currentTask.phase) }}</span>
                    </div>
                  </div>

                  <div class="ea-mon-panel">
                    <div class="ea-row" style="margin-bottom: 8px">
                      <h4 class="ea-mb0">Agent 工具 / Skill 调用</h4>
                      <EaPill v-if="currentSkillCalls.length" variant="ok" style="margin-left: 6px">
                        {{ currentSkillCalls.filter(c => c.source === 'tool_call').length }} 真实调用
                      </EaPill>
                    </div>
                    <div v-if="!currentSkillCalls.length" class="ea-muted" style="font-size: 12px">Agent 尚未触发任何工具 / Skill 调用</div>
                    <div v-else class="skill-call-list">
                      <div
                        v-for="(call, i) in currentSkillCalls"
                        :key="i"
                        class="scall"
                        :class="{
                          ok: call.completed_ts && !call.error,
                          run: call.source === 'tool_call' && !call.completed_ts,
                          err: call.error,
                        }"
                      >
                        <div class="sc-line1">
                          <span class="sc-name">{{ call.skill_id }}</span>
                          <EaPill v-if="call.source === 'tool_call' && !call.completed_ts" variant="info">运行中</EaPill>
                          <EaPill v-else-if="call.source === 'tool_call' && call.completed_ts && !call.error" variant="ok">完成</EaPill>
                          <EaPill v-else-if="call.error" variant="err">失败</EaPill>
                          <EaPill v-else variant="muted">标记</EaPill>
                        </div>
                        <div v-if="call.args || call.purpose" class="sc-args">
                          {{ call.args || call.purpose }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="ea-mon-panel flex-fill">
                    <h4>事件流</h4>
                    <div ref="eventsScroller" class="events-scroller">
                      <div v-for="(ev, i) in currentEvents" :key="i" class="evt">
                        <span class="evt-ts">{{ formatTs(ev.ts) }}</span>
                        <span>
                          <EaPill variant="muted" style="font-size: 10px; margin-right: 6px">{{ ev.type }}</EaPill>
                          {{ formatEventPayload(ev.payload) }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-show="activeReportTab === 'report'" class="tab-pane">
              <NSpin :show="reportLoading">
                <div v-if="reportDetail" class="report-card">
                  <div class="ea-meta-grid" style="margin-bottom: 16px">
                    <div class="mg"><div class="mg-k">Task</div><div class="mg-v" style="font-size: 13px"><code>{{ reportDetail.task_id }}</code></div></div>
                    <div class="mg"><div class="mg-k">JIRA</div><div class="mg-v" style="font-size: 13px"><a :href="reportDetail.jira_url" target="_blank">{{ reportDetail.jira_key }}</a></div></div>
                    <div v-if="reportDetail.module" class="mg"><div class="mg-k">模块</div><div class="mg-v" style="font-size: 13px">{{ reportDetail.module }}</div></div>
                    <div class="mg"><div class="mg-k">耗时</div><div class="mg-v" style="font-size: 13px">{{ fmtDuration(reportDetail.duration_ms) }}</div></div>
                  </div>
                  <div class="report-meta-extra">
                    <div class="meta-row"><span class="mk">执行</span>
                      <EaPill variant="ok">{{ reportDetail.execution_mode === 'agent' ? 'Agent' : (reportDetail.execution_mode || 'agent') }}</EaPill>
                      <span v-if="reportDetail.tool_call_count != null" class="ea-muted meta-hint">真实工具调用 {{ reportDetail.tool_call_count }} 次</span>
                    </div>
                    <div class="meta-row"><span class="mk">Skill</span>
                      <EaPill v-for="s in reportDetail.skills_used || []" :key="s" variant="warn" style="margin-right: 6px">{{ s }}</EaPill>
                      <span v-if="!(reportDetail.skills_used || []).length" class="ea-muted">无</span>
                    </div>
                  </div>
                  <div v-if="reportDetail.corrections && reportDetail.corrections.length" class="report-corrections">
                    <div class="rc-title">补充信息历史（{{ reportDetail.corrections.length }} 次）</div>
                    <div v-for="(c, i) in reportDetail.corrections" :key="i" class="rc-item">
                      <span class="rc-idx">#{{ i + 1 }}</span>
                      <span class="rc-text">{{ c }}</span>
                    </div>
                  </div>
                  <div class="report-body">
                    <MarkdownRenderer :content="reportDetail.llm_response || ''" />
                  </div>
                </div>
                <NEmpty v-else-if="!reportLoading" description="尚未生成报告" />
              </NSpin>
            </div>

            <div v-show="activeReportTab === 'jira'" class="tab-pane">
              <NEmpty v-if="!currentTask.issue && !reportDetail?.jira" description="未获取到 JIRA 详情（可能 fetch 失败或正在拉取）" />
              <div v-else class="jira-card">
                <div class="jira-row"><span class="mk">Key</span><a :href="(currentTask.issue?.url || reportDetail?.jira?.url) || '#'" target="_blank">{{ currentTask.issue?.key || reportDetail?.jira?.key }}</a></div>
                <div class="jira-row"><span class="mk">标题</span>{{ currentTask.issue?.summary || reportDetail?.jira?.summary }}</div>
                <div class="jira-grid">
                  <div><span class="mk">状态</span>{{ currentTask.issue?.status || reportDetail?.jira?.status || '-' }}</div>
                  <div><span class="mk">优先级</span>{{ currentTask.issue?.priority || reportDetail?.jira?.priority || '-' }}</div>
                  <div><span class="mk">经办</span>{{ currentTask.issue?.assignee || reportDetail?.jira?.assignee || '-' }}</div>
                  <div><span class="mk">报告人</span>{{ currentTask.issue?.reporter || reportDetail?.jira?.reporter || '-' }}</div>
                </div>
                <div v-if="(currentTask.issue?.description || reportDetail?.jira?.description)" class="jira-desc">
                  <div class="mk" style="margin-bottom: 6px">描述</div>
                  <pre>{{ currentTask.issue?.description || reportDetail?.jira?.description }}</pre>
                </div>
                <div v-if="(currentTask.issue?.attachments || reportDetail?.jira?.attachments || []).length" class="jira-att">
                  <div class="mk" style="margin-bottom: 6px">附件</div>
                  <a
                    v-for="a in (currentTask.issue?.attachments || reportDetail?.jira?.attachments || [])"
                    :key="a.id"
                    :href="a.url"
                    target="_blank"
                    class="att-item"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    {{ a.filename }}
                    <span v-if="a.size" class="att-size">({{ (a.size / 1024).toFixed(1) }} KB)</span>
                  </a>
                </div>
              </div>
            </div>

            <div v-show="activeReportTab === 'log'" class="tab-pane">
              <NSpin :show="logLoading">
                <div class="log-header">
                  <span class="ea-muted log-hint">日志文件: <code>{{ currentTaskId }}.log</code>（位于 hermes-web-ui 数据目录）</span>
                  <NSpace size="small">
                    <NButton size="small" @click="loadLog">刷新</NButton>
                    <NButton size="small" type="primary" :disabled="!taskLog" @click="downloadLog">下载日志</NButton>
                  </NSpace>
                </div>
                <pre class="log-body">{{ taskLog || '(无日志或未加载)' }}</pre>
              </NSpin>
            </div>
          </div>

          <footer class="task-footer">
            <NSpace size="small" wrap>
              <NPopover trigger="click" placement="top">
                <template #trigger>
                  <NButton type="primary" :disabled="!currentLlm && !reportDetail">
                    <template #icon>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </template>
                    保存到本地
                  </NButton>
                </template>
                <div style="display: flex; flex-direction: column; gap: 6px; min-width: 160px;">
                  <NButton size="small" block @click="saveReportLocally('md')">保存为 Markdown</NButton>
                  <NButton size="small" block @click="saveReportLocally('json')">保存为 JSON</NButton>
                </div>
              </NPopover>

              <NButton tertiary :disabled="!modelProviderReady" @click="handoffToAgent('single')">
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </template>
                在 AI 对话中继续讨论
              </NButton>

              <NButton
                v-if="isRunning || isPending"
                type="warning"
                @click="stopOrCancelCurrentTask"
              >
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12"/></svg>
                </template>
                {{ isRunning ? '强行中断当前任务' : '取消等待中的任务' }}
              </NButton>

              <NButton :disabled="!modelProviderReady || isRunning || isPending || !currentTaskId" @click="openContinue">
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                </template>
                补充信息继续分析
              </NButton>
              <NButton :disabled="isRunning || currentTask.status !== 'completed'" @click="openDistill">
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/></svg>
                </template>
                沉淀为知识库 / Skill
                <EaPill variant="warn" style="margin-left: 6px">即将上线</EaPill>
              </NButton>
              <NButton tertiary @click="router.push({ name: 'tahp.reports' })">
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </template>
                所有报告
              </NButton>
            </NSpace>
          </footer>
        </EaCard>
      </div>
    </div>

    <!-- ────── 补充信息继续分析弹窗 ────── -->
    <NModal
      v-model:show="showJiraConfigDialog"
      preset="dialog"
      :closable="jiraConfigReady"
      :mask-closable="jiraConfigReady"
      title="配置 JIRA 账号"
      positive-text="保存配置"
      :negative-text="jiraConfigReady ? '取消' : undefined"
      style="width: 520px"
      @positive-click="saveJiraConfig"
    >
      <NAlert type="warning" :show-icon="false" style="margin-bottom: 12px">
        进入智能诊断前必须先配置一次 JIRA 凭证（TAHP_JIRA_USERNAME + TAHP_JIRA_PASSWORD）。
      </NAlert>
      <NForm label-placement="top">
        <NFormItem label="TAHP_JIRA_USERNAME">
          <NInput v-model:value="jiraConfigForm.username" placeholder="请输入 Jira 用户名" />
        </NFormItem>
        <NFormItem label="TAHP_JIRA_PASSWORD">
          <NInput v-model:value="jiraConfigForm.password" type="password" show-password-on="click" placeholder="请输入 Jira 密码" />
        </NFormItem>
      </NForm>
    </NModal>

    <NModal
      v-model:show="showContinueDialog"
      preset="dialog"
      title="补充信息继续分析"
      positive-text="开始分析"
      negative-text="取消"
      style="width: 580px"
      @positive-click="submitContinue"
    >
      <div class="modal-hint">
        将基于<strong>前次分析的完整上下文 + 你的补充信息</strong>重新生成分析报告，原任务报告会保留。
      </div>
      <NInput
        v-model:value="continueText"
        type="textarea"
        placeholder="补充新发现的现象、最新日志结论、复现步骤变化、已排除可能..."
        :autosize="{ minRows: 5, maxRows: 12 }"
      />
    </NModal>

    <!-- ────── 知识沉淀弹窗（占位） ────── -->
    <NModal
      v-model:show="showDistillDialog"
      preset="dialog"
      title="沉淀为知识库 / Skill"
      positive-text="提交记录"
      negative-text="取消"
      style="width: 540px"
      @positive-click="submitDistill"
    >
      <NAlert type="info" :show-icon="false" style="margin-bottom: 12px">
        当前版本仅会<strong>记录沉淀请求</strong>到 <code>logs/bug-analysis/distill-pending.json</code>，
        实际的 Skill / 知识库条目生成将在后续版本上线。
      </NAlert>
      <div class="modal-body-text">
        请简述这条 Bug 分析中值得沉淀为长期知识的核心结论（可选）：
      </div>
      <NInput
        v-model:value="distillNote"
        type="textarea"
        placeholder="如：某场景下 RILJ 异常的固定排查路径；某类亮度问题的策略影响识别要点..."
        :autosize="{ minRows: 3, maxRows: 8 }"
      />
    </NModal>
  </div>
</template>

<style scoped lang="scss">
.bug-analysis-root {
  :deep(.model-provider-banner) { margin-bottom: 12px; }
}

.bug-split { align-items: stretch; min-height: 0; }
.bug-left { min-height: 0; }
.bug-tasks-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.task-scroll { max-height: calc(100vh - 520px); min-height: 240px; }

.mode-toggle {
  display: flex; gap: 4px; background: var(--surface-2); padding: 3px; border-radius: 10px;
  .mode-idle { background: none; border: none; color: var(--muted); cursor: pointer; font-family: inherit; font-weight: 600; }
}

.exec-mode-banner {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px; margin: 0 0 14px;
  border-radius: 10px; cursor: pointer; font-size: 11.5px; color: var(--text);
  background: linear-gradient(90deg, color-mix(in srgb, var(--success) 10%, transparent), color-mix(in srgb, var(--info) 8%, transparent));
  border: 1px solid color-mix(in srgb, var(--success) 22%, transparent);
  &.agent-mode .emb-dot { background: var(--success); box-shadow: 0 0 6px color-mix(in srgb, var(--success) 55%, transparent); }
  .emb-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--info); flex-shrink: 0; }
  .emb-text { flex: 1; strong { font-weight: 700; } }
  .emb-link { color: var(--accent); text-decoration: underline; font-weight: 600; flex-shrink: 0; }
}

.field-hint { font-size: 11px; color: var(--muted); margin-top: 4px; }
.info-icon { color: var(--faint); cursor: help; margin-left: 4px; vertical-align: middle; }
.action-row { margin-top: 4px; gap: 8px; }
.alert-sub { margin-top: 4px; color: var(--muted); font-size: 12px; }
.alert-link { cursor: pointer; color: var(--accent); }

.preview-summary { font-size: 13px; font-weight: 600; color: var(--text); }
.preview-meta { gap: 14px; margin-top: 8px; font-size: 12px; color: var(--muted); }
.pv-link { color: var(--accent); text-decoration: none; font-weight: 600; &:hover { text-decoration: underline; } }

.jql-summary { font-size: 12px; margin-bottom: 8px; color: var(--text); }
.jql-item {
  display: flex; align-items: center; gap: 10px; padding: 6px 0;
  border-bottom: 1px dashed var(--line); font-size: 12px;
  &:last-child { border-bottom: none; }
  .jql-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
}

.ti-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ti-key { font-family: ui-monospace, monospace; font-size: 12px; font-weight: 700; color: var(--accent); text-decoration: none; }
.ti-title { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-meta { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--faint); }
.ti-badge { background: var(--warn-soft); color: var(--warn); padding: 1px 6px; border-radius: 6px; font-weight: 600; &.ti-batch { background: var(--violet-bg); color: var(--violet-fg); } }

.bug-main-wrap { min-height: 0; display: flex; flex-direction: column; }
.bug-main { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.bug-detail { min-height: 520px; }

.bug-empty {
  align-items: center; text-align: center; padding: 48px 24px;
  .empty-illus { opacity: 0.45; color: var(--faint); margin-bottom: 8px; }
  h2 { margin: 0; font-size: 18px; font-weight: 700; color: var(--head); }
  p { color: var(--muted); font-size: 13px; margin: 8px 0 0; max-width: 520px; }
}
.empty-tips { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; max-width: 480px; width: 100%; }
.tip { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text); text-align: left; }
.tip-num {
  width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center;
  background: linear-gradient(135deg, var(--accent), var(--violet-ic)); color: #fff; font-size: 11px; font-weight: 800;
}

.mono { font-family: ui-monospace, monospace; font-size: 11px; color: var(--faint); }
.job-jql { font-size: 12px; color: var(--text); background: var(--bg); padding: 8px 10px; border-radius: 10px; word-break: break-all; }
.job-progress { margin: 16px 0; }
.jp-stats { margin-top: 6px; font-size: 12px; color: var(--muted); }
.stat-ok { color: var(--success); }
.stat-err { color: var(--error); }
.job-tasks { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.ea-task-item.compact { padding: 10px 12px; }

.task-head { margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.task-head-left { min-width: 0; gap: 12px; flex-wrap: wrap; }
.task-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 420px; }
.task-id { background: var(--bg); padding: 2px 6px; border-radius: 6px; }

.task-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-shrink: 0; }
.tp-text { font-size: 11px; min-width: 32px; text-align: right; }

.tab-body { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.tab-pane { flex: 1; min-height: 320px; overflow-y: auto; padding-bottom: 8px; scrollbar-width: thin; }

.live-grid { min-height: 360px; height: 100%; }
.live-llm-panel {
  display: flex; flex-direction: column; min-height: 260px; background: var(--bg);
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
}
.live-llm-header { padding: 12px 14px; border-bottom: 1px solid var(--line); background: var(--surface); }
.live-llm-body { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 16px; font-size: 13.5px; line-height: 1.7; }
.llm-waiting { display: flex; align-items: center; padding: 20px; }

.live-side { gap: 12px; min-height: 0; }
.flex-fill { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.ss-current-phase {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  background: var(--surface); border-radius: 8px; border-left: 3px solid var(--line-strong);
  font-size: 13px; font-weight: 600; color: var(--text);
}

.skill-call-list { display: flex; flex-direction: column; gap: 6px; max-height: 220px; overflow-y: auto; }
.scall {
  border-left: 2px solid var(--line-strong); padding: 6px 10px; border-radius: 0 8px 8px 0;
  background: var(--bg); font-size: 12px;
  &.ok { border-left-color: var(--success); }
  &.run { border-left-color: var(--info); }
  &.err { border-left-color: var(--error); background: var(--error-soft); }
}
.sc-line1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sc-name { font-family: ui-monospace, monospace; font-weight: 600; flex: 1; word-break: break-all; color: var(--text); }
.sc-args { color: var(--muted); font-size: 11px; margin-top: 2px; word-break: break-all; font-family: ui-monospace, monospace; }

.events-scroller { flex: 1; min-height: 0; overflow-y: auto; }
.evt {
  display: grid; grid-template-columns: auto 1fr; gap: 8px; padding: 8px 0;
  border-bottom: 1px dashed var(--line); font-size: 12px; color: var(--text);
  &:last-child { border: none; }
}
.evt-ts { color: var(--faint); font-family: ui-monospace, monospace; font-size: 11px; }

.report-meta-extra { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; font-size: 12.5px; }
.meta-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.meta-hint { margin-left: 6px; font-size: 11.5px; }
.mk { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; font-weight: 700; min-width: 48px; }

.report-corrections {
  margin-bottom: 16px; padding: 10px 14px; background: var(--warn-soft);
  border-left: 3px solid var(--warn); border-radius: 8px;
}
.rc-title { font-size: 12px; font-weight: 700; color: var(--warn); margin-bottom: 6px; }
.rc-item { font-size: 12px; padding: 3px 0; }
.rc-idx { display: inline-block; min-width: 28px; color: var(--warn); font-weight: 700; }
.rc-text { color: var(--text); }
.report-body { font-size: 13.5px; line-height: 1.7; }

.jira-card { font-size: 13px; }
.jira-row {
  display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px dashed var(--line); align-items: center;
  a { color: var(--accent); }
}
.jira-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px 16px; padding: 10px 0;
  > div { display: flex; gap: 8px; align-items: center; }
}
.jira-desc pre {
  background: var(--bg); padding: 10px 12px; border-radius: 10px; font-size: 12px; line-height: 1.6;
  max-height: 360px; overflow: auto; margin: 0; white-space: pre-wrap; word-break: break-word;
}
.jira-att { margin-top: 14px; display: flex; flex-direction: column; gap: 4px; }
.att-item {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--accent);
  text-decoration: none; padding: 4px 8px; border-radius: 8px; background: var(--accent-soft);
  &:hover { filter: brightness(0.98); }
  .att-size { color: var(--muted); font-size: 11px; }
}

.log-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; gap: 12px; flex-wrap: wrap; }
.log-hint code { font-size: 11px; }
.log-body {
  background: #1b1e2b; color: #e7e9f2; padding: 14px 16px; border-radius: 14px;
  font-family: ui-monospace, monospace; font-size: 12px; line-height: 1.55;
  white-space: pre-wrap; word-break: break-all; max-height: 60vh; overflow: auto; margin: 0;
}

.task-footer {
  margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); flex-shrink: 0;
}

.popover-body { font-size: 12.5px; line-height: 1.7; color: var(--text); max-width: 420px; }
.popover-title { font-weight: 700; margin-bottom: 8px; }
.popover-section { margin-bottom: 8px; }
.popover-muted { color: var(--muted); }
.popover-foot { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--line); color: var(--faint); font-size: 11px; }

.modal-hint { margin-bottom: 8px; font-size: 12px; color: var(--muted); }
.modal-body-text { margin-bottom: 8px; font-size: 13px; color: var(--text); }

code {
  background: var(--surface-2); padding: 1px 5px; border-radius: 4px;
  font-size: 0.9em; font-family: ui-monospace, monospace;
}

@media (max-width: 1100px) {
  .task-scroll { max-height: 320px; }
  .task-title { max-width: 100%; }
}
</style>