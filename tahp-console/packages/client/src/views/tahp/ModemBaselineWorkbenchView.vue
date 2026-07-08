<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, useMessage } from 'naive-ui'
import ModemBaselineBranchTemplateApplyCard from '@/components/tahp/modem-baseline/ModemBaselineBranchTemplateApplyCard.vue'
import ModemBaselineConfigCard from '@/components/tahp/modem-baseline/ModemBaselineConfigCard.vue'
import ModemBaselineHistoryPanel from '@/components/tahp/modem-baseline/ModemBaselineHistoryPanel.vue'
import ModemBaselineLogFilterBar from '@/components/tahp/modem-baseline/ModemBaselineLogFilterBar.vue'
import ModemBaselineNoticeRecommendCard from '@/components/tahp/modem-baseline/ModemBaselineNoticeRecommendCard.vue'
import ModemBaselinePrecheckPanel from '@/components/tahp/modem-baseline/ModemBaselinePrecheckPanel.vue'
import ModemBaselineStagePanel from '@/components/tahp/modem-baseline/ModemBaselineStagePanel.vue'
import { useModemBaseline } from '@/composables/useModemBaseline'

const router = useRouter()
const message = useMessage()
const {
  config,
  runs,
  repoProfiles,
  branchTemplates,
  selectedRepo,
  selectedTosVersion,
  selectedBranchTemplateId,
  selectedBranchTarget,
  rules,
  noticeText,
  noticeParsed,
  recommendation,
  precheck,
  selectedRun,
  selectedRunId,
  conflictFiles,
  logContent,
  loading,
  loadingBranchTemplates,
  starting,
  prechecking,
  parsingNotice,
  recommending,
  continuing,
  refreshing,
  errorMessage,
  statusMeta,
  stageItems,
  metrics,
  initialize,
  loadDefaults,
  requestRecommend,
  applyRecommendation,
  chooseTosVersion,
  chooseBranchTemplate,
  applyBranchTemplate,
  runPrecheck,
  selectRun,
  startRun,
  continueRun,
  refreshConflicts,
  openConflictFile,
  closeEventSource,
} = useModemBaseline()

const summaryText = computed(() => statusMeta.value.summary)
const logScroller = ref<HTMLElement | null>(null)
const shouldStickToBottom = ref(true)
const LOG_BOTTOM_THRESHOLD = 24
const onlyErrors = ref(false)
const onlyConflicts = ref(false)

