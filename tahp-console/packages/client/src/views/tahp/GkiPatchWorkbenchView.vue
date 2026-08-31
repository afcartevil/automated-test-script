<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, useMessage } from 'naive-ui'
import {
  listGkiAnalysisTasks,
  listGkiUpgradeJobs,
  startGkiPatchServer,
  type GkiAnalysisTaskSummary,
  type GkiUpgradeJobSummary,
} from '@/api/tahp/gki-patch'
import {
  applyGkiUpgradeNotice,
  dismissGkiUpgradeNotice,
  listGkiUpgradeNotices,
  parseGkiUpgradeNotice,
  type GkiExternalNotice,
} from '@/api/tahp/gki-upgrade-notices'
import GkiUpgradeHistoryPanel from '@/components/tahp/gki-patch/GkiUpgradeHistoryPanel.vue'
import type { GkiHistoryKind } from '@/components/tahp/gki-patch/GkiUpgradeHistoryPanel.vue'
import GkiUpgradePendingNoticesCard from '@/components/tahp/gki-patch/GkiUpgradePendingNoticesCard.vue'

const router = useRouter()
const message = useMessage()

const notices = ref<GkiExternalNotice[]>([])
const loadingNotices = ref(false)
const applyingNoticeId = ref('')
const confirmingNoticeId = ref('')
const dismissingNoticeId = ref('')
const filledNoticeIds = ref<string[]>([])

const historyKind = ref<GkiHistoryKind>('upgrade')
const jobs = ref<GkiUpgradeJobSummary[]>([])
const tasks = ref<GkiAnalysisTaskSummary[]>([])
const loadingHistory = ref(false)
const selectedId = ref('')
const historyError = ref('')

const fromTag = ref('')
const toTag = ref('')
const noticeHint = ref('')
let noticesPollTimer: number | null = null

const pendingNoticeCount = computed(() =>
  notices.value.filter(item => item.status === 'pending').length,
)

const runningCount = computed(() =>
  jobs.value.filter((j) => {
    const s = String(j.status || '').toLowerCase()
    return ['running', 'pending', 'awaiting_ssh', 'awaiting_otp', 'applied', 'committed', 'conflicts'].includes(s)
      || s.includes('conflict')
  }).length,
)

const completedCount = computed(() =>
  jobs.value.filter((j) => {
    const s = String(j.status || '').toLowerCase()
    return s === 'completed' || s === 'success' || s === 'done'
  }).length,
)

const canOpenWithTags = computed(() => Boolean(fromTag.value.trim() && toTag.value.trim()))


async function reloadNotices() {
  loadingNotices.value = true
  try {
    const result = await listGkiUpgradeNotices('all')
    notices.value = result.items || []
  } catch {
    /* ignore */
  } finally {
    loadingNotices.value = false
  }
}

async function reloadHistory() {
  loadingHistory.value = true
  historyError.value = ''
  try {
    // 与父页 ensure 共用服务端 startingPromise；进页时若仍在拉起则等待而非直接报错
    try {
      await startGkiPatchServer()
    } catch {
      /* list 接口内仍会 ensure */
    }
    const [jobResult, taskResult] = await Promise.all([
      listGkiUpgradeJobs(50),
      listGkiAnalysisTasks(50),
    ])
    jobs.value = jobResult.jobs || []
    tasks.value = taskResult.tasks || []
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    historyError.value = /未就绪|启动较慢|timeout|ECONNREFUSED/i.test(msg)
      ? 'GKI 服务仍在启动，请稍后点刷新重试'
      : msg
  } finally {
    loadingHistory.value = false
  }
}

function startNoticesPolling() {
  stopNoticesPolling()
  noticesPollTimer = window.setInterval(() => {
    void reloadNotices()
  }, 30_000)
}

function stopNoticesPolling() {
  if (noticesPollTimer != null) {
    window.clearInterval(noticesPollTimer)
    noticesPollTimer = null
  }
}

