<template>
  <section>
    <div class="topbar">
      <div>
        <p class="eyebrow">Patch Analysis</p>
        <h1 class="page-title">Patch 分析</h1>
        <p v-if="!isEmbedded" class="page-desc">支持单 SHA 和 tag 区间分析，复用现有评分脚本、报告渲染和实时进度推送。</p>
      </div>
      <div class="toolbar">
        <a v-if="selectedTask" class="btn" :href="`/api/tasks/${selectedTask.id}/report?inline=1`" target="_blank">查看报告</a>
        <a v-if="selectedTask" class="btn" :href="`/api/tasks/${selectedTask.id}/report`" target="_blank">下载报告</a>
        <button
          v-if="selectedTask"
          class="btn"
          :disabled="exportingFeishu"
          @click="exportFeishuChecklist"
        >{{ exportingFeishu ? '导出中...' : '导出到飞书' }}</button>
        <a
          v-if="selectedTask?.feishu_checklist_url"
          class="btn"
          :href="selectedTask.feishu_checklist_url"
          target="_blank"
        >打开飞书表格</a>
        <a
          v-if="selectedTask?.feishu_module_report_folder || selectedTask?.feishu_module_report_url"
          class="btn"
          :href="selectedTask.feishu_module_report_folder || selectedTask.feishu_module_report_url"
          target="_blank"
        >打开模块代码云盘</a>
        <a v-if="selectedTask" class="btn" :href="`/api/tasks/${selectedTask.id}/diff`" target="_blank">下载 Diff</a>
        <RouterLink
          v-if="canStartUpgrade"
          class="btn primary"
          :to="{ path: '/upgrade', query: { task: selectedTask.id } }"
        >
          升级合入
        </RouterLink>
      </div>
    </div>

    <div class="workspace-layout">
      <div class="workspace-left">
      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>新建分析</h2>
            <p>选择分析模式并提交任务</p>
          </div>
          <div class="segmented">
            <button :class="{ active: mode === 'single' }" @click="mode = 'single'">单 SHA</button>
            <button :class="{ active: mode === 'range' }" @click="mode = 'range'">Tag 区间</button>
          </div>
        </div>

        <div class="form-grid">
          <div class="field full">
            <label>仓库 URL</label>
            <input v-model="form.repo" class="input" />
          </div>
          <template v-if="mode === 'single'">
            <div class="field full">
              <label>Commit SHA</label>
              <input v-model="form.sha" class="input mono" placeholder="输入 commit sha" />
            </div>
          </template>
          <template v-else>
            <div class="field">
              <label>From Tag</label>
              <TagSelect
                v-model="form.from_tag"
                :options="repoTags"
                :loading="tagsLoading"
                :empty-hint="tagsHint"
                placeholder="输入检索，如 android15 2026-01 r11"
              />
            </div>
            <div class="field">
              <label>To Tag</label>
              <TagSelect
                v-model="form.to_tag"
                :options="repoTags"
                :loading="tagsLoading"
                :empty-hint="tagsHint"
                placeholder="输入检索，如 android15 2026-01 r36"
              />
            </div>
            <div class="field">
              <label>采样数量</label>
              <input
                v-model="form.sample_size"
                class="input"
                type="number"
                min="1"
                placeholder="留空=全量分析"
              />
            </div>
          </template>
          <label class="field full" style="display:flex;align-items:center;gap:9px">
            <input v-model="form.force_reanalyze" type="checkbox" />
            <span>强制重新分析</span>
          </label>
        </div>

        <div class="toolbar" style="margin-top: 16px">
          <button class="btn primary" :disabled="submitting" @click="startAnalysis">
            {{ submitting ? '提交中...' : '开始分析' }}
          </button>
          <button class="btn" @click="loadTasks">刷新历史</button>
        </div>
        <div v-if="message" class="message" style="margin-top: 14px">{{ message }}</div>
        <div v-if="error" class="message error" style="margin-top: 14px">{{ error }}</div>
      </div>

      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>任务历史</h2>
            <p>点击任务查看详情</p>
          </div>
          <div v-if="tasks.length" class="toolbar task-history-toolbar">
            <label class="task-select-all">
              <input
                type="checkbox"
                :checked="allTasksSelected"
                @change="toggleSelectAll(($event.target as HTMLInputElement).checked)"
              />
              全选
            </label>
            <button
              v-if="selectedCount > 0"
              class="btn danger btn-sm"
              :disabled="actionPending"
              @click="deleteSelectedTasks"
            >
              {{ actionPending ? '删除中…' : `批量删除 (${selectedCount})` }}
            </button>
          </div>
        </div>
        <div v-if="tasks.length" class="workspace-list">
          <div
            v-for="task in tasks"
            :key="task.id"
            class="selectable-item split task-history-item"
            :class="{ active: selectedTaskId === task.id, loading: loadingTaskId === task.id }"
          >
            <label class="task-history-check" @click.stop>
              <input
                type="checkbox"
                :checked="selectedTaskIds.has(task.id)"
                @change="toggleTaskSelection(task.id, ($event.target as HTMLInputElement).checked)"
              />
            </label>
            <button type="button" class="task-history-main" @click="selectTask(task.id)">
              <span>
                <strong>{{ taskTitle(task) }}</strong>
                <span v-if="taskDurationText(task, nowMs)" class="muted task-duration">{{ taskDurationText(task, nowMs) }}</span>
              </span>
              <span class="pill" :class="loadingTaskId === task.id ? 'info' : statusTone(task.status)">
                {{ loadingTaskId === task.id ? '加载中' : task.status || '-' }}
              </span>
            </button>
            <RouterLink
              v-if="task.type === 'range' && task.status === 'completed'"
              class="btn btn-sm primary"
              :to="{ path: '/upgrade', query: { task: task.id } }"
              @click.stop
            >
              升级合入
            </RouterLink>
          </div>
        </div>
        <div v-else class="empty">暂无任务</div>
      </div>
      </div>

      <aside class="workspace-detail-shell">
      <div ref="detailPanelRef" class="workspace-detail">
    <div v-if="selectedTask" class="card card-pad">
      <div v-if="loadingTaskId" class="detail-banner">
        正在加载任务详情：{{ shortId(loadingTaskId) }}
      </div>
      <div class="section-title">
        <div>
          <h2>{{ taskTitle(selectedTask) }}</h2>
          <p class="mono">{{ selectedTask.id }}</p>
        </div>
        <div class="toolbar task-actions">
          <span class="pill" :class="statusTone(displayStatus)">
            {{ displayStatus || '-' }}
          </span>
          <button v-if="isCancellable" class="btn danger" :disabled="actionPending" @click="cancelTask">
            {{ actionPending ? '处理中…' : '取消' }}
          </button>
          <button class="btn danger" :disabled="actionPending" @click="deleteTask">删除</button>
        </div>
      </div>

      <div v-if="selectedTask.created_at || selectedTask.llm_analyzed_count || selectedTaskDurationText" class="task-meta-bar muted">
        <span v-if="selectedTask.created_at">{{ formatDate(selectedTask.created_at) }}</span>
        <span v-if="selectedTaskDurationText">⏱ {{ selectedTaskDurationText }}</span>
        <span v-if="showResults">{{ patchCount }} 笔 patch</span>
        <span v-else-if="selectedTask.total">共 {{ selectedTask.total }} 笔 · 分析中</span>
        <span v-if="selectedTask.llm_analyzed_count">LLM {{ selectedTask.llm_analyzed_count }} 笔</span>
        <span v-if="tokenCount">🪙 {{ tokenCount.toLocaleString() }} tokens</span>
        <span v-if="selectedTask.new_analyzed">📊 新分析 {{ selectedTask.new_analyzed }} 笔</span>
        <span v-if="selectedTask.reused_count">已有 {{ selectedTask.reused_count }} 笔</span>
      </div>

      <div v-if="showProgressPanel" style="margin: 18px 0">
        <AnalysisProgressPanel
          :progress="progress"
          :failed-count="selectedTask.failed || 0"
        />
      </div>

      <div v-else-if="!showResults && displayStatus !== 'failed'" class="grid grid-4">
        <div class="metric card">
          <div class="metric-label">总数</div>
          <div class="metric-value">{{ selectedTask.total || progress.total || 0 }}</div>
        </div>
        <div class="metric card">
          <div class="metric-label">已分析</div>
          <div class="metric-value">{{ selectedTask.analyzed || progress.analyzed || 0 }}</div>
        </div>
        <div class="metric card">
          <div class="metric-label">平均分</div>
          <div class="metric-value">{{ averageScore }}</div>
        </div>
        <div class="metric card">
          <div class="metric-label">Patch</div>
          <div class="metric-value">{{ patchCount }}</div>
        </div>
      </div>

      <div v-if="llmErrorBanner" class="message warning">{{ llmErrorBanner }}</div>

      <div v-if="showResults" class="analysis-results">
        <AnalysisSectionNav
          v-if="analysisNavSections.length"
          v-model:active-id="activeNavSection"
          :sections="analysisNavSections"
          @navigate="scrollToAnalysisSection"
        />
        <MonthlySubtagPanel
          v-if="monthlySubtagData && selectedTask"
          :task-id="selectedTask.id"
          :recommendation="monthlySubtagData"
        />
        <AnalysisSummaryPanel
          v-if="taskSummary"
          :task-id="selectedTask?.id || ''"
          :summary="taskSummary"
          @filter-module="filterIndexModule"
          @jump-to-patch="jumpToPatch"
        />
        <TaskPatchIndexPanel
          v-if="selectedTask"
          ref="patchIndexRef"
          :task-id="selectedTask.id"
          :initial-module="indexModule"
        />
      </div>
      <div v-else-if="isTaskRunning" class="empty-state-inline">
        ⏳ 分析进行中，完成后将显示总结与可点击的 patch 入口…
      </div>

      <div v-else-if="displayStatus === 'failed'" class="message error">
        ❌ 分析失败：{{ selectedTask.error_msg || '未知错误' }}
      </div>

      <div v-else-if="displayStatus === 'cancelled'" class="empty-state-inline">
        任务已取消{{ selectedTask.error_msg ? `：${selectedTask.error_msg}` : '' }}
      </div>
    </div>
    <div v-else class="card detail-empty">
      <div>
        <strong>请选择一条任务</strong>
        <span>点击左侧任务历史后，详情会在这里显示。</span>
      </div>
    </div>
      </div>
        <ScrollToTopButton
          v-if="showDetailScrollTop"
          :scroll-target="detailPanelRef"
          :can-return="Boolean(panelScroll.returnSnapshot.value)"
          @click="panelScroll.scrollToSavedOrTop()"
        />
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import TagSelect from '../components/TagSelect.vue'
import AnalysisProgressPanel from '../components/analysis/AnalysisProgressPanel.vue'
import AnalysisSectionNav from '../components/analysis/AnalysisSectionNav.vue'
import AnalysisSummaryPanel from '../components/analysis/AnalysisSummaryPanel.vue'
import MonthlySubtagPanel from '../components/analysis/MonthlySubtagPanel.vue'
import TaskPatchIndexPanel from '../components/analysis/TaskPatchIndexPanel.vue'
import ScrollToTopButton from '../components/ScrollToTopButton.vue'
import { usePanelScrollReturn } from '../composables/usePanelScrollReturn'
import { useRepoTags } from '../composables/useRepoTags'
import { scrollPanelToSection, useAnalysisSectionSpy } from '../composables/useSectionScroll'
import { buildAnalysisNavSections, isSameMonthSubtagRange } from '../utils/analysisDisplay'
import { api, formatDate, formatElapsed, shortId, statusTone, wsUrl } from '../api'
import { isEmbeddedMode } from '../composables/useEmbeddedNav'

