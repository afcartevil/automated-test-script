<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NInput, useMessage } from 'naive-ui'
import {
  listGkiAnalysisTasks,
  listGkiRepoTags,
  listGkiUpgradeJobs,
  startGkiPatchServer,
  type GkiAnalysisTaskSummary,
  type GkiUpgradeJobSummary,
} from '@/api/tahp/gki-patch'
import {
  applyGkiUpgradeNotice,
  deleteGkiUpgradeNotice,
  dismissGkiUpgradeNotice,
  listGkiUpgradeNotices,
  restoreGkiUpgradeNotice,
  type GkiExternalNotice,
} from '@/api/tahp/gki-upgrade-notices'
import GkiUpgradeHistoryPanel from '@/components/tahp/gki-patch/GkiUpgradeHistoryPanel.vue'
import type { GkiHistoryKind } from '@/components/tahp/gki-patch/GkiUpgradeHistoryPanel.vue'
import GkiUpgradePendingNoticesCard from '@/components/tahp/gki-patch/GkiUpgradePendingNoticesCard.vue'
import GkiApplyNoticeModal from '@/components/tahp/gki-patch/GkiApplyNoticeModal.vue'
import GkiDismissNoticeModal from '@/components/tahp/gki-patch/GkiDismissNoticeModal.vue'
import { pickSecondNewestMonthTarget } from '@/utils/gki-month-tags'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const highlightNoticeId = computed(() =>
  String(route.query.notice || route.query.notice_id || '').trim(),
)

const notices = ref<GkiExternalNotice[]>([])
const loadingNotices = ref(false)
const applyingNoticeId = ref('')
const confirmingNoticeId = ref('')
const dismissingNoticeId = ref('')
const restoringNoticeId = ref('')
const deletingNoticeId = ref('')
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
const applyModalShow = ref(false)
const applyNotice = ref<GkiExternalNotice | null>(null)
const applyFromTag = ref('')
const applyToTag = ref('')
const applyLatestTag = ref('')
const applyLatestMonth = ref('')
const applyRecommendedTag = ref('')
const applyRecommendedMonth = ref('')
const applyTagOptions = ref<string[]>([])
const applyTagsLoading = ref(false)
const applyTagsHint = ref('')
const applyWarning = ref('')
const dismissModalShow = ref(false)
const dismissNotice = ref<GkiExternalNotice | null>(null)
const dismissReason = ref('')
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


function matchNotice(item: GkiExternalNotice, id: string) {
  if (!id) return false
  return (
    item.noticeId === id
    || item.sourceId === id
    || item.parentSourceId === id
    || Boolean(item.sourceId && item.sourceId.startsWith(`${id}#`))
  )
}

const lastAppliedHighlight = ref('')

function applyHighlightedNotice() {
  const id = highlightNoticeId.value
  if (!id) return
  const found = notices.value.find(item => matchNotice(item, id))
  const matched = notices.value.filter(item => matchNotice(item, id))
  if (!found) {
    if (notices.value.length && lastAppliedHighlight.value !== id) {
      noticeHint.value = '未在本机收件箱找到该通知，请点「刷新」或核对中心任务是否已同步'
    }
    return
  }
  if (lastAppliedHighlight.value === found.noticeId || lastAppliedHighlight.value === id) return
  lastAppliedHighlight.value = matched.length > 1 ? id : found.noticeId
  if (matched.length > 1) {
    noticeHint.value = `已定位 ${matched.length} 条异常告警，请在收件箱逐条处理`
    return
  }
  if (found.fromTag || found.currentGkiVersion) fromTag.value = found.fromTag || found.currentGkiVersion || ''
  if (found.toTag) toTag.value = found.toTag
  if (found.fromTag && found.toTag) {
    if (!filledNoticeIds.value.includes(found.noticeId)) {
      filledNoticeIds.value = [...filledNoticeIds.value, found.noticeId]
    }
    noticeHint.value = `已填入 ${found.fromTag} → ${found.toTag}，可前往分析或直接合入`
    historyKind.value = 'analysis'
  } else if (found.fromTag || found.currentGkiVersion) {
    noticeHint.value = `当前 GKI ${fromTag.value}。请点「采用并填入」选择次新月 To Tag`
    historyKind.value = 'analysis'
  } else {
    noticeHint.value = '已定位该通知；请点「采用并填入」选择 To Tag'
  }
}

