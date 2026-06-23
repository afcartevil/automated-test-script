<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NInput, NButton, NSpin, NEmpty, NAlert,
  NModal, NScrollbar, NProgress, NPopover, useMessage, NTooltip,
  NSpace, NForm, NFormItem, NCheckbox,
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
  listBugReports, deleteBugReport,
  type JiraIssueDetail, type JqlPreview, type BugReport, type BugReportSummary, type JiraUserConfig,
} from '@/api/tahp/bug-analysis'
import {
  extractBugAnalysisReportBody,
  stripBugStageMarkers,
  parseHistoryStageDetails,
  reportToBugTask,
  type HistoryStageDetail,
} from '@/utils/bug-analysis-report'
import {
  skillAssociation,
  mergeIntoSkill,
  createUpgradeDraft,
  generateSkillDraft,
  type SkillAssociationItem,
} from '@/api/tahp/knowledge'

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
// 已启动任务/批次 / 历史任务展示
// ─────────────────────────────────────────────────────────────────────────────
type TaskListMode = 'recent' | 'history'
const taskListMode = ref<TaskListMode>('recent')
const historyReports = ref<BugReportSummary[]>([])
const historyListLoading = ref(false)
const historySelectedId = ref<string | null>(null)
const historyTask = ref<import('@/api/tahp/bug-analysis').BugTask | null>(null)
const historyStageDetails = ref<Record<string, HistoryStageDetail>>({})
const isHistoryView = computed(() => !!historySelectedId.value)

const currentTaskId = computed(() =>
  isHistoryView.value ? historySelectedId.value : store.selectedTaskId,
)
const currentTask = computed(() => {
  if (isHistoryView.value) return historyTask.value
  return currentTaskId.value ? store.tasks[currentTaskId.value] : null
})
const currentLlm = computed(() => {
  if (isHistoryView.value) {
    const raw = reportDetail.value?.llm_response || historyTask.value?.llm_response || ''
    return raw ? stripBugStageMarkers(raw) : ''
  }
  return currentTaskId.value ? store.llmText(currentTaskId.value) : ''
})
const currentReasoning = computed(() => {
  if (isHistoryView.value) return ''
  return currentTaskId.value ? store.reasoningText(currentTaskId.value) : ''
})

const currentJobId = computed(() => store.selectedJobId)
const currentJob = computed(() => currentJobId.value ? store.jobs[currentJobId.value] : null)

const isRunning = computed(() => !isHistoryView.value && currentTask.value?.status === 'running')
const isPending = computed(() => !isHistoryView.value && currentTask.value?.status === 'pending')

// 详情 Tab：选择已完成报告时载入
const activeReportTab = ref<'live' | 'report' | 'jira' | 'log'>('live')
const reportDetail = ref<BugReport | null>(null)
const reportLoading = ref(false)
const taskLog = ref<string>('')
const logLoading = ref(false)

const reportMarkdown = computed(() => {
  if (!reportDetail.value) return ''
  const raw = reportDetail.value.report_body || reportDetail.value.llm_response || ''
  return extractBugAnalysisReportBody(raw)
})

// 补充信息弹窗
const showContinueDialog = ref(false)
const continueText = ref('')

// 知识沉淀弹窗
const showDistillDialog = ref(false)
const distillStep = ref<'deposit' | 'skill'>('deposit')
const distillNote = ref('')
const distillContent = ref('')
const distillLinkSkill = ref(true)
const distillSubmitting = ref(false)
const distilledEntry = ref<{ id: string; module: string; func_type: string } | null>(null)
const distillAssociations = ref<SkillAssociationItem[]>([])
const distillOverall = ref<'enhance_existing' | 'create_new'>('create_new')
const distillLoadingAssoc = ref(false)
const distillSkillBusy = ref('')

// ─────────────────────────────────────────────────────────────────────────────
// 阶段名映射 — 用于侧栏显示更友好的标签
// ─────────────────────────────────────────────────────────────────────────────
const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  PREPARING:          { label: '准备任务',       color: 'var(--faint)' },
  CONNECTING_AGENT:   { label: '连接 Agent',     color: 'var(--info)' },
  STARTING:           { label: '启动中',         color: 'var(--faint)' },
  FETCH_JIRA_INFO:    { label: '拉取 JIRA 信息', color: 'var(--info)' },
  DOWNLOAD_JIRA_LOGS: { label: '下载 JIRA 日志', color: 'var(--success)' },
  MATCH_SKILLS:       { label: '匹配 Skill',     color: 'var(--violet-ic)' },
  ANALYZING:          { label: '大模型分析',     color: 'var(--warn)' },
  GENERATING_REPORT:  { label: '生成分析报告',   color: 'var(--info)' },
  COMPLETED:          { label: '已完成',         color: 'var(--success)' },
  FAILED:             { label: '失败',           color: 'var(--error)' },
  CANCELLED:          { label: '已取消',         color: 'var(--violet-ic)' },
  QUEUED:             { label: '等待中',         color: 'var(--warn)' },
  BATCH_RUNNING:      { label: '批量执行中',     color: 'var(--info)' },
}