const isEmbedded = isEmbeddedMode()
const route = useRoute()
const router = useRouter()
const mode = ref<'single' | 'range'>('range')
const submitting = ref(false)
const tasks = ref<any[]>([])
const selectedTaskIds = ref<Set<string>>(new Set())
const selectedTaskId = ref('')
const loadingTaskId = ref('')
const selectedTask = ref<any | null>(null)
const progress = ref<any>({})
const detailPanelRef = ref<HTMLElement | null>(null)
const activeNavSection = ref('')
const indexModule = ref('')
const patchIndexRef = ref<InstanceType<typeof TaskPatchIndexPanel> | null>(null)
const panelScroll = usePanelScrollReturn(detailPanelRef, ref(null))

watch(selectedTaskId, () => {
  panelScroll.returnSnapshot.value = null
  activeNavSection.value = ''
})

const actionPending = ref(false)
const exportingFeishu = ref(false)
const { repoTags, tagsLoading, tagsHint, loadRepoTags } = useRepoTags()
const message = ref('')
const error = ref('')
const nowMs = ref(Date.now())
let socket: WebSocket | null = null
let terminalRefreshDone = false
let durationTimer: ReturnType<typeof setInterval> | null = null

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

watch(mode, (value) => {
  if (value === 'range') {
    void loadRepoTags()
  }
})

