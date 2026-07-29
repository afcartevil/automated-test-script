<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NInput, NSelect, useMessage } from 'naive-ui'
import {
  getModemBaselineLog,
  getModemBaselineRun,
  listModemBaselineRuns,
  openModemBaselineConflictFile,
  type ModemBaselineRunMeta,
} from '@/api/tahp/modem-baseline'
import ModemBaselineLogFilterBar from '@/components/tahp/modem-baseline/ModemBaselineLogFilterBar.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loadingRuns = ref(false)
const loadingDetail = ref(false)
const runs = ref<ModemBaselineRunMeta[]>([])

const statusFilter = ref<'all' | ModemBaselineRunMeta['status']>('all')
const keyword = ref('')

const selectedRunId = ref('')
const selectedRun = ref<ModemBaselineRunMeta | null>(null)
const logContent = ref('')

const onlyErrors = ref(false)
const onlyConflicts = ref(false)
const logScroller = ref<HTMLElement | null>(null)
const shouldStickToBottom = ref(true)
const LOG_BOTTOM_THRESHOLD = 24

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '执行中', value: 'running' },
  { label: '已完成', value: 'success' },
  { label: '冲突停驻', value: 'conflict' },
  { label: '执行失败', value: 'failed' },
]

function toneClass(status: ModemBaselineRunMeta['status']) {
  switch (status) {
    case 'success':
      return 'ea-pill-ok'
    case 'conflict':
      return 'ea-pill-warn'
    case 'failed':
      return 'ea-pill-err'
    case 'running':
      return 'ea-pill-info'
    default:
      return 'ea-pill-muted'
  }
}

function statusLabel(status: ModemBaselineRunMeta['status']) {
  switch (status) {
    case 'success':
      return '已完成'
    case 'conflict':
      return '冲突停驻'
    case 'failed':
      return '执行失败'
    case 'running':
      return '执行中'
    default:
      return '待启动'
  }
}