async function onApplyNotice(noticeId: string) {
  const notice = notices.value.find(item => item.noticeId === noticeId)
  if (!notice) return
  applyingNoticeId.value = noticeId
  noticeHint.value = ''
  try {
    const parsed = await parseGkiUpgradeNotice({
      text: notice.text,
      fromTag: notice.fromTag,
      toTag: notice.toTag,
      taskKind: notice.taskKind,
    })
    const nextFrom = parsed.fromTag || notice.fromTag || ''
    const nextTo = parsed.toTag || notice.toTag || ''
    if (!nextFrom || !nextTo) {
      noticeHint.value = '未能解析 From/To Tag，请核对通知或改用结构化 from_tag/to_tag'
      message.warning(noticeHint.value)
      return
    }
    fromTag.value = nextFrom
    toTag.value = nextTo
    historyKind.value = 'analysis'
    if (!filledNoticeIds.value.includes(noticeId)) {
      filledNoticeIds.value = [...filledNoticeIds.value, noticeId]
    }
    noticeHint.value = `已填入 ${nextFrom} → ${nextTo}，点击「前往分析」创建分析任务`
    message.success('已填入 Tag')
  } catch (err) {
    noticeHint.value = err instanceof Error ? err.message : String(err)
    message.error(noticeHint.value)
  } finally {
    applyingNoticeId.value = ''
  }
}

async function onConfirmNotice(noticeId: string) {
  confirmingNoticeId.value = noticeId
  try {
    await applyGkiUpgradeNotice(noticeId)
    filledNoticeIds.value = filledNoticeIds.value.filter(id => id !== noticeId)
    await reloadNotices()
    noticeHint.value = ''
    message.success('已确认完成')
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err))
  } finally {
    confirmingNoticeId.value = ''
  }
}

async function onDismissNotice(noticeId: string) {
  dismissingNoticeId.value = noticeId
  try {
    await dismissGkiUpgradeNotice(noticeId)
    filledNoticeIds.value = filledNoticeIds.value.filter(id => id !== noticeId)
    await reloadNotices()
    message.success('已忽略')
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err))
  } finally {
    dismissingNoticeId.value = ''
  }
}

function goUpgrade(query: Record<string, string> = {}) {
  void router.push({ name: 'tahp.gki-patch.upgrade', query })
}

function goAnalysis(query: Record<string, string> = {}) {
  void router.push({ name: 'tahp.gki-patch.analysis', query })
}

function handleCreate() {
  selectedId.value = ''
  if (historyKind.value === 'analysis') {
    goAnalysis()
    return
  }
  fromTag.value = ''
  toTag.value = ''
  noticeHint.value = '请填写 From/To Tag 后前往合入'
}

function handleSelect(id: string) {
  selectedId.value = id
  if (historyKind.value === 'upgrade') {
    const job = jobs.value.find(item => String(item.id) === id)
    if (job?.from_tag) fromTag.value = job.from_tag
    if (job?.to_tag) toTag.value = job.to_tag
    return
  }
  const task = tasks.value.find(item => String(item.id) === id)
  if (task?.from_tag) fromTag.value = task.from_tag
  if (task?.to_tag) toTag.value = task.to_tag
}

function handleOpen(id: string) {
  if (historyKind.value === 'analysis') {
    goAnalysis({ task: id })
    return
  }
  goUpgrade({ job: id })
}

function handleGoAnalysis() {
  if (!canOpenWithTags.value) {
    message.warning('请先填写 From Tag 与 To Tag')
    return
  }
  goAnalysis({
    from_tag: fromTag.value.trim(),
    to_tag: toTag.value.trim(),
    ...(noticeHint.value ? { notice_text: noticeHint.value } : {}),
  })
}

function onKindChange(kind: GkiHistoryKind) {
  historyKind.value = kind
  selectedId.value = ''
}