function effectiveTaskStatus(task: any) {
  if (!task) return ''
  if (selectedTaskId.value === task.id) {
    const progStatus = String(progress.value.status || '').toLowerCase()
    if (progStatus && progStatus !== 'unknown') return progStatus
    if (selectedTask.value?.llm_running) return 'llm_analyzing'
  }
  return String(task.status || '').toLowerCase()
}

function isTaskStillRunning(task: any) {
  const status = effectiveTaskStatus(task)
  return status && !TERMINAL_STATUSES.has(status)
}

function resolveTaskElapsedSeconds(task: any): number | null {
  if (!task) return null
  const status = effectiveTaskStatus(task)
  const saved = Number(task.elapsed_seconds || 0)

  if (TERMINAL_STATUSES.has(status)) {
    if (saved > 0) return saved
    if (status === 'cancelled' && task.created_at && task.completed_at) {
      const start = new Date(task.created_at).getTime()
      const end = new Date(task.completed_at).getTime()
      if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
        return Math.floor((end - start) / 1000)
      }
    }
    return saved > 0 ? saved : null
  }

  if (isTaskStillRunning(task) && task.created_at) {
    const start = new Date(task.created_at).getTime()
    if (!Number.isNaN(start)) {
      return Math.max(0, Math.floor((nowMs.value - start) / 1000))
    }
  }

  if (saved > 0) return saved
  return null
}

