<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import type { ModemBaselineRunMeta, ModemBaselineStatus } from '@/api/tahp/modem-baseline'
import { getRunStatusBrief } from '@/composables/useModemBaseline'

const props = defineProps<{
  runs: ModemBaselineRunMeta[]
  selectedRunId: string
  loading?: boolean
  limit?: number
}>()

const emit = defineEmits<{
  select: [runId: string]
  refresh: []
  reopen: [runId: string]
  create: []
}>()

type StatusFilter = 'all' | ModemBaselineStatus

const statusFilter = ref<StatusFilter>('all')

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '执行中', value: 'running' },
  { label: '冲突', value: 'conflict' },
  { label: '失败', value: 'failed' },
  { label: '已完成', value: 'success' },
]

const filteredRuns = computed(() => {
  const list = statusFilter.value === 'all'
    ? props.runs
    : props.runs.filter(item => item.status === statusFilter.value)
  return list.slice(0, props.limit ?? 50)
})

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

function shortId(runId: string) {
  return runId.length > 18 ? `${runId.slice(0, 8)}…${runId.slice(-6)}` : runId
}

/** 中间省略，适合长分支名 */
function middleEllipsis(text: string, head = 10, tail = 10) {
  const value = String(text || '').trim()
  if (!value) return '—'
  if (value.length <= head + tail + 1) return value
  return `${value.slice(0, head)}…${value.slice(-tail)}`
}

function branchTitle(item: ModemBaselineRunMeta) {
  const from = item.config.NODE_BRANCH || '—'
  const to = item.config.target_BRANCH || '—'
  return `${from} → ${to}`
}

function briefOf(item: ModemBaselineRunMeta) {
  return getRunStatusBrief(
    item.status,
    item.error,
    item.phase,
    item.conflictFiles?.length,
  )
}

function onReopen(event: Event, runId: string) {
  event.stopPropagation()
  emit('reopen', runId)
}
</script>

<template>
  <div class="ea-card history-panel">
    <div class="panel-head">
      <div>
        <div class="ea-section-title">历史升级任务</div>
        <h3 class="panel-title">最近 {{ filteredRuns.length }} 条</h3>
      </div>
      <div class="panel-actions">
        <NSelect
          v-model:value="statusFilter"
          size="small"
          :options="filterOptions"
          class="status-filter"
        />
        <NButton type="primary" size="small" title="打开右侧新建升级配置" @click="emit('create')">
          新建升级
        </NButton>
        <NButton secondary size="small" :loading="loading" @click="emit('refresh')">刷新</NButton>
      </div>
    </div>

    <div v-if="filteredRuns.length" class="task-list">
      <button
        v-for="item in filteredRuns"
        :key="item.runId"
        type="button"
        class="task-item"
        :class="{ active: item.runId === selectedRunId }"
        @click="emit('select', item.runId)"
      >
        <div class="task-main">
          <strong :title="branchTitle(item)">
            {{ middleEllipsis(item.config.NODE_BRANCH || '') }}
            →
            {{ middleEllipsis(item.config.target_BRANCH || '') }}
          </strong>
          <span class="task-id">{{ shortId(item.runId) }}</span>
          <span class="task-line">{{ item.config.JIRAID || item.config.AP_lable || '未填写标识' }}</span>
          <span v-if="briefOf(item)" class="task-brief">{{ briefOf(item) }}</span>
        </div>
        <div class="task-side">
          <span :class="toneClass(item.status)">{{ statusLabel(item.status) }}</span>
          <NButton size="tiny" secondary @click="onReopen($event, item.runId)">
            基于此再开
          </NButton>
        </div>
      </button>
    </div>
    <div v-else class="empty-note">
      {{ statusFilter === 'all'
        ? '暂无历史升级任务，填写配置后启动首个升级任务。'
        : '当前筛选条件下暂无任务。' }}
    </div>
  </div>
</template>

<style scoped lang="scss">
.history-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.status-filter {
  width: 96px;
}

.panel-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--head);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: border-color 0.18s, background 0.18s;

  &:hover {
    border-color: var(--line-strong);
  }

  &.active {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
    background: var(--accent-soft);
  }
}

.task-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;

  strong {
    font-size: 13px;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.task-id {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--muted);
}

.task-line {
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-brief {
  font-size: 12px;
  color: var(--amber-fg, #b45309);
  line-height: 1.35;
}

.task-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex: 0 0 auto;
}

.empty-note {
  flex: 1;
  display: grid;
  place-items: center;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px dashed var(--line);
  color: var(--muted);
  font-size: 13px;
  background: color-mix(in srgb, var(--surface) 70%, transparent);
}
</style>
