<script setup lang="ts">
/**
 * 质量评测 — bug-analysis / adapt / retrieval 三套评测域。
 * 回答「改了 skill / 路由 / 换了模型之后，质量是变好还是变坏」。
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NSpin, NEmpty, NModal, NButton, NSelect, NInput, NInputNumber,
  NPopconfirm, NSwitch, NTooltip, useMessage,
} from 'naive-ui'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import EaSectionTitle from '@/components/layout/EaSectionTitle.vue'
import { subscribeTahp } from '@/api/tahp/socket'
import {
  abortEvalRun, compareEvalRuns, createEvalCaseFromReport, deleteEvalCase,
  exportEvalBundle, getCalibration, getEvalCaseResult, getEvalRun, importEvalBundle,
  importRetrievalSeeds, listEvalCandidates, listEvalCases, listEvalRuns, saveEvalCase,
  setHumanLabel, startEvalRun,
  type CalibrationReport, type CaseVerdict, type EvalCase, type EvalCaseCandidate,
  type EvalCaseResult, type EvalCaseStatus, type EvalComparison, type EvalRunSummary,
  type EvalSuite, type Rubric,
} from '@/api/tahp/eval'

const router = useRouter()
const message = useMessage()

const suite = ref<EvalSuite>('adapt')
const activeTab = ref<'runs' | 'cases'>('runs')

const suiteOptions = [
  { label: 'AI 适配', value: 'adapt' },
  { label: '智能诊断', value: 'bug-analysis' },
  { label: '检索路由', value: 'retrieval' },
]

const pageTitle = computed(() => {
  if (suite.value === 'adapt') return '适配评测'
  if (suite.value === 'retrieval') return '检索路由评测'
  return '诊断评测'
})
const pageSubtitle = computed(() => {
  if (suite.value === 'adapt') {
    return '客观信号优先（完成/改动/编译/自检），衡量 skill / 模型改动对适配质量的影响'
  }
  if (suite.value === 'retrieval') {
    return '完全离线：断言 intent / skill top-k / preferred / mode 覆盖是否选对，不调 Agent'
  }
  return '对固定用例批量重跑 Bug 分析并由判官打分，衡量 skill / 模型改动带来的质量变化'
})

const importingSeeds = ref(false)
const exportingBundle = ref(false)
const importingBundle = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ── 评测记录 ────────────────────────────────────────────────────────────────
const runs = ref<EvalRunSummary[]>([])
const runsLoading = ref(false)
const selectedRunId = ref<string>('')
const selectedRun = ref<EvalRunSummary | null>(null)

const baselineId = ref<string>('')
const comparison = ref<EvalComparison | null>(null)

const drill = ref<{ result: EvalCaseResult; case: EvalCase | null } | null>(null)
const calibration = ref<CalibrationReport | null>(null)
const labelNote = ref('')

// ── 评测集 ──────────────────────────────────────────────────────────────────
const cases = ref<EvalCase[]>([])
const defaultRubric = ref<Rubric[]>([])
const casesLoading = ref(false)
const candidates = ref<EvalCaseCandidate[]>([])
const candidatesLoading = ref(false)

const editing = ref<EvalCase | null>(null)
const editRubric = ref<Rubric[]>([])

// ── 启动评测 ────────────────────────────────────────────────────────────────
const startModal = ref(false)
const startCaseIds = ref<string[]>([])
const startJudgeModel = ref('')
const startConcurrency = ref(2)
const starting = ref(false)

const runOptions = computed(() =>
  runs.value
    .filter(r => r.run_id !== selectedRunId.value && r.status !== 'running')
    .map(r => ({ label: `${r.run_id}（通过率 ${pct(r.pass_rate)}）`, value: r.run_id })),
)

const caseOptions = computed(() =>
  cases.value.map(c => ({ label: `${c.id}${c.title ? ` · ${c.title}` : ''}`, value: c.id })),
)

const runningRun = computed(() => selectedRun.value?.status === 'running')

let unsubscribers: Array<() => void> = []

onMounted(async () => {
  await reloadSuite()

  unsubscribers = [
    subscribeTahp('eval.case_done', ev => onRunProgress(String(ev.payload?.run_id || ''))),
    subscribeTahp('eval.completed', ev => onRunProgress(String(ev.payload?.run_id || ''))),
    subscribeTahp('eval.failed', ev => onRunProgress(String(ev.payload?.run_id || ''))),
  ]
})

watch(suite, () => { void reloadSuite() })

async function reloadSuite() {
  selectedRunId.value = ''
  selectedRun.value = null
  comparison.value = null
  baselineId.value = ''
  candidates.value = []
  await Promise.all([loadRuns(), loadCases()])
  if (runs.value.length) await selectRun(runs.value[0].run_id)
}

onUnmounted(() => {
  unsubscribers.forEach(off => off())
  unsubscribers = []
})

async function onRunProgress(runId: string) {
  if (!runId) return
  await loadRuns()
  if (runId === selectedRunId.value) await refreshSelectedRun()
}

// ── 数据加载 ────────────────────────────────────────────────────────────────

async function loadRuns() {
  runsLoading.value = true
  try {
    runs.value = await listEvalRuns(suite.value)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    runsLoading.value = false
  }
}

async function refreshSelectedRun() {
  if (!selectedRunId.value) return
  try {
    const [run, report] = await Promise.all([
      getEvalRun(selectedRunId.value),
      getCalibration(selectedRunId.value),
    ])
    selectedRun.value = run
    calibration.value = report
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function selectRun(runId: string) {
  selectedRunId.value = runId
  comparison.value = null
  baselineId.value = ''
  await refreshSelectedRun()
}

async function loadCases() {
  casesLoading.value = true
  try {
    const data = await listEvalCases(suite.value)
    cases.value = data.cases
    defaultRubric.value = data.default_rubric
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    casesLoading.value = false
  }
}

async function loadCandidates() {
  candidatesLoading.value = true
  try {
    candidates.value = await listEvalCandidates(suite.value)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    candidatesLoading.value = false
  }
}

// ── 评测操作 ────────────────────────────────────────────────────────────────

function openStartModal() {
  if (!cases.value.length) {
    message.warning(
      suite.value === 'retrieval'
        ? '评测集为空，请先导入种子案例或转为案例'
        : '评测集为空，请先在「评测集」页转存用例',
    )
    return
  }
  startCaseIds.value = []
  if (suite.value === 'retrieval') startConcurrency.value = 8
  else startConcurrency.value = 2
  startModal.value = true
}

async function confirmStart() {
  starting.value = true
  try {
    const result = await startEvalRun({
      case_ids: startCaseIds.value.length ? startCaseIds.value : undefined,
      judge_model: startJudgeModel.value.trim() || undefined,
      concurrency: startConcurrency.value,
      suite: suite.value,
    })
    message.success(`评测已启动（${result.total} 个用例）`)
    startModal.value = false
    activeTab.value = 'runs'
    await loadRuns()
    await selectRun(result.run_id)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    starting.value = false
  }
}

async function handleAbort() {
  if (!selectedRunId.value) return
  try {
    await abortEvalRun(selectedRunId.value)
    message.info('已请求中止，正在跑的用例结束后停止')
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function handleCompare(runId: string | null) {
  baselineId.value = runId || ''
  comparison.value = null
  if (!runId || !selectedRunId.value) return
  try {
    comparison.value = await compareEvalRuns(selectedRunId.value, runId)
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function openDrill(caseId: string) {
  if (!selectedRunId.value) return
  try {
    drill.value = await getEvalCaseResult(selectedRunId.value, caseId)
    labelNote.value = drill.value.result.human_label?.note || ''
  } catch (err) {
    message.error((err as Error).message)
  }
}

/** 人工独立打分：一致率过低说明 rubric 太主观，此时所有分数都不可信 */
async function submitLabel(verdict: CaseVerdict) {
  if (!drill.value || !selectedRunId.value) return
  try {
    const updated = await setHumanLabel(selectedRunId.value, drill.value.result.case_id, {
      verdict,
      note: labelNote.value.trim() || undefined,
    })
    drill.value = { ...drill.value, result: updated }
    calibration.value = await getCalibration(selectedRunId.value)
    message.success('已记录人工打分')
  } catch (err) {
    message.error((err as Error).message)
  }
}