onMounted(() => {
  void reloadNotices()
  void reloadHistory()
  startNoticesPolling()
})

onUnmounted(() => {
  stopNoticesPolling()
})
</script>

<template>
  <div class="workspace-layout">
    <div class="workspace-left">
      <GkiUpgradePendingNoticesCard
        :notices="notices"
        :loading="loadingNotices"
        :applying-id="applyingNoticeId"
        :confirming-id="confirmingNoticeId"
        :dismissing-id="dismissingNoticeId"
        :filled-ids="filledNoticeIds"
        @refresh="reloadNotices"
        @apply="onApplyNotice"
        @confirm="onConfirmNotice"
        @dismiss="onDismissNotice"
      />

      <GkiUpgradeHistoryPanel
        :kind="historyKind"
        :jobs="jobs"
        :tasks="tasks"
        :selected-id="selectedId"
        :loading="loadingHistory"
        @update:kind="onKindChange"
        @select="handleSelect"
        @refresh="reloadHistory"
        @create="handleCreate"
        @open="handleOpen"
      />
    </div>

    <aside class="workspace-detail">
      <div class="config-stack">
        <div class="metrics-row">
          <div class="metric">
            <div class="metric-label">升级任务</div>
            <div class="metric-value">{{ jobs.length }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">分析任务</div>
            <div class="metric-value">{{ tasks.length }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">升级进行中</div>
            <div class="metric-value">{{ runningCount }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">待确认通知</div>
            <div class="metric-value">{{ pendingNoticeCount }}</div>
          </div>
        </div>

        <div class="ea-card create-card">
          <div class="ea-section-title">新建任务</div>
          <h3>填写 Tag 区间后前往分析</h3>
          <p class="create-desc">
            外部通知解析后创建「分析任务」（不会自动创建升级合入）。核对 Tag 后点下方按钮进入分析页再启动。
            升级已完成数：{{ completedCount }}
          </p>

          <div class="tag-row">
            <label class="field">
              <span>From Tag</span>
              <NInput v-model:value="fromTag" size="small" placeholder="android14-5.10-..." class="mono" />
            </label>
            <span class="arrow" aria-hidden="true">→</span>
            <label class="field">
              <span>To Tag</span>
              <NInput v-model:value="toTag" size="small" placeholder="android14-5.10-..." class="mono" />
            </label>
          </div>

          <p v-if="noticeHint" class="hint">{{ noticeHint }}</p>
          <p v-if="historyError" class="hint error">{{ historyError }}</p>

          <div class="actions">
            <NButton type="primary" :disabled="!canOpenWithTags" @click="handleGoAnalysis">
              前往分析
            </NButton>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped lang="scss">
.workspace-layout {
  display: grid;
  grid-template-columns: minmax(360px, 460px) minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
  height: calc(100vh - 148px);
  min-height: 520px;
}

.workspace-left,
.workspace-detail {
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.workspace-left {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.workspace-left > :deep(.pending-card),
.workspace-left > :deep(.history-panel) {
  flex: 1 1 0;
  min-height: 0;
}

.workspace-detail {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.config-stack {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.metric {
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface, #fff);
}

.metric-label {
  font-size: 12px;
  color: var(--muted);
}

.metric-value {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 700;
  color: var(--head);
}

.create-card {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.create-card h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--head);
}

.create-desc {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.tag-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: end;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  font-size: 12px;
  color: var(--muted);
}

.arrow {
  padding-bottom: 8px;
  color: var(--muted);
}

.mono :deep(input) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.hint {
  margin: 0;
  font-size: 12px;
  color: var(--sky-fg);
}

.hint.error {
  color: var(--error);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

@media (max-width: 960px) {
  .workspace-layout {
    grid-template-columns: 1fr;
    height: auto;
  }

  .workspace-left,
  .workspace-detail {
    height: auto;
  }

  .metrics-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