function taskDurationText(task: any, _tick?: number) {
  void _tick
  const seconds = resolveTaskElapsedSeconds(task)
  if (seconds == null) return ''
  const label = isTaskStillRunning(task) ? '已运行' : '耗时'
  return `${label} ${formatElapsed(seconds)}`
}

const selectedTaskDurationText = computed(() => {
  nowMs.value
  if (!selectedTask.value) return ''
  return taskDurationText(selectedTask.value)
})

const selectedCount = computed(() => selectedTaskIds.value.size)

const allTasksSelected = computed(() => {
  if (!tasks.value.length) return false
  return tasks.value.every((task) => selectedTaskIds.value.has(task.id))
})

async function refreshTaskDetail(taskId: string) {
  const task = await api.get<any>(`/api/tasks/${taskId}`)
  selectedTask.value = task
  progress.value = task.progress && Object.keys(task.progress).length ? task.progress : {}
}

function jumpToPatch(sha: string) {
  const target = String(sha || '').trim()
  if (!target) return
  const href = router.resolve({ name: 'patch-detail', params: { sha: target } }).href
  window.open(href, '_blank', 'noopener,noreferrer')
}

function filterIndexModule(moduleName: string) {
  const name = String(moduleName || '').trim()
  indexModule.value = name
  patchIndexRef.value?.setModuleFilter(name)
  nextTick(() => scrollToAnalysisSection('analysis-section-patch-index'))
}

