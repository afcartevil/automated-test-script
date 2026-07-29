<script setup lang="ts">
import { computed, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import ModemBaselineConfigCard from '@/components/tahp/modem-baseline/ModemBaselineConfigCard.vue'
import ModemBaselineLogFilterBar from '@/components/tahp/modem-baseline/ModemBaselineLogFilterBar.vue'
import ModemBaselineStagePanel from '@/components/tahp/modem-baseline/ModemBaselineStagePanel.vue'
import { useModemBaseline } from '@/composables/useModemBaseline'

const message = useMessage()
const {
  config,
  noticeText,
  noticeParsed,
  recommendation,
  selectedRepo,
  selectedRun,
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
  statusMeta,
  stageItems,
  initialize,
  loadBuildProjects,
  requestRecommend,
  applyRecommendation,
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
type RecommendationFeedback = {
  tone: 'success' | 'warning'
  title: string
  successes: string[]
  failures: string[]
}

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
}

function withText(value?: string) {
  return String(value ?? '').trim()
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
): RecommendationFeedback {
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

  const tone: RecommendationFeedback['tone'] = failures.length ? 'warning' : 'success'
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

function showRecommendationToast(feedback: RecommendationFeedback) {
  const renderSection = (title: string, items: string[], tone: 'success' | 'warning') => {
    if (!items.length) return null
    return h('div', { style: 'margin-top: 8px;' }, [
      h(
        'div',
        {
          style: `font-size: 12px; font-weight: 600; margin-bottom: 4px; color: ${
            tone === 'success' ? 'var(--ok-fg)' : 'var(--amber-fg)'
          };`,
        },
        title,
      ),
      ...items.map(item =>
        h(
          'div',
          {
            style: 'font-size: 12px; line-height: 1.5; word-break: break-word;',
          },
          item,
        ),
      ),
    ])
  }

  message.create(
    () =>
      h('div', { style: 'max-width: 560px;' }, [
        h('div', { style: 'font-weight: 600; line-height: 1.5;' }, feedback.title),
        renderSection('已识别 / 已回填', feedback.successes, 'success'),
        renderSection('未识别 / 未回填', feedback.failures, 'warning'),
      ]),
    {
      type: feedback.tone,
      duration: 8000,
      closable: true,
      keepAliveOnHover: true,
    },
  )
}

async function handleStart() {
  try {
    await startRun()
    message.success('已启动 Modem升级任务')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
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
    showRecommendationToast(feedback)
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
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
        :build-projects="buildProjects"
        :build-projects-warning="buildProjectsWarning"
        :loading-build-projects="loadingBuildProjects"
        :loading="starting || loading"
        :notice-text="noticeText"
        :parsing="parsingNotice"
        :recommending="recommending"
        @update:model-value="applyConfig"
        @update:notice-text="noticeText = $event"
        @refresh-projects="loadBuildProjects()"
        @parse-and-apply="handleParseAndApply"
        @start="handleStart"
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
  grid-template-columns: minmax(320px, 0.95fr) minmax(420px, 1.2fr);
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