async function reloadNotices() {
  loadingNotices.value = true
  try {
    const result = await listGkiUpgradeNotices('all')
    notices.value = result.items || []
    applyHighlightedNotice()
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
  const nextFrom = notice.fromTag || notice.currentGkiVersion || ''
  if (!nextFrom) {
    noticeHint.value = '未能解析当前 GKI 版本，请核对通知'
    message.warning(noticeHint.value)
    return
  }
  applyingNoticeId.value = noticeId
  applyNotice.value = notice
  applyFromTag.value = nextFrom
  applyToTag.value = notice.toTag || ''
  applyLatestTag.value = ''
  applyLatestMonth.value = ''
  applyRecommendedTag.value = ''
  applyRecommendedMonth.value = ''
  applyTagOptions.value = []
  applyWarning.value = ''
  applyTagsHint.value = '正在从代码仓读取 tag…'
  applyTagsLoading.value = true
  applyModalShow.value = true
  try {
    try {
      await startGkiPatchServer()
    } catch {
      /* list tags 内仍会 ensure */
    }
    const result = await listGkiRepoTags()
    const pick = pickSecondNewestMonthTarget(result.tags || [], nextFrom)
    applyTagOptions.value = pick.sameSeries.length ? pick.sameSeries : (result.tags || [])
    applyLatestTag.value = pick.latestTag
    applyLatestMonth.value = pick.latestMonth
    applyRecommendedTag.value = pick.recommendedTag
    applyRecommendedMonth.value = pick.recommendedMonth
    applyWarning.value = pick.warning
    if (!applyToTag.value) applyToTag.value = pick.recommendedTag
    if (!result.configured) {
      applyTagsHint.value = '未配置本地 kernel 仓，请先在 GKI 设置中填写路径；仍可手动输入 To Tag'
    } else if (!(result.tags || []).length) {
      applyTagsHint.value = '本地仓库暂无 tag，请确认已 fetch tags；仍可手动输入'
    } else {
      applyTagsHint.value = `已加载 ${result.total} 个 tag，同系列 ${pick.sameSeries.length} 个。策略：最新月的前一个月（次新月）`
    }
  } catch (err) {
    applyTagOptions.value = []
    applyTagsHint.value = err instanceof Error ? err.message : '读取仓库 tag 失败，请手动输入 To Tag'
  } finally {
    applyTagsLoading.value = false
    applyingNoticeId.value = ''
  }
}

function onConfirmApplyModal() {
  const nextFrom = applyFromTag.value.trim()
  const nextTo = applyToTag.value.trim()
  if (!nextFrom || !nextTo) {
    message.warning('请选择 To Tag')
    return
  }
  fromTag.value = nextFrom
  toTag.value = nextTo
  historyKind.value = 'analysis'
  const noticeId = applyNotice.value?.noticeId
  if (noticeId && !filledNoticeIds.value.includes(noticeId)) {
    filledNoticeIds.value = [...filledNoticeIds.value, noticeId]
  }
  noticeHint.value = `已填入 ${nextFrom} → ${nextTo}，可前往分析或直接合入`
  applyModalShow.value = false
  message.success('已填入 Tag')
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

function onDismissNotice(noticeId: string) {
  const item = notices.value.find(notice => notice.noticeId === noticeId) || null
  dismissNotice.value = item
  dismissReason.value = ''
  dismissModalShow.value = true
}

async function onConfirmDismissModal() {
  const noticeId = dismissNotice.value?.noticeId
  const reason = dismissReason.value.trim()
  if (!noticeId || !reason) return
  dismissingNoticeId.value = noticeId
  try {
    await dismissGkiUpgradeNotice(noticeId, reason)
    filledNoticeIds.value = filledNoticeIds.value.filter(id => id !== noticeId)
    dismissModalShow.value = false
    dismissNotice.value = null
    dismissReason.value = ''
    await reloadNotices()
    message.success('已忽略')
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err))
  } finally {
    dismissingNoticeId.value = ''
  }
}