function connectTaskSocket(taskId: string) {
  if (socket) {
    socket.onmessage = null
    socket.onclose = null
    socket.close()
    socket = null
  }
  terminalRefreshDone = false
  socket = new WebSocket(wsUrl(`/ws/${taskId}`))
  socket.onmessage = (event) => {
    progress.value = JSON.parse(event.data || '{}')
    const status = String(progress.value.status || '').toLowerCase()
    if (TERMINAL_STATUSES.has(status) && !terminalRefreshDone) {
      terminalRefreshDone = true
      refreshTaskDetail(taskId).catch(() => {})
      loadTasks().catch(() => {})
    }
  }
}

const form = reactive({
  repo: 'https://android.googlesource.com/kernel/common',
  sha: '',
  from_tag: '',
  to_tag: '',
  sample_size: '' as number | string,
  force_reanalyze: false,
})

const taskSummary = computed(() => {
  const raw = selectedTask.value?.summary
  if (raw && typeof raw === 'object' && raw.total != null) return raw
  return null
})

const monthlySubtagData = computed(() => {
  const task = selectedTask.value
  if (isSameMonthSubtagRange(task?.from_tag, task?.to_tag)) return null
  const rec =
    progress.value.monthly_recommendation ||
    task?.monthly_recommendation ||
    task?.progress?.monthly_recommendation
  if (!rec) return null
  if (rec.has_recommendation || (rec.range_stats && rec.range_stats.length > 0)) return rec
  return null
})

const analysisNavSections = computed(() =>
  buildAnalysisNavSections(taskSummary.value, [], monthlySubtagData.value),
)

const analysisNavSectionIds = computed(() => analysisNavSections.value.map((section) => section.id))

const { pauseSpy: pauseNavSpy, refreshSpy: refreshNavSpy } = useAnalysisSectionSpy(
  detailPanelRef,
  analysisNavSectionIds,
  activeNavSection,
)

function scrollToAnalysisSection(sectionId: string) {
  activeNavSection.value = sectionId
  pauseNavSpy(900)
  scrollPanelToSection(detailPanelRef.value, sectionId)
}

const displayStatus = computed(() => {
  const progStatus = progress.value.status
  if (progStatus && progStatus !== 'unknown') return progStatus
  return selectedTask.value?.status || ''
})

const showResults = computed(() => {
  const task = selectedTask.value
  if (!task) return false
  const status = String(displayStatus.value || '').toLowerCase()
  if (status === 'completed') return true
  if (status === 'failed') return Boolean(taskSummary.value || Number(task.patch_count || task.total || 0) > 0)
  return false
})

watch(showResults, (visible) => {
  if (visible) nextTick(() => refreshNavSpy())
})

const isTaskRunning = computed(() => {
  const task = selectedTask.value
  if (!task) return false
  if (task.llm_running) return true
  const status = String(displayStatus.value || '').toLowerCase()
  return status && !['completed', 'failed', 'cancelled'].includes(status)
})

const showProgressPanel = computed(() => {
  if (!selectedTask.value) return false
  const status = String(displayStatus.value || '').toLowerCase()
  if (['completed', 'failed', 'cancelled'].includes(status)) return false
  return isTaskRunning.value || status === 'monthly_recommendation' || Boolean(progress.value?.message)
})

const showDetailScrollTop = computed(
  () => Boolean(selectedTask.value && (showResults.value || showProgressPanel.value)),
)

const llmErrorBanner = computed(() => {
  const msg = selectedTask.value?.error_msg || ''
  return showResults.value && msg.startsWith('LLM:') ? `⚠ ${msg}` : ''
})

const tokenCount = computed(() => {
  const task = selectedTask.value
  if (!task) return 0
  return Number(task.llm_prompt_tokens || 0) + Number(task.llm_completion_tokens || 0)
})

const patchCount = computed(() => {
  const task = selectedTask.value
  if (!task) return 0
  return Number(task.patch_count || taskSummary.value?.total || task.total || 0)
})