const BUG_STAGE_ORDER = [
  'FETCH_JIRA_INFO', 'DOWNLOAD_JIRA_LOGS', 'MATCH_SKILLS', 'ANALYZING', 'GENERATING_REPORT',
] as const
const PREP_PHASES = new Set(['STARTING', 'PREPARING', 'CONNECTING_AGENT', 'QUEUED'])

const detailTabs = computed(() => [
  { key: 'live', label: isHistoryView.value ? '分析过程' : '实时进展' },
  {
    key: 'report',
    label: '分析报告',
    disabled: !isHistoryView.value
      && currentTask.value?.status === 'running'
      && !currentTask.value?.completed_at,
  },
  { key: 'jira', label: 'JIRA 详情' },
  { key: 'log', label: '任务日志' },
])

const BUG_STAGE_STEP_IDS = [
  'fetch-jira', 'download-logs', 'match-skills', 'analyze', 'generate-report',
] as const

function allStageDetailsSuccess(tid: string): boolean {
  const detailMap = isHistoryView.value
    ? historyStageDetails.value
    : store.stageDetailMap(tid)
  return BUG_STAGE_STEP_IDS.every(id => detailMap[id]?.status === 'success')
}

const bugStages = computed(() => {
  const phase = currentTask.value?.phase
  const status = currentTask.value?.status
  const tid = currentTaskId.value
  const idx = phase && !PREP_PHASES.has(phase)
    ? BUG_STAGE_ORDER.indexOf(phase as typeof BUG_STAGE_ORDER[number])
    : -1
  const stagesComplete = tid ? allStageDetailsSuccess(tid) : false
  const allDone = status === 'completed' || phase === 'COMPLETED' || stagesComplete
  return BUG_STAGE_ORDER.map((key, i) => ({
    key,
    label: PHASE_LABELS[key]?.label || key,
    done: allDone || (idx >= 0 && i < idx),
    active: !allDone && phase === key,
  }))
})

const displayProgress = computed(() => {
  const task = currentTask.value
  if (!task) return 0
  if (task.status === 'completed' || task.phase === 'COMPLETED') return 100
  if (bugStages.value.every(s => s.done)) return 100
  return typeof task.progress === 'number' ? task.progress : 0
})

function phaseLabel(phase?: string): string {
  if (!phase) return '准备中'
  return PHASE_LABELS[phase]?.label || phase
}

function phaseColor(phase?: string): string {
  if (!phase) return 'var(--faint)'
  return PHASE_LABELS[phase]?.color || 'var(--faint)'
}

function pickStr(...vals: Array<string | number | undefined | null>): string | undefined {
  for (const v of vals) {
    if (v == null) continue
    const s = String(v).trim()
    if (s) return s
  }
  return undefined
}

interface JiraDisplayInfo {
  key?: string
  url?: string
  summary?: string
  status?: string
  priority?: string
  assignee?: string
  reporter?: string
  description?: string
  commentCount?: string
  attachmentCount?: string
  fetchOk?: string
  skillUsed?: string
  attachments?: Array<{ id: string; filename: string; url: string; size?: number }>
  hasData: boolean
}