async function onRestoreNotice(noticeId: string) {
  restoringNoticeId.value = noticeId
  try {
    await restoreGkiUpgradeNotice(noticeId)
    filledNoticeIds.value = filledNoticeIds.value.filter(id => id !== noticeId)
    await reloadNotices()
    message.success('已放回待处理')
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err))
  } finally {
    restoringNoticeId.value = ''
  }
}

async function onDeleteNotice(noticeId: string) {
  deletingNoticeId.value = noticeId
  try {
    await deleteGkiUpgradeNotice(noticeId)
    filledNoticeIds.value = filledNoticeIds.value.filter(id => id !== noticeId)
    await reloadNotices()
    message.success('已删除')
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err))
  } finally {
    deletingNoticeId.value = ''
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

function tagQuery() {
  const query: Record<string, string> = {
    from_tag: fromTag.value.trim(),
    to_tag: toTag.value.trim(),
  }
  const hint = noticeHint.value.trim()
  if (hint.startsWith('已填入')) query.notice_text = hint
  return query
}

function handleGoAnalysis() {
  if (!canOpenWithTags.value) {
    message.warning('请先填写 From Tag 与 To Tag')
    return
  }
  goAnalysis(tagQuery())
}

function handleGoUpgrade() {
  if (!canOpenWithTags.value) {
    message.warning('请先填写 From Tag 与 To Tag')
    return
  }
  goUpgrade(tagQuery())
}

function onKindChange(kind: GkiHistoryKind) {
  historyKind.value = kind
  selectedId.value = ''
}

watch(highlightNoticeId, () => {
  lastAppliedHighlight.value = ''
  void reloadNotices()
})

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
        :restoring-id="restoringNoticeId"
        :deleting-id="deletingNoticeId"
        :filled-ids="filledNoticeIds"
        :highlight-id="highlightNoticeId"
        @refresh="reloadNotices"
        @apply="onApplyNotice"
        @confirm="onConfirmNotice"
        @dismiss="onDismissNotice"
        @restore="onRestoreNotice"
        @remove="onDeleteNotice"
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
          <h3>填写 Tag 区间后分析或合入</h3>
          <p class="create-desc">
            可先做区间分析，也可直接前往 patch 入库。直接合入会复用已有区间 patch；没有时从本地 kernel 仓库生成。
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
            <NButton :disabled="!canOpenWithTags" @click="handleGoAnalysis">
              前往分析
            </NButton>
            <NButton type="primary" :disabled="!canOpenWithTags" @click="handleGoUpgrade">
              前往合入
            </NButton>
          </div>
        </div>
      </div>
    </aside>
  </div>

  <GkiApplyNoticeModal
    v-model:show="applyModalShow"
    v-model:to-tag="applyToTag"
    :notice="applyNotice"
    :from-tag="applyFromTag"
    :latest-tag="applyLatestTag"
    :latest-month="applyLatestMonth"
    :recommended-tag="applyRecommendedTag"
    :recommended-month="applyRecommendedMonth"
    :tag-options="applyTagOptions"
    :tags-loading="applyTagsLoading"
    :tags-hint="applyTagsHint"
    :warning="applyWarning"
    @confirm="onConfirmApplyModal"
  />

  <GkiDismissNoticeModal
    v-model:show="dismissModalShow"
    v-model:reason="dismissReason"
    :notice="dismissNotice"
    :submitting="Boolean(dismissingNoticeId)"
    @confirm="onConfirmDismissModal"
  />
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
