<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import ModemBaselineAdvancedConfig from '@/components/tahp/modem-baseline/ModemBaselineAdvancedConfig.vue'
import type { ConfigFieldErrors } from '@/components/tahp/modem-baseline/ModemBaselineAdvancedConfig.vue'
import ModemBaselineConfigCard from '@/components/tahp/modem-baseline/ModemBaselineConfigCard.vue'
import type { ParseFeedback } from '@/components/tahp/modem-baseline/ModemBaselineConfigCard.vue'
import ModemBaselineHistoryPanel from '@/components/tahp/modem-baseline/ModemBaselineHistoryPanel.vue'
import ModemBaselineLogFilterBar from '@/components/tahp/modem-baseline/ModemBaselineLogFilterBar.vue'
import ModemBaselinePendingNoticesCard from '@/components/tahp/modem-baseline/ModemBaselinePendingNoticesCard.vue'
import ModemBaselineStagePanel from '@/components/tahp/modem-baseline/ModemBaselineStagePanel.vue'
import { useModemBaseline } from '@/composables/useModemBaseline'
import type { ModemPlatformTaskStatus } from '@/api/tahp/modem-baseline'
import { isModemConflictLogLine, isModemErrorLogLine, takeModemLogTail } from '@/utils/modemBaselineLog'

const message = useMessage()
const {
  config,
  noticeText,
  noticeParsed,
  recommendation,
  selectedRepo,
  runs,
  selectedRun,
  selectedRunId,
  conflictFiles,
  logContent,
  loading,
  starting,
  parsingNotice,
  recommending,
  continuing,
  refreshing,
  buildProjects,
  buildProjectsWarning,
  loadingBuildProjects,
  errorMessage,
  pendingNotices,
  loadingNotices,
  applyingNoticeId,
  confirmingNoticeId,
  dismissingNoticeId,
  filledNoticeIds,
  statusMeta,
  stageItems,
  initialize,
  loadBuildProjects,
  requestRecommend,
  applyRecommendation,
  selectRun,
  reloadRuns,
  startRun,
  continueRun,
  refreshConflicts,
  openConflictFile,
  reloadPendingNotices,
  applyExternalNotice,
  confirmExternalNotice,
  dismissExternalNotice,
  setPlatformTaskStatus,
  activeNoticeId,
  activePlatform,
  disposeModemBaseline,
} = useModemBaseline()

function withText(value?: string) {
  return String(value ?? '').trim()
}

const summaryText = computed(() => statusMeta.value.summary)
const logScroller = ref<HTMLElement | null>(null)
const shouldStickToBottom = ref(true)
const LOG_BOTTOM_THRESHOLD = 24
const onlyErrors = ref(false)
const onlyConflicts = ref(false)
const refreshingRuns = ref(false)
const showConfigPanel = ref(true)
const parseFeedback = ref<ParseFeedback>(null)
const startAttempted = ref(false)
const lastFailedLogRunId = ref('')

const hasRunningRun = computed(() => runs.value.some(item => item.status === 'running'))

const fieldErrors = computed<ConfigFieldErrors>(() => {
  if (!startAttempted.value) return {}
  const errors: ConfigFieldErrors = {}
  if (!withText(config.value.NODE_BRANCH)) errors.NODE_BRANCH = '请填写源分支'
  if (!withText(config.value.target_BRANCH)) errors.target_BRANCH = '请填写目标分支'
  if (!withText(config.value.work_dir)) errors.work_dir = '请填写工作区目录'
  return errors
})

const configReady = computed(
  () =>
    Boolean(
      withText(config.value.NODE_BRANCH)
      && withText(config.value.target_BRANCH)
      && withText(config.value.work_dir),
    ),
)

const startDisabled = computed(() => Boolean(starting.value || loading.value || hasRunningRun.value))

const startDisabledReason = computed(() => {
  if (hasRunningRun.value) return '已有任务执行中，请等待完成后再启动新升级'
  if (!withText(config.value.NODE_BRANCH) || !withText(config.value.target_BRANCH) || !withText(config.value.work_dir)) {
    return '请先填写源分支、目标分支与工作区目录'
  }
  return ''
})

const filteredLog = computed(() => {
  const raw = takeModemLogTail(logContent.value || '')
  if (!onlyErrors.value && !onlyConflicts.value) return raw
  const lines = raw.split(/\r?\n/)
  const out = lines.filter((line) => {
    if (onlyErrors.value && isModemErrorLogLine(line)) return true
    if (onlyConflicts.value && isModemConflictLogLine(line)) return true
    return false
  })
  return out.join('\n')
})

function isNearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= LOG_BOTTOM_THRESHOLD
}

function scrollLogToBottom() {
  if (logScroller.value) {
    logScroller.value.scrollTop = logScroller.value.scrollHeight
  }
}

function handleLogScroll() {
  if (!logScroller.value) return
  shouldStickToBottom.value = isNearBottom(logScroller.value)
}

watch(logContent, async (_, previous) => {
  const shouldAutoScroll = shouldStickToBottom.value || !previous
  await nextTick()
  if (shouldAutoScroll) {
    scrollLogToBottom()
    shouldStickToBottom.value = true
  }
})

watch(
  () => selectedRun.value?.runId,
  (runId) => {
    if (!runId) return
    // 切换任务时重置日志筛选，避免上一个失败任务的「只看错误」带到新任务
    onlyErrors.value = selectedRun.value?.status === 'failed'
    onlyConflicts.value = false
    lastFailedLogRunId.value = selectedRun.value?.status === 'failed' ? runId : ''
  },
)

function applyConfig(nextValue: typeof config.value) {
  config.value = { ...nextValue }
}

function warningLabel(code: string) {
  switch (code) {
    case 'no_platform_detected':
      return '平台未识别'
    case 'no_version_detected':
      return '版本未识别'
    case 'branch_template_not_found':
      return '未找到对应分支模板'
    case 'branch_template_ambiguous':
      return '匹配到多个分支模板'
    case 'no_rule_matched':
      return '未匹配到分支规则'
    case 'unresolved_placeholders_in_node':
      return 'NODE_BRANCH 仍含未替换占位符'
    case 'unresolved_placeholders_in_target':
      return 'target_BRANCH 仍含未替换占位符'
    default:
      return code
  }
}

function buildRecommendationFeedback(
  apply: ReturnType<typeof applyRecommendation>,
): NonNullable<ParseFeedback> {
  const successes: string[] = []
  const failures: string[] = []

  if (withText(noticeParsed.value?.platform)) successes.push(`平台：${noticeParsed.value?.platform}`)
  else failures.push('平台：未识别')

  if (withText(noticeParsed.value?.tosVersion)) successes.push(`tOS：${noticeParsed.value?.tosVersion}`)
  else failures.push('tOS：未识别')

  if (withText(noticeParsed.value?.version)) successes.push(`版本：${noticeParsed.value?.version}`)
  else failures.push('版本：未识别')

  if (noticeParsed.value?.targetMode) {
    successes.push(`目标模式：${noticeParsed.value.targetMode === 'mp' ? 'MP' : '主干'}`)
  }

  const currentRepoLabel = selectedRepo.value?.platform || selectedRepo.value?.label || ''
  if (apply.repoAction === 'ambiguous') {
    const list = (apply.candidates ?? []).slice(0, 4).map(item => item.platform || item.label).join('、')
    failures.push(`仓库：匹配到多个候选（${(apply.candidates ?? []).length}）${list ? `，候选 ${list}` : ''}`)
  } else if (apply.repoAction === 'no_platform') {
    failures.push('仓库：未识别平台，无法自动同步')
  } else if (apply.repoAction === 'no_match') {
    failures.push('仓库：未匹配到对应仓库')
  } else if (apply.repoAction === 'fallback_selected') {
    failures.push(`仓库：未精确匹配，已回退到当前仓库${currentRepoLabel ? `（${currentRepoLabel}）` : ''}`)
  } else if (currentRepoLabel) {
    successes.push(`仓库：${currentRepoLabel}`)
  }

  if (withText(recommendation.value?.nodeBranch)) successes.push(`NODE_BRANCH：${recommendation.value?.nodeBranch}`)
  else failures.push('NODE_BRANCH：未匹配')

  if (withText(recommendation.value?.targetBranch)) successes.push(`target_BRANCH：${recommendation.value?.targetBranch}`)
  else failures.push('target_BRANCH：未匹配')

  if (withText(recommendation.value?.apLabel)) successes.push(`AP 标签：${recommendation.value?.apLabel}`)
  else failures.push('AP 标签：未回填')

  const warnings = [
    ...(noticeParsed.value?.warnings ?? []),
    ...(recommendation.value?.warnings ?? []),
  ]
  const extraWarnings = Array.from(new Set(warnings.map(warningLabel)))
  for (const warning of extraWarnings) {
    const exists = failures.some(item => item.includes(warning))
    if (!exists) failures.push(`提示：${warning}`)
  }

  const tone: NonNullable<ParseFeedback>['tone'] = failures.length ? 'warning' : 'success'
  const title = failures.length
    ? (successes.length ? '已部分解析并应用推荐' : '解析完成，但未成功回填推荐')
    : '已解析并应用推荐'

  return {
    tone,
    title,
    successes,
    failures,
  }
}