const jiraDisplayInfo = computed((): JiraDisplayInfo | null => {
  const task = currentTask.value
  if (!task) return null

  const tid = currentTaskId.value
  const fetchFields = tid
    ? (isHistoryView.value
      ? historyStageDetails.value['fetch-jira']?.fields
      : store.stageDetailMap(tid)['fetch-jira']?.fields)
    : undefined
  const f = fetchFields || {}
  const issue = task.issue
  const reportJira = reportDetail.value?.jira
  const preview = jiraPreview.value?.key === task.jira_key ? jiraPreview.value : null

  const key = pickStr(task.jira_key, f.jira_key, reportJira?.key, preview?.key)
  const url = pickStr(task.jira_url, reportJira?.url, preview?.url)
  const summary = pickStr(issue?.summary, reportJira?.summary, f.issue_summary, preview?.summary, task.title)
  const status = pickStr(issue?.status, reportJira?.status, f.status, preview?.status)
  const priority = pickStr(issue?.priority, reportJira?.priority, f.priority, preview?.priority)
  const assignee = pickStr(issue?.assignee, reportJira?.assignee, f.assignee, preview?.assignee)
  const reporter = pickStr(issue?.reporter, reportJira?.reporter, f.reporter, preview?.reporter)
  const description = pickStr(
    issue?.description,
    reportJira?.description,
    f.description,
    f.description_preview,
    preview?.description,
  )
  const commentCount = pickStr(
    issue?.comments?.length ? String(issue.comments.length) : undefined,
    reportJira?.commentCount != null ? String(reportJira.commentCount) : undefined,
    f.comment_count,
  )
  const attachmentCount = pickStr(
    issue?.attachments?.length ? String(issue.attachments.length) : undefined,
    reportJira?.attachmentCount != null ? String(reportJira.attachmentCount) : undefined,
    f.attachment_count,
  )
  const fetchOk = pickStr(f.fetch_ok, reportJira?.fetch_ok)
  const skillUsed = pickStr(f.skill_used, reportJira?.skill_used)
  const attachments = (issue?.attachments?.length ? issue.attachments : reportJira?.attachments) || []

  const hasData = !!(
    key || summary || status || priority || assignee || reporter || description
    || commentCount || attachmentCount || fetchFields || reportJira || preview
  )

  return {
    key,
    url,
    summary,
    status,
    priority,
    assignee,
    reporter,
    description,
    commentCount,
    attachmentCount,
    fetchOk,
    skillUsed,
    attachments: attachments.length ? attachments : undefined,
    hasData,
  }
})

function statusPillVariant(status?: string): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  if (status === 'completed') return 'ok'
  if (status === 'failed') return 'err'
  if (status === 'cancelled') return 'warn'
  if (status === 'running') return 'info'
  if (status === 'pending') return 'warn'
  return 'muted'
}