const averageScore = computed(() => {
  const summary = taskSummary.value
  const avg = summary?.avg_score ?? summary?.average_score
  if (avg != null && Number.isFinite(Number(avg))) return Number(avg).toFixed(1)
  return '-'
})

function parseProgressFraction(message: string) {
  const match = String(message || '').match(/(\d+)\s*\/\s*(\d+)/)
  if (!match) return null
  const done = Number(match[1])
  const total = Number(match[2])
  if (!Number.isFinite(done) || !Number.isFinite(total) || total <= 0 || done < 0 || done > total) {
    return null
  }
  return { done, total }
}

const progressPercent = computed(() => {
  const status = String(progress.value.status || selectedTask.value?.status || '').toLowerCase()
  if (status === 'completed') return 100
  if (status === 'failed' || status === 'cancelled') return 0

  const message = progress.value.message || ''
  if (status === 'summarizing' || status === 'monthly_recommendation') {
    const fraction = parseProgressFraction(message)
    if (fraction) {
      return Math.min(99, Math.round((fraction.done / fraction.total) * 100))
    }
  }

  const overallTotal = Number(progress.value.overall_total ?? 0)
  const overallCurrent = Number(progress.value.overall_current ?? 0)
  if (overallTotal > 0) {
    return Math.min(99, Math.round((overallCurrent / overallTotal) * 100))
  }

  if (status === 'monthly_recommendation') {
    const total = Number(progress.value.total ?? 0)
    const done = Number(progress.value.current ?? 0)
    if (total > 0) return Math.min(99, Math.round((done / total) * 100))
  }

  const phaseTotal = Number(progress.value.total ?? 0)
  const phaseDone = Number(progress.value.current ?? 0)
  if (phaseTotal > 0) {
    return Math.min(99, Math.round((phaseDone / phaseTotal) * 100))
  }

  return 0
})

const isCancellable = computed(() => {
  const status = String(displayStatus.value || '').toLowerCase()
  return status && !['completed', 'failed', 'cancelled'].includes(status)
})

const canStartUpgrade = computed(() => {
  const task = selectedTask.value
  if (!task || task.type !== 'range') return false
  return String(displayStatus.value || task.status || '').toLowerCase() === 'completed'
})

function taskTitle(task: any) {
  if (!task) return ''
  if (task.type === 'single') return task.sha || '单笔分析'
  return `${task.from_tag || '-'} -> ${task.to_tag || '-'}`
}

async function loadTasks() {
  const data = await api.get<any>('/api/tasks?limit=80')
  tasks.value = data.tasks || []
  const alive = new Set(tasks.value.map((task) => task.id))
  const next = new Set<string>()
  for (const id of selectedTaskIds.value) {
    if (alive.has(id)) next.add(id)
  }
  selectedTaskIds.value = next
}

function toggleTaskSelection(taskId: string, checked: boolean) {
  const next = new Set(selectedTaskIds.value)
  if (checked) next.add(taskId)
  else next.delete(taskId)
  selectedTaskIds.value = next
}

function toggleSelectAll(checked: boolean) {
  selectedTaskIds.value = checked ? new Set(tasks.value.map((task) => task.id)) : new Set()
}

function clearTaskDetail() {
  if (socket) {
    socket.onmessage = null
    socket.onclose = null
    socket.close()
    socket = null
  }
  selectedTask.value = null
  selectedTaskId.value = ''
  progress.value = {}
}

async function selectTask(taskId: string) {
  error.value = ''
  selectedTaskId.value = taskId
  loadingTaskId.value = taskId
  progress.value = {}
  indexModule.value = ''
  try {
    await refreshTaskDetail(taskId)
    connectTaskSocket(taskId)
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    loadingTaskId.value = ''
  }
}