function showRecommendationToast(feedback: NonNullable<ParseFeedback>) {
  message.create(feedback.title, {
    type: feedback.tone,
    duration: 3500,
    closable: true,
  })
}

async function handleStart() {
  startAttempted.value = true
  if (!configReady.value) {
    openConfigPanel()
    message.warning('请先补齐必填项后再启动升级')
    return
  }
  if (hasRunningRun.value) {
    message.warning('已有任务执行中，请等待完成后再启动')
    return
  }
  try {
    await startRun()
    startAttempted.value = false
    showConfigPanel.value = false
    message.success('已启动 Modem 升级任务')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleSelectRun(runId: string) {
  try {
    showConfigPanel.value = false
    await selectRun(runId)
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

function openConfigPanel() {
  showConfigPanel.value = true
}

function closeConfigPanel() {
  showConfigPanel.value = false
}

const parseHighlight = ref(false)
let parseHighlightTimer: ReturnType<typeof setTimeout> | null = null

/** 历史区「新建升级」：切到配置面板；已在配置页时聚焦通知输入并高亮提示 */
function handleCreateUpgrade() {
  if (showConfigPanel.value) {
    message.info('当前已在新建升级面板，可直接填写通知内容后启动')
    parseHighlight.value = true
    if (parseHighlightTimer) clearTimeout(parseHighlightTimer)
    parseHighlightTimer = setTimeout(() => {
      parseHighlight.value = false
      parseHighlightTimer = null
    }, 1400)
    void nextTick(() => {
      const el = document.querySelector('.config-stack .notice-input textarea, .config-stack .notice-input input') as HTMLElement | null
      el?.focus()
    })
    return
  }
  showConfigPanel.value = true
  message.success('已打开新建升级面板')
  void nextTick(() => {
    const el = document.querySelector('.config-stack .notice-input textarea, .config-stack .notice-input input') as HTMLElement | null
    el?.focus()
  })
}

async function handleRefreshRuns() {
  refreshingRuns.value = true
  try {
    await reloadRuns()
    if (selectedRunId.value) {
      await selectRun(selectedRunId.value)
    }
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  } finally {
    refreshingRuns.value = false
  }
}

async function handleContinueRun() {
  try {
    await continueRun()
    if (config.value.build_project) {
      message.success(`已发送继续执行请求，完成后将编译 ${config.value.build_project}`)
    } else {
      message.warning('已发送继续执行请求（未选择编译项目，将跳过自动编译）')
    }
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleRefreshConflicts() {
  try {
    await refreshConflicts()
    message.success('已刷新冲突状态')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleOpenConflictFile(file: string) {
  try {
    await openConflictFile(file)
    message.success('已尝试打开冲突文件')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleParseAndApply() {
  try {
    await requestRecommend()
    const apply = applyRecommendation()
    if (!apply.applied) return
    const feedback = buildRecommendationFeedback(apply)
    parseFeedback.value = feedback
    showRecommendationToast(feedback)
    openConfigPanel()
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleApplyExternalNotice(noticeId: string, platform?: string) {
  try {
    const apply = await applyExternalNotice(noticeId, platform)
    if (!apply.applied) {
      parseFeedback.value = {
        tone: 'warning',
        title: '通知已填入，但推荐未完全应用',
        successes: [],
        failures: ['请核对基础配置后启动；完成后请点「确认完成」'],
      }
      message.warning('通知已填入，但推荐未完全应用，请核对基础配置；完成后请点「确认完成」')
      openConfigPanel()
      return
    }
    const feedback = buildRecommendationFeedback(apply)
    parseFeedback.value = feedback
    showRecommendationToast(feedback)
    openConfigPanel()
    message.success(platform
      ? `已填入表单（平台 ${platform}）。核对并启动后，该平台任务完成会自动标记`
      : '已填入表单（通知仍保留）。核对并启动后，请点「确认完成」才会从待确认消失')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleSetPlatformTaskStatus(
  noticeId: string,
  platform: string,
  status: ModemPlatformTaskStatus,
) {
  try {
    await setPlatformTaskStatus(noticeId, platform, status)
    message.success(`已将平台 ${platform} 标记为${status === 'skipped' ? '跳过' : '待升级'}`)
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleConfirmExternalNotice(noticeId: string) {
  try {
    await confirmExternalNotice(noticeId)
    message.success('已确认完成，通知已从待确认移除')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleDismissExternalNotice(noticeId: string) {
  try {
    await dismissExternalNotice(noticeId)
    message.success('已忽略该通知')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

function handleReopenFromRun(runId: string) {
  const run = runs.value.find(item => item.runId === runId)
  if (!run) {
    message.warning('未找到该历史任务')
    return
  }
  config.value = {
    ...config.value,
    ...run.config,
  }
  startAttempted.value = false
  openConfigPanel()
  message.success('已基于该任务回填配置，请核对后启动升级')
}

onMounted(() => {
  void initialize()
})

onUnmounted(() => {
  if (parseHighlightTimer) clearTimeout(parseHighlightTimer)
  disposeModemBaseline()
})
</script>

<template>
  <div class="workspace-layout">
    <div class="workspace-left">
      <div v-if="errorMessage" class="preview-note">
        <strong>接入异常</strong>
        <span>{{ errorMessage }}</span>
      </div>

      <ModemBaselinePendingNoticesCard
        :notices="pendingNotices"
        :loading="loadingNotices"
        :applying-id="applyingNoticeId"
        :confirming-id="confirmingNoticeId"
        :dismissing-id="dismissingNoticeId"
        :filled-ids="filledNoticeIds"
        :applying-platform="applyingNoticeId ? { noticeId: activeNoticeId, platform: activePlatform } : null"
        @refresh="reloadPendingNotices"
        @apply="handleApplyExternalNotice"
        @confirm="handleConfirmExternalNotice"
        @dismiss="handleDismissExternalNotice"
        @set-platform-task-status="handleSetPlatformTaskStatus"
      />

      <ModemBaselineHistoryPanel
        :runs="runs"
        :selected-run-id="showConfigPanel ? '' : selectedRunId"
        :loading="refreshingRuns || loading"
        @select="handleSelectRun"
        @refresh="handleRefreshRuns"
        @reopen="handleReopenFromRun"
        @create="handleCreateUpgrade"
      />
    </div>

    <aside class="workspace-detail">
      <div v-if="showConfigPanel" class="config-stack" :class="{ 'parse-flash': parseHighlight }">
        <ModemBaselineConfigCard
          :notice-text="noticeText"
          :parsing="parsingNotice"
          :recommending="recommending"
          :parse-feedback="parseFeedback"
          @update:notice-text="noticeText = $event"
          @parse-and-apply="handleParseAndApply"
        />

        <ModemBaselineAdvancedConfig
          :model-value="config"
          :build-projects="buildProjects"
          :build-projects-warning="buildProjectsWarning"
          :loading-build-projects="loadingBuildProjects"
          :loading="loading"
          :starting="starting"
          :field-errors="fieldErrors"
          :start-disabled="startDisabled"
          :start-disabled-reason="startDisabledReason"
          :show-close="Boolean(selectedRunId)"
          close-label="查看运行详情"
          @update:model-value="applyConfig"
          @refresh-projects="loadBuildProjects()"
          @close="closeConfigPanel"
          @start="handleStart"
        />
      </div>

      <div v-else-if="selectedRun" class="detail-stack ea-stack">
        <div
          v-if="selectedRun.status === 'conflict'"
          class="conflict-banner"
        >
          <div>
            <strong>冲突停驻</strong>
            <span>{{ conflictFiles.length }} 个待处理文件 · {{ summaryText }}</span>
          </div>
          <div class="conflict-banner-actions">
            <NButton secondary size="small" :loading="refreshing" @click="handleRefreshConflicts">
              刷新冲突
            </NButton>
            <NButton type="primary" size="small" :loading="continuing" @click="handleContinueRun">
              继续执行
            </NButton>
          </div>
        </div>

        <div class="ea-card detail-summary">
          <div class="detail-head">
            <div class="detail-title">
              <div class="ea-section-title">运行详情</div>
              <h2>{{ selectedRun.config.NODE_BRANCH || '—' }} → {{ selectedRun.config.target_BRANCH || '—' }}</h2>
              <p class="detail-id">{{ selectedRun.runId }}</p>
            </div>
            <div class="detail-meta">
              <span
                :class="{
                  'ea-pill-ok': selectedRun.status === 'success',
                  'ea-pill-warn': selectedRun.status === 'conflict',
                  'ea-pill-err': selectedRun.status === 'failed',
                  'ea-pill-info': selectedRun.status === 'running',
                  'ea-pill-muted': !['success', 'conflict', 'failed', 'running'].includes(selectedRun.status),
                }"
              >
                {{ statusMeta.label }}
              </span>
              <NButton type="primary" secondary size="small" @click="handleCreateUpgrade">
                新建升级
              </NButton>
              <NButton secondary size="small" @click="handleReopenFromRun(selectedRun.runId)">
                基于此再开
              </NButton>
              <NButton secondary size="small" @click="handleSelectRun(selectedRun.runId)">刷新</NButton>
            </div>
          </div>

          <div class="summary-strip">
            <div class="summary-item">
              <span class="summary-label">JIRA</span>
              <span class="summary-value">{{ selectedRun.config.JIRAID || '—' }}</span>
            </div>
            <span class="summary-divider" />
            <div class="summary-item">
              <span class="summary-label">冲突</span>
              <span class="summary-value">{{ conflictFiles.length }}</span>
            </div>
            <span class="summary-divider" />
            <div class="summary-item summary-grow">
              <span class="summary-label">工作区</span>
              <span class="summary-value" :title="selectedRun.config.work_dir || ''">
                {{ selectedRun.config.work_dir || '—' }}
              </span>
            </div>
          </div>
        </div>

        <ModemBaselineStagePanel
          :run="selectedRun"
          :items="stageItems"
          :summary="summaryText"
          :refreshing="refreshing"
          :continuing="continuing"
          @refresh-conflicts="handleRefreshConflicts"
          @continue-run="handleContinueRun"
        />

        <div class="ea-card ea-stack">
          <div class="console-head">
            <div>
              <div class="ea-section-title">执行日志</div>
              <h3>实时输出</h3>
            </div>
            <span class="ea-pill-muted">Run {{ selectedRun.runId }}</span>
          </div>
          <ModemBaselineLogFilterBar
            v-model:only-errors="onlyErrors"
            v-model:only-conflicts="onlyConflicts"
            @jump-latest="scrollLogToBottom"
          />
          <div ref="logScroller" class="ea-mon-output" @scroll="handleLogScroll">
            {{ filteredLog || '暂无日志输出' }}
          </div>
        </div>

        <div class="ea-card ea-stack">
          <div class="console-head">
            <div>
              <div class="ea-section-title">冲突工作区</div>
              <h3>待处理文件</h3>
            </div>
            <div class="conflict-head-actions">
              <span :class="conflictFiles.length ? 'ea-pill-warn' : 'ea-pill-ok'">
                {{ conflictFiles.length ? `${conflictFiles.length} 个条目` : '当前无冲突' }}
              </span>
              <template v-if="selectedRun.status === 'conflict'">
                <NButton secondary size="small" :loading="refreshing" @click="handleRefreshConflicts">
                  刷新冲突
                </NButton>
                <NButton type="primary" size="small" :loading="continuing" @click="handleContinueRun">
                  继续执行
                </NButton>
              </template>
            </div>
          </div>

          <div v-if="conflictFiles.length" class="conflict-list">
            <div v-for="file in conflictFiles" :key="file" class="conflict-item">
              <div>
                <strong>{{ file }}</strong>
                <p>研发手动处理完成后，请先点“刷新冲突”，确认清空后再继续执行。</p>
              </div>
              <div class="conflict-actions">
                <span class="ea-pill-warn">待处理</span>
                <NButton secondary size="small" @click="handleOpenConflictFile(file)">打开文件</NButton>
              </div>
            </div>
          </div>

          <div v-else class="conflict-empty">
            {{ selectedRun.status === 'conflict'
              ? '冲突已清空。确认无误后点击上方「继续执行」。'
              : '当前任务没有冲突文件；如果刚处理过冲突，请点击“刷新冲突”确认状态。' }}
          </div>
        </div>
      </div>

      <div v-else class="ea-card detail-empty">
        <div>
          <strong>右侧工作区</strong>
          <span>点击左侧「新建升级」填写通知与配置，或选择历史任务查看运行详情。</span>
        </div>
        <NButton type="primary" class="empty-action" @click="handleCreateUpgrade">新建升级</NButton>
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

.workspace-left > .preview-note {
  flex: 0 0 auto;
}

/* 外部通知与历史各占一半，内容各自滚动 */
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
  gap: 0;
  overflow: hidden;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface, #fff);
  transition: box-shadow 0.25s ease, border-color 0.25s ease;

  &.parse-flash {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);

    :deep(.parse-card) {
      background: color-mix(in srgb, var(--accent) 6%, transparent);
      border-radius: 10px;
      margin: -4px -6px 0;
      padding: 4px 6px 14px;
    }
  }
}

.config-stack > :deep(.parse-card) {
  flex: 0 0 auto;
}

.config-stack > :deep(.basic-config-card) {
  flex: 1 1 auto;
  min-height: 0;
  padding-top: 12px;
}

.workspace-detail > .detail-stack,
.workspace-detail > .detail-empty {
  flex: 1;
  min-height: 0;
}

.detail-stack {
  overflow: auto;
  scrollbar-gutter: stable;
}

.detail-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 18px;
}

.conflict-banner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--amber-fg, #b45309) 35%, var(--line));
  border-radius: 12px;
  background: color-mix(in srgb, var(--amber-fg, #b45309) 10%, var(--bg));

  strong {
    display: block;
    font-size: 13px;
    color: var(--amber-fg, #b45309);
  }

  span {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: var(--text);
    line-height: 1.4;
  }
}

.conflict-banner-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex: 0 0 auto;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-title {
  min-width: 0;
  flex: 1;

  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
    line-height: 1.3;
    word-break: break-word;
  }
}

.detail-id {
  margin: 4px 0 0;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--muted);
  word-break: break-all;
}

.detail-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  flex: 0 0 auto;
}

.summary-strip {
  display: flex;
  align-items: center;
  min-width: 0;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg);
}

.summary-item {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  padding: 0 12px;

  &:first-child {
    padding-left: 0;
  }
}

.summary-grow {
  flex: 1;
}

.summary-label {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  white-space: nowrap;
}

.summary-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-divider {
  width: 1px;
  align-self: stretch;
  background: var(--line);
  flex: 0 0 auto;
}

.detail-empty {
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 16px;
  padding: 36px;
  color: var(--muted);
  text-align: center;

  strong {
    display: block;
    margin-bottom: 6px;
    color: var(--text);
    font-size: 17px;
  }

  span {
    font-size: 13px;
    line-height: 1.5;
  }
}

.empty-action {
  min-width: 140px;
}

.console-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }
}

.ea-mon-output {
  height: 320px;
  min-height: 320px;
  max-height: 320px;
  overflow: auto;
}

.conflict-head-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.conflict-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.conflict-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--bg);

  strong {
    display: block;
    font-size: 13px;
    color: var(--text);
    word-break: break-word;
    overflow-wrap: anywhere;
  }

  p {
    margin-top: 4px;
    font-size: 12px;
    color: var(--muted);
  }

  > div:first-child {
    flex: 1;
    min-width: 0;
  }
}

.conflict-empty {
  padding: 18px;
  border-radius: 14px;
  border: 1px dashed var(--line-strong);
  background: var(--bg);
  color: var(--muted);
  font-size: 13px;
}

.preview-note {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--amber-bg);
  color: var(--amber-fg);
  border: 1px solid color-mix(in srgb, var(--amber-ic) 20%, transparent);

  strong {
    font-size: 13px;
  }

  span {
    font-size: 12.5px;
  }
}

.conflict-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  justify-content: flex-end;
  min-width: 128px;
}

@media (max-width: 1200px) {
  .workspace-layout {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
  }

  .workspace-left,
  .workspace-detail {
    height: auto;
  }

  .workspace-detail {
    overflow: visible;
  }

  .workspace-detail > :deep(.basic-config-card),
  .workspace-detail > .detail-stack,
  .workspace-detail > .detail-empty {
    flex: none;
    min-height: 360px;
  }
}

@media (max-width: 720px) {
  .conflict-item,
  .conflict-actions,
  .console-head,
  .detail-head {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
