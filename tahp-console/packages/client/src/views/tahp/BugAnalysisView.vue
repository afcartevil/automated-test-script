<script setup lang="ts">
import { ref, computed, reactive, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NInput, NButton, NSpin, NEmpty, NAlert,
  NModal, NScrollbar, NProgress, useMessage, NTooltip,
  NSpace, NSwitch, NCheckbox, NAutoComplete,
} from 'naive-ui'
import MarkdownRenderer from '@/components/hermes/chat/MarkdownRenderer.vue'
import BugAnalysisInteractionModal from '@/components/tahp/BugAnalysisInteractionModal.vue'
import ModelProviderBanner from '@/components/tahp/ModelProviderBanner.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import EaInnerTabs from '@/components/layout/EaInnerTabs.vue'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'
import { useBugAnalysisStore } from '@/stores/tahp/bug-analysis'
import {
  startSingle, startBatch, startLocal, continueAnalysis, distillToKnowledge,
  previewJira, previewJql, getBugReport, getBugLog, cancelBugTask,
  listBugReports, deleteBugReport, respondBugApproval, submitBugUserInput, postJiraComment,
  fetchJiraConfigStatus, getBugTaskContinueStatus,
  fetchChannelConfig, saveChannelConfig, getCodeSourceOptions,
  getBugSkillSnapshot, resumeBugJob, retryFailedBugJob,
  type JiraIssueDetail, type JqlPreview, type BugReport, type BugReportSummary,
  type SkillImproveRecord, type BugSkillSnapshot,
} from '@/api/tahp/bug-analysis'
import {
  extractBugAnalysisReportBody,
  stripBugStageMarkers,
  parseHistoryStageDetails,
  reportToBugTask,
  type HistoryStageDetail,
} from '@/utils/bug-analysis-report'
import { bugJobHasUnfinished, bugJobSettledCount, countBugJobQueue } from '@/utils/bug-analysis-job-stats'
import { bugTaskCardPhase, bugTaskDefaultDetailTab, bugTaskListTitle } from '@/utils/bug-analysis-task-label'
import {
  buildBugActivityLog,
  formatBugActivityLine,
  lastBugActivityHint,
} from '@/utils/bug-analysis-activity'
import { composeJiraCommentFromReport, sanitizeJiraCommentText } from '@/utils/compose-jira-comment'
import { hasJiraRemarkSection } from '@/utils/jira-comment-from-report'
import {
  buildJiraCommentSections,
  joinSelectedSnippets,
  toggleJiraCommentSection,
  type JiraCommentSection,
} from '@/utils/jira-comment-sections'
import { prependDistillJiraHeader } from '@/utils/distill-jira-header'
import { formatBugReportPlainText } from '@/utils/format-bug-report-plain'
import {
  skillAssociation,
  mergeIntoSkill,
  createUpgradeDraft,
  startGenerateStream,
  subscribeSkillGenProgress,
  getSkillGenJob,
  type SkillAssociationItem,
  type SkillGenJobResult,
} from '@/api/tahp/knowledge'
import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const store = useBugAnalysisStore()
const { isReady: modelProviderReady } = useModelProviderReadiness()

function ensureModelProviderOrWarn(): boolean {
  if (modelProviderReady.value) return true
  message.warning('请先在「配置 → 模型管理」中配置模型 Provider 和 API Key')
  return false
}

// ─────────────────────────────────────────────────────────────────────────────
// 表单状态：mode = 'single' | 'batch' | 'local'
const mode = ref<'single' | 'batch' | 'local'>('single')

const singleForm = ref({
  input: '',
  user_description: '',
  code_source: '',
})

const batchForm = ref({
  jql: '',
  code_source: '',
})

const localForm = ref({
  log_path: '',
  problem_description: '',
  code_source: '',
})

// ─── 指定代码源（可选，三种模式通用）───────────────────────────────────────
//
// 判型以服务端 code-source.ts 为准；这里只做输入提示。
const codeSourceBranches = ref<string[]>([])
const codeSourceDefaultBranch = ref('tOS_mtk_A16_trunk')
const CODE_SOURCE_QUICK_BRANCHES = [
  'tOS_mtk_A16_trunk',
  'tOS_mtk_A17_trunk',
  'tOS_qcom_A16_trunk',
  'tOS_qcom_A17_trunk',
] as const
const CODE_SOURCE_FIELD_HINT = '支持本地/映射盘代码路径、OpenGrok代码分支，填写后结合源码取证'

const codeSourceInput = computed(() => {
  if (mode.value === 'single') return singleForm.value.code_source
  if (mode.value === 'batch') return batchForm.value.code_source
  return localForm.value.code_source
})

const codeSourceHint = computed(() => {
  const raw = codeSourceInput.value.trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) {
    return /\/xref\//i.test(raw) || /opengrok/i.test(raw) || /[?&]project=/i.test(raw)
      ? '识别为 OpenGrok 代码链接'
      : '无法判型：不是 OpenGrok 链接，将作为线索传给 Agent'
  }
  if (/^[A-Za-z]:[\\/]/.test(raw) || /^\\\\[^\\]/.test(raw) || raw.startsWith('/')) {
    return '识别为本地/映射盘代码路径'
  }
  if (codeSourceBranches.value.includes(raw)) return '识别为 OpenGrok 代码分支'
  if (/^(tOS|tos|tran|transsion)[A-Za-z0-9._-]*$/.test(raw) || /^A\d{2}$/i.test(raw)) {
    return '识别为 OpenGrok 代码分支（不在已知清单，Agent 会先核对分支名）'
  }
  return '无法判型：将作为代码线索传给 Agent'
})

const codeSourcePlaceholder = computed(
  () => `如 ${codeSourceDefaultBranch.value} / D:\\code\\tOS_mtk_A16`,
)

/** 分支候选：输入为路径或链接时不提示分支 */
const codeSourceSuggestions = computed(() => {
  const raw = codeSourceInput.value.trim()
  if (/^https?:\/\//i.test(raw) || /^[A-Za-z]:[\\/]/.test(raw) || /^\\\\/.test(raw) || raw.startsWith('/')) {
    return []
  }
  if (!raw) return codeSourceBranches.value
  const lower = raw.toLowerCase()
  return codeSourceBranches.value.filter(b => b.toLowerCase().includes(lower))
})

function applyCodeSourceBranch(branch: string) {
  if (mode.value === 'single') singleForm.value.code_source = branch
  else if (mode.value === 'batch') batchForm.value.code_source = branch
  else localForm.value.code_source = branch
}

function toggleQuickCodeSourceBranch(branch: string, checked: boolean) {
  if (checked) applyCodeSourceBranch(branch)
  else if (codeSourceInput.value.trim() === branch) applyCodeSourceBranch('')
}

async function loadCodeSourceOptions() {
  try {
    const opts = await getCodeSourceOptions()
    codeSourceBranches.value = opts.branches || []
    if (opts.default_branch) codeSourceDefaultBranch.value = opts.default_branch
  } catch {
    // 分支清单拿不到不影响填写，输入框仍可自由输入
  }
}

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

/** 收起「提交分析任务」后，下方任务列表占满左侧剩余高度 */
const submitFormCollapsed = ref(false)

function toggleSubmitForm() {
  submitFormCollapsed.value = !submitFormCollapsed.value
}

// JIRA 配置状态改由服务端统一管理（.tahp/unified-config.json / jira-user-config.json），
// 页面只读取状态并展示；配置入口跳转「配置 → 一键配置表单」。
const jiraStatus = ref<{ configured: boolean; connected: boolean; detail?: string; error?: string }>({
  configured: false,
  connected: false,
})
const jiraStatusLoading = ref(false)

const jiraReady = computed(() => jiraStatus.value.configured && jiraStatus.value.connected)

async function loadJiraStatus() {
  jiraStatusLoading.value = true
  try {
    jiraStatus.value = await fetchJiraConfigStatus()
  } catch {
    jiraStatus.value = { configured: false, connected: false }
  } finally {
    jiraStatusLoading.value = false
  }
}

// 远程分析渠道开关（仅单条/批量 Jira；默认全关）
const channelBugfix = ref(false)
const channelLoginsight = ref(false)
const channelBugfixFound = ref(false)
const channelLoginsightFound = ref(false)
const channelConfigLoading = ref(false)
const channelConfigSaving = ref(false)
let channelHydrating = false

const showRemoteChannelPanel = computed(() => mode.value === 'single' || mode.value === 'batch')

async function loadChannelConfig() {
  channelConfigLoading.value = true
  channelHydrating = true
  try {
    const data = await fetchChannelConfig()
    channelBugfix.value = data.remote_channels.bugfix_analysis.enabled
    channelLoginsight.value = data.remote_channels.loginsight_remote.enabled
    channelBugfixFound.value = data.remote_channels.bugfix_analysis.skill_found
    channelLoginsightFound.value = data.remote_channels.loginsight_remote.skill_found
  } catch {
    // 保持默认全关
    channelBugfix.value = false
    channelLoginsight.value = false
  } finally {
    channelConfigLoading.value = false
    // 等下一 tick 再允许保存，避免 NSwitch 回填触发 PUT
    await nextTick()
    channelHydrating = false
  }
}

async function persistChannelConfig() {
  if (channelHydrating || channelConfigLoading.value) return
  channelConfigSaving.value = true
  channelHydrating = true
  try {
    const data = await saveChannelConfig({
      bugfix_analysis: channelBugfix.value,
      loginsight_remote: channelLoginsight.value,
    })
    channelBugfix.value = data.remote_channels.bugfix_analysis.enabled
    channelLoginsight.value = data.remote_channels.loginsight_remote.enabled
    channelBugfixFound.value = data.remote_channels.bugfix_analysis.skill_found
    channelLoginsightFound.value = data.remote_channels.loginsight_remote.skill_found
    message.success('AI2D故障分析能力已保存')
  } catch (err) {
    message.error((err as Error).message || '保存渠道开关失败')
    await loadChannelConfig()
  } finally {
    channelConfigSaving.value = false
    await nextTick()
    channelHydrating = false
  }
}

function goConfigureJira() {
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'form' } })
}