async function exportFeishuChecklist() {
  if (!selectedTask.value) return
  exportingFeishu.value = true
  error.value = ''
  try {
    const result = await api.post(`/api/tasks/${selectedTask.value.id}/checklist-feishu`, {})
    if (selectedTask.value) {
      selectedTask.value.feishu_checklist_url = result.url
      selectedTask.value.feishu_checklist_token = result.token
      if (result.module_report_url) {
        selectedTask.value.feishu_module_report_url = result.module_report_url
      }
      if (result.module_report_folder) {
        selectedTask.value.feishu_module_report_folder = result.module_report_folder
      }
    }
    if (result.url) {
      window.open(result.url, '_blank')
    }
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    exportingFeishu.value = false
  }
}

async function cancelTask() {
  if (!selectedTask.value || !confirm('确定取消此分析任务？进行中的分析将停止。')) return
  actionPending.value = true
  error.value = ''
  try {
    await api.post(`/api/tasks/${selectedTaskId.value}/cancel`, {})
    if (socket) {
      socket.onmessage = null
      socket.onclose = null
      socket.close()
      socket = null
    }
    await refreshTaskDetail(selectedTaskId.value)
    await loadTasks()
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    actionPending.value = false
  }
}

async function deleteTask() {
  if (!selectedTask.value || !confirm('确定删除此任务及其所有分析结果？')) return
  actionPending.value = true
  error.value = ''
  try {
    await api.delete(`/api/tasks/${selectedTaskId.value}`)
    const nextSelection = new Set(selectedTaskIds.value)
    nextSelection.delete(selectedTaskId.value)
    selectedTaskIds.value = nextSelection
    clearTaskDetail()
    await loadTasks()
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    actionPending.value = false
  }
}

async function deleteSelectedTasks() {
  const ids = [...selectedTaskIds.value]
  if (!ids.length) return
  if (!confirm(`确定删除选中的 ${ids.length} 个分析任务及其所有分析结果？`)) return
  actionPending.value = true
  error.value = ''
  try {
    await Promise.all(ids.map((id) => api.delete(`/api/tasks/${id}`)))
    if (ids.includes(selectedTaskId.value)) {
      clearTaskDetail()
    }
    selectedTaskIds.value = new Set()
    await loadTasks()
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    actionPending.value = false
  }
}

async function startAnalysis() {
  submitting.value = true
  error.value = ''
  message.value = ''
  try {
    const body: any = {
      type: mode.value,
      repo: String(form.repo || '').trim(),
      force_reanalyze: form.force_reanalyze,
    }
    if (mode.value === 'single') {
      body.sha = String(form.sha || '').trim()
    } else {
      body.from_tag = String(form.from_tag || '').trim()
      body.to_tag = String(form.to_tag || '').trim()
      const sample = Number(form.sample_size)
      body.sample_size = Number.isFinite(sample) && sample > 0 ? Math.floor(sample) : 0
    }
    const data = await api.post<any>('/api/analyze', body)
    if (mode.value === 'range') {
      if (data.from_tag) form.from_tag = String(data.from_tag)
      if (data.to_tag) form.to_tag = String(data.to_tag)
    }
    const resolvedNote = data.tag_resolved
      ? `（已自动补全 Tag：${data.from_tag} → ${data.to_tag}）`
      : ''
    message.value = `任务已创建：${data.task_id}${resolvedNote}`
    await loadTasks()
    await selectTask(data.task_id)
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  durationTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
  applyNoticeQueryPrefill()
  if (mode.value === 'range') {
    void loadRepoTags()
  }
  await loadTasks()
  const taskId = String(route.query.task || '')
  if (taskId) {
    await selectTask(taskId)
  }
})

function applyNoticeQueryPrefill() {
  const fromTag = String(route.query.from_tag || '').trim()
  const toTag = String(route.query.to_tag || '').trim()
  if (!fromTag || !toTag) return
  mode.value = 'range'
  form.from_tag = fromTag
  form.to_tag = toTag
}

watch(
  () => [route.query.from_tag, route.query.to_tag] as const,
  () => applyNoticeQueryPrefill(),
)

onBeforeUnmount(() => {
  if (durationTimer) {
    clearInterval(durationTimer)
    durationTimer = null
  }
  if (socket) {
    socket.onmessage = null
    socket.onclose = null
    socket.close()
    socket = null
  }
})
</script>