const filteredLog = computed(() => {
  const raw = logContent.value || ''
  if (!onlyErrors.value && !onlyConflicts.value) return raw
  const lines = raw.split(/\r?\n/)
  const out = lines.filter((line) => {
    if (onlyErrors.value && (/\berror\b/i.test(line) || /\bfailed\b/i.test(line))) return true
    if (onlyConflicts.value && (/\bconflict\b/i.test(line) || /\[conflicts\]/i.test(line))) return true
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

function applyConfig(nextValue: typeof config.value) {
  config.value = { ...nextValue }
  precheck.value = null
}

async function handleLoadDefaults() {
  try {
    await loadDefaults()
    message.success('已重新加载默认配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleStart() {
  try {
    await startRun()
    message.success('已启动 Modem 基线任务')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleRunPrecheck() {
  try {
    const result = await runPrecheck()
    if (result.canStart) message.success('执行前检查通过')
    else message.warning('执行前检查发现阻断项')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleContinueRun() {
  try {
    await continueRun()
    message.success('已发送继续执行请求')
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
    const hasRecommendedBranches = Boolean(recommendation.value?.nodeBranch && recommendation.value?.targetBranch)
    if (apply.repoAction === 'ambiguous') {
      const list = (apply.candidates ?? []).slice(0, 4).map(item => item.platform || item.label).join('、')
      message.warning(`匹配到多个候选仓库（${(apply.candidates ?? []).length}）：${list}。请先到配置中心设为当前仓库`)
      return
    }
    if (apply.repoAction === 'no_platform') {
      message.warning('通知中未解析出平台，无法自动同步仓库与执行参数')
      return
    }
    if (apply.repoAction === 'no_match') {
      message.warning('未匹配到推荐平台对应仓库，无法自动同步仓库与执行参数')
      return
    }
    if (apply.repoAction === 'auto_selected') {
      message.success('已解析并应用推荐（自动同步仓库路径）')
      return
    }
    if (apply.repoAction === 'synced_selected') {
      message.success('已解析并应用推荐（同步当前仓库路径）')
      return
    }
    if (apply.repoAction === 'fallback_selected') {
      message.warning('未匹配到推荐平台对应仓库，已回退为当前仓库路径并应用推荐')
      return
    }
    if (!hasRecommendedBranches) {
      message.warning('已解析平台和版本，但未匹配到可用分支模板或规则，请手动选择分支模板或直接填写分支')
      return
    }
    if (recommendation.value?.branchSource === 'template') {
      message.success(`已解析并应用导入模板（${recommendation.value.targetMode === 'mp' ? 'MP' : '主干'}）`)
      return
    }
    message.success('已解析并应用推荐')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

function handleApplyBranchTemplate() {
  const result = applyBranchTemplate()
  if (!result.applied) {
    message.warning('请先选择一个可用的分支模板')
    return
  }
  message.success(`已按 ${selectedBranchTarget.value === 'mp' ? 'MP' : '主干'} 模板回填分支`)
}

function goSettings() {
  router.push({ name: 'tahp.modem-baseline.settings' })
}

onMounted(() => {
  void initialize()
})

onUnmounted(() => {
  closeEventSource()
})
</script>

<template>
  <div class="main-grid">
    <div class="ea-stack">
      <ModemBaselineConfigCard
        :model-value="config"
        :loading="starting || loading"
        @update:model-value="applyConfig"
        @load-defaults="handleLoadDefaults"
        @start="handleStart"
      />

      <ModemBaselineNoticeRecommendCard
        :notice-text="noticeText"
        :parsed="noticeParsed"
        :recommendation="recommendation"
        :parsing="parsingNotice"
        :recommending="recommending"
        @update:notice-text="noticeText = $event"
        @parse-and-apply="handleParseAndApply"
      />

      <ModemBaselineBranchTemplateApplyCard
        :templates="branchTemplates"
        :selected-tos="selectedTosVersion"
        :selected-template-id="selectedBranchTemplateId"
        :selected-target="selectedBranchTarget"
        :loading="loadingBranchTemplates"
        :parsed="noticeParsed"
        @update:selected-tos="chooseTosVersion"
        @update:selected-template-id="chooseBranchTemplate"
        @update:selected-target="selectedBranchTarget = $event"
        @apply="handleApplyBranchTemplate"
      />

      <ModemBaselinePrecheckPanel
        :result="precheck"
        :loading="prechecking"
        @run="handleRunPrecheck"
      />
    </div>

    <div class="ea-stack">
      <ModemBaselineStagePanel
        v-if="selectedRun"
        :run="selectedRun"
        :items="stageItems"
        :summary="summaryText"
        :refreshing="refreshing"
        :continuing="continuing"
        @refresh-conflicts="handleRefreshConflicts"
        @continue-run="handleContinueRun"
      />

      <div v-else class="ea-card conflict-empty">暂无运行记录，填写配置后可直接启动首个基线任务。</div>

      <div class="ea-card ea-stack">
        <div class="console-head">
          <div>
            <div class="ea-section-title">实时日志</div>
            <h3>执行输出</h3>
          </div>
          <span class="ea-pill-muted">Run {{ selectedRun?.runId || '—' }}</span>
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
          <span :class="conflictFiles.length ? 'ea-pill-warn' : 'ea-pill-ok'">
            {{ conflictFiles.length ? `${conflictFiles.length} 个条目` : '当前无冲突' }}
          </span>
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
          当前任务没有冲突文件；如果刚处理过冲突，请点击“刷新冲突”确认状态。
        </div>
      </div>
    </div>

    <div class="ea-stack">
      <div class="ea-card ea-stack">
        <div class="console-head">
          <div>
            <div class="ea-section-title">当前执行上下文</div>
            <h3>仓库与规则入口</h3>
            <p>工作台优先展示高频执行区，低频的工作区、仓库和规则维护统一放到配置中心。</p>
          </div>
          <NButton secondary @click="goSettings">打开配置中心</NButton>
        </div>

        <div class="repo-summary">
          <div class="repo-summary__item">
            <span class="ea-pill-muted">已选仓库</span>
            <strong>{{ selectedRepo?.label || '未选择' }}</strong>
            <p>{{ selectedRepo?.localPath || '请先到配置中心登记并选择仓库，或手动填写 work_dir。' }}</p>
          </div>
          <div class="repo-summary__item">
            <span class="ea-pill-info">规则</span>
            <strong>{{ rules.length }}</strong>
            <p>当前用户下可用的推荐规则数量。</p>
          </div>
          <div class="repo-summary__item">
            <span class="ea-pill-info">仓库</span>
            <strong>{{ repoProfiles.length }}</strong>
            <p>已登记仓库数量；仍支持手动填写执行路径。</p>
          </div>
        </div>
      </div>

      <div class="ea-card">
        <div class="ea-section-title">任务摘要</div>
        <div class="ea-meta-grid modem-meta-grid">
          <div
            v-for="item in metrics"
            :key="item.label"
            class="mg"
            :class="{ 'mg-wide': item.label === '工作区' }"
          >
            <div class="mg-k">{{ item.label }}</div>
            <div class="mg-v">{{ item.value }}</div>
          </div>
        </div>
      </div>

      <ModemBaselineHistoryPanel
        :runs="runs"
        :selected-run-id="selectedRunId"
        @select="selectRun"
      />

      <div v-if="errorMessage" class="preview-note">
        <strong>接入异常</strong>
        <span>{{ errorMessage }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.main-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.95fr) minmax(420px, 1.2fr) minmax(300px, 0.85fr);
  gap: 16px;
  align-items: start;
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

  p {
    margin-top: 4px;
    font-size: 13px;
    color: var(--muted);
  }
}

.repo-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.repo-summary__item {
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--bg);
  border: 1px solid var(--line);

  strong {
    display: block;
    margin-top: 10px;
    font-size: 16px;
    color: var(--text);
    word-break: break-word;
  }

  p {
    margin-top: 6px;
    font-size: 12px;
    color: var(--muted);
    word-break: break-word;
  }
}

.ea-mon-output {
  height: 320px;
  min-height: 320px;
  max-height: 320px;
  overflow: auto;
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

.modem-meta-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));

  .mg {
    min-width: 0;
  }

  .mg-wide {
    grid-column: 1 / -1;
  }

  .mg-k {
    font-size: 12px;
    margin-bottom: 6px;
  }

  .mg-v {
    font-size: 15px;
    line-height: 1.5;
    word-break: break-word;
    overflow-wrap: anywhere;
    white-space: normal;
  }
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
  .main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .repo-summary,
  .conflict-item,
  .conflict-actions,
  .console-head {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