function fmtDuration(ms?: number): string {
  if (!ms && ms !== 0) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

// 自动滚动 LLM 流到底部
const llmScroller = ref<HTMLElement | null>(null)
watch([currentLlm, currentReasoning], async () => {
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
    clearHistoryView()
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
    clearHistoryView()
    activeReportTab.value = 'live'
    message.success(`批量分析已启动: 共 ${resp.total} 单`)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 操作：任务列表（最近 / 历史）/ 切换任务 / 加载报告
// ─────────────────────────────────────────────────────────────────────────────
async function loadHistoryReports() {
  historyListLoading.value = true
  try {
    historyReports.value = await listBugReports()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    historyListLoading.value = false
  }
}

function switchTaskListMode(mode: TaskListMode) {
  taskListMode.value = mode
  if (mode === 'history') loadHistoryReports()
}

function clearHistoryView() {
  historySelectedId.value = null
  historyTask.value = null
  historyStageDetails.value = {}
}

async function selectHistoryTask(taskId: string) {
  historySelectedId.value = taskId
  store.selectTask(null)
  store.selectJob(null)
  reportDetail.value = null
  taskLog.value = ''
  historyTask.value = null
  historyStageDetails.value = {}
  activeReportTab.value = 'report'
  reportLoading.value = true
  try {
    const report = await getBugReport(taskId)
    reportDetail.value = report
    historyTask.value = reportToBugTask(report)
    historyStageDetails.value = parseHistoryStageDetails(report.llm_response || '')
  } catch (err) {
    message.error((err as Error).message)
    clearHistoryView()
  } finally {
    reportLoading.value = false
  }
}

async function deleteHistoryTask(taskId: string, ev?: Event) {
  ev?.stopPropagation()
  if (!window.confirm('确定永久删除该历史记录？将删除报告 JSON、提示词目录与任务日志。')) return
  try {
    await deleteBugReport(taskId)
    message.success('历史记录已删除')
    if (historySelectedId.value === taskId) {
      clearHistoryView()
      reportDetail.value = null
      taskLog.value = ''
    }
    if (store.selectedTaskId === taskId) store.selectTask(null)
    await Promise.all([loadHistoryReports(), store.refresh()])
  } catch (err) {
    message.error((err as Error).message)
  }
}

function selectTask(taskId: string) {
  clearHistoryView()
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
  if ((tab === 'report' || tab === 'jira') && currentTaskId.value && !reportDetail.value) loadReport()
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
      (reportMarkdown.value || extractBugAnalysisReportBody(llm) || '(无内容)'),
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
    clearHistoryView()
    activeReportTab.value = 'live'
    showContinueDialog.value = false
    message.success(`补充分析任务已启动: ${resp.task_id}`)
  } catch (err) {
    message.error((err as Error).message)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 知识沉淀：① 沉淀为知识条目 ② 关联 / 生成 Skill
// ─────────────────────────────────────────────────────────────────────────────
function openDistill() {
  distillStep.value = 'deposit'
  distillNote.value = ''
  distillContent.value = reportMarkdown.value || ''
  distillLinkSkill.value = true
  distillSubmitting.value = false
  distilledEntry.value = null
  distillAssociations.value = []
  distillSkillBusy.value = ''
  showDistillDialog.value = true
}

async function submitDeposit() {
  if (!currentTaskId.value) return
  if (!distillContent.value.trim()) { message.warning('知识条目正文不能为空'); return }
  distillSubmitting.value = true
  try {
    const r = await distillToKnowledge(currentTaskId.value, {
      note: distillNote.value || undefined,
      content: distillContent.value,
      to_knowledge: true,
    })
    distilledEntry.value = r.entry
    if (distillLinkSkill.value && r.entry) {
      distillStep.value = 'skill'
      await loadDistillAssociations()
    } else {
      message.success(r.message || '已沉淀为知识条目（待审核）')
      showDistillDialog.value = false
    }
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    distillSubmitting.value = false
  }
}

async function loadDistillAssociations() {
  if (!distilledEntry.value) return
  distillLoadingAssoc.value = true
  try {
    const r = await skillAssociation({
      entry_ids: [distilledEntry.value.id],
      module: distilledEntry.value.module,
      func_type: distilledEntry.value.func_type,
      text: currentTask.value?.title || '',
    })
    distillAssociations.value = r.associations
    distillOverall.value = r.overall_recommendation
  } catch (err) {
    message.error('关联检索失败：' + (err as Error).message)
  } finally {
    distillLoadingAssoc.value = false
  }
}

async function distillEnhance(a: SkillAssociationItem) {
  if (!distilledEntry.value) return
  distillSkillBusy.value = a.id
  try {
    if (a.type === 'draft' && a.can_merge) {
      await mergeIntoSkill(a.id, [distilledEntry.value.id])
      message.success(`已补充到草稿「${a.display_name}」`)
    } else {
      await createUpgradeDraft(a.id, [distilledEntry.value.id])
      message.success(`已为「${a.display_name}」生成升级草案，请到 Skill 工坊审核`)
    }
    showDistillDialog.value = false
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    distillSkillBusy.value = ''
  }
}

async function distillCreateNew() {
  if (!distilledEntry.value) return
  distillSkillBusy.value = '__new__'
  try {
    const r = await generateSkillDraft({
      module: distilledEntry.value.module,
      func_type: distilledEntry.value.func_type,
      entry_ids: [distilledEntry.value.id],
      generated_by: 'bug-analysis-distill',
    })
    if (r.llm_error) message.warning('草稿已创建，但 LLM 生成存在问题：' + r.llm_error)
    else message.success('已生成新的 Skill 草稿，请到 Skill 工坊审核')
    showDistillDialog.value = false
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    distillSkillBusy.value = ''
  }
}

function goToWorkshop() {
  showDistillDialog.value = false
  router.push({ name: 'tahp.knowledge' })
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
  await loadHistoryReports()
  const queryTid = route.query.task_id as string | undefined
  if (queryTid) {
    if (store.tasks[queryTid]) {
      selectTask(queryTid)
    } else if (historyReports.value.some(r => r.task_id === queryTid)) {
      taskListMode.value = 'history'
      await selectHistoryTask(queryTid)
    }
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

const liveStreamHint = computed(() => {
  if (currentLlm.value || currentReasoning.value) return null
  if (!isRunning.value) return null
  return '等待 Agent 响应...'
})
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
          <div class="task-list-head ea-row ea-between">
            <div class="mode-toggle">
              <button
                type="button"
                class="ea-btn-sm"
                :class="taskListMode === 'recent' ? 'ea-btn-soft' : 'mode-idle'"
                @click="switchTaskListMode('recent')"
              >最近任务</button>
              <button
                type="button"
                class="ea-btn-sm"
                :class="taskListMode === 'history' ? 'ea-btn-soft' : 'mode-idle'"
                @click="switchTaskListMode('history')"
              >历史任务</button>
            </div>
            <EaPill variant="muted">
              {{ taskListMode === 'recent' ? store.recentTasks.length : historyReports.length }} 条
            </EaPill>
          </div>

          <div class="task-list-body">
          <template v-if="taskListMode === 'recent'">
            <NEmpty v-if="!store.recentTasks.length" size="small" description="还没有任务" />
            <NScrollbar v-else class="task-scroll" trigger="none">
              <div class="ea-tasklist">
                <button
                  v-for="t in store.recentTasks"
                  :key="t.task_id"
                  type="button"
                  class="ea-task-item"
                  :class="{ active: !isHistoryView && currentTaskId === t.task_id, [`status-${t.status}`]: true }"
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
          </template>

          <template v-else>
            <NSpin :show="historyListLoading" class="task-list-spin">
              <NEmpty v-if="!historyListLoading && !historyReports.length" size="small" description="暂无历史记录" />
              <NScrollbar v-else class="task-scroll" trigger="none">
                <div class="ea-tasklist">
                  <div
                    v-for="r in historyReports"
                    :key="r.task_id"
                    class="history-task-row"
                  >
                    <button
                      type="button"
                      class="ea-task-item"
                      :class="{ active: historySelectedId === r.task_id, [`status-${r.status || 'completed'}`]: true }"
                      @click="selectHistoryTask(r.task_id)"
                    >
                      <div class="ti-top">
                        <span class="ti-key">{{ r.jira_key || r.task_id }}</span>
                        <EaPill :variant="statusPillVariant(r.status)">{{ r.status || 'completed' }}</EaPill>
                      </div>
                      <div class="ti-title">{{ r.title || r.task_id }}</div>
                      <div class="ti-meta">
                        <span class="ea-muted">{{ r.completed_at?.slice(0, 16) || r.started_at?.slice(0, 16) || '-' }}</span>
                        <span v-if="r.skills_used?.length" class="ti-badge">{{ r.skills_used.length }} skill</span>
                      </div>
                    </button>
                    <NButton
                      size="tiny"
                      quaternary
                      type="error"
                      class="history-del-btn"
                      @click="deleteHistoryTask(r.task_id, $event)"
                    >删除</NButton>
                  </div>
                </div>
              </NScrollbar>
            </NSpin>
          </template>
          </div>
        </EaCard>
      </div>

      <!-- Right: main panel -->
      <div class="bug-main-wrap">
        <EaCard v-if="!currentTaskId && !currentJob" class="bug-main bug-empty">
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
              <EaPill v-if="isHistoryView" variant="muted">历史记录</EaPill>
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

          <div v-if="currentTask" class="task-progress">
            <NProgress :percentage="displayProgress" :show-indicator="false" :height="6" :color="phaseColor(currentTask.phase)" />
            <span class="ea-muted tp-text">{{ displayProgress }}%</span>
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
            <div v-show="activeReportTab === 'live'" class="tab-pane tab-pane-live">
              <div class="live-llm-panel live-llm-panel-full">
                <div class="ea-row ea-between live-llm-header">
                  <strong style="font-size: 13px">AI 分析（流式）</strong>
                  <EaPill v-if="isRunning" variant="info"><span class="ea-dot-live" />分析中</EaPill>
                  <EaPill v-else-if="isHistoryView || currentTask.status === 'completed'" variant="ok">已完成</EaPill>
                  <EaPill v-else-if="currentTask.status === 'failed'" variant="err">失败</EaPill>
                </div>
                <div ref="llmScroller" class="live-llm-body">
                  <div v-if="currentReasoning && !currentLlm" class="reasoning-block">
                    <div class="reasoning-label ea-muted">Agent 推理中</div>
                    <pre class="reasoning-text">{{ currentReasoning }}</pre>
                  </div>
                  <MarkdownRenderer v-if="currentLlm" :content="currentLlm" />
                  <div v-else-if="liveStreamHint" class="llm-waiting">
                    <NSpin size="small" />
                    <span class="ea-muted" style="margin-left: 8px">{{ liveStreamHint }}</span>
                  </div>
                  <NEmpty v-else size="small" description="暂无输出" />
                </div>
              </div>
            </div>

            <div v-show="activeReportTab === 'report'" class="tab-pane tab-pane-report">
              <NSpin :show="reportLoading" class="report-spin-wrap">
                <NScrollbar v-if="reportDetail && reportMarkdown" class="report-body-scroll" trigger="none">
                  <div class="report-markdown-inner">
                    <MarkdownRenderer :content="reportMarkdown" />
                  </div>
                </NScrollbar>
                <NEmpty v-else-if="!reportLoading" description="尚未生成报告" />
              </NSpin>
            </div>

            <div v-show="activeReportTab === 'jira'" class="tab-pane tab-pane-jira">
              <NSpin :show="reportLoading && !jiraDisplayInfo?.hasData">
                <NEmpty v-if="!jiraDisplayInfo?.hasData" description="尚未获取到 JIRA 详情（Agent 拉取中或未开始）" />
                <div v-else class="jira-card jira-scroll">
                  <div v-if="jiraDisplayInfo.key" class="jira-row">
                    <span class="mk">Key</span>
                    <a v-if="jiraDisplayInfo.url" :href="jiraDisplayInfo.url" target="_blank">{{ jiraDisplayInfo.key }}</a>
                    <span v-else>{{ jiraDisplayInfo.key }}</span>
                  </div>
                  <div v-if="jiraDisplayInfo.summary" class="jira-row">
                    <span class="mk">标题</span><span>{{ jiraDisplayInfo.summary }}</span>
                  </div>
                  <div class="jira-grid">
                    <div v-if="jiraDisplayInfo.status"><span class="mk">状态</span>{{ jiraDisplayInfo.status }}</div>
                    <div v-if="jiraDisplayInfo.priority"><span class="mk">优先级</span>{{ jiraDisplayInfo.priority }}</div>
                    <div v-if="jiraDisplayInfo.assignee"><span class="mk">经办</span>{{ jiraDisplayInfo.assignee }}</div>
                    <div v-if="jiraDisplayInfo.reporter"><span class="mk">报告人</span>{{ jiraDisplayInfo.reporter }}</div>
                    <div v-if="jiraDisplayInfo.commentCount"><span class="mk">评论数</span>{{ jiraDisplayInfo.commentCount }}</div>
                    <div v-if="jiraDisplayInfo.attachmentCount && !jiraDisplayInfo.attachments?.length">
                      <span class="mk">附件数</span>{{ jiraDisplayInfo.attachmentCount }}
                    </div>
                    <div v-if="jiraDisplayInfo.fetchOk"><span class="mk">拉取</span>{{ jiraDisplayInfo.fetchOk === 'true' ? '成功' : jiraDisplayInfo.fetchOk }}</div>
                    <div v-if="jiraDisplayInfo.skillUsed"><span class="mk">Skill</span>{{ jiraDisplayInfo.skillUsed }}</div>
                  </div>
                  <div v-if="jiraDisplayInfo.description" class="jira-desc">
                    <div class="mk" style="margin-bottom: 6px">描述</div>
                    <pre>{{ jiraDisplayInfo.description }}</pre>
                  </div>
                  <div v-if="jiraDisplayInfo.attachments?.length" class="jira-att">
                    <div class="mk" style="margin-bottom: 6px">附件</div>
                    <a
                      v-for="a in jiraDisplayInfo.attachments"
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
              </NSpin>
            </div>

            <div v-show="activeReportTab === 'log'" class="tab-pane tab-pane-log">
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

              <NButton
                v-if="!isHistoryView && (isRunning || isPending)"
                type="warning"
                @click="stopOrCancelCurrentTask"
              >
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12"/></svg>
                </template>
                {{ isRunning ? '强行中断当前任务' : '取消等待中的任务' }}
              </NButton>

              <NButton v-if="!isHistoryView" :disabled="!modelProviderReady || isRunning || isPending || !currentTaskId" @click="openContinue">
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

    <!-- ────── 知识沉淀弹窗 ────── -->
    <NModal
      v-model:show="showDistillDialog"
      preset="card"
      title="沉淀为知识库 / Skill"
      style="width: 660px"
      :mask-closable="false"
    >
      <!-- Step 1: 沉淀为知识条目 -->
      <div v-if="distillStep === 'deposit'">
        <NAlert type="info" :show-icon="false" style="margin-bottom: 12px">
          将本次诊断结论沉淀为<strong>知识条目</strong>（状态：待审核），可选择同时关联或生成 Skill。
        </NAlert>
        <div class="modal-body-text">知识条目正文（已自动预填报告，可编辑）：</div>
        <NInput
          v-model:value="distillContent"
          type="textarea"
          placeholder="知识条目正文..."
          :autosize="{ minRows: 6, maxRows: 14 }"
        />
        <div class="modal-body-text" style="margin-top: 10px">人工补充要点（可选）：</div>
        <NInput
          v-model:value="distillNote"
          type="textarea"
          placeholder="如：某场景下 RILJ 异常的固定排查路径..."
          :autosize="{ minRows: 2, maxRows: 5 }"
        />
        <NSpace align="center" style="margin-top: 14px">
          <NCheckbox :checked="true" disabled>存入知识库（待审核）</NCheckbox>
          <NCheckbox v-model:checked="distillLinkSkill">并关联 / 生成 Skill</NCheckbox>
        </NSpace>
      </div>

      <!-- Step 2: 关联 / 生成 Skill -->
      <div v-else>
        <NSpin :show="distillLoadingAssoc">
          <NAlert
            :type="distillOverall === 'enhance_existing' ? 'warning' : 'success'"
            :show-icon="false"
            style="margin-bottom: 12px"
          >
            <template v-if="distillOverall === 'enhance_existing'">
              检索到相关 Skill，建议<strong>补充到现有 Skill</strong>，避免重复建设。
            </template>
            <template v-else>
              未发现高度相关的 Skill，建议<strong>新建 Skill 草稿</strong>。
            </template>
          </NAlert>

          <div v-if="distillAssociations.length" class="assoc-list">
            <div v-for="a in distillAssociations" :key="a.id" class="assoc-item">
              <div class="assoc-head">
                <span class="assoc-name">{{ a.display_name }}</span>
                <span class="assoc-badge" :class="a.type">{{ a.type === 'activated' ? '已激活' : '草稿' }}</span>
                <span class="assoc-score">相关度 {{ Math.round(a.association_score * 100) }}%</span>
                <span v-if="a.recommendation === 'enhance_existing'" class="assoc-rec">建议增强</span>
              </div>
              <div class="assoc-desc">{{ a.description }}</div>
              <div v-if="a.reasons.length" class="assoc-reasons">{{ a.reasons.join(' · ') }}</div>
              <NButton
                size="small"
                type="primary"
                ghost
                :loading="distillSkillBusy === a.id"
                style="margin-top: 8px"
                @click="distillEnhance(a)"
              >
                {{ a.type === 'activated' ? '生成升级草案' : '补充到此草稿' }}
              </NButton>
            </div>
          </div>
          <NEmpty v-else-if="!distillLoadingAssoc" description="未找到相关 Skill" style="padding: 20px 0" />

          <div style="margin-top: 16px; text-align: center">
            <NButton type="primary" :loading="distillSkillBusy === '__new__'" @click="distillCreateNew">
              ＋ 新建 Skill 草稿
            </NButton>
          </div>
        </NSpin>
      </div>

      <template #footer>
        <NSpace justify="end">
          <template v-if="distillStep === 'deposit'">
            <NButton @click="showDistillDialog = false">取消</NButton>
            <NButton
              type="primary"
              :loading="distillSubmitting"
              :disabled="!distillContent.trim()"
              @click="submitDeposit"
            >
              {{ distillLinkSkill ? '沉淀并下一步' : '沉淀为知识条目' }}
            </NButton>
          </template>
          <template v-else>
            <NButton @click="showDistillDialog = false">完成</NButton>
            <NButton tertiary @click="goToWorkshop">前往 Skill 工坊</NButton>
          </template>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
.bug-analysis-root {
  :deep(.model-provider-banner) { margin-bottom: 12px; }
}

.bug-split {
  align-items: stretch;
  min-height: 0;
}

.bug-left {
  min-height: 0;
}

.bug-tasks-card {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  /* 单条任务卡片约 88px，列表间距 8px → 可见 3 条 */
  --bug-task-item-height: 88px;
  --bug-task-list-gap: 8px;
  --bug-task-list-height: calc(var(--bug-task-item-height) * 3 + var(--bug-task-list-gap) * 2);
}

.task-list-head {
  flex-shrink: 0;
  margin-bottom: 12px;
}

.task-list-body {
  flex: 0 0 auto;
  height: var(--bug-task-list-height);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.task-list-spin {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  :deep(.n-spin-container) {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  :deep(.n-spin-content) {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
}

.task-scroll {
  height: var(--bug-task-list-height);
  max-height: var(--bug-task-list-height);
  flex: 0 0 auto;
}

.mode-toggle {
  display: flex; gap: 4px; background: var(--surface-2); padding: 3px; border-radius: 10px;
  .mode-idle { background: none; border: none; color: var(--muted); cursor: pointer; font-family: inherit; font-weight: 600; }
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
.bug-detail {
  min-height: 520px;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 120px);
}

.history-task-row {
  display: flex;
  align-items: stretch;
  gap: 4px;
  margin-bottom: 6px;
  .ea-task-item { flex: 1; min-width: 0; margin-bottom: 0; }
}
.history-del-btn {
  flex-shrink: 0;
  align-self: center;
  font-size: 11px;
}

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
.tab-pane {
  flex: 1; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column; padding-bottom: 8px;
}
.tab-pane-live,
.tab-pane-report,
.tab-pane-jira {
  max-height: min(520px, calc(100vh - 360px));
}

.live-llm-panel {
  display: flex; flex-direction: column; min-height: 0; max-height: 100%;
  background: var(--bg); border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
}
.live-llm-panel-full {
  flex: 1;
  min-height: 0;
  height: 100%;
  max-height: 100%;
}
.live-llm-header { padding: 12px 14px; border-bottom: 1px solid var(--line); background: var(--surface); flex-shrink: 0; }
.live-llm-body {
  flex: 1; min-height: 0; overflow-y: auto; padding: 14px 16px;
  font-size: 13.5px; line-height: 1.7; scrollbar-width: thin;
}
.llm-waiting { display: flex; align-items: center; padding: 20px; }

.reasoning-block {
  margin-bottom: 12px; padding: 10px 12px; background: var(--surface);
  border: 1px dashed var(--line); border-radius: 10px;
}
.reasoning-label { font-size: 11px; font-weight: 600; margin-bottom: 6px; }
.reasoning-text {
  margin: 0; font-size: 12px; line-height: 1.55; color: var(--muted);
  white-space: pre-wrap; word-break: break-word; font-family: inherit;
}

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
.report-spin-wrap {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  :deep(.n-spin-container) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  :deep(.n-spin-content) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
}
.report-body-scroll {
  flex: 1;
  min-height: 0;
  max-height: min(480px, calc(100vh - 400px));
}
.report-markdown-inner {
  padding: 4px 12px 16px 4px;
  font-size: 13.5px;
  line-height: 1.7;
}

.jira-card { font-size: 13px; }
.jira-scroll {
  flex: 1; min-height: 0; max-height: 100%; overflow-y: auto; scrollbar-width: thin;
}
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
.tab-pane-log {
  max-height: min(520px, calc(100vh - 360px));
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.log-body {
  flex: 1;
  min-height: 0;
  max-height: min(440px, calc(100vh - 420px));
  overflow: auto;
  background: #1b1e2b;
  color: #e7e9f2;
  padding: 14px 16px;
  border-radius: 14px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  scrollbar-width: thin;
}

.task-footer {
  margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); flex-shrink: 0;
}

.modal-hint { margin-bottom: 8px; font-size: 12px; color: var(--muted); }
.modal-body-text { margin-bottom: 8px; font-size: 13px; color: var(--text); }

.assoc-list { display: flex; flex-direction: column; gap: 10px; max-height: 360px; overflow-y: auto; }
.assoc-item {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2, rgba(0,0,0,.02));
}
.assoc-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.assoc-name { font-weight: 600; font-size: 13px; color: var(--text); }
.assoc-badge {
  font-size: 11px; padding: 1px 7px; border-radius: 10px;
  background: rgba(32,128,240,.12); color: #2080f0;
}
.assoc-badge.activated { background: rgba(24,160,88,.14); color: #18a058; }
.assoc-score { font-size: 11px; color: #888; }
.assoc-rec {
  font-size: 11px; padding: 1px 7px; border-radius: 10px;
  background: rgba(240,160,32,.16); color: #d98c00; font-weight: 600;
}
.assoc-desc { font-size: 12px; color: var(--text-2, #888); margin-top: 6px; line-height: 1.5; }
.assoc-reasons { font-size: 11px; color: #aaa; margin-top: 4px; }

code {
  background: var(--surface-2); padding: 1px 5px; border-radius: 4px;
  font-size: 0.9em; font-family: ui-monospace, monospace;
}

@media (max-width: 1100px) {
  .task-title { max-width: 100%; }
}
</style>