const filteredRuns = computed(() => {
  const rawKeyword = keyword.value.trim().toLowerCase()
  const status = statusFilter.value
  return runs.value.filter((item) => {
    if (status !== 'all' && item.status !== status) return false
    if (!rawKeyword) return true
    const haystack = [
      item.runId,
      item.config.JIRAID,
      item.config.AP_lable,
      item.config.NODE_BRANCH,
      item.config.target_BRANCH,
      item.config.work_dir,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(rawKeyword)
  })
})

const filteredCountLabel = computed(() => `${filteredRuns.value.length} / ${runs.value.length}`)

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

async function reloadRuns() {
  loadingRuns.value = true
  try {
    runs.value = await listModemBaselineRuns()
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  } finally {
    loadingRuns.value = false
  }
}

async function loadDetail(runId: string) {
  loadingDetail.value = true
  try {
    const [run, log] = await Promise.all([
      getModemBaselineRun(runId),
      getModemBaselineLog(runId),
    ])
    selectedRun.value = run
    logContent.value = log.content || ''
  } catch (error) {
    selectedRun.value = null
    logContent.value = ''
    message.error(String((error as Error)?.message ?? error))
  } finally {
    loadingDetail.value = false
  }
}

function selectRun(runId: string) {
  if (!runId) return
  selectedRunId.value = runId
  router.replace({ name: 'tahp.modem-baseline.history', params: { runId } })
  void loadDetail(runId)
}

async function openConflictFile(file: string) {
  if (!selectedRun.value) return
  try {
    await openModemBaselineConflictFile(selectedRun.value.runId, file)
    message.success('已尝试打开冲突文件')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function refreshSelected() {
  if (!selectedRunId.value) return
  await loadDetail(selectedRunId.value)
}

watch(
  () => route.params.runId,
  (value) => {
    const runId = typeof value === 'string' ? value : ''
    if (!runId) return
    if (runId === selectedRunId.value) return
    selectedRunId.value = runId
    void loadDetail(runId)
  },
)

onMounted(async () => {
  await reloadRuns()
  const initial = typeof route.params.runId === 'string' ? route.params.runId : ''
  if (initial) {
    selectedRunId.value = initial
    await loadDetail(initial)
    return
  }
  if (runs.value.length) {
    selectRun(runs.value[0].runId)
  }
})
</script>

<template>
  <div class="history-grid">
    <div class="ea-card ea-stack list-card">
      <div class="card-head">
        <div>
          <div class="ea-section-title">运行历史</div>
          <h3>任务列表</h3>
        </div>
        <div class="head-actions">
          <span class="ea-pill-muted">{{ filteredCountLabel }}</span>
          <NButton secondary size="small" :loading="loadingRuns" @click="reloadRuns">刷新</NButton>
        </div>
      </div>

      <div class="list-toolbar">
        <div class="filter-grid">
          <NInput
            v-model:value="keyword"
            placeholder="runId / JIRA / AP / 分支 / 工作区"
            clearable
          />
          <NSelect v-model:value="statusFilter" :options="statusOptions" />
        </div>
      </div>

      <div class="run-list">
        <button
          v-for="item in filteredRuns"
          :key="item.runId"
          type="button"
          class="run-item"
          :class="{ active: item.runId === selectedRunId }"
          @click="selectRun(item.runId)"
        >
          <div class="run-head">
            <strong class="run-id">{{ item.runId }}</strong>
            <span :class="toneClass(item.status)">{{ statusLabel(item.status) }}</span>
          </div>
          <span class="run-line primary">{{ item.config.JIRAID || item.config.AP_lable || '未填写标识' }}</span>
          <span class="run-line branch">{{ item.config.NODE_BRANCH }} -> {{ item.config.target_BRANCH }}</span>
          <div class="run-meta">
            <span class="run-time">{{ item.finishedAt || item.startedAt || item.createdAt }}</span>
            <span class="run-workdir">{{ item.config.work_dir || '—' }}</span>
          </div>
        </button>

        <div v-if="!filteredRuns.length" class="empty-note">暂无匹配记录</div>
      </div>
    </div>

    <div class="ea-card ea-stack detail-card">
      <div class="card-head">
        <div>
          <div class="ea-section-title">运行详情</div>
          <h3>{{ selectedRun ? `Run ${selectedRun.runId}` : '选择任务查看' }}</h3>
        </div>
        <div class="detail-actions">
          <span v-if="selectedRun" :class="toneClass(selectedRun.status)">{{ statusLabel(selectedRun.status) }}</span>
          <NButton secondary size="small" :disabled="!selectedRunId" :loading="loadingDetail" @click="refreshSelected">
            刷新
          </NButton>
        </div>
      </div>

      <div v-if="selectedRun" class="detail-body">
        <div class="kv-grid">
          <div class="kv-item">
            <span class="kv-k">JIRA</span>
            <span class="kv-v">{{ selectedRun.config.JIRAID || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">AP label</span>
            <span class="kv-v">{{ selectedRun.config.AP_lable || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">NODE_BRANCH</span>
            <span class="kv-v">{{ selectedRun.config.NODE_BRANCH || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">target_BRANCH</span>
            <span class="kv-v">{{ selectedRun.config.target_BRANCH || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">工作区</span>
            <span class="kv-v">{{ selectedRun.config.work_dir || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">报告</span>
            <span class="kv-v">{{ selectedRun.reportPath || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">创建时间</span>
            <span class="kv-v">{{ selectedRun.createdAt || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">开始时间</span>
            <span class="kv-v">{{ selectedRun.startedAt || '—' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-k">结束时间</span>
            <span class="kv-v">{{ selectedRun.finishedAt || '—' }}</span>
          </div>
        </div>

        <div class="ea-divider" />

        <div class="ea-section-title">冲突文件</div>
        <div v-if="(selectedRun.conflictFiles || []).length" class="conflict-list">
          <button
            v-for="file in selectedRun.conflictFiles || []"
            :key="file"
            type="button"
            class="conflict-item"
            @click="openConflictFile(file)"
          >
            <strong>{{ file }}</strong>
            <span class="ea-pill-warn">打开</span>
          </button>
        </div>
        <div v-else class="empty-note">无冲突文件</div>

        <div class="ea-divider" />

        <div class="log-head">
          <div class="ea-section-title">运行日志</div>
          <span class="ea-pill-muted">Log</span>
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

      <div v-else class="empty-note">选择左侧任务查看详情</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.history-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(520px, 1.3fr);
  gap: 16px;
  align-items: start;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.filter-grid {
  display: grid;
  grid-template-columns: 1fr 160px;
  gap: 10px;
  align-items: center;
}

.list-toolbar {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface);
}

.run-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  max-height: calc(100vh - 270px);
  overflow: auto;
  padding-right: 4px;
}

.run-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--bg);
  padding: 12px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.18s, background 0.18s;

  &:hover {
    border-color: var(--line-strong);
  }

  &.active {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
    background: var(--accent-soft);
  }
}

.run-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.run-id {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-line {
  font-size: 12.5px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.primary {
    font-weight: 600;
  }

  &.branch {
    color: var(--muted);
  }
}

.run-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  min-width: 0;
  font-size: 12px;
  color: var(--muted);
}

.run-time,
.run-workdir {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-workdir {
  text-align: right;
}

.empty-note {
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px dashed var(--line);
  color: var(--muted);
  background: color-mix(in srgb, var(--surface) 70%, transparent);
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
}

.kv-item {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 10px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--bg);
}

.kv-k {
  font-size: 12px;
  color: var(--muted);
}

.kv-v {
  font-size: 12.5px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--bg);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.18s;

  &:hover {
    border-color: var(--line-strong);
  }

  strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.log-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.ea-mon-output {
  height: 360px;
  min-height: 360px;
  max-height: 360px;
  overflow: auto;
}

@media (max-width: 1100px) {
  .history-grid {
    grid-template-columns: 1fr;
  }

  .run-list {
    max-height: none;
  }
}

@media (max-width: 720px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }

  .run-meta {
    flex-direction: column;
    align-items: flex-start;
  }

  .run-workdir {
    text-align: left;
  }
}
</style>