/** 提交/预览前确保 JIRA 已配置且连通；否则提示并跳转配置表单 */
function ensureJiraReady(): boolean {
  if (jiraReady.value) return true
  if (jiraStatus.value.configured && !jiraStatus.value.connected) {
    message.warning(jiraStatus.value.error || 'JIRA 配置无效，请前往「配置 → 一键配置表单」更新')
  } else {
    message.warning('请先在「配置 → 一键配置表单」中配置 JIRA 账号密码')
  }
  goConfigureJira()
  return false
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

const searchExpanded = ref(false)
const searchKeyword = ref('')
const searchInputRef = ref<{ focus: () => void } | null>(null)

const kw = computed(() => searchKeyword.value.trim().toLowerCase())
const isSearching = computed(() => searchExpanded.value && kw.value.length > 0)

const filteredRecent = computed(() => {
  if (!kw.value) return store.recentTasks
  const k = kw.value
  return store.recentTasks.filter(t =>
    t.jira_key?.toLowerCase().includes(k)
    || (t.title || '').toLowerCase().includes(k)
    || t.task_id.toLowerCase().includes(k),
  )
})

const filteredHistory = computed(() => {
  if (!kw.value) return historyReports.value
  const k = kw.value
  return historyReports.value.filter(r =>
    (r.jira_key || r.task_id).toLowerCase().includes(k)
    || (r.title || '').toLowerCase().includes(k)
    || r.task_id.toLowerCase().includes(k),
  )
})

const currentTaskId = computed(() =>
  isHistoryView.value ? historySelectedId.value : store.selectedTaskId,
)
const currentTask = computed(() => {
  if (isHistoryView.value) return historyTask.value
  return currentTaskId.value ? store.tasks[currentTaskId.value] : null
})
const currentTaskCodeSource = computed(() => currentTask.value?.code_source || null)
const currentTaskCodeSourceLabel = computed(() => {
  const cs = currentTaskCodeSource.value
  if (!cs) return ''
  switch (cs.kind) {
    case 'local_path': return '本地路径'
    case 'opengrok_branch': return cs.branch || 'OpenGrok'
    case 'opengrok_url': return cs.branch ? `OpenGrok ${cs.branch}` : 'OpenGrok 链接'
    default: return '代码线索'
  }
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

// 当前任务所属的批量队列（用于从子任务详情返回队列总览）。
// 按 parent_job_id 反查而不是用 selectedJobId，这样从左侧任务列表直接点进
// 某个子任务时也能回到它真正所属的队列。
const parentQueueJob = computed(() => {
  if (isHistoryView.value) return null
  const pid = currentTask.value?.parent_job_id
  return pid ? store.jobs[pid] || null : null
})

const queuePosition = computed(() => {
  const job = parentQueueJob.value
  const tid = currentTaskId.value
  if (!job || !tid) return null
  const idx = job.task_ids.indexOf(tid)
  if (idx < 0) return null
  return { index: idx + 1, total: job.task_ids.length }
})

function backToQueue() {
  const job = parentQueueJob.value
  if (!job) return
  selectQueue(job.job_id)
}

/** 切到某个批量队列的总览（清掉选中的子任务，否则会被任务详情卡片挡住） */
function selectQueue(jobId: string) {
  clearHistoryView()
  store.selectJob(jobId)
  store.selectTask(null)
  reportDetail.value = null
  taskLog.value = ''
  activeReportTab.value = 'live'
}

const isRunning = computed(() => !isHistoryView.value && currentTask.value?.status === 'running')
const isPending = computed(() => !isHistoryView.value && currentTask.value?.status === 'pending')
const isWaitingUserInput = computed(() => !isHistoryView.value && currentTask.value?.status === 'waiting_user_input')

const taskRunError = computed(() => {
  const task = currentTask.value
  if (!task) return ''
  const status = String(task.status || '').toLowerCase()
  if (status !== 'failed' && status !== 'cancelled') return ''
  return String(task.error || '').trim()
})

const currentPendingApproval = computed(() => {
  const tid = currentTaskId.value
  return tid ? store.pendingApprovals[tid] || null : null
})
const currentPendingUserInput = computed(() => {
  const tid = currentTaskId.value
  return tid ? store.pendingUserInputs[tid] || null : null
})
const interactionSubmitting = ref(false)

// 详情 Tab：选择已完成报告时载入
const activeReportTab = ref<'live' | 'report' | 'jira' | 'log'>('live')
const reportDetail = ref<BugReport | null>(null)
const reportLoading = ref(false)
const taskLog = ref<string>('')
const logLoading = ref(false)
const activityScroller = ref<HTMLElement | null>(null)
let logPollTimer: ReturnType<typeof setInterval> | null = null

const reportMarkdown = computed(() => {
  if (!reportDetail.value) return ''
  const raw = reportDetail.value.report_body || reportDetail.value.llm_response || ''
  return extractBugAnalysisReportBody(raw)
})

const SKILL_IMPROVE_ACTION_LABELS: Record<string, string> = {
  create: '新建',
  edit: '整篇改写',
  patch: '局部补丁',
  write_file: '附属文件',
  remove_file: '删除文件',
  delete: '删除',
  file_write: '直接改文件',
}

function skillImproveActionLabel(actions: string[]): string {
  return actions.map(a => SKILL_IMPROVE_ACTION_LABELS[a] || a).filter(Boolean).join('、')
}

function improvedSkillRoute(name: string) {
  return { name: 'hermes.skills', query: { tab: 'improved', skill: name } }
}

const snapshotModalShow = ref(false)
const snapshotLoading = ref(false)
const snapshotError = ref('')
const snapshotData = ref<BugSkillSnapshot | null>(null)
const snapshotSkillName = ref('')

async function openSkillSnapshot(rec: SkillImproveRecord) {
  const tid = reportDetail.value?.task_id || currentTaskId.value || historySelectedId.value || ''
  if (!tid || !rec.snapshot_dir) {
    snapshotError.value = '这份报告还没有 Skill 快照。可在 Skills 库「自改进」Tab 查看当前内容。'
    snapshotData.value = null
    snapshotSkillName.value = rec.name
    snapshotModalShow.value = true
    return
  }
  snapshotSkillName.value = rec.name
  snapshotModalShow.value = true
  snapshotLoading.value = true
  snapshotError.value = ''
  snapshotData.value = null
  try {
    snapshotData.value = await getBugSkillSnapshot(tid, rec.name)
  } catch (err: any) {
    snapshotError.value = err?.message || '读取快照失败'
  } finally {
    snapshotLoading.value = false
  }
}

const currentSkillsImproved = computed<SkillImproveRecord[]>(() => {
  const fromReport = reportDetail.value?.skills_improved || []
  const fromTask = currentTask.value?.skills_improved || []
  return fromReport.length >= fromTask.length ? fromReport : fromTask
})

// 补充信息弹窗
const showContinueDialog = ref(false)
const continueText = ref('')

// 知识沉淀弹窗
const showDistillDialog = ref(false)
type DistillMode = 'knowledge' | 'skill'
const distillMode = ref<DistillMode>('knowledge')
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

type SkillOpStepStatus = 'wait' | 'process' | 'finish' | 'error'
interface SkillOpStep { label: string; status: SkillOpStepStatus }

const skillOpActive = ref(false)
const skillOpProgress = ref(0)
const skillOpMessage = ref('')
const skillOpSteps = ref<SkillOpStep[]>([])
const skillOpBlocking = computed(() =>
  skillOpActive.value && !skillOpSteps.value.some(s => s.status === 'error'),
)
let skillGenSse: EventSource | null = null
let skillOpPumpTimer: ReturnType<typeof setInterval> | null = null

function closeSkillGenSse() {
  skillGenSse?.close()
  skillGenSse = null
}

function stopSkillOpPump() {
  if (skillOpPumpTimer) {
    clearInterval(skillOpPumpTimer)
    skillOpPumpTimer = null
  }
}

function resetSkillOp() {
  stopSkillOpPump()
  closeSkillGenSse()
  skillOpActive.value = false
  skillOpProgress.value = 0
  skillOpMessage.value = ''
  skillOpSteps.value = []
}

function beginSkillOp(stepLabels: string[], message = '准备中...') {
  skillOpActive.value = true
  skillOpProgress.value = 5
  skillOpMessage.value = message
  skillOpSteps.value = stepLabels.map(label => ({ label, status: 'wait' as SkillOpStepStatus }))
}

function patchSkillOpStep(
  index: number,
  status: SkillOpStepStatus,
  progress: number,
  message: string,
) {
  skillOpSteps.value = skillOpSteps.value.map((step, i) => {
    if (status === 'error') {
      if (i < index) return { ...step, status: 'finish' }
      if (i === index) return { ...step, status: 'error' }
      return step
    }
    if (i < index) return { ...step, status: 'finish' }
    if (i === index) return { ...step, status }
    return step
  })
  skillOpProgress.value = progress
  skillOpMessage.value = message
}

async function runWithSkillOpPump(
  stepIndex: number,
  from: number,
  to: number,
  message: string,
  work: () => Promise<void>,
) {
  patchSkillOpStep(stepIndex, 'process', from, message)
  stopSkillOpPump()
  let current = from
  skillOpPumpTimer = setInterval(() => {
    current = Math.min(to - 4, current + 3)
    skillOpProgress.value = current
  }, 700)
  try {
    await work()
    patchSkillOpStep(stepIndex, 'finish', to, message)
  } catch (err) {
    patchSkillOpStep(stepIndex, 'error', current, (err as Error).message || '操作失败')
    throw err
  } finally {
    stopSkillOpPump()
  }
}

function updateSkillGenSteps(job: SkillGenJobResult) {
  const stageMap: Record<string, number> = {
    init: -1,
    duplicate_check: 0,
    similarity_check: 1,
    llm_generate: 2,
    eval_extract: 3,
    quality_score: 4,
    persist: 4,
    done: 4,
  }
  const currentIdx = stageMap[job.stage] ?? -1
  skillOpSteps.value = skillOpSteps.value.map((step, i) => {
    if (job.status === 'error') {
      if (i < currentIdx) return { ...step, status: 'finish' }
      if (i === currentIdx) return { ...step, status: 'error' }
      return { ...step, status: 'wait' }
    }
    if (i < currentIdx) return { ...step, status: 'finish' }
    if (i === currentIdx) {
      return { ...step, status: job.status === 'completed' ? 'finish' : 'process' }
    }
    if (job.status === 'completed') return { ...step, status: 'finish' }
    return { ...step, status: 'wait' }
  })
  skillOpProgress.value = job.progress ?? skillOpProgress.value
  skillOpMessage.value = job.message || skillOpMessage.value
}

function subscribeSkillGen(jobId: string, onDone: (job: SkillGenJobResult) => void) {
  closeSkillGenSse()
  skillGenSse = subscribeSkillGenProgress(jobId)
  skillGenSse.onmessage = (e) => {
    try {
      const job: SkillGenJobResult = JSON.parse(e.data)
      updateSkillGenSteps(job)
      if (job.status === 'completed') {
        closeSkillGenSse()
        onDone(job)
      } else if (job.status === 'error') {
        closeSkillGenSse()
        patchSkillOpStep(
          skillOpSteps.value.findIndex(s => s.status === 'process'),
          'error',
          job.progress ?? skillOpProgress.value,
          job.message || 'Skill 生成失败',
        )
        message.error('Skill 生成失败：' + (job.message || '未知错误'))
        distillSkillBusy.value = ''
      }
    } catch { /* ignore */ }
  }
  skillGenSse.onerror = () => {
    closeSkillGenSse()
    getSkillGenJob(jobId).then(job => {
      updateSkillGenSteps(job)
      if (job.status === 'completed') onDone(job)
      else if (job.status === 'running') setTimeout(() => subscribeSkillGen(jobId, onDone), 2000)
      else {
        message.error('生成任务异常中断，请重试')
        distillSkillBusy.value = ''
      }
    }).catch(() => {
      message.error('无法获取生成进度，请重试')
      distillSkillBusy.value = ''
    })
  }
}

/** 本任务已沉淀的知识条目（避免「知识库」与「Skill」重复写入） */
const distilledEntryByTaskId = reactive<Record<string, { id: string; module: string; func_type: string }>>({})

function rememberDistilledEntry(taskId: string, entry: { id: string; module: string; func_type: string } | null | undefined) {
  if (!taskId || !entry?.id) return
  distilledEntryByTaskId[taskId] = entry
  distilledEntry.value = entry
}

const distillDialogTitle = computed(() =>
  distillStep.value === 'skill'
    ? '沉淀为 Skill'
    : distillMode.value === 'knowledge'
      ? '沉淀为知识库'
      : '沉淀为 Skill',
)

const distillCompleted = computed(() =>
  !isRunning.value && currentTask.value?.status === 'completed',
)

const canContinueSession = ref(false)

const canContinueAnalysis = computed(() =>
  !isHistoryView.value
  && distillCompleted.value
  && canContinueSession.value
  && !isRunning.value
  && !isPending.value
  && !isWaitingUserInput.value
  && !!currentTaskId.value,
)

async function refreshContinueStatus() {
  const tid = currentTaskId.value
  if (!tid || isHistoryView.value) {
    canContinueSession.value = false
    return
  }
  const t = currentTask.value
  if (!t || t.status !== 'completed') {
    canContinueSession.value = false
    return
  }
  try {
    const st = await getBugTaskContinueStatus(tid)
    canContinueSession.value = st.can_continue
  } catch {
    canContinueSession.value = false
  }
}

const isLocalAnalysisTask = computed(() => {
  const t = currentTask.value
  if (!t) return false
  if (t.analysis_mode === 'local') return true
  return (t.jira_key || '').startsWith('LOCAL-')
})

const canPostJiraComment = computed(() =>
  distillCompleted.value
  && !isLocalAnalysisTask.value
  && !!(currentTask.value?.jira_key && !currentTask.value.jira_key.startsWith('LOCAL-')),
)

// 分析结论回到 jira comment 弹窗
const showJiraCommentDialog = ref(false)
const jiraCommentText = ref('')
const jiraCommentSubmitting = ref(false)
const jiraCommentSections = ref<JiraCommentSection[]>([])
const jiraCommentSelectedIds = ref<string[]>([])
const jiraCommentInserted = ref<Record<string, string>>({})

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
  WAITING_USER_INPUT: { label: '等待配置',       color: 'var(--warn)' },
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

const BUG_PHASE_PROGRESS: Record<string, number> = {
  FETCH_JIRA_INFO: 15,
  DOWNLOAD_JIRA_LOGS: 32,
  MATCH_SKILLS: 48,
  ANALYZING: 72,
  GENERATING_REPORT: 92,
  COMPLETED: 100,
}

function stageDetailMapForTask(tid: string | null) {
  if (!tid) return {} as Record<string, HistoryStageDetail>
  return isHistoryView.value
    ? historyStageDetails.value
    : store.stageDetailMap(tid) as Record<string, HistoryStageDetail>
}

function allStageDetailsSuccess(tid: string): boolean {
  const detailMap = stageDetailMapForTask(tid)
  return BUG_STAGE_STEP_IDS.every(id => detailMap[id]?.status === 'success')
}

/** 结合 phase 与 stage_detail，避免本地模式 phase 回退导致进度条卡在 JIRA 步骤 */
function deriveEffectiveBugPhase(
  phase: string | undefined,
  detailMap: Record<string, HistoryStageDetail>,
  isLocal: boolean,
): string | undefined {
  for (let i = 0; i < BUG_STAGE_STEP_IDS.length; i += 1) {
    if (detailMap[BUG_STAGE_STEP_IDS[i]]?.status === 'running') {
      return BUG_STAGE_ORDER[i]
    }
  }

  let lastSuccess = -1
  for (let i = 0; i < BUG_STAGE_STEP_IDS.length; i += 1) {
    if (detailMap[BUG_STAGE_STEP_IDS[i]]?.status === 'success') lastSuccess = i
  }

  const phaseIdx = phase && !PREP_PHASES.has(phase)
    ? BUG_STAGE_ORDER.indexOf(phase as typeof BUG_STAGE_ORDER[number])
    : -1

  if (lastSuccess >= 0 && lastSuccess < BUG_STAGE_ORDER.length - 1) {
    const nextIdx = lastSuccess + 1
    const nextPhase = BUG_STAGE_ORDER[nextIdx]
    if (phaseIdx < 0) return nextPhase
    if (isLocal && phaseIdx < nextIdx) return nextPhase
    if (phaseIdx > nextIdx) return phase
    // JIRA 单条/批量：以服务端 phase 为准，避免本地推导把进度条超前到「匹配 Skill」
    if (isLocal) return nextPhase
    return phase
  }

  if (phaseIdx >= 0) return phase
  if (isLocal && lastSuccess >= 2) return 'ANALYZING'
  if (isLocal && lastSuccess >= 1) return 'MATCH_SKILLS'
  return phase
}

const effectiveBugPhase = computed(() =>
  deriveEffectiveBugPhase(
    currentTask.value?.phase,
    stageDetailMapForTask(currentTaskId.value),
    isLocalAnalysisTask.value,
  ),
)

const bugStages = computed(() => {
  const phase = effectiveBugPhase.value
  const status = currentTask.value?.status
  const tid = currentTaskId.value
  const detailMap = stageDetailMapForTask(tid)
  const idx = phase && !PREP_PHASES.has(phase)
    ? BUG_STAGE_ORDER.indexOf(phase as typeof BUG_STAGE_ORDER[number])
    : -1
  const stagesComplete = tid ? allStageDetailsSuccess(tid) : false
  const allDone = status === 'completed' || currentTask.value?.phase === 'COMPLETED' || stagesComplete
  return BUG_STAGE_ORDER.map((key, i) => {
    const detailDone = detailMap[BUG_STAGE_STEP_IDS[i]]?.status === 'success'
    return {
      key,
      label: PHASE_LABELS[key]?.label || key,
      done: allDone || detailDone || (idx >= 0 && i < idx),
      active: !allDone && idx >= 0 && i === idx,
    }
  })
})

const displayProgress = computed(() => {
  const task = currentTask.value
  if (!task) return 0
  if (task.status === 'completed' || task.phase === 'COMPLETED') return 100
  if (bugStages.value.every(s => s.done)) return 100
  const eff = effectiveBugPhase.value
  if (eff && BUG_PHASE_PROGRESS[eff] != null) return BUG_PHASE_PROGRESS[eff]
  return typeof task.progress === 'number' ? task.progress : 0
})

function phaseLabel(phase?: string, status?: string): string {
  const resolved = bugTaskCardPhase(status, phase)
  const p = resolved || effectiveBugPhase.value
  if (!p) return '准备中'
  if (PREP_PHASES.has(p)) {
    const eff = effectiveBugPhase.value
    if (eff && !PREP_PHASES.has(eff)) return PHASE_LABELS[eff]?.label || eff
  }
  return PHASE_LABELS[p]?.label || p
}

function phaseColor(phase?: string, status?: string): string {
  const resolved = bugTaskCardPhase(status, phase)
  const p = resolved || effectiveBugPhase.value
  if (!p) return 'var(--faint)'
  if (PREP_PHASES.has(p)) {
    const eff = effectiveBugPhase.value
    if (eff && !PREP_PHASES.has(eff)) return PHASE_LABELS[eff]?.color || 'var(--faint)'
  }
  return PHASE_LABELS[p]?.color || 'var(--faint)'
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
  if (status === 'waiting_user_input') return 'warn'
  if (status === 'interrupted') return 'warn'
  return 'muted'
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
  if (!ensureJiraReady()) return
  const v = singleForm.value.input.trim()
  if (!v) { message.warning('请先填入 Bug ID 或 URL'); return }
  previewingJira.value = true
  previewError.value = null
  jiraPreview.value = null
  try {
    jiraPreview.value = await previewJira(v)
  } catch (err) {
    previewError.value = (err as Error).message
  } finally {
    previewingJira.value = false
  }
}

async function doPreviewJql() {
  if (!ensureJiraReady()) return
  const v = batchForm.value.jql.trim()
  if (!v) { message.warning('请填入 JQL 查询语句'); return }
  previewingJql.value = true
  jqlPreviewError.value = null
  jqlPreview.value = null
  try {
    jqlPreview.value = await previewJql(v)
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
  if (!ensureJiraReady()) return
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
      code_source: singleForm.value.code_source.trim() || undefined,
    })
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

/** 注册批量 Job + 其排队中的子任务，并切到队列视图 */
function registerBatchQueue(
  resp: { job_id: string; total: number; tasks: Array<{ task_id: string; jira_key: string }> },
  jql?: string,
  resumedFrom?: string,
) {
  const startedAt = new Date().toISOString()
  store.registerJob({
    job_id: resp.job_id,
    type: 'batch',
    jql,
    resumed_from: resumedFrom,
    task_ids: resp.tasks.map(t => t.task_id),
    started_at: startedAt,
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
      started_at: startedAt,
      parent_job_id: resp.job_id,
    })
  }
  store.selectJob(resp.job_id)
  // 长队列停在队列总览而不是跳进第一单，方便观察整体进度
  store.selectTask(null)
  clearHistoryView()
  activeReportTab.value = 'live'
}

async function startBatchAnalysis() {
  if (!ensureModelProviderOrWarn()) return
  if (!ensureJiraReady()) return
  if (!batchForm.value.jql.trim()) {
    message.warning('请填入 JQL')
    return
  }
  submitting.value = true
  try {
    store.ensureSocket()
    const jql = batchForm.value.jql.trim()
    const resp = await startBatch({
      jql,
      code_source: batchForm.value.code_source.trim() || undefined,
    })
    registerBatchQueue(resp, jql)
    message.success(`批量分析已启动: 共 ${resp.total} 单，串行执行，失败自动跳过`)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

// ─── 队列续跑 / 重跑失败项 ─────────────────────────────────────────────────
const jobActionLoading = ref(false)

async function resumeCurrentJob() {
  const job = currentJob.value
  if (!job || !ensureModelProviderOrWarn()) return
  jobActionLoading.value = true
  try {
    store.ensureSocket()
    const resp = await resumeBugJob(job.job_id)
    registerBatchQueue(resp, job.jql, job.job_id)
    message.success(`已继续未完成的 ${resp.total} 单`)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    jobActionLoading.value = false
  }
}

async function retryCurrentJobFailures() {
  const job = currentJob.value
  if (!job || !ensureModelProviderOrWarn()) return
  jobActionLoading.value = true
  try {
    store.ensureSocket()
    const resp = await retryFailedBugJob(job.job_id)
    registerBatchQueue(resp, job.jql, job.job_id)
    message.success(`已重跑 ${resp.total} 个失败单`)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    jobActionLoading.value = false
  }
}

// ─── 队列筛选（上百单时按状态过滤） ───────────────────────────────────────
type QueueFilter = 'all' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

const queueFilter = ref<QueueFilter>('all')

function jobQueueCountsFor(taskIds: string[]) {
  const taskMap = store.tasks
  return countBugJobQueue(taskIds, tid => taskMap[tid]?.status)
}

const queueCounts = computed(() => {
  const taskMap = store.tasks
  return countBugJobQueue(currentJob.value?.task_ids || [], tid => taskMap[tid]?.status)
})

const currentJobSettled = computed(() => bugJobSettledCount(queueCounts.value))

const currentJobFailedOnly = computed(() => queueCounts.value.failed)

const canResumeUnfinished = computed(() => {
  const job = currentJob.value
  if (!job || job.status === 'running') return false
  return bugJobHasUnfinished(job.task_ids || [], tid => store.tasks[tid]?.status)
})

const recentJobQueueCounts = computed(() => {
  const map: Record<string, ReturnType<typeof countBugJobQueue>> = {}
  for (const j of store.recentJobs) {
    map[j.job_id] = jobQueueCountsFor(j.task_ids || [])
  }
  return map
})

const filteredQueueTaskIds = computed(() => {
  const ids = currentJob.value?.task_ids || []
  if (queueFilter.value === 'all') return ids
  return ids.filter(tid => {
    const status = store.tasks[tid]?.status || 'pending'
    if (queueFilter.value === 'completed') return status === 'completed'
    if (queueFilter.value === 'failed') return status === 'failed'
    if (queueFilter.value === 'cancelled') return status === 'cancelled'
    if (queueFilter.value === 'running') return status === 'running' || status === 'waiting_user_input'
    return status === 'pending'
  })
})

const QUEUE_FILTERS: Array<{ key: QueueFilter; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '等待中' },
  { key: 'running', label: '执行中' },
  { key: 'completed', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'cancelled', label: '已取消' },
]

async function startLocalAnalysis() {
  if (!ensureModelProviderOrWarn()) return
  if (!localForm.value.log_path.trim()) {
    message.warning('请填入本地日志路径')
    return
  }
  if (!localForm.value.problem_description.trim()) {
    message.warning('请填入问题描述')
    return
  }
  submitting.value = true
  try {
    store.ensureSocket()
    const resp = await startLocal({
      log_path: localForm.value.log_path.trim(),
      problem_description: localForm.value.problem_description.trim(),
      code_source: localForm.value.code_source.trim() || undefined,
    })
    const label = localForm.value.log_path.trim().replace(/[/\\]+$/, '').split(/[/\\]/).pop() || 'local'
    store.registerTask({
      task_id: resp.task_id,
      jira_key: resp.jira_key || `LOCAL-${label}`,
      jira_url: '',
      status: 'running',
      phase: 'ANALYZING',
      progress: 0,
      started_at: new Date().toISOString(),
      title: `本地日志: ${label}`,
      analysis_mode: 'local',
      local_log_path: localForm.value.log_path.trim(),
      user_description: localForm.value.problem_description.trim(),
    })
    store.selectTask(resp.task_id)
    store.selectJob(null)
    clearHistoryView()
    activeReportTab.value = 'live'
    message.success('本地日志分析已启动')
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

async function toggleSearch() {
  searchExpanded.value = !searchExpanded.value
  if (searchExpanded.value) {
    if (!historyReports.value.length && !historyListLoading.value) {
      await loadHistoryReports()
    }
    await nextTick()
    searchInputRef.value?.focus()
  } else {
    searchKeyword.value = ''
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
  const tab = bugTaskDefaultDetailTab(store.tasks[taskId]?.status)
  activeReportTab.value = tab
  if (tab === 'report') void loadReport()
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

async function loadLog(silent = false) {
  if (!currentTaskId.value) return
  if (!silent) logLoading.value = true
  try {
    const r = await getBugLog(currentTaskId.value)
    taskLog.value = r.content || '(日志为空)'
  } catch (err) {
    if (!silent) taskLog.value = `加载日志失败: ${(err as Error).message}`
  } finally {
    if (!silent) logLoading.value = false
  }
}

function stopLogPoll() {
  if (logPollTimer) {
    clearInterval(logPollTimer)
    logPollTimer = null
  }
}

function startLogPoll() {
  stopLogPoll()
  logPollTimer = setInterval(() => {
    if (!isRunning.value || !currentTaskId.value) {
      stopLogPoll()
      return
    }
    void loadLog(true)
  }, 2500)
}

watch(activeReportTab, (tab) => {
  if ((tab === 'report' || tab === 'jira') && currentTaskId.value && !reportDetail.value) loadReport()
  if (tab === 'log' && currentTaskId.value) void loadLog()
})

watch(
  () => isRunning.value,
  (running) => {
    if (running && currentTaskId.value) startLogPoll()
    else stopLogPoll()
  },
  { immediate: true },
)

watch(
  () => currentTask.value?.status,
  (status, prev) => {
    if (isHistoryView.value || !currentTaskId.value) return
    if (status === 'completed' && prev === 'running') {
      activeReportTab.value = 'report'
      loadReport()
    }
    void refreshContinueStatus()
  },
)

watch(
  () => currentTaskId.value,
  () => { void refreshContinueStatus() },
)

watch(
  () => store.stream(currentTaskId.value || ''),
  (evs) => {
    const tid = currentTaskId.value
    if (!tid || isHistoryView.value) return
    for (let i = evs.length - 1; i >= 0; i -= 1) {
      const ev = evs[i]
      if (ev.type === 'task.continue_started') {
        canContinueSession.value = false
        break
      }
      if (ev.type === 'task.completed' && typeof ev.payload.can_continue_session === 'boolean') {
        canContinueSession.value = ev.payload.can_continue_session as boolean
        break
      }
    }
  },
  { deep: true },
)

function downloadLog() {
  if (!currentTaskId.value || !displayTaskLog.value) {
    message.warning('请先在"任务日志"页加载日志')
    return
  }
  const blob = new Blob([displayTaskLog.value], { type: 'text/plain;charset=utf-8' })
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
// 人机协同：危险命令审批 + 结构化配置输入
// ─────────────────────────────────────────────────────────────────────────────
async function onApprovalRespond(choice: string) {
  const tid = currentTaskId.value
  const ap = currentPendingApproval.value
  if (!tid || !ap) return
  interactionSubmitting.value = true
  try {
    await respondBugApproval(tid, { approval_id: ap.approval_id, choice })
    message.success(choice === 'deny' ? '已拒绝执行' : '已确认')
  } catch (err) {
    const msg = (err as Error).message || '审批提交失败'
    if (msg.includes('不存在或已处理')) {
      store.clearPendingInteraction(tid)
      return
    }
    message.error(msg)
  } finally {
    interactionSubmitting.value = false
  }
}

function onInteractionDismiss() {
  const tid = currentTaskId.value
  if (tid) store.clearPendingInteraction(tid)
}

async function onUserInputSubmit(values: Record<string, string>) {
  const tid = currentTaskId.value
  const ui = currentPendingUserInput.value
  if (!tid || !ui) return
  interactionSubmitting.value = true
  try {
    await submitBugUserInput(tid, { request_id: ui.request_id, values })
    message.success('配置已提交，Agent 继续分析')
  } catch (err) {
    message.error((err as Error).message || '配置提交失败')
  } finally {
    interactionSubmitting.value = false
  }
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
    const tid = currentTaskId.value
    const resp = await continueAnalysis(tid, {
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
      started_at: currentTask.value?.started_at || new Date().toISOString(),
      title: currentTask.value?.title,
      skills_used: currentTask.value?.skills_used,
      skills_improved: currentTask.value?.skills_improved,
    })
    activeReportTab.value = 'live'
    showContinueDialog.value = false
    canContinueSession.value = false
    message.success(`补充分析已开始，将在当前会话继续分析 ${currentTask.value?.jira_key || ''}`)
  } catch (err) {
    message.error((err as Error).message)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 知识沉淀：① 沉淀为知识条目 ② 关联 / 生成 Skill
// ─────────────────────────────────────────────────────────────────────────────
function buildDistillContentWithJira(): string {
  const body = formatBugReportPlainText(reportMarkdown.value || '')
  const j = jiraDisplayInfo.value
  if (!j) return body
  return prependDistillJiraHeader(body, {
    key: j.key,
    summary: j.summary,
    description: j.description,
  })
}

function resetDistillForm(mode: DistillMode) {
  distillMode.value = mode
  distillStep.value = 'deposit'
  distillNote.value = ''
  distillContent.value = buildDistillContentWithJira()
  distillLinkSkill.value = mode === 'skill'
  distillSubmitting.value = false
  distilledEntry.value = null
  distillAssociations.value = []
  distillSkillBusy.value = ''
}

async function ensureReportForDistill(): Promise<boolean> {
  if (reportMarkdown.value.trim()) return true
  if (!currentTaskId.value) return false
  await loadReport()
  return !!reportMarkdown.value.trim()
}

async function openJiraCommentDialog() {
  if (!canPostJiraComment.value) return
  if (!ensureJiraReady()) return
  const ok = await ensureReportForDistill()
  if (!ok) {
    message.warning('暂无分析报告，无法提交 jira comment')
    return
  }

  const markdown = reportMarkdown.value
  const sections = buildJiraCommentSections(markdown)
  const remarkFallback = composeJiraCommentFromReport(markdown)
  if (!sections.length && !remarkFallback.trim()) {
    message.warning('报告未包含可回填的章节，请重新分析后重试')
    return
  }

  jiraCommentSections.value = sections
  const selected = sections.filter(s => s.defaultSelected).map(s => s.id)
  jiraCommentSelectedIds.value = selected
  const inserted: Record<string, string> = {}
  for (const section of sections) {
    if (selected.includes(section.id)) inserted[section.id] = section.snippet
  }
  jiraCommentInserted.value = inserted
  jiraCommentText.value = sections.length
    ? joinSelectedSnippets(sections, selected)
    : remarkFallback

  if (!jiraCommentText.value.trim()) {
    message.warning('报告未包含第 9 节「Jira 备注」，请勾选其它章节或重新分析')
  } else if (!hasJiraRemarkSection(markdown)) {
    message.info('当前为旧版报告，建议重新分析以生成标准 §9 Jira 备注')
  }
  showJiraCommentDialog.value = true
}

function isJiraCommentSectionChecked(id: string): boolean {
  return jiraCommentSelectedIds.value.includes(id)
}

function onJiraCommentSectionToggle(id: string, checked: boolean) {
  const section = jiraCommentSections.value.find(s => s.id === id)
  if (!section) return
  const next = toggleJiraCommentSection({
    preview: jiraCommentText.value,
    snippet: section.snippet,
    selected: checked,
    inserted: jiraCommentInserted.value[id],
  })
  jiraCommentText.value = next.preview
  const inserted = { ...jiraCommentInserted.value }
  if (next.inserted) inserted[id] = next.inserted
  else delete inserted[id]
  jiraCommentInserted.value = inserted
  if (checked) {
    if (!jiraCommentSelectedIds.value.includes(id)) {
      jiraCommentSelectedIds.value = [...jiraCommentSelectedIds.value, id]
    }
  } else {
    jiraCommentSelectedIds.value = jiraCommentSelectedIds.value.filter(x => x !== id)
  }
}

async function submitJiraComment() {
  const tid = currentTaskId.value
  if (!tid) return false
  if (!ensureJiraReady()) return false
  const text = sanitizeJiraCommentText(jiraCommentText.value.trim())
  if (!text) {
    message.warning('备注内容不能为空')
    return false
  }
  jiraCommentSubmitting.value = true
  try {
    await postJiraComment(tid, text)
    message.success(`分析结论已回到 jira comment（${currentTask.value?.jira_key || ''}）`)
    showJiraCommentDialog.value = false
    return true
  } catch (err) {
    message.error((err as Error).message)
    return false
  } finally {
    jiraCommentSubmitting.value = false
  }
}

/** Skill 流程：跳过沉淀表单，后台复用/准备 entry_id 后直接进入关联检索 */
async function prepareSkillDistill() {
  const tid = currentTaskId.value
  if (!tid) return

  distillStep.value = 'skill'
  distillAssociations.value = []
  beginSkillOp(
    ['加载分析报告', '准备知识条目', '检索相关 Skill'],
    '正在准备 Skill 关联...',
  )

  try {
    patchSkillOpStep(0, 'process', 12, '正在加载分析报告...')
    const hasReport = await ensureReportForDistill()
    if (!hasReport) {
      patchSkillOpStep(0, 'error', 12, '分析报告为空')
      message.warning('分析报告为空，请先在「分析报告」页确认报告已生成')
      distillStep.value = 'deposit'
      distillContent.value = ''
      resetSkillOp()
      return
    }
    patchSkillOpStep(0, 'finish', 28, '分析报告已就绪')

    const cached = distilledEntryByTaskId[tid]
    if (cached) {
      distilledEntry.value = cached
      patchSkillOpStep(1, 'finish', 45, '已复用本任务知识条目')
    } else {
      await runWithSkillOpPump(1, 32, 48, '正在准备知识条目...', async () => {
        const r = await distillToKnowledge(tid, {
          content: buildDistillContentWithJira(),
          to_knowledge: true,
        })
        if (!r.entry) throw new Error(r.message || '无法准备 Skill 关联')
        rememberDistilledEntry(tid, r.entry)
      })
    }

    patchSkillOpStep(2, 'process', 55, '正在检索相关 Skill...')
    await loadDistillAssociations()
    patchSkillOpStep(2, 'finish', 100, `已找到 ${distillAssociations.value.length} 个候选 Skill`)
    setTimeout(() => resetSkillOp(), 500)
  } catch (err) {
    message.error((err as Error).message)
    showDistillDialog.value = false
    resetSkillOp()
  }
}

function openDistillKnowledge() {
  resetDistillForm('knowledge')
  const tid = currentTaskId.value
  if (tid && distilledEntryByTaskId[tid]) {
    distilledEntry.value = distilledEntryByTaskId[tid]
  }
  showDistillDialog.value = true
}

async function openDistillSkill() {
  resetDistillForm('skill')
  showDistillDialog.value = true
  await prepareSkillDistill()
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
    rememberDistilledEntry(currentTaskId.value, r.entry)
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
      text: [reportMarkdown.value, currentTask.value?.title || ''].filter(Boolean).join('\n'),
    })
    distillAssociations.value = r.associations
    distillOverall.value = r.overall_recommendation
  } catch (err) {
    message.error('关联检索失败：' + (err as Error).message)
    throw err
  } finally {
    distillLoadingAssoc.value = false
  }
}

async function distillEnhance(a: SkillAssociationItem) {
  if (!distilledEntry.value) return
  distillSkillBusy.value = a.id
  const entryId = distilledEntry.value.id

  if (a.type === 'draft' && a.can_merge) {
    beginSkillOp(
      ['加载知识条目', 'AI 精准融合', '保存 Skill 草稿'],
      `正在补充到「${a.display_name}」...`,
    )
    try {
      patchSkillOpStep(0, 'process', 15, '正在加载知识条目...')
      await new Promise(r => setTimeout(r, 200))
      patchSkillOpStep(0, 'finish', 22, '知识条目已就绪')

      await runWithSkillOpPump(
        1,
        28,
        82,
        `AI 正在将诊断结论融合到「${a.display_name}」...`,
        async () => {
          await mergeIntoSkill(a.id, [entryId])
        },
      )

      patchSkillOpStep(2, 'finish', 100, 'Skill 草稿已更新')
      message.success(`已补充到草稿「${a.display_name}」`)
      distillSkillBusy.value = ''
      setTimeout(() => {
        resetSkillOp()
        showDistillDialog.value = false
      }, 600)
    } catch (err) {
      message.error((err as Error).message)
      distillSkillBusy.value = ''
    }
    return
  }

  beginSkillOp(
    ['读取已激活 Skill', '创建升级草案'],
    `正在为「${a.display_name}」生成升级草案...`,
  )
  try {
    patchSkillOpStep(0, 'process', 18, '正在读取已激活 Skill 内容...')
    await new Promise(r => setTimeout(r, 250))
    patchSkillOpStep(0, 'finish', 32, 'Skill 内容已加载')
    await runWithSkillOpPump(1, 38, 92, '正在创建升级草案并关联知识条目...', async () => {
      await createUpgradeDraft(a.id, [entryId])
    })
    patchSkillOpStep(1, 'finish', 100, '升级草案已生成')
    message.success(`已为「${a.display_name}」生成升级草案，请到 Skill 工坊审核`)
    distillSkillBusy.value = ''
    setTimeout(() => {
      resetSkillOp()
      showDistillDialog.value = false
    }, 600)
  } catch (err) {
    message.error((err as Error).message)
    distillSkillBusy.value = ''
  }
}

async function distillCreateNew() {
  if (!distilledEntry.value) return
  distillSkillBusy.value = '__new__'
  beginSkillOp(
    ['文档重复检测', '相似 Skill 检索', 'AI 生成骨架', '生成 Eval 用例', '质量评分计算'],
    '正在启动 Skill 生成任务...',
  )
  try {
    const { job_id } = await startGenerateStream({
      module: distilledEntry.value.module,
      func_type: distilledEntry.value.func_type,
      entry_ids: [distilledEntry.value.id],
      generated_by: 'bug-analysis-distill',
    })
    patchSkillOpStep(0, 'process', 8, '生成任务已启动，等待进度推送...')
    subscribeSkillGen(job_id, (job) => {
      if (job.result?.llm_error) {
        message.warning('草稿已创建，但 LLM 生成存在问题：' + job.result.llm_error)
      } else {
        message.success('已生成新的 Skill 草稿，请到 Skill 工坊审核')
      }
      distillSkillBusy.value = ''
      setTimeout(() => {
        resetSkillOp()
        showDistillDialog.value = false
      }, 800)
    })
  } catch (err) {
    message.error((err as Error).message)
    resetSkillOp()
    distillSkillBusy.value = ''
  }
}

function goToWorkshop() {
  showDistillDialog.value = false
  resetSkillOp()
  router.push({ name: 'tahp.knowledge' })
}

watch(showDistillDialog, (open) => {
  if (!open) resetSkillOp()
})

onBeforeUnmount(() => {
  resetSkillOp()
  stopLogPoll()
})

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
  void loadJiraStatus()
  void loadChannelConfig()
  void loadCodeSourceOptions()
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
  const hint = lastBugActivityHint(currentStream.value)
  if (hint) return hint
  const phase = currentTask.value?.phase
  if (phase === 'ANALYZING') return 'Agent 正在调用 Skill / 工具，完成后会继续输出分析结论...'
  if (phase === 'PREPARING' || phase === 'CONNECTING_AGENT') return '正在连接 Agent Bridge...'
  return '等待 Agent 响应...'
})

const currentStream = computed(() => {
  const tid = currentTaskId.value
  return tid ? store.stream(tid) : []
})

const liveActivityItems = computed(() => {
  const items: Array<{ key: string; text: string; kind: string }> = []
  for (let i = 0; i < currentStream.value.length; i += 1) {
    const ev = currentStream.value[i]
    const text = formatBugActivityLine(ev)
    if (!text) continue
    items.push({
      key: `${ev.ts}-${ev.type}-${i}`,
      text: text.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, ''),
      kind: ev.type,
    })
  }
  return items.slice(-40)
})

const agentSkillEvents = computed(() =>
  currentStream.value.filter(ev => ev.type === 'task.skill_use' || ev.type === 'task.tool_completed'),
)

const streamTaskLog = computed(() => buildBugActivityLog(currentStream.value))

const displayTaskLog = computed(() => {
  if (isRunning.value && streamTaskLog.value) return streamTaskLog.value
  return taskLog.value || streamTaskLog.value || ''
})

watch(
  () => liveActivityItems.value.length,
  async () => {
    await nextTick()
    const el = activityScroller.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<template>
  <div class="page page-wide bug-analysis-root">
    <ModelProviderBanner />

    <div class="ea-split bug-split">
      <!-- Left: form + task list -->
      <div class="ea-stack bug-left" :class="{ 'submit-collapsed': submitFormCollapsed }">
        <EaCard class="bug-submit-card">
          <div class="submit-head ea-row ea-between ea-mb0">
            <strong style="font-size: 14px">提交分析任务</strong>
            <div v-show="!submitFormCollapsed" class="mode-toggle">
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
              <button
                type="button"
                class="ea-btn-sm"
                :class="mode === 'local' ? 'ea-btn-soft' : 'mode-idle'"
                @click="mode = 'local'"
              >本地日志分析</button>
            </div>
          </div>

          <div v-show="!submitFormCollapsed" class="submit-body">
          <!-- AI2D故障分析能力：仅单条 / 批量 -->
          <div v-if="showRemoteChannelPanel" class="ea-field ai2d-field">
            <label>
              AI2D故障分析能力
              <NTooltip placement="top" trigger="hover">
                <template #trigger>
                  <svg class="info-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
                  </svg>
                </template>
                远程接入AI2D故障分析能力，失败则调用本地故障分析skill
              </NTooltip>
            </label>
            <NSpin :show="channelConfigLoading || channelConfigSaving">
              <div class="ai2d-box">
                <div class="ai2d-row">
                  <div class="ai2d-label">
                    <span>Bugfix AI（通用缺陷）</span>
                    <span v-if="channelBugfix && !channelBugfixFound" class="ai2d-warn">Skill 未找到</span>
                  </div>
                  <NSwitch
                    v-model:value="channelBugfix"
                    :disabled="channelConfigLoading || channelConfigSaving"
                    @update:value="persistChannelConfig"
                  />
                </div>
                <div class="ai2d-row">
                  <div class="ai2d-label">
                    <span>LogInsight（稳定性优先）</span>
                    <span v-if="channelLoginsight && !channelLoginsightFound" class="ai2d-warn">Skill 未找到</span>
                  </div>
                  <NSwitch
                    v-model:value="channelLoginsight"
                    :disabled="channelConfigLoading || channelConfigSaving"
                    @update:value="persistChannelConfig"
                  />
                </div>
              </div>
            </NSpin>
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
              <label>指定代码源（可选）</label>
              <NAutoComplete
                v-model:value="singleForm.code_source"
                :options="codeSourceSuggestions"
                :placeholder="codeSourcePlaceholder"
                clearable
                blur-after-select
              />
              <div class="field-hint code-source-hint">
                <span v-if="codeSourceHint">{{ codeSourceHint }}</span>
                <span v-else>{{ CODE_SOURCE_FIELD_HINT }}</span>
              </div>
              <div class="code-source-quick">
                <NCheckbox
                  v-for="branch in CODE_SOURCE_QUICK_BRANCHES"
                  :key="branch"
                  size="small"
                  :checked="codeSourceInput.trim() === branch"
                  @update:checked="(v: boolean) => toggleQuickCodeSourceBranch(branch, v)"
                >
                  {{ branch }}
                </NCheckbox>
              </div>
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
          <template v-else-if="mode === 'batch'">
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
              <label>指定代码源（可选）</label>
              <NAutoComplete
                v-model:value="batchForm.code_source"
                :options="codeSourceSuggestions"
                :placeholder="codeSourcePlaceholder"
                clearable
                blur-after-select
              />
              <div class="field-hint code-source-hint">
                <span v-if="codeSourceHint">{{ codeSourceHint }}</span>
                <span v-else>{{ CODE_SOURCE_FIELD_HINT }}</span>
              </div>
              <div class="code-source-quick">
                <NCheckbox
                  v-for="branch in CODE_SOURCE_QUICK_BRANCHES"
                  :key="branch"
                  size="small"
                  :checked="codeSourceInput.trim() === branch"
                  @update:checked="(v: boolean) => toggleQuickCodeSourceBranch(branch, v)"
                >
                  {{ branch }}
                </NCheckbox>
              </div>
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
                将入队 <strong>{{ jqlPreview.issues.length }}</strong> 单（JQL 命中 {{ jqlPreview.total }}）
                <EaPill v-if="jqlPreview.truncated" variant="warn">
                  已截至上限 {{ jqlPreview.cap ?? jqlPreview.issues.length }}
                </EaPill>
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

          <!-- 本地日志分析 -->
          <template v-else>
            <div class="ea-field">
              <label>本地日志路径 <span class="req">*</span></label>
              <NInput
                v-model:value="localForm.log_path"
                placeholder="如 D:\logs\modem\issue_001 或 /data/local/tmp/modem_log"
                clearable
              />
            </div>

            <div class="ea-field">
              <label>问题描述 <span class="req">*</span></label>
              <NInput
                v-model:value="localForm.problem_description"
                type="textarea"
                placeholder="描述现象、复现条件、关注模块（如 SIM 掉卡、数据不通）..."
                :autosize="{ minRows: 3, maxRows: 8 }"
              />
            </div>

            <div class="ea-field">
              <label>指定代码源（可选）</label>
              <NAutoComplete
                v-model:value="localForm.code_source"
                :options="codeSourceSuggestions"
                :placeholder="codeSourcePlaceholder"
                clearable
                blur-after-select
              />
              <div class="field-hint code-source-hint">
                <span v-if="codeSourceHint">{{ codeSourceHint }}</span>
                <span v-else>{{ CODE_SOURCE_FIELD_HINT }}</span>
              </div>
              <div class="code-source-quick">
                <NCheckbox
                  v-for="branch in CODE_SOURCE_QUICK_BRANCHES"
                  :key="branch"
                  size="small"
                  :checked="codeSourceInput.trim() === branch"
                  @update:checked="(v: boolean) => toggleQuickCodeSourceBranch(branch, v)"
                >
                  {{ branch }}
                </NCheckbox>
              </div>
            </div>

            <NAlert type="info" :show-icon="false" style="margin-bottom: 12px">
              本地模式跳过 JIRA 拉取与日志下载，进度条从<strong>大模型分析</strong>起步；Agent 仍会按问题描述在 Skills 目录匹配并 Read 分析 Skill。完成后不支持备注到 JIRA。
            </NAlert>

            <div class="ea-row ea-wrap action-row">
              <NButton
                type="primary"
                :loading="submitting"
                :disabled="!modelProviderReady || !localForm.log_path.trim() || !localForm.problem_description.trim()"
                @click="startLocalAnalysis"
              >
                开始分析
              </NButton>
            </div>
          </template>
          </div>

          <div class="submit-fold-wrap">
            <NTooltip placement="bottom" trigger="hover">
              <template #trigger>
                <button
                  type="button"
                  class="submit-fold-btn"
                  :aria-label="submitFormCollapsed ? '展开提交分析任务' : '收起提交分析任务，扩大任务列表'"
                  :aria-expanded="!submitFormCollapsed"
                  @click="toggleSubmitForm"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                    <polyline points="18 15 12 9 6 15" />
                  </svg>
                </button>
              </template>
              {{ submitFormCollapsed ? '展开提交分析任务' : '收起，扩大任务列表' }}
            </NTooltip>
          </div>
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
            <div class="ea-row" style="gap: 6px">
              <button
                type="button"
                class="search-toggle-btn"
                :class="{ active: searchExpanded }"
                title="搜索任务"
                @click="toggleSearch"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="7" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
              </button>
              <EaPill v-if="!isSearching" variant="muted">
                {{ taskListMode === 'recent' ? store.recentTasks.length : historyReports.length }} 条
              </EaPill>
            </div>
          </div>

          <div v-if="searchExpanded" class="task-search-bar">
            <NInput
              ref="searchInputRef"
              v-model:value="searchKeyword"
              size="small"
              placeholder="搜索"
              clearable
            />
          </div>

          <div class="task-list-body">
          <template v-if="isSearching">
            <NScrollbar class="task-scroll" trigger="none">
              <div class="ea-tasklist">
                <div v-if="filteredRecent.length" class="search-group">
                  <div class="search-group-title">最近任务 ({{ filteredRecent.length }})</div>
                  <button
                    v-for="t in filteredRecent"
                    :key="`recent-${t.task_id}`"
                    type="button"
                    class="ea-task-item"
                    :class="{ active: !isHistoryView && currentTaskId === t.task_id, [`status-${t.status}`]: true }"
                    @click="selectTask(t.task_id)"
                  >
                    <div class="ti-top">
                      <span class="ti-key">{{ t.jira_key }}</span>
                      <EaPill :variant="statusPillVariant(t.status)">{{ t.status }}</EaPill>
                    </div>
                    <div class="ti-title">{{ bugTaskListTitle(t) }}</div>
                    <div class="ti-meta">
                      <span
                        class="ea-dot"
                        :class="{ 'ea-dot-live': t.status === 'running' }"
                        :style="t.status !== 'running' ? { background: phaseColor(t.phase, t.status) } : undefined"
                      />
                      <span>{{ phaseLabel(t.phase, t.status) }}</span>
                      <span v-if="t.skills_used?.length" class="ti-badge">{{ t.skills_used.length }} skill</span>
                      <span v-if="t.skills_improved?.length" class="ti-badge ti-improve">自改进 {{ t.skills_improved.length }}</span>
                      <span v-if="t.parent_job_id" class="ti-badge ti-batch">批量</span>
                    </div>
                  </button>
                </div>
                <div v-if="filteredHistory.length" class="search-group">
                  <div class="search-group-title">历史任务 ({{ filteredHistory.length }})</div>
                  <div
                    v-for="r in filteredHistory"
                    :key="`history-${r.task_id}`"
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
                        <span v-if="r.skills_improved?.length" class="ti-badge ti-improve">自改进 {{ r.skills_improved.length }}</span>
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
                <NEmpty
                  v-if="!filteredRecent.length && !filteredHistory.length"
                  description="没有匹配的任务"
                  size="small"
                />
              </div>
            </NScrollbar>
          </template>

          <template v-else-if="taskListMode === 'recent'">
            <NEmpty v-if="!store.recentTasks.length && !store.recentJobs.length" size="small" description="还没有任务" />
            <NScrollbar v-else class="task-scroll" trigger="none">
              <div v-if="store.recentJobs.length" class="ea-tasklist queue-list">
                <div class="search-group-title">批量队列 ({{ store.recentJobs.length }})</div>
                <button
                  v-for="j in store.recentJobs"
                  :key="`job-${j.job_id}`"
                  type="button"
                  class="ea-task-item"
                  :class="{ active: !isHistoryView && !currentTaskId && currentJobId === j.job_id, [`status-${j.status}`]: true }"
                  @click="selectQueue(j.job_id)"
                >
                  <div class="ti-top">
                    <span class="ti-key">批量 {{ j.total }} 单</span>
                    <EaPill :variant="statusPillVariant(j.status)">{{ j.status }}</EaPill>
                  </div>
                  <div class="ti-title">{{ j.jql || j.job_id }}</div>
                  <div class="ti-meta">
                    <span class="stat-ok">成功 {{ recentJobQueueCounts[j.job_id]?.completed ?? j.completed }}</span>
                    <span class="stat-err">失败 {{ recentJobQueueCounts[j.job_id]?.failed ?? j.failed }}</span>
                    <span v-if="recentJobQueueCounts[j.job_id]?.cancelled" class="stat-warn">
                      取消 {{ recentJobQueueCounts[j.job_id].cancelled }}
                    </span>
                    <span class="ea-muted">共 {{ j.total }}</span>
                  </div>
                </button>
              </div>
              <div class="ea-tasklist">
                <div v-if="store.recentJobs.length" class="search-group-title">最近任务 ({{ store.recentTasks.length }})</div>
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
                  <div class="ti-title">{{ bugTaskListTitle(t) }}</div>
                  <div class="ti-meta">
                    <span
                      class="ea-dot"
                      :class="{ 'ea-dot-live': t.status === 'running' }"
                      :style="t.status !== 'running' ? { background: phaseColor(t.phase, t.status) } : undefined"
                    />
                    <span>{{ phaseLabel(t.phase, t.status) }}</span>
                    <span v-if="t.skills_used?.length" class="ti-badge">{{ t.skills_used.length }} skill</span>
                    <span v-if="t.skills_improved?.length" class="ti-badge ti-improve">自改进 {{ t.skills_improved.length }}</span>
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
                        <span v-if="r.skills_improved?.length" class="ti-badge ti-improve">自改进 {{ r.skills_improved.length }}</span>
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
          <p v-if="currentJob.resumed_from" class="ea-muted" style="font-size: 12px; margin: -4px 0 8px">
            续跑自 <code class="mono">{{ currentJob.resumed_from }}</code>
          </p>
          <div class="job-progress">
            <span class="ea-muted" style="font-size: 12px">进度</span>
            <NProgress
              :percentage="currentJob.total ? Math.round((currentJobSettled / currentJob.total) * 100) : 0"
              :show-indicator="true"
            />
            <div class="jp-stats">
              完成 <strong class="stat-ok">{{ queueCounts.completed }}</strong> /
              失败 <strong class="stat-err">{{ queueCounts.failed }}</strong>
              <template v-if="queueCounts.cancelled">
                / 取消 <strong class="stat-warn">{{ queueCounts.cancelled }}</strong>
              </template>
              / 总 {{ currentJob.total }}
            </div>
          </div>

          <NAlert v-if="currentJob.status === 'interrupted' && canResumeUnfinished" type="warning" :show-icon="false" style="margin: 12px 0">
            该队列在服务重启前没跑完，未完成的单子没有结论。点「继续未完成」会用新的子任务重跑它们。
          </NAlert>

          <div v-if="canResumeUnfinished || (currentJob.status !== 'running' && currentJobFailedOnly > 0)" class="ea-row ea-wrap" style="gap: 8px; margin: 12px 0 6px">
            <NButton
              v-if="canResumeUnfinished"
              size="small"
              type="primary"
              :loading="jobActionLoading"
              :disabled="!modelProviderReady"
              @click="resumeCurrentJob"
            >
              继续未完成
            </NButton>
            <NButton
              v-if="currentJob.status !== 'running' && currentJobFailedOnly > 0"
              size="small"
              :loading="jobActionLoading"
              :disabled="!modelProviderReady"
              @click="retryCurrentJobFailures"
            >
              重跑失败项（{{ currentJobFailedOnly }}）
            </NButton>
          </div>

          <div class="ea-row ea-wrap queue-filters">
            <button
              v-for="f in QUEUE_FILTERS"
              :key="f.key"
              type="button"
              class="queue-filter"
              :class="{ active: queueFilter === f.key }"
              @click="queueFilter = f.key"
            >
              {{ f.label }} {{ queueCounts[f.key] }}
            </button>
          </div>

          <p class="ea-muted" style="font-size: 12px; margin: 10px 0 6px">点击任一子任务查看详情：</p>
          <NScrollbar style="max-height: 420px">
            <div class="job-tasks">
              <button
                v-for="tid in filteredQueueTaskIds"
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
                  <span class="ea-dot" :style="{ background: phaseColor(store.tasks[tid]?.phase, store.tasks[tid]?.status) }" />
                  <span>{{ phaseLabel(store.tasks[tid]?.phase, store.tasks[tid]?.status) }}</span>
                </div>
              </button>
            </div>
          </NScrollbar>
          <NEmpty v-if="!filteredQueueTaskIds.length" description="该筛选下没有子任务" style="padding: 16px 0" />
        </EaCard>

        <EaCard v-else-if="currentTask" class="bug-main bug-detail">
          <div class="ea-row ea-between task-head">
            <div class="ea-row task-head-left">
              <button v-if="parentQueueJob" type="button" class="queue-back" @click="backToQueue">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
                返回队列
              </button>
              <EaPill v-if="isHistoryView" variant="muted">历史记录</EaPill>
              <EaPill :variant="statusPillVariant(currentTask.status)">
                <span v-if="isRunning" class="ea-dot-live" />
                {{ phaseLabel(currentTask.phase, currentTask.status) }}
              </EaPill>
              <a v-if="currentTask.jira_url" :href="currentTask.jira_url" target="_blank" class="ti-key">{{ currentTask.jira_key }}</a>
              <span v-else class="ti-key">{{ currentTask.jira_key }}</span>
              <span class="ea-muted task-title">{{ currentTask.title || '...' }}</span>
            </div>
            <div class="ea-row">
              <EaPill v-if="queuePosition" variant="info">队列 {{ queuePosition.index }}/{{ queuePosition.total }}</EaPill>
              <EaPill v-if="currentTask.module" variant="muted">{{ currentTask.module }}</EaPill>
              <NTooltip v-if="currentTaskCodeSource" placement="bottom" trigger="hover">
                <template #trigger>
                  <EaPill variant="info">代码源 {{ currentTaskCodeSourceLabel }}</EaPill>
                </template>
                {{ currentTaskCodeSource.raw }}
                <template v-if="currentTaskCodeSource.exists === false">（BFF 探测：路径不可访问）</template>
              </NTooltip>
              <code class="mono task-id">{{ currentTask.task_id }}</code>
            </div>
          </div>

          <div v-if="taskRunError" class="bug-error-banner">
            <strong>{{ currentTask?.status === 'cancelled' ? '任务已取消' : '分析失败' }}</strong>
            <pre class="bug-error-text">{{ taskRunError }}</pre>
            <div class="ea-row" style="gap:8px;margin-top:8px;">
              <NButton size="small" type="warning" @click="router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'models' } })">前往配置</NButton>
              <NButton
                v-if="!isHistoryView"
                size="small"
                :disabled="!modelProviderReady || isRunning"
                @click="openContinue"
              >
                补充信息重试
              </NButton>
            </div>
          </div>

          <div v-if="currentSkillsImproved.length && !(activeReportTab === 'report' && reportMarkdown)" class="bug-skill-improve-banner">
            <strong>本次任务自改进了 {{ currentSkillsImproved.length }} 个 Skill</strong>
            <ul class="bug-skill-improve-list">
              <li v-for="s in currentSkillsImproved" :key="s.name">
                <RouterLink :to="improvedSkillRoute(s.name)" class="bug-skill-improve-link">{{ s.name }}</RouterLink>
                <span v-if="skillImproveActionLabel(s.actions)">（{{ skillImproveActionLabel(s.actions) }}）</span>
                <button
                  v-if="s.snapshot_dir"
                  type="button"
                  class="bug-skill-improve-snap"
                  @click="openSkillSnapshot(s)"
                >查看快照</button>
                <span v-if="s.snapshot_source === 'backfill'" class="bug-skill-improve-backfill">事后回填</span>
              </li>
            </ul>
            <p class="bug-skill-improve-hint">改动写在本机 Hermes Skill 目录，可在 Skills 库「自改进」Tab 查看并固化进仓库。</p>
          </div>

          <div v-if="currentTask" class="task-progress">
            <NProgress :percentage="displayProgress" :show-indicator="false" :height="6" :color="phaseColor(currentTask.phase, currentTask.status)" />
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
                  <EaPill v-else-if="isWaitingUserInput" variant="warn">等待配置输入</EaPill>
                  <EaPill v-else-if="currentPendingApproval" variant="warn">等待命令确认</EaPill>
                  <EaPill v-else-if="isHistoryView || currentTask.status === 'completed'" variant="ok">已完成</EaPill>
                  <EaPill v-else-if="currentTask.status === 'failed'" variant="err">失败</EaPill>
                </div>
                <div class="live-monitor-grid">
                  <div class="live-activity-panel">
                    <div class="live-activity-head">
                      <strong>执行动态</strong>
                      <span v-if="isRunning" class="ea-muted live-activity-sub">实时更新</span>
                    </div>
                    <div ref="activityScroller" class="live-activity-body">
                      <div v-if="!liveActivityItems.length" class="live-activity-empty ea-muted">
                        {{ isRunning ? '等待 Agent 开始输出...' : '暂无执行记录' }}
                      </div>
                      <div
                        v-for="item in liveActivityItems"
                        :key="item.key"
                        class="live-activity-line"
                        :class="{ 'is-tool': item.kind === 'task.skill_use' || item.kind === 'task.tool_completed' }"
                      >
                        {{ item.text }}
                      </div>
                    </div>
                  </div>
                  <div class="live-llm-main">
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
                    <div v-if="agentSkillEvents.length" class="live-tool-strip">
                      <div class="live-tool-head ea-muted">最近工具调用</div>
                      <div class="live-tool-list">
                        <span
                          v-for="(ev, i) in agentSkillEvents.slice(-6)"
                          :key="'tool-' + i"
                          class="live-tool-chip"
                        >
                          {{ String(ev.payload?.skill_id || 'tool') }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-show="activeReportTab === 'report'" class="tab-pane tab-pane-report">
              <NSpin :show="reportLoading" class="report-spin-wrap">
                <NScrollbar v-if="reportDetail && reportMarkdown" class="report-body-scroll" trigger="none">
                  <div class="report-markdown-inner">
                    <div v-if="currentSkillsImproved.length" class="bug-skill-improve-banner bug-skill-improve-in-report">
                      <strong>本次任务自改进了 {{ currentSkillsImproved.length }} 个 Skill</strong>
                      <ul class="bug-skill-improve-list">
                        <li v-for="s in currentSkillsImproved" :key="'report-' + s.name">
                          <RouterLink :to="improvedSkillRoute(s.name)" class="bug-skill-improve-link">{{ s.name }}</RouterLink>
                          <span v-if="skillImproveActionLabel(s.actions)">（{{ skillImproveActionLabel(s.actions) }}）</span>
                          <button
                            v-if="s.snapshot_dir"
                            type="button"
                            class="bug-skill-improve-snap"
                            @click="openSkillSnapshot(s)"
                          >查看快照</button>
                          <span v-if="s.snapshot_source === 'backfill'" class="bug-skill-improve-backfill">事后回填</span>
                        </li>
                      </ul>
                      <p class="bug-skill-improve-hint">改动写在本机 Hermes Skill 目录，可在 Skills 库「自改进」Tab 查看并固化进仓库。</p>
                    </div>
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
                  <span class="ea-muted log-hint">
                    日志文件: <code>{{ currentTaskId }}.log</code>
                    <template v-if="isRunning"> · 运行中每 2.5s 自动刷新</template>
                  </span>
                  <NSpace size="small">
                    <NButton size="small" @click="() => loadLog()">刷新</NButton>
                    <NButton size="small" type="primary" :disabled="!displayTaskLog" @click="downloadLog">下载日志</NButton>
                  </NSpace>
                </div>
                <pre class="log-body">{{ displayTaskLog || '(无日志或未加载)' }}</pre>
              </NSpin>
            </div>
          </div>

          <footer class="task-footer">
            <NSpace size="small" wrap>
              <NButton
                v-if="!isHistoryView && (isRunning || isPending || isWaitingUserInput)"
                type="warning"
                @click="stopOrCancelCurrentTask"
              >
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12"/></svg>
                </template>
                {{ isRunning ? '强行中断当前任务' : isWaitingUserInput ? '取消等待配置' : '取消等待中的任务' }}
              </NButton>

              <NButton
                v-if="canContinueAnalysis"
                :disabled="!modelProviderReady"
                @click="openContinue"
              >
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                </template>
                补充信息继续分析
              </NButton>
              <NButton :disabled="!distillCompleted" @click="openDistillKnowledge">
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
                </template>
                沉淀为知识库
              </NButton>
              <NButton :disabled="!distillCompleted" @click="openDistillSkill">
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/></svg>
                </template>
                沉淀为 Skill
              </NButton>
              <NButton
                v-if="canPostJiraComment"
                type="warning"
                secondary
                strong
                class="jira-comment-btn"
                @click="openJiraCommentDialog"
              >
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </template>
                分析结论回到jira comment
              </NButton>
            </NSpace>
          </footer>
        </EaCard>
      </div>
    </div>

    <!-- ────── 补充信息继续分析弹窗 ────── -->
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
        将在<strong>当前 Agent 会话</strong>中继续分析
        <strong>{{ isLocalAnalysisTask ? '本地日志' : currentTask?.jira_key }}</strong>：
        流式窗口保留此前对话，并在下方追加本轮输出；分析报告 Tab 在完成后更新为最新一版。
        补充信息仅用于完善对该{{ isLocalAnalysisTask ? '任务' : ' JIRA 单' }}的分析，不会切换到其它 Issue。
      </div>
      <NInput
        v-model:value="continueText"
        type="textarea"
        placeholder="补充新发现的现象、最新日志结论、复现步骤变化、已排除可能..."
        :autosize="{ minRows: 5, maxRows: 12 }"
      />
    </NModal>

    <BugAnalysisInteractionModal
      :approval="currentPendingApproval"
      :user-input="currentPendingUserInput"
      :submitting="interactionSubmitting"
      @approval="onApprovalRespond"
      @user-input="onUserInputSubmit"
      @dismiss="onInteractionDismiss"
    />

    <!-- ────── 分析结论回到 jira comment ────── -->
    <NModal
      v-model:show="showJiraCommentDialog"
      preset="card"
      title="分析结论回到jira comment"
      style="width: 720px"
      :mask-closable="false"
    >
      <NAlert type="info" :show-icon="false" style="margin-bottom: 12px">
        默认填入报告<strong>第 4 节「根因定位」</strong>与<strong>第 9 节「Jira 备注」</strong>（分析结论 / 结论依据 / 建议）。
        勾选其它章节会追加到预览末尾，取消勾选会去掉对应段落；预览可直接删改后写入
        <strong>{{ currentTask?.jira_key }}</strong>。
      </NAlert>
      <div v-if="jiraCommentSections.length" class="jira-section-block">
        <div class="modal-body-text">选择章节：</div>
        <div class="jira-section-checks">
          <NCheckbox
            v-for="section in jiraCommentSections"
            :key="section.id"
            :checked="isJiraCommentSectionChecked(section.id)"
            @update:checked="(v: boolean) => onJiraCommentSectionToggle(section.id, v)"
          >
            {{ section.title }}
            <span v-if="section.defaultSelected" class="jira-section-default">默认</span>
          </NCheckbox>
        </div>
      </div>
      <div class="modal-body-text">备注内容（可编辑）：</div>
      <NInput
        v-model:value="jiraCommentText"
        type="textarea"
        placeholder="分析结论、结论依据、建议..."
        :autosize="{ minRows: 8, maxRows: 16 }"
      />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showJiraCommentDialog = false">取消</NButton>
          <NButton
            type="primary"
            :loading="jiraCommentSubmitting"
            :disabled="!jiraCommentText.trim()"
            @click="submitJiraComment"
          >
            提交
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- ────── 知识沉淀弹窗 ────── -->
    <NModal
      v-model:show="showDistillDialog"
      preset="card"
      :title="distillDialogTitle"
      style="width: 660px"
      :mask-closable="false"
    >
      <!-- Step 1: 沉淀为知识条目 -->
      <div v-if="distillStep === 'deposit'">
        <NAlert type="info" :show-icon="false" style="margin-bottom: 12px">
          <template v-if="distillMode === 'knowledge'">
            将本次诊断结论沉淀为<strong>知识条目</strong>（状态：待审核），可在知识库中审核后启用。
          </template>
          <template v-else>
            将先创建知识条目作为 Skill 关联来源，随后检索相关 Skill，支持补充到现有 Skill 或新建草稿。
          </template>
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
      </div>

      <!-- Step 2: 关联 / 生成 Skill -->
      <div v-else>
        <div v-if="skillOpActive" class="skill-op-panel">
          <div class="skill-op-steps">
            <div
              v-for="(step, i) in skillOpSteps"
              :key="'skill-op-' + i"
              class="skill-op-step"
              :class="{
                'step-finish': step.status === 'finish',
                'step-process': step.status === 'process',
                'step-error': step.status === 'error',
                'step-wait': step.status === 'wait',
              }"
            >
              <span class="skill-op-step-icon">
                <template v-if="step.status === 'finish'">✓</template>
                <template v-else-if="step.status === 'error'">✕</template>
                <template v-else-if="step.status === 'process'">●</template>
                <template v-else>{{ i + 1 }}</template>
              </span>
              <span class="skill-op-step-label">{{ step.label }}</span>
            </div>
          </div>
          <p class="skill-op-message" :class="{ 'is-error': skillOpSteps.some(s => s.status === 'error') }">
            {{ skillOpMessage }}
          </p>
          <NProgress
            type="line"
            :percentage="skillOpProgress"
            :show-indicator="true"
            :height="10"
            :status="skillOpSteps.some(s => s.status === 'error') ? 'error' : skillOpProgress >= 100 ? 'success' : 'default'"
          />
        </div>

        <template v-else>
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
                  :disabled="!!distillSkillBusy"
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
              <NButton
                type="primary"
                :disabled="!!distillSkillBusy"
                :loading="distillSkillBusy === '__new__'"
                @click="distillCreateNew"
              >
                ＋ 新建 Skill 草稿
              </NButton>
            </div>
          </NSpin>
        </template>
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
              {{ distillMode === 'skill' ? '沉淀并关联 Skill' : '沉淀为知识条目' }}
            </NButton>
          </template>
          <template v-else>
            <NButton :disabled="skillOpBlocking" @click="showDistillDialog = false">完成</NButton>
            <NButton tertiary :disabled="skillOpBlocking" @click="goToWorkshop">前往 Skill 工坊</NButton>
          </template>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="snapshotModalShow"
      preset="card"
      :title="snapshotSkillName ? `Skill 快照 · ${snapshotSkillName}` : 'Skill 快照'"
      style="width: min(820px, 92vw)"
    >
      <NSpin :show="snapshotLoading">
        <NAlert
          v-if="snapshotData?.snapshot_source === 'backfill'"
          type="warning"
          :bordered="false"
          style="margin-bottom: 12px"
        >
          这是事后回填的快照，内容是回填当时 profile 上的版本，不一定等于任务结束那一刻。
        </NAlert>
        <p v-if="snapshotError" class="bug-skill-improve-hint">{{ snapshotError }}</p>
        <MarkdownRenderer v-else-if="snapshotData?.skill_md" :content="snapshotData.skill_md" />
        <NEmpty v-else-if="!snapshotLoading" description="没有可显示的快照内容" />
      </NSpin>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
.bug-analysis-root {
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
  :deep(.model-provider-banner) { margin-bottom: 12px; }
}

.bug-split {
  align-items: stretch;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.bug-left {
  min-height: 0;
  min-width: 0;

  &.submit-collapsed {
    min-height: calc(100vh - 148px);
    overflow: hidden;
  }
}

.bug-submit-card {
  position: relative;
  z-index: 2;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.submit-head {
  margin-bottom: 14px;
}

.submit-fold-wrap {
  position: absolute;
  left: 50%;
  bottom: 0;
  z-index: 3;
  transform: translate(-50%, 50%);
}

.submit-fold-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--faint);
  box-shadow: var(--shadow);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;

  svg {
    display: block;
    transition: transform 0.2s ease;
  }

  &:hover,
  &:focus-visible {
    color: var(--accent);
    background: var(--accent-soft);
    border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
    outline: none;
  }
}

.submit-collapsed {
  .bug-submit-card {
    padding-top: 14px;
    padding-bottom: 16px;
  }

  .submit-head {
    margin-bottom: 0;
  }

  .submit-fold-btn svg {
    transform: rotate(180deg);
  }

  .bug-tasks-card {
    flex: 1 1 auto;
    min-height: 0;
  }

  .task-list-spin {
    flex: 1 1 auto;
    min-height: 0;
  }

  .task-list-body,
  .task-scroll {
    flex: 1 1 auto;
    height: auto;
    max-height: none;
    min-height: 0;
  }

  :deep(.task-scroll) {
    height: 100%;
    max-height: none;
  }

  :deep(.n-scrollbar-container),
  :deep(.n-spin-content) {
    height: 100%;
  }
}

.bug-tasks-card {
  position: relative;
  z-index: 1;
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

.search-toggle-btn {
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  padding: 0;
  /* 默认：柔和品牌色 chip，明显是可点 */
  color: var(--accent);
  background: var(--accent-soft);
  transition: background .15s ease, color .15s ease, box-shadow .15s ease;
  &:hover {
    background: linear-gradient(135deg, var(--accent), var(--violet-ic));
    color: #fff;
    box-shadow: 0 2px 8px -2px color-mix(in srgb, var(--accent) 50%, transparent);
  }
  &.active {
    background: linear-gradient(135deg, var(--accent), var(--violet-ic));
    color: #fff;
    box-shadow: 0 2px 8px -2px color-mix(in srgb, var(--accent) 50%, transparent);
  }
}

.task-search-bar {
  flex-shrink: 0;
  margin-bottom: 10px;
}

.search-group {
  margin-bottom: 8px;
}

.search-group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  padding: 4px 8px;
  position: sticky;
  top: 0;
  background: var(--surface-1);
  z-index: 1;
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

.ai2d-field {
  margin-bottom: 16px;

  label {
    color: var(--accent);
  }
}

.ai2d-box {
  border: 1px solid var(--accent);
  border-radius: 8px;
  padding: 6px 10px;
  background: var(--accent-soft);
}

.ai2d-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
  font-size: 13px;
}

.ai2d-label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.ai2d-warn {
  font-size: 11px;
  color: var(--warn, #d97706);
}

.field-hint { font-size: 11px; color: var(--muted); margin-top: 4px; }
.code-source-hint { display: block; }
.code-source-quick {
  display: grid;
  grid-template-columns: repeat(2, max-content);
  column-gap: 20px;
  row-gap: 6px;
  margin-top: 8px;
  :deep(.n-checkbox) {
    font-size: 11px;
    color: var(--muted);
  }
}
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
.ti-badge { background: var(--warn-soft); color: var(--warn); padding: 1px 6px; border-radius: 6px; font-weight: 600; &.ti-batch { background: var(--violet-bg); color: var(--violet-fg); } &.ti-improve { background: color-mix(in srgb, var(--success) 16%, var(--surface)); color: var(--success); } }

.bug-main-wrap {
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.bug-main {
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.bug-detail {
  min-height: 520px;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
.stat-warn { color: var(--warn); }
.job-tasks { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.ea-task-item.compact { padding: 10px 12px; }

.queue-list { margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--line); }

.queue-back {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 6px;
  background: transparent; color: var(--muted);
  &:hover { color: var(--accent, #2080f0); border-color: var(--accent, #2080f0); }
}

.queue-filters { gap: 6px; }
.queue-filter {
  padding: 4px 10px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 12px;
  background: transparent; color: var(--muted);
  &:hover { color: var(--text); }
  &.active {
    border-color: var(--accent, #2080f0);
    color: var(--accent, #2080f0);
    background: rgba(32, 128, 240, .1);
  }
}

.task-head { margin-bottom: 14px; gap: 12px; flex-wrap: wrap; max-width: 100%; min-width: 0; }
.task-head-left { min-width: 0; gap: 12px; flex-wrap: wrap; flex: 1; }
.task-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 420px; }
.task-id { background: var(--bg); padding: 2px 6px; border-radius: 6px; }

.task-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-shrink: 0; }
.tp-text { font-size: 11px; min-width: 32px; text-align: right; }

.tab-body { flex: 1; min-height: 0; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
.tab-pane {
  flex: 1; min-height: 0; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; padding-bottom: 8px;
}

.live-llm-panel {
  display: flex; flex-direction: column; min-height: 0; min-width: 0; max-height: 100%;
  background: var(--bg); border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
}
.live-llm-panel-full {
  flex: 1;
  min-height: 0;
  min-width: 0;
  height: 100%;
  max-height: 100%;
}
.live-llm-header { padding: 12px 14px; border-bottom: 1px solid var(--line); background: var(--surface); flex-shrink: 0; }
.live-monitor-grid {
  display: grid;
  grid-template-columns: minmax(220px, 34%) minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  min-width: 0;
}
.live-activity-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--line);
  background: var(--surface);
}
.live-activity-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
}
.live-activity-sub { font-size: 11px; }
.live-activity-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.55;
}
.live-activity-empty { padding: 12px 4px; font-size: 12px; }
.live-activity-line {
  padding: 6px 8px;
  margin-bottom: 4px;
  border-radius: 8px;
  background: var(--bg);
  word-break: break-word;
}
.live-activity-line.is-tool {
  border-left: 3px solid var(--brand, #0969da);
}
.live-llm-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}
.live-tool-strip {
  flex-shrink: 0;
  border-top: 1px solid var(--line);
  padding: 8px 12px;
  background: var(--surface);
}
.live-tool-head { font-size: 11px; margin-bottom: 6px; }
.live-tool-list { display: flex; flex-wrap: wrap; gap: 6px; }
.live-tool-chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg);
  border: 1px solid var(--line);
}
.live-llm-body {
  flex: 1; min-height: 0; min-width: 0;
  overflow-x: auto;
  overflow-y: auto;
  padding: 14px 16px;
  font-size: 13.5px; line-height: 1.7; scrollbar-width: thin;

  :deep(.markdown-body) {
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
  }

  :deep(.hljs-code-block) {
    max-width: 100%;

    code.hljs {
      white-space: pre-wrap;
      word-break: break-word;
      overflow-x: auto;
    }
  }
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
  min-width: 0;
}
.report-markdown-inner {
  padding: 4px 12px 16px 4px;
  font-size: 13.5px;
  line-height: 1.7;
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;

  :deep(.markdown-body) {
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
  }

  :deep(.hljs-code-block) {
    max-width: 100%;

    code.hljs {
      white-space: pre-wrap;
      word-break: break-word;
      overflow-x: auto;
    }
  }
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
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.log-body {
  flex: 1;
  min-height: 0;
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

.bug-detail :deep(.ea-stage-track) {
  max-width: 100%;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.task-footer {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  flex-shrink: 0;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
}

/* class 与 .n-button 在同一节点；须覆盖 Naive UI 的 --n-* 变量 */
:deep(.n-button.jira-comment-btn) {
  --n-color: #fff4e6 !important;
  --n-color-hover: #ffe8cc !important;
  --n-color-pressed: #ffddb0 !important;
  --n-color-focus: #ffe8cc !important;
  --n-text-color: #c05621 !important;
  --n-text-color-hover: #9c4221 !important;
  --n-text-color-pressed: #9c4221 !important;
  --n-text-color-focus: #9c4221 !important;
  --n-border: 1px solid #f5c48a !important;
  --n-border-hover: 1px solid #f0b56e !important;
  --n-border-pressed: 1px solid #e9a85c !important;
  --n-border-focus: 1px solid #f0b56e !important;
  font-weight: 600;
}

.modal-hint { margin-bottom: 8px; font-size: 12px; color: var(--muted); }
.modal-body-text { margin-bottom: 8px; font-size: 13px; color: var(--text); }

.jira-section-block { margin-bottom: 12px; }
.jira-section-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.jira-section-default {
  margin-left: 4px;
  font-size: 11px;
  color: var(--muted);
}

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

.skill-op-panel {
  padding: 8px 4px 4px;
}

.skill-op-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}

.skill-op-step {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--muted);

  &.step-finish { color: var(--success, #18a058); }
  &.step-process { color: var(--accent, #2080f0); font-weight: 600; }
  &.step-error { color: var(--error, #d03050); font-weight: 600; }
}

.skill-op-step-icon {
  width: 22px;
  text-align: center;
  flex-shrink: 0;
  font-size: 12px;
}

.skill-op-step-label { line-height: 1.4; }

.skill-op-message {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-2, #666);
  line-height: 1.5;

  &.is-error { color: var(--error, #d03050); }
}

.bug-error-banner {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--error) 12%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--error) 35%, transparent);
  color: var(--error);
}

.bug-skill-improve-banner {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--success) 12%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--success) 35%, transparent);
  color: var(--text);
}

.bug-skill-improve-banner strong {
  display: block;
  color: var(--success);
  font-size: 13px;
}

.bug-skill-improve-in-report {
  margin-bottom: 18px;
}

.bug-skill-improve-list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.6;
}

.bug-skill-improve-link {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  border-bottom: 1px dashed color-mix(in srgb, var(--accent) 45%, transparent);
}
.bug-skill-improve-link:hover {
  text-decoration: none;
  border-bottom-style: solid;
}

.bug-skill-improve-snap {
  margin-left: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--success);
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.bug-skill-improve-backfill {
  margin-left: 6px;
  font-size: 11px;
  color: #b45309;
}

.bug-skill-improve-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.bug-error-text {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
  font-family: ui-monospace, monospace;
}

code {
  background: var(--surface-2); padding: 1px 5px; border-radius: 4px;
  font-size: 0.9em; font-family: ui-monospace, monospace;
}

/* Desktop: left column owns Grid row height; right card fills via absolute inset. */
@media (min-width: 1101px) {
  .bug-main-wrap {
    position: relative;
    overflow: hidden;
  }

  .bug-main {
    position: absolute;
    inset: 0;
    flex: none;
    width: 100%;
    height: 100%;
  }

  .bug-detail {
    min-height: 0;
  }
}

@media (max-width: 1100px) {
  .task-title { max-width: 100%; }
}
</style>