function openReport(taskId?: string) {
  if (!taskId || suite.value === 'retrieval') return
  if (suite.value === 'adapt') {
    router.push({ name: 'tahp.adapt-debug', query: { task_id: taskId } })
    return
  }
  router.push({ name: 'tahp.bug-analysis', query: { task_id: taskId } })
}

async function adoptCandidate(candidate: EvalCaseCandidate) {
  try {
    let created: EvalCase
    if (suite.value === 'adapt') {
      created = await createEvalCaseFromReport({
        suite: 'adapt',
        kind: candidate.kind || 'adapt_agent',
        task_id: candidate.kind === 'pipeline' ? undefined : (candidate.id || candidate.task_id),
        run_id: candidate.kind === 'pipeline' ? candidate.id : undefined,
        id: candidate.id,
      })
    } else if (suite.value === 'retrieval') {
      created = await createEvalCaseFromReport({
        suite: 'retrieval',
        kind: 'seed',
        seed_id: candidate.id,
        id: candidate.id,
      })
    } else {
      created = await createEvalCaseFromReport({
        suite: 'bug-analysis',
        task_id: candidate.task_id,
      })
    }
    const tip =
      suite.value === 'bug-analysis'
        ? `已转存为用例 ${created.id}，请补全评分标准`
        : `已转为案例 ${created.id}`
    message.success(tip)
    await Promise.all([loadCases(), loadCandidates()])
    openEditor(created)
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function handleImportSeeds() {
  importingSeeds.value = true
  try {
    const result = await importRetrievalSeeds()
    const parts = [
      result.imported.length ? `导入 ${result.imported.length}` : '',
      result.skipped.length ? `跳过已有 ${result.skipped.length}` : '',
      result.errors.length ? `失败 ${result.errors.length}` : '',
    ].filter(Boolean)
    message.success(parts.length ? parts.join('，') : '无变更')
    if (result.errors.length) message.warning(result.errors.slice(0, 3).join('；'))
    await Promise.all([loadCases(), loadCandidates()])
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    importingSeeds.value = false
  }
}

async function handleExportBundle() {
  if (!cases.value.length) {
    message.warning('评测集为空，无法导出')
    return
  }
  exportingBundle.value = true
  try {
    const bundle = await exportEvalBundle(suite.value, { redact: true })
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tahp-eval-${suite.value}-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    const note = bundle.redaction_notes?.length
      ? `（已脱敏 ${bundle.redaction_notes.length} 处）`
      : '（已脱敏）'
    message.success(`已导出 ${bundle.cases.length} 条${note}`)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    exportingBundle.value = false
  }
}

function openImportBundlePicker() {
  fileInputRef.value?.click()
}

async function handleImportBundleFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  importingBundle.value = true
  try {
    const text = await file.text()
    const parsed = JSON.parse(text) as Record<string, unknown>
    const result = await importEvalBundle({
      suite: suite.value,
      bundle: parsed,
      overwrite: false,
    })
    const parts = [
      result.imported.length ? `新增 ${result.imported.length}` : '',
      result.skipped.length ? `跳过 ${result.skipped.length}` : '',
      result.overwritten.length ? `覆盖 ${result.overwritten.length}` : '',
    ].filter(Boolean)
    message.success(parts.length ? parts.join('，') : '无变更')
    await Promise.all([loadCases(), loadCandidates()])
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    importingBundle.value = false
  }
}

function caseSourceMeta(item: EvalCase): string {
  if (item.source.type === 'retrieval_query') {
    const q = item.source.query || item.title || ''
    const intent = item.source.expected_intent || '-'
    return `${intent} · ${q.slice(0, 48)}${q.length > 48 ? '…' : ''}`
  }
  if (item.source.type === 'jira') return item.source.jira_key || item.id
  if (item.source.type === 'adapt_agent' || item.source.type === 'pipeline') {
    return item.source.domain_label || item.source.domain_id || item.source.origin_task_id || item.id
  }
  return item.source.log_path || item.id
}

function openEditor(evalCase: EvalCase) {
  editing.value = evalCase
  editRubric.value = evalCase.rubric.map(r => ({ ...r, must: !!r.must }))
}

function addRubricRow() {
  editRubric.value.push({ id: '', weight: 1, must: false, criterion: '' })
}

function removeRubricRow(index: number) {
  editRubric.value.splice(index, 1)
}

async function saveEditing() {
  if (!editing.value) return
  const invalid = editRubric.value.find(r => !r.id.trim() || !r.criterion.trim())
  if (invalid || !editRubric.value.length) {
    message.error('每条评分标准都需要填写 id 与判分标准')
    return
  }
  try {
    await saveEvalCase(editing.value.id, {
      title: editing.value.title,
      rubric: editRubric.value.map(r => ({ ...r, id: r.id.trim(), criterion: r.criterion.trim() })),
      mode: editing.value.mode,
    }, suite.value)
    message.success('已保存')
    editing.value = null
    await loadCases()
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function removeCase(caseId: string) {
  try {
    await deleteEvalCase(caseId, suite.value)
    message.success(`已删除 ${caseId}`)
    await Promise.all([loadCases(), loadCandidates()])
  } catch (err) {
    message.error((err as Error).message)
  }
}

function switchTab(tab: 'runs' | 'cases') {
  activeTab.value = tab
  if (tab === 'cases' && !candidates.value.length) void loadCandidates()
}

// ── 展示工具 ────────────────────────────────────────────────────────────────

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function signed(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}pp`
}

function fmtTime(iso?: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const STATUS_LABEL: Record<EvalCaseStatus, string> = {
  passed: '通过',
  warned: '警告',
  failed: '失败',
  error: '异常',
}

function statusVariant(status: EvalCaseStatus): 'ok' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'passed': return 'ok'
    case 'warned': return 'warn'
    case 'failed': return 'err'
    default: return 'muted'
  }
}

function runVariant(status: EvalRunSummary['status']): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'completed': return 'ok'
    case 'running': return 'info'
    case 'failed': return 'err'
    case 'aborted': return 'warn'
    default: return 'muted'
  }
}

function deltaVariant(value: number): 'ok' | 'err' | 'muted' {
  if (value > 0.001) return 'ok'
  if (value < -0.001) return 'err'
  return 'muted'
}
</script>

<template>
  <div class="eval-page">
    <EaPageHead :title="pageTitle" :subtitle="pageSubtitle">
      <template #actions>
        <NSelect
          v-model:value="suite"
          :options="suiteOptions"
          size="small"
          style="width: 140px"
        />
        <NButton size="small" @click="switchTab(activeTab === 'runs' ? 'cases' : 'runs')">
          {{ activeTab === 'runs' ? '管理评测集' : '查看评测记录' }}
        </NButton>
        <NButton size="small" type="primary" @click="openStartModal">开始评测</NButton>
      </template>
    </EaPageHead>

    <!-- ── 评测记录 ─────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'runs'" class="eval-main">
      <EaCard class="run-list">
        <EaSectionTitle>评测记录</EaSectionTitle>
        <NSpin :show="runsLoading">
          <NEmpty v-if="!runs.length" description="还没有评测记录" size="small" />
          <button
            v-for="run in runs"
            :key="run.run_id"
            class="run-item"
            :class="{ active: run.run_id === selectedRunId }"
            @click="selectRun(run.run_id)"
          >
            <div class="run-item-head">
              <span class="run-id">{{ run.run_id }}</span>
              <EaPill :variant="runVariant(run.status)">{{ run.status }}</EaPill>
            </div>
            <div class="run-item-meta">
              <span>{{ fmtTime(run.started_at) }}</span>
              <span>通过率 {{ pct(run.pass_rate) }} · {{ run.cases.length }}/{{ run.total }}</span>
            </div>
          </button>
        </NSpin>
      </EaCard>

      <EaCard class="run-detail">
        <NEmpty v-if="!selectedRun" description="选择左侧一条评测记录" />
        <template v-else>
          <div class="detail-head">
            <EaSectionTitle>{{ selectedRun.run_id }}</EaSectionTitle>
            <NButton v-if="runningRun" size="tiny" @click="handleAbort">中止</NButton>
          </div>

          <div class="variant-bar">
            <span>被评模型 <b>{{ selectedRun.variant.model || 'profile 默认' }}</b></span>
            <span>判官 <b>{{ selectedRun.variant.judge_model || 'profile 默认' }}</b></span>
            <span>skills <b>{{ selectedRun.variant.skills_hash }}</b></span>
            <span>判分口径 <b>{{ selectedRun.variant.prompt_version }}</b></span>
          </div>

          <div class="stat-row">
            <div class="stat"><span class="stat-num ok">{{ selectedRun.passed }}</span><span>通过</span></div>
            <div class="stat"><span class="stat-num warn">{{ selectedRun.warned }}</span><span>警告</span></div>
            <div class="stat"><span class="stat-num err">{{ selectedRun.failed }}</span><span>失败</span></div>
            <div class="stat"><span class="stat-num muted">{{ selectedRun.errored }}</span><span>异常</span></div>
            <div class="stat"><span class="stat-num">{{ pct(selectedRun.pass_rate) }}</span><span>通过率</span></div>
            <div class="stat"><span class="stat-num">{{ selectedRun.avg_score.toFixed(3) }}</span><span>平均分</span></div>
          </div>

          <div v-if="calibration" class="calibration-bar" :class="{ ok: calibration.trustworthy, warn: !calibration.trustworthy }">
            <span>
              判官校准：已人工打分 {{ calibration.labeled }} / {{ calibration.min_labeled_samples }}，
              一致率 {{ pct(calibration.agreement_rate) }}
              （门槛 {{ pct(calibration.min_agreement_rate) }}）
            </span>
            <EaPill :variant="calibration.trustworthy ? 'ok' : 'warn'">
              {{ calibration.trustworthy ? '可信' : '尚不可信' }}
            </EaPill>
            <span v-if="!calibration.trustworthy" class="calibration-hint">
              {{ calibration.labeled < calibration.min_labeled_samples
                ? '请在评分明细里继续人工独立打分'
                : '一致率偏低，说明评分标准太主观，请先收紧 rubric' }}
            </span>
          </div>

          <div class="compare-bar">
            <span class="compare-label">与 baseline 对比</span>
            <NSelect
              :value="baselineId || null"
              :options="runOptions"
              size="small"
              clearable
              placeholder="选择一次历史评测"
              style="max-width: 320px"
              @update:value="handleCompare"
            />
            <template v-if="comparison">
              <EaPill :variant="deltaVariant(comparison.pass_rate_delta)">
                通过率 {{ signed(comparison.pass_rate_delta) }}
              </EaPill>
              <EaPill :variant="deltaVariant(comparison.avg_score_delta)">
                平均分 {{ signed(comparison.avg_score_delta) }}
              </EaPill>
            </template>
          </div>

          <div v-if="comparison" class="compare-detail">
            <div v-if="comparison.regressed.length" class="compare-line err">
              回归：{{ comparison.regressed.join('、') }}
            </div>
            <div v-if="comparison.improved.length" class="compare-line ok">
              改善：{{ comparison.improved.join('、') }}
            </div>
            <div v-if="!comparison.variant_matched" class="compare-line warn">
              变体指纹与 baseline 不一致（模型或 skill 改过），分数差异不能单一归因。
            </div>
          </div>

          <table class="case-table">
            <thead>
              <tr><th>用例</th><th>结论</th><th>得分</th><th>说明</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in selectedRun.cases" :key="item.case_id">
                <td>
                  <div class="case-id">{{ item.case_id }}</div>
                  <div v-if="item.title" class="case-title">{{ item.title }}</div>
                </td>
                <td><EaPill :variant="statusVariant(item.status)">{{ STATUS_LABEL[item.status] }}</EaPill></td>
                <td>{{ typeof item.total === 'number' ? item.total.toFixed(2) : '-' }}</td>
                <td class="case-error">{{ item.error || '-' }}</td>
                <td class="case-actions">
                  <NButton v-if="item.status !== 'error'" size="tiny" quaternary @click="openDrill(item.case_id)">
                    评分明细
                  </NButton>
                  <NButton v-if="item.task_id" size="tiny" quaternary @click="openReport(item.task_id)">
                    原报告
                  </NButton>
                </td>
              </tr>
              <tr v-if="!selectedRun.cases.length">
                <td colspan="5" class="empty-row">等待首个用例完成…</td>
              </tr>
            </tbody>
          </table>
        </template>
      </EaCard>
    </div>

    <!-- ── 评测集 ───────────────────────────────────────────────────────── -->
    <div v-else class="eval-main">
      <EaCard class="case-list">
        <div class="detail-head">
          <EaSectionTitle>评测集（{{ cases.length }}）</EaSectionTitle>
          <div class="case-actions">
            <NButton size="tiny" :loading="exportingBundle" :disabled="!cases.length" @click="handleExportBundle">
              导出（脱敏）
            </NButton>
            <NButton size="tiny" :loading="importingBundle" @click="openImportBundlePicker">
              导入
            </NButton>
            <input
              ref="fileInputRef"
              type="file"
              accept="application/json,.json"
              style="display: none"
              @change="handleImportBundleFile"
            >
          </div>
        </div>
          <div class="hint">
            评测集保存在本机 <code>.tahp-config/evals/{{ suite }}/</code>；导出默认脱敏，便于团队共享而不走 git。
          </div>
        <NSpin :show="casesLoading">
          <NEmpty v-if="!cases.length" description="评测集为空，先从右侧导入或转为案例" size="small" />
          <div v-for="item in cases" :key="item.id" class="case-row">
            <div class="case-row-main">
              <div class="case-id">
                {{ item.id }}
                <EaPill v-if="item.had_corrections" variant="warn">曾被补充</EaPill>
                <EaPill v-if="item.mode === 'offline'" variant="info">离线</EaPill>
              </div>
              <div class="case-row-meta">
                {{ caseSourceMeta(item) }}
                · {{ item.rubric.length }} 条评分标准
              </div>
            </div>
            <div class="case-actions">
              <NButton size="tiny" quaternary @click="openEditor(item)">编辑标准</NButton>
              <NPopconfirm @positive-click="removeCase(item.id)">
                <template #trigger><NButton size="tiny" quaternary type="error">删除</NButton></template>
                删除用例 {{ item.id }}？
              </NPopconfirm>
            </div>
          </div>
        </NSpin>
      </EaCard>

      <EaCard class="candidate-list">
        <div class="detail-head">
          <EaSectionTitle>
            {{ suite === 'retrieval' ? '内置种子案例' : '可转存的历史报告' }}
          </EaSectionTitle>
          <div class="case-actions">
            <NButton
              v-if="suite === 'retrieval'"
              size="tiny"
              type="primary"
              :loading="importingSeeds"
              @click="handleImportSeeds"
            >
              一键导入缺失种子
            </NButton>
            <NButton size="tiny" @click="loadCandidates">刷新</NButton>
          </div>
        </div>
        <div class="hint">
          <template v-if="suite === 'adapt'">
            可从适配报告（可重跑）或流水线 run（离线客观分：编译/自检）转存。
          </template>
          <template v-else-if="suite === 'retrieval'">
            种子对齐 intent-router 单测与域路由表；导入后离线断言 intent / skill top-k，不调 Agent。
          </template>
          <template v-else>
            带补充轮次的排在前面 —— 首轮没达标，是天然的负样本。
          </template>
        </div>
        <NSpin :show="candidatesLoading">
          <NEmpty
            v-if="!candidates.length"
            :description="suite === 'retrieval' ? '暂无种子定义' : '没有可转存的已完成报告'"
            size="small"
          />
          <div v-for="item in candidates" :key="item.id || item.task_id" class="case-row">
            <div class="case-row-main">
              <div class="case-id">
                {{ item.jira_key || item.domain_label || item.title || item.id || item.task_id }}
                <EaPill v-if="item.kind === 'pipeline'" variant="info">流水线</EaPill>
                <EaPill v-else-if="item.kind === 'adapt_agent'" variant="info">Agent</EaPill>
                <EaPill v-else-if="item.kind === 'seed'" variant="info">种子</EaPill>
                <EaPill v-if="item.expected_intent" variant="muted">{{ item.expected_intent }}</EaPill>
                <EaPill v-if="item.corrections_count" variant="warn">{{ item.corrections_count }} 轮补充</EaPill>
                <EaPill v-if="item.files_modified_count" variant="ok">{{ item.files_modified_count }} 文件</EaPill>
              </div>
              <div class="case-row-meta">
                {{ item.query || item.title || item.pipeline_status || '-' }}
                <template v-if="item.started_at"> · {{ fmtTime(item.started_at) }}</template>
              </div>
            </div>
            <div class="case-actions">
              <EaPill v-if="item.existing_case_id" variant="ok">已转存</EaPill>
              <NButton v-else size="tiny" quaternary @click="adoptCandidate(item)">转为案例</NButton>
            </div>
          </div>
        </NSpin>
      </EaCard>
    </div>

    <!-- ── 启动评测 ─────────────────────────────────────────────────────── -->
    <NModal v-model:show="startModal" preset="card" title="开始评测" style="max-width: 520px">
      <div class="form-row">
        <label>用例</label>
        <NSelect
          v-model:value="startCaseIds"
          :options="caseOptions"
          multiple
          clearable
          placeholder="不选则全量跑"
        />
      </div>
      <div v-if="suite !== 'retrieval'" class="form-row">
        <label>判官模型</label>
        <NInput v-model:value="startJudgeModel" placeholder="留空则用 profile 默认模型" />
        <div class="form-hint">判官应与被评模型不同，避免同源偏袒。</div>
      </div>
      <div class="form-row">
        <label>并发</label>
        <NInputNumber
          v-model:value="startConcurrency"
          :min="1"
          :max="suite === 'retrieval' ? 16 : 4"
        />
        <div class="form-hint">
          {{ suite === 'retrieval'
            ? '检索评测纯本地函数，可提高并发。'
            : '并发越高越抢 Agent Bridge，建议不超过 2。' }}
        </div>
      </div>
      <template #footer>
        <div class="modal-footer">
          <NButton size="small" @click="startModal = false">取消</NButton>
          <NButton size="small" type="primary" :loading="starting" @click="confirmStart">开始</NButton>
        </div>
      </template>
    </NModal>

    <!-- ── 评分明细 ─────────────────────────────────────────────────────── -->
    <NModal
      :show="!!drill"
      preset="card"
      title="评分明细"
      style="max-width: 760px"
      @update:show="v => { if (!v) drill = null }"
    >
      <template v-if="drill">
        <div class="drill-head">
          <span class="case-id">{{ drill.result.case_id }}</span>
          <EaPill :variant="statusVariant(drill.result.status)">{{ STATUS_LABEL[drill.result.status] }}</EaPill>
          <span v-if="drill.result.score">加权 {{ drill.result.score.total.toFixed(3) }}</span>
        </div>
        <div v-if="drill.result.score?.summary" class="drill-summary">
          {{ drill.result.score.summary }}
        </div>
        <div v-if="drill.result.score?.must_failed.length" class="compare-line err">
          必过项未通过：{{ drill.result.score.must_failed.join('、') }}
        </div>

        <table class="rubric-table">
          <thead><tr><th>标准</th><th>结论</th><th>达成度</th><th>理由 / 证据</th></tr></thead>
          <tbody>
            <tr v-for="r in drill.result.score?.rubrics || []" :key="r.id">
              <td>
                <div class="case-id">{{ r.id }}</div>
                <div class="case-title">
                  {{ drill.case?.rubric.find(x => x.id === r.id)?.criterion || '' }}
                </div>
              </td>
              <td><EaPill :variant="r.pass ? 'ok' : 'err'">{{ r.pass ? '通过' : '未通过' }}</EaPill></td>
              <td>{{ r.score.toFixed(2) }}</td>
              <td>
                <div>{{ r.reason || '-' }}</div>
                <div v-if="r.evidence" class="evidence">{{ r.evidence }}</div>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="suite !== 'retrieval'" class="human-label">
          <div class="human-label-title">人工独立打分（用于校准判官）</div>
          <div class="hint">
            请按评分标准独立判断整例结论，不要参考判官结论。一致率低于门槛时所有分数都不可信。
          </div>
          <div v-if="drill.result.human_label" class="human-label-current">
            已记录：{{ drill.result.human_label.verdict }}
            <span v-if="drill.result.human_label.note"> · {{ drill.result.human_label.note }}</span>
          </div>
          <NInput
            v-model:value="labelNote"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="可选：写下你与判官分歧的原因"
          />
          <div class="human-label-actions">
            <NTooltip trigger="hover" placement="top">
              <template #trigger>
                <NButton size="small" type="success" @click="submitLabel('pass')">判 pass</NButton>
              </template>
              整例过关：主要必过项基本达标（对应判官加权分 ≥ 0.8 且 must 未挂）
            </NTooltip>
            <NTooltip trigger="hover" placement="top">
              <template #trigger>
                <NButton size="small" type="warning" @click="submitLabel('warn')">判 warn</NButton>
              </template>
              勉强能用：有明显瑕疵但不至于整例作废（约 0.6～0.8，或有非致命问题）
            </NTooltip>
            <NTooltip trigger="hover" placement="top">
              <template #trigger>
                <NButton size="small" type="error" @click="submitLabel('fail')">判 fail</NButton>
              </template>
              整例不合格：如根因错、证据虚、skill 选错（低于 0.6，或 must 项失败）
            </NTooltip>
            <NButton
              v-if="drill.result.task_id"
              size="small"
              quaternary
              @click="openReport(drill.result.task_id)"
            >
              打开原报告
            </NButton>
          </div>
        </div>
        <div v-else class="hint" style="margin-top: 12px">
          检索评测为客观离线打分，无需人工校准判官。
        </div>
      </template>
    </NModal>

    <!-- ── 编辑评分标准 ─────────────────────────────────────────────────── -->
    <NModal
      :show="!!editing"
      preset="card"
      title="编辑评分标准"
      style="max-width: 860px"
      @update:show="v => { if (!v) editing = null }"
    >
      <template v-if="editing">
        <div class="hint">
          必过项未通过时整例直接判失败。判分标准写得越具体，判官越稳定。
        </div>
        <table class="rubric-table">
          <thead><tr><th>id</th><th>权重</th><th>必过</th><th>判分标准</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(row, index) in editRubric" :key="index">
              <td><NInput v-model:value="row.id" size="small" placeholder="root_cause" /></td>
              <td><NInputNumber v-model:value="row.weight" size="small" :min="0" style="width: 84px" /></td>
              <td><NSwitch v-model:value="row.must" size="small" /></td>
              <td><NInput v-model:value="row.criterion" size="small" type="textarea" :autosize="{ minRows: 1 }" /></td>
              <td>
                <NButton size="tiny" quaternary type="error" @click="removeRubricRow(index)">移除</NButton>
              </td>
            </tr>
          </tbody>
        </table>
        <NButton size="tiny" @click="addRubricRow">添加一条</NButton>
      </template>
      <template #footer>
        <div class="modal-footer">
          <NButton size="small" @click="editing = null">取消</NButton>
          <NButton size="small" type="primary" @click="saveEditing">保存</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.eval-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.eval-main {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 1100px) {
  .eval-main { grid-template-columns: 1fr; }
}

.run-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  margin-top: 6px;
  border: 1px solid var(--ea-border, #e5e7eb);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
}

.run-item.active {
  border-color: var(--ea-primary, #2080f0);
  background: rgba(32, 128, 240, 0.06);
}

.run-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.run-id {
  font-family: var(--ea-mono, monospace);
  font-size: 12px;
}

.run-item-meta,
.case-row-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  opacity: 0.7;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.variant-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin: 8px 0 12px;
  font-size: 12px;
  opacity: 0.8;
}

.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 12px 0;
  border-top: 1px solid var(--ea-border, #e5e7eb);
  border-bottom: 1px solid var(--ea-border, #e5e7eb);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  opacity: 0.75;
}

.stat-num {
  font-size: 20px;
  font-weight: 600;
  opacity: 1;
}

.stat-num.ok { color: #18a058; }
.stat-num.warn { color: #f0a020; }
.stat-num.err { color: #d03050; }
.stat-num.muted { opacity: 0.5; }

.calibration-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  border: 1px solid var(--ea-border, #e5e7eb);
}

.calibration-bar.ok {
  background: rgba(24, 160, 88, 0.06);
  border-color: rgba(24, 160, 88, 0.35);
}

.calibration-bar.warn {
  background: rgba(240, 160, 32, 0.08);
  border-color: rgba(240, 160, 32, 0.4);
}

.calibration-hint {
  opacity: 0.75;
}

.human-label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--ea-border, #e5e7eb);
}

.human-label-title {
  font-size: 13px;
  font-weight: 600;
}

.human-label-current {
  font-size: 12px;
  opacity: 0.8;
}

.human-label-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.compare-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
}

.compare-label {
  font-size: 13px;
  opacity: 0.8;
}

.compare-detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.compare-line { font-size: 12px; }
.compare-line.ok { color: #18a058; }
.compare-line.warn { color: #f0a020; }
.compare-line.err { color: #d03050; }

.case-table,
.rubric-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.case-table th,
.case-table td,
.rubric-table th,
.rubric-table td {
  padding: 8px 6px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--ea-border, #e5e7eb);
}

.case-id {
  font-family: var(--ea-mono, monospace);
  font-size: 12px;
}

.case-title,
.case-error {
  font-size: 12px;
  opacity: 0.65;
}

.case-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.empty-row {
  text-align: center;
  opacity: 0.6;
  padding: 16px 0;
}

.case-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--ea-border, #e5e7eb);
}

.case-row-main { min-width: 0; }

.hint {
  margin: 6px 0 10px;
  font-size: 12px;
  opacity: 0.7;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.form-row label {
  font-size: 13px;
  font-weight: 500;
}

.form-hint {
  font-size: 12px;
  opacity: 0.65;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.drill-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.drill-summary {
  margin-bottom: 10px;
  font-size: 13px;
  opacity: 0.85;
}

.evidence {
  margin-top: 4px;
  padding-left: 8px;
  border-left: 2px solid var(--ea-border, #e5e7eb);
  font-size: 12px;
  opacity: 0.7;
  white-space: pre-wrap;
}
</style